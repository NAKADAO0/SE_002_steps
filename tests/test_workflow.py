import json

import pytest

from workflow.engine import ReviewWorkflow
from workflow.agents import build_agents
from workflow.state import WorkflowState
from workflow.storage import RunStore

BUG = "def average(values):\n    return sum(values) / len(values)\n"
FIX = "def average(values):\n    total = sum(values)\n    count = len(values)\n    if count == 0:\n        return 0.0\n    return total / count\n"
ISSUE = {"line": 2, "category": "空列表除零", "severity": "CRITICAL",
         "description": "空列表的长度为零", "suggestion": "先判断列表是否为空"}


class ScriptedLLM:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.inputs = []

    def chat(self, messages, tools=None):
        from code_analyzer.core.llm_client import LLMResponse
        self.inputs.append(messages[-1]["content"])
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return LLMResponse(content=json.dumps(value, ensure_ascii=False))


def runner(tmp_path, outputs):
    from code_analyzer.core.config import Config
    llm = ScriptedLLM(outputs)
    agents = build_agents(Config(api_key="test", workspace_dir=str(tmp_path)), llm)
    return ReviewWorkflow(agents, RunStore(tmp_path / "runs")), llm


def test_three_agents_pass_outputs_and_recheck(tmp_path):
    flow, llm = runner(tmp_path, [
        {"code": BUG, "summary": "初始代码"}, {"summary": "有缺陷", "issues": [ISSUE]},
        {"code": FIX, "summary": "修复空输入"}, {"summary": "通过", "issues": []},
    ])
    state = flow.run(WorkflowState(requirement="计算平均值，空列表返回0"))
    assert state.status == "completed"
    assert state.code == FIX and state.repairs == 1
    assert [m.receiver for m in state.messages] == ["code", "review", "fix", "review"]
    assert BUG in json.loads(llm.inputs[1])["code"]
    assert json.loads(llm.inputs[2])["issues"]
    assert json.loads(llm.inputs[3])["code"] == FIX
    checkpoint = flow.store.load(state.run_id)
    assert checkpoint.model_dump(mode="json") == state.model_dump(mode="json")
    assert (flow.store.directory(state.run_id) / "final_code.py").read_text(encoding="utf-8") == FIX


def test_clean_code_skips_fix_agent(tmp_path):
    flow, _ = runner(tmp_path, [{"code": FIX, "summary": "代码"}, {"summary": "通过", "issues": []}])
    state = flow.run(WorkflowState(requirement="平均值"))
    assert state.status == "completed" and state.repairs == 0
    assert len(state.messages) == 2


def test_failed_node_can_resume_without_repeating_completed_nodes(tmp_path):
    flow, llm = runner(tmp_path, [{"code": FIX, "summary": "代码"}, RuntimeError("offline"),
                                {"summary": "恢复后通过", "issues": []}])
    state = flow.run(WorkflowState(requirement="平均值"))
    assert state.status == "failed" and state.next_node == "review"
    recovered = flow.run(flow.store.load(state.run_id))
    assert recovered.status == "completed" and recovered.code == FIX
    assert [e.node for e in recovered.events if e.kind == "node_completed"] == ["code", "review"]


def test_repair_limit_does_not_claim_success(tmp_path):
    flow, _ = runner(tmp_path, [{"code": BUG, "summary": "代码"}, {"summary": "缺陷", "issues": [ISSUE]}])
    state = flow.run(WorkflowState(requirement="平均值", max_repairs=0))
    assert state.status == "needs_attention" and state.issues


def test_invalid_code_does_not_commit_partial_state(tmp_path):
    flow, _ = runner(tmp_path, [{"code": "def broken(:", "summary": "invalid"}])
    state = flow.run(WorkflowState(requirement="平均值"))
    assert state.status == "failed" and not state.code


def test_bad_review_line_is_failure(tmp_path):
    invalid = dict(ISSUE, line=999)
    flow, _ = runner(tmp_path, [{"code": BUG, "summary": "代码"}, {"summary": "错误行号", "issues": [invalid]}])
    state = flow.run(WorkflowState(requirement="平均值"))
    assert state.status == "failed" and state.next_node == "review"


def test_run_id_cannot_escape_storage(tmp_path):
    with pytest.raises(ValueError):
        RunStore(tmp_path).load("../outside")


def test_empty_requirement_is_rejected():
    with pytest.raises(ValueError):
        WorkflowState(requirement=" ")


