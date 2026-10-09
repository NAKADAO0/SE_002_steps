from fastapi.testclient import TestClient
from workflow.demo import BUG, FIX
from workflow.state import WorkflowState
from workflow.storage import RunStore
from web.server import create_app
import time


def wait_result(api, run_id):
    for _ in range(100):
        state = api.get(f"/api/runs/{run_id}").json()
        if state["status"] not in ("running", "pending"):
            return state
        time.sleep(.03)
    raise AssertionError("Workflow did not finish")


def factory(tmp_path):
    class Flow:
        def run(self, state, on_event=None):
            state.code = FIX
            state.status = "completed"
            RunStore(tmp_path).save(state)
            if on_event:
                on_event(state)
            return state
    return lambda mode: Flow()


def test_upload_python_and_submit_without_extra_requirement(tmp_path):
    with TestClient(create_app(tmp_path, factory(tmp_path))) as api:
        uploaded = api.post("/api/files", params={"filename": "平均值.py"}, content=BUG.encode())
        assert uploaded.status_code == 200
        assert uploaded.json() == {"filename": "平均值.py", "source_code": BUG}
        response = api.post("/api/runs", json={"source_filename": "平均值.py", "source_code": BUG})
        assert response.status_code == 202
        state = wait_result(api, response.json()["run_id"])
        assert state["intent"] == "review_fix"
        assert state["source_filename"] == "平均值.py" and "审查" in state["requirement"]


def test_natural_language_only_review_disables_repairs(tmp_path):
    with TestClient(create_app(tmp_path, factory(tmp_path))) as api:
        response = api.post("/api/runs", json={"requirement": "请只审查这个文件，不要修改代码",
                                              "source_code": BUG, "source_filename": "average.py"})
        assert response.status_code == 202
        state = wait_result(api, response.json()["run_id"])
        assert state["intent"] == "review_only" and state["max_repairs"] == 0


def test_generation_intent_uses_natural_language(tmp_path):
    with TestClient(create_app(tmp_path, factory(tmp_path))) as api:
        response = api.post("/api/runs", json={"requirement": "请实现一个计算平均值的函数"})
        state = wait_result(api, response.json()["run_id"])
        assert state["intent"] == "generate"


def test_scoped_constraints_do_not_disable_requested_repairs():
    from web.inputs import resolve_input
    for text in ("不仅审查，还要修复", "不要修改正常输入行为，请修复空列表缺陷", "不要修复风格问题，只修复潜在bug"):
        _, intent, repairs = resolve_input(text, BUG, "average.py", 2)
        assert intent == "review_fix" and repairs == 2


def test_upload_rejects_invalid_files_and_accepts_python_encoding(tmp_path):
    with TestClient(create_app(tmp_path, factory(tmp_path))) as api:
        for name, content in [("../x.py", b"x=1"), ("x.txt", b"x=1"), ("x.py", b" "),
                              ("x.py", b"x" * 100001), ("x.py", b"\xff")]:
            assert api.post("/api/files", params={"filename": name}, content=content).status_code == 422
        source = '# coding: gbk\nmessage = "你好"\n'
        assert api.post("/api/files", params={"filename": "x.py"}, content=source.encode("gbk")).json()["source_code"] == source
        assert api.post("/api/files", params={"filename": "x.py"}, content=b"\xef\xbb\xbfx=1\n").json()["source_code"] == "x=1\n"


def test_export_completed_code_as_utf8_attachment(tmp_path):
    state = WorkflowState(requirement="平均值", status="completed", code=FIX,
                          source_filename="平均值.py")
    RunStore(tmp_path).save(state)
    with TestClient(create_app(tmp_path, factory(tmp_path))) as api:
        response = api.get(f"/api/runs/{state.run_id}/export")
        assert response.status_code == 200 and response.text == FIX
        assert "attachment" in response.headers["content-disposition"]
        assert "filename*=UTF-8''" in response.headers["content-disposition"]


def test_export_rejects_unfinished_or_unreviewed_code(tmp_path):
    with TestClient(create_app(tmp_path, factory(tmp_path))) as api:
        for status in ("pending", "failed", "needs_attention"):
            state = WorkflowState(requirement="平均值", status=status, code=BUG)
            RunStore(tmp_path).save(state)
            assert api.get(f"/api/runs/{state.run_id}/export").status_code == 409


def test_utf8_export_updates_legacy_python_encoding_declaration(tmp_path):
    import ast
    code = '# coding: gbk\nmessage = "你好"\n'
    state = WorkflowState(requirement="原样检查", status="completed", code=code)
    RunStore(tmp_path).save(state)
    with TestClient(create_app(tmp_path, factory(tmp_path))) as api:
        exported = api.get(f"/api/runs/{state.run_id}/export")
        tree = ast.parse(exported.content)
        assert tree.body[0].value.value == "你好"
        assert "coding: utf-8" in exported.text


def test_only_review_preserves_uploaded_source_without_generation(tmp_path):
    from code_analyzer.core.config import Config
    from code_analyzer.core.llm_client import LLMResponse
    from workflow.agents import build_agents
    from workflow.engine import ReviewWorkflow

    class Reviewer:
        def chat(self, messages, tools=None):
            assert "你是审查 Agent" in messages[0]["content"]
            return LLMResponse(content='{"summary":"发现除零风险", "issues":[]}')

    flow = ReviewWorkflow(build_agents(Config(api_key="test", workspace_dir=str(tmp_path)), Reviewer()), RunStore(tmp_path))
    result = flow.run(WorkflowState(requirement="只审查，不要修改", source_code=BUG,
                                   intent="review_only", max_repairs=0))
    assert result.code == BUG and result.revisions == [BUG]
    assert result.status == "needs_attention" and result.repairs == 0
