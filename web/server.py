"""Local FastAPI workspace. Credentials stay on the server."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from difflib import unified_diff
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from code_analyzer.core.config import Config
from workflow.demo import BUG, REQUIREMENT
from workflow.service import ROOT, create_workflow
from workflow.state import WorkflowEvent, WorkflowState
from workflow.storage import RunStore
from .inputs import MAX_SOURCE_BYTES, decode_python, resolve_input, validate_filename, utf8_source
from urllib.parse import quote


class RunInput(BaseModel):
    mode: Literal["demo", "live"] = "live"
    requirement: str = Field(default="", max_length=10000)
    source_code: str = Field(default="", max_length=100000)
    source_filename: str = Field(default="", max_length=120)
    max_repairs: int = Field(default=2, ge=0, le=10)


class RunManager:
    def __init__(self, store, factory):
        self.store, self.factory = store, factory
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="workflow")
        self.lock = Lock()
        self.active: dict[str, WorkflowState] = {}

    def start(self, state):
        with self.lock:
            if state.run_id in self.active:
                raise HTTPException(409, "该任务正在执行，无需重复恢复")
            if len(self.active) >= 2:
                raise HTTPException(429, "最多同时执行两个任务，请稍后提交")
            flow = self.factory(state.mode)  # Fail configuration checks before accepting.
            state.status, state.error = "running", ""
            state.events.append(WorkflowEvent(kind="workspace_accepted", node=state.next_node))
            self.store.save(state)
            self.active[state.run_id] = state.model_copy(deep=True)
            self.executor.submit(self._execute, flow, state)

    def recover_interrupted(self):
        """Only recover jobs owned by this single-process workspace, never CLI jobs."""
        for path in self.store.root.glob("*/state.json"):
            try:
                state = self.store.load(path.parent.name)
            except (ValueError, OSError):
                continue
            if state.status == "running" and any(e.kind == "workspace_accepted" for e in state.events):
                state.status = "failed"
                state.error = "服务在任务执行期间重启；可从最后保存的节点恢复。"
                state.events.append(WorkflowEvent(kind="workspace_interrupted", node=state.next_node,
                                                 message=state.error))
                self.store.save(state)

    def _execute(self, flow, state):
        def update(snapshot):
            with self.lock:
                self.active[state.run_id] = snapshot
        try:
            flow.run(state, on_event=update)
        except Exception as exc:
            with self.lock:
                snapshot = self.active[state.run_id].model_copy(deep=True)
            snapshot.status = "failed"
            secret = Config().api_key
            snapshot.error = str(exc).replace(secret, "[REDACTED]") if secret else str(exc)
            snapshot.events.append(WorkflowEvent(kind="storage_or_worker_error", node=snapshot.next_node,
                                                 message=snapshot.error))
            self.store.save(snapshot)
        finally:
            with self.lock:
                self.active.pop(state.run_id, None)

    def get(self, run_id):
        self.store.directory(run_id)
        with self.lock:
            if run_id in self.active:
                return self.active[run_id].model_copy(deep=True)
        return self.store.load(run_id)


def create_app(output_dir=None, factory=None):
    store = RunStore(output_dir or ROOT / "runs")
    manager = RunManager(store, factory or (lambda mode: create_workflow(mode, store.root)))

    @asynccontextmanager
    async def lifespan(app):
        manager.recover_interrupted()
        yield
        manager.executor.shutdown(wait=True)

    app = FastAPI(title="Code Review Workspace", lifespan=lifespan)
    app.state.manager = manager
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "DELETE"} and origin and origin != str(request.base_url).rstrip("/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "只允许同源工作区请求"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/api/settings")
    def settings():
        config = Config()
        return {"configured": config.has_valid_api_key(), "model": config.model_name,
                "provider": "DeepSeek", "execution_enabled": False}

    @app.get("/api/runs")
    def history():
        entries = []
        if store.root.exists():
            for path in store.root.glob("*/state.json"):
                try:
                    state = manager.get(path.parent.name)
                except (ValueError, OSError):
                    continue
                entries.append({"run_id": state.run_id, "requirement": state.requirement,
                                "status": state.status, "mode": state.mode,
                                "updated_at": state.events[-1].timestamp if state.events else ""})
        return sorted(entries, key=lambda item: item["updated_at"], reverse=True)

    @app.post("/api/runs", status_code=202)
    def submit(data: RunInput):
        try:
            if len(data.source_code.encode("utf-8")) > 100000:
                raise ValueError("源码不能超过 100KB")
            requirement, intent, repairs = resolve_input(data.requirement, data.source_code,
                                                        data.source_filename, data.max_repairs)
            state = WorkflowState(requirement=REQUIREMENT if data.mode == "demo" else requirement,
                                  source_code=BUG if data.mode == "demo" else data.source_code,
                                  source_filename="" if data.mode == "demo" else data.source_filename,
                                  intent="review_fix" if data.mode == "demo" else intent,
                                  mode=data.mode, max_repairs=data.max_repairs if data.mode == "demo" else repairs)
            manager.start(state)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"run_id": state.run_id}

    @app.post("/api/files")
    async def upload(request: Request, filename: str):
        try:
            validate_filename(filename)
            content = bytearray()
            async for chunk in request.stream():
                content.extend(chunk)
                if len(content) > MAX_SOURCE_BYTES:
                    raise ValueError("文件不能超过 100KB")
            return decode_python(filename, bytes(content))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def load(run_id):
        try:
            return manager.get(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "任务不存在") from exc
        except ValueError as exc:
            raise HTTPException(400, "任务 ID 或检查点无效") from exc

    @app.get("/api/runs/{run_id}")
    def detail(run_id: str):
        state = load(run_id)
        data = state.model_dump(mode="json")
        original = state.revisions[0] if state.revisions else state.source_code
        data["diff"] = "".join(unified_diff(original.splitlines(keepends=True),
                            state.code.splitlines(keepends=True), fromfile="initial.py", tofile="current.py")) if state.code else ""
        return data

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    def resume(run_id: str):
        state = load(run_id)
        if state.status != "failed":
            raise HTTPException(409, "只能恢复失败任务；运行中或已结束的任务无需恢复")
        try:
            manager.start(state)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"run_id": run_id}

    @app.get("/api/runs/{run_id}/export")
    def export_code(run_id: str):
        state = load(run_id)
        if state.status != "completed" or not state.code.strip():
            raise HTTPException(409, "仅复审通过的任务可导出最终代码，请先完成流程或解决剩余问题")
        try:
            filename = validate_filename(state.source_filename or "final_code.py")
        except ValueError as exc:
            raise HTTPException(400, "检查点文件名无效") from exc
        return Response(utf8_source(state.code), media_type="text/x-python; charset=utf-8", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
            "X-Content-Type-Options": "nosniff"})

    return app


app = create_app()
