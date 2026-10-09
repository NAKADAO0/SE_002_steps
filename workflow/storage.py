"""Local checkpoints and artifacts. Run IDs cannot contain paths."""
import json
import re
from pathlib import Path
from .state import WorkflowState


class RunStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def directory(self, run_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("非法运行 ID，应为 32 位十六进制字符串")
        path = self.root / run_id
        if path.resolve().parent != self.root:
            raise ValueError("运行目录不能越过存储根目录")
        return path

    def save(self, state: WorkflowState):
        directory = self.directory(state.run_id)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "state.tmp"
        temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(directory / "state.json")
        (directory / "events.jsonl").write_text(
            "".join(e.model_dump_json() + "\n" for e in state.events), encoding="utf-8")
        if state.code:
            (directory / "final_code.py").write_text(state.code, encoding="utf-8")
        report = (f"# Workflow 报告\n\n运行：{state.run_id}\n\n模式：{state.mode}\n\n"
                  f"状态：{state.status}\n\n需求：{state.requirement}\n\n"
                  f"成功节点数：{state.steps}；修复次数：{state.repairs}\n\n"
                  f"审查摘要：{state.summary}\n\n错误：{state.error or '无'}\n\n"
                  "完成仅表示本轮审查未发现问题，不等于实际执行测试或证明代码无缺陷。\n\n"
                  "```json\n" + json.dumps(state.issues, ensure_ascii=False, indent=2) + "\n```\n")
        (directory / "report.md").write_text(report, encoding="utf-8")

    def load(self, run_id: str) -> WorkflowState:
        state = WorkflowState.model_validate_json(
            (self.directory(run_id) / "state.json").read_text(encoding="utf-8"))
        if state.run_id != run_id:
            raise ValueError("检查点 ID 与目录不一致")
        return state
