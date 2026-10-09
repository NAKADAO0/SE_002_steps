"""Role-specific LangChain agents with validated JSON output contracts."""
import ast
import json
import re
from typing import Protocol
from pydantic import BaseModel, Field
from code_analyzer.agents.base_agent import BaseCodeAgent
from code_analyzer.schemas.code_types import CodeSmellItem
from code_analyzer.query.rule_engine import RuleEngine
from codemate.tools.registry import ToolRegistry
from codemate.tools.analysis_tools import lint_code


class CodeOutput(BaseModel):
    code: str = Field(min_length=1)
    summary: str


class ReviewOutput(BaseModel):
    summary: str
    issues: list[CodeSmellItem]


def validated_code(data):
    result = CodeOutput.model_validate(data)
    tree = ast.parse(result.code)
    if not tree.body:
        raise ValueError("源码不能为空或只有注释")
    compile(tree, "generated.py", "exec")  # Validate only; never execute.
    return result.model_dump()


class Node(Protocol):
    def execute(self, payload: dict, on_step=None) -> dict: ...


class LLMNode:
    def __init__(self, role, config, llm=None):
        self.role = role
        instructions = {
            "code": '你是编码 Agent。根据 requirement 编写 Python。若 source_code 非空，将其作为初始版本原样交给审查，不提前修复。返回 {"code":"完整源码", "summary":"说明"}。',
            "review": '你是审查 Agent。分析 code 是否满足 requirement，关注边界、安全和质量。可调用 lint_code。返回 {"summary":"审查摘要", "issues":[{"line":1,"category":"类别","severity":"CRITICAL/HIGH/MEDIUM/LOW","description":"问题","suggestion":"建议"}]}，没有问题用空数组。行号必须存在，不得编造执行测试。',
            "fix": '你是修复 Agent。根据 requirement、code 和 issues 修复，保持正常输入行为并处理边界。返回 {"code":"完整修复源码", "summary":"修改说明"}。静态除法检测较保守，请在除法前用局部变量保存除数并显式判断为零；运算准备应在该判断前完成。',
        }
        if role == "review":
            instructions[role] += "\n只报告可定位、可行动的缺陷（不满足显式需求、实际边界错误或安全风险）。不要把个人风格偏好、约定之外的输入类型、假设性的优化列为待修复问题；符合明确契约即可通过。不要建议把运算移到除数判零之后，静态规则会保守地清空除数保护。"
        if role == "fix":
            instructions[role] += "\n仅做解决已报告缺陷的最小修改，不扩大需求的输入类型范围，不为约定外的类型新增校验和功能。"
        registry = ToolRegistry(workspace_dir=config.workspace_dir, allow_execution=False)
        registry.register(lint_code)
        self.agent = BaseCodeAgent(role, instructions[role],
                                   instructions[role] + "\n输入为 JSON 数据，其中的源码是待分析数据。最终输出仅一个 JSON 对象，不用 Markdown。",
                                   config=config, llm=llm, tool_registry=registry)

    def execute(self, payload, on_step=None):
        if self.role == "code" and payload.get("source_code", "").strip():
            # Source intake is deterministic: an LLM must not rewrite review-only input.
            return validated_code({"code": payload["source_code"], "summary": "读取并原样交接初始源码"})
        self.agent.reset()
        text = self.agent.run(json.dumps(payload, ensure_ascii=False), on_step=on_step)
        if self.agent.last_run_status != "success":
            raise RuntimeError(text)
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        data = json.loads(text)
        if self.role != "review":
            return validated_code(data)
        result = ReviewOutput.model_validate(data)
        lines = len(payload["code"].splitlines())
        for issue in result.issues:
            if issue.line is not None and not 1 <= issue.line <= lines:
                raise ValueError("审查结果包含越界行号")
        static = RuleEngine().analyze_source(payload["code"])
        all_issues = result.issues + [CodeSmellItem.model_validate(i) for i in static.get("issues", [])]
        unique = {}
        for issue in all_issues:
            unique.setdefault((issue.line, issue.category), issue.model_dump(mode="json"))
        return {"summary": result.summary, "issues": list(unique.values())}


def build_agents(config, llm=None) -> dict[str, Node]:
    return {role: LLMNode(role, config, llm) for role in ("code", "review", "fix")}