def test_static_review_cannot_be_overridden_by_empty_model_result(tmp_path):
    flow, _ = runner(tmp_path, [{"code": BUG, "summary": "代码"}, {"summary": "通过", "issues": []}])
    state = flow.run(WorkflowState(requirement="平均值", max_repairs=0))
    assert state.status == "needs_attention" and state.issues


def test_step_limit_does_not_claim_review_success(tmp_path):
    flow, _ = runner(tmp_path, [{"code": FIX, "summary": "代码"}])
    state = flow.run(WorkflowState(requirement="平均值", max_steps=1))
    assert state.status == "needs_attention" and state.next_node == "review"


def test_completed_workflow_is_idempotent(tmp_path):
    flow, llm = runner(tmp_path, [{"code": FIX, "summary": "代码"}, {"summary": "通过", "issues": []}])
    state = flow.run(WorkflowState(requirement="平均值"))
    result = flow.run(state)
    assert result.model_dump() == state.model_dump() and len(llm.inputs) == 2


def test_review_agent_can_call_lint_tool(tmp_path):
    from code_analyzer.core.llm_client import LLMResponse
    from code_analyzer.core.config import Config

    class ToolLLM:
        def __init__(self):
            self.called = False

        def chat(self, messages, tools=None):
            if messages[-1]["role"] == "tool":
                assert "success" not in messages[-1]["content"] or messages[-1]["content"]
                return LLMResponse(content='{"summary":"通过", "issues":[]}')
            self.called = True
            return LLMResponse(tool_calls=[{"id": "lint1", "function": {
                "name": "lint_code", "arguments": json.dumps({"code": FIX})}}])

    llm = ToolLLM()
    node = build_agents(Config(api_key="test", workspace_dir=str(tmp_path)), llm)["review"]
    events = []
    result = node.execute({"code": FIX, "requirement": "平均值"},
                          lambda kind, data: events.append((kind, data)))
    assert llm.called and not result["issues"]
    assert any(kind == "tool_result" and data["success"] for kind, data in events)


@pytest.mark.parametrize("code", ["return 1\n", "   \n", "# comment only\n"])
def test_unusable_code_is_rejected(tmp_path, code):
    flow, _ = runner(tmp_path, [{"code": code, "summary": "code"}, {"summary": "通过", "issues": []}])
    result = flow.run(WorkflowState(requirement="生成函数"))
    assert result.status == "failed" and not result.code


def test_ui_notification_error_does_not_repeat_completed_node(tmp_path):
    flow, llm = runner(tmp_path, [{"code": FIX, "summary": "代码"}, {"summary": "通过", "issues": []}])

    def disconnected(state):
        if state.events[-1].kind == "node_completed":
            raise RuntimeError("UI disconnected")

    result = flow.run(WorkflowState(requirement="平均值"), on_event=disconnected)
    assert result.status == "completed" and len(result.revisions) == 1 and len(llm.inputs) == 2


def test_custom_generation_node_can_be_inserted_via_routes(tmp_path):
    flow, _ = runner(tmp_path, [{"code": FIX, "summary": "代码"}, {"summary": "通过", "issues": []}])

    class FormatNode:
        def execute(self, payload, on_step=None):
            return {"code": payload["code"] + "\n", "summary": "格式化"}

    flow.agents["format"] = FormatNode()
    flow.routes = {"code": "format", "format": "review", "fix": "review"}
    state = flow.run(WorkflowState(requirement="平均值"))
    assert state.status == "completed"
    assert [m.receiver for m in state.messages] == ["code", "format", "review"]


def test_failed_fix_preserves_last_valid_code_and_issues(tmp_path):
    flow, _ = runner(tmp_path, [{"code": BUG, "summary": "代码"}, {"summary": "缺陷", "issues": [ISSUE]},
                              {"code": "return 1", "summary": "无法编译"}])
    state = flow.run(WorkflowState(requirement="平均值"))
    assert state.status == "failed" and state.next_node == "fix"
    assert state.code == BUG and state.issues and state.repairs == 0


def test_storage_rejects_checkpoint_id_mismatch(tmp_path):
    store = RunStore(tmp_path)
    state = WorkflowState(requirement="平均值")
    store.save(state)
    checkpoint = store.directory(state.run_id) / "state.json"
    checkpoint.write_text(WorkflowState(requirement="另一任务").model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="ID"):
        store.load(state.run_id)
