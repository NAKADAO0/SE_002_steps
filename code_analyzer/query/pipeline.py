"""
核心两阶段分析流水线 (Two-Phase Code Pipeline)
企业级智能代码多阶段协同编排设计。

架构流程：
Phase 1: 零 LLM 共享特征抽取与 AST 规则初筛 (RuleEngine)
Phase 2: 垂直领域专家 Agent 并行/定向推理 (Agents: Reviewer / Tester / Refactor / Explainer)
Phase 3: 校验去重与最终统一呈现 (Verifier & Dedup)
"""

from pathlib import Path
import json
import re
from typing import Dict, Any, Optional, Callable
from ..core.config import Config
from ..core.llm_client import LLMClient
from ..schemas.code_types import CodeSmellItem
from codemate.tools.policy import resolve_workspace_path
from .rule_engine import RuleEngine
from .verifier import Verifier
from ..agents.reviewer_agent import CodeReviewerAgent
from ..agents.explainer_agent import CodeExplainerAgent
from ..agents.tester_agent import TestGeneratorAgent
from ..agents.refactor_agent import CodeRefactorAgent


class CodePipeline:
    """两阶段多 Agent 代码分析流水线编排器"""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.from_env()
        self.llm = LLMClient(self.config)
        self.rule_engine = RuleEngine()
        self.verifier = Verifier()

        # 挂载各垂直领域专家智能体
        self.reviewer_agent = CodeReviewerAgent(config=self.config, llm=self.llm)
        self.explainer_agent = CodeExplainerAgent(config=self.config, llm=self.llm)
        self.tester_agent = TestGeneratorAgent(config=self.config, llm=self.llm)
        self.refactor_agent = CodeRefactorAgent(config=self.config, llm=self.llm)

    def run_pipeline(
        self,
        target: str,
        task_type: str = "review",
        on_step: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        source_kind: str = "auto",
    ) -> Dict[str, Any]:
        """
        运行完整流水线
        :param target: 代码字符串或代码文件路径
        :param task_type: "review" | "explain" | "test" | "refactor"
        :param on_step: 观察者回调
        """
        def notify(event: str, data: Dict[str, Any]):
            if on_step:
                try:
                    on_step(event, data)
                except Exception:
                    pass

        def fail(message, error_type="input_error", **extra):
            notify("pipeline_error", {"error": message, "error_type": error_type})
            return {"success": False, "error": message, "error_type": error_type, **extra}

        if task_type not in {"review", "test", "refactor", "explain"}:
            return fail("不支持的任务类型")
        if source_kind not in {"auto", "code", "file"}:
            return fail("不支持的输入类型")
        if not isinstance(target, str) or not target.strip():
            return fail("代码或文件路径不能为空")

        # 显式 code/file 消除歧义；兼容旧调用的 auto 仅识别单行 .py 路径。
        file_path_str = None
        code_content = target
        is_file = source_kind == "file" or (
            source_kind == "auto" and "\n" not in target and "\r" not in target
            and target.strip().lower().endswith(".py")
        )
        if is_file:
            try:
                p = resolve_workspace_path(target.strip(), self.config.workspace_dir)
                if not p.is_file():
                    return fail("目标文件不存在或不是普通文件")
                file_path_str = str(p)
                with open(p, "r", encoding="utf-8") as f:
                    code_content = f.read()
            except Exception as e:
                return fail(f"无法读取目标文件: {e}")
        if not code_content.strip():
            return fail("代码内容为空")

        notify("pipeline_start", {
            "task_type": task_type,
            "target": file_path_str or "内存代码片段",
            "lines": len(code_content.splitlines()),
        })

        # ================= Phase 1: 静态规则引擎初筛 (零 LLM) =================
        phase1_result = self.rule_engine.analyze_source(code_content)
        notify("phase1_complete", {
            "syntax_valid": phase1_result["syntax_valid"],
            "functions": phase1_result["functions"],
            "classes": phase1_result["classes"],
            "initial_issues_count": len(phase1_result["issues"]),
        })

        if not phase1_result["syntax_valid"]:
            return fail(phase1_result["error"], "syntax_error", issues=[
                i.model_dump(mode="json") for i in phase1_result["issues"]
            ])

        # ================= Phase 2: 专业领域 Agent 深度推理 =================
        context_hint = ""
        if file_path_str:
            context_hint = f"目标文件路径: {file_path_str}\n"

        if phase1_result["issues"]:
            smell_texts = [f"行 {i.line}: {i.description}" for i in phase1_result["issues"]]
            context_hint += f"【Phase 1 静态初筛发现的线索】:\n" + "\n".join(smell_texts) + "\n"

        agent_output = ""
        selected_agent = None

        if task_type == "review":
            selected_agent = self.reviewer_agent
            prompt = (
                f"{context_hint}请深度审查以下代码，发现所有潜在 Bug、异常崩溃点与代码风险隐患，"
                f"并给出修复后的对比代码：\n\n```python\n{code_content}\n```"
            )
            prompt += (
                '\n最终回答必须为 JSON 对象（不要 Markdown）：'
                '{"summary":"审查总结", "issues":[{"line":1,"category":"分类",'
                '"severity":"CRITICAL|HIGH|MEDIUM|LOW","description":"依据",'
                '"suggestion":"改进建议"}]}。行号使用本次给定源码行号。'
                '只列出有代码依据的问题，不把规则线索当作已证实缺陷。'
            )
        elif task_type == "test":
            selected_agent = self.tester_agent
            prompt = (
                f"{context_hint}请为以下代码编写高覆盖率的 pytest 单元测试，"
                f"并主动调用 execute_python_code 工具在沙箱中运行验证，确保测试全部通过：\n\n```python\n{code_content}\n```"
            )
        elif task_type == "refactor":
            selected_agent = self.refactor_agent
            prompt = (
                f"{context_hint}请对以下代码进行架构重构，消除风险隐患（除零隐患、句柄泄露、硬编码if-elif等），应用合适设计模式（如策略模式、上下文管理器）。\n"
                f"【极其重要的要求】：请在重构设计说明后，必须在回答的最末尾使用独立的 ```python 代码块输出【整份完整的重构后 Python 源码】（第一行写 # FULL_REFACTORED_CODE 注释）。必须包含原业务中的全部类与所有函数，保证可以直接替换原代码完整运行，严禁省略或局部替换！\n\n```python\n{code_content}\n```"
            )
        elif task_type == "explain":
            selected_agent = self.explainer_agent
            prompt = (
                f"{context_hint}请详细解释以下代码的执行流程、核心算法原理解析与时空复杂度：\n\n```python\n{code_content}\n```"
            )
        else:
            selected_agent = self.reviewer_agent
            prompt = f"请分析以下代码：\n\n```python\n{code_content}\n```"

        notify("phase2_dispatch", {"agent": selected_agent.name})
        agent_output = selected_agent.run(prompt, on_step=on_step)

        if selected_agent.last_run_status != "success":
            return fail(agent_output, selected_agent.last_run_status,
                        issues=[i.model_dump(mode="json") for i in phase1_result["issues"]])

        # ================= Phase 3: 聚合与校验 (Verifier) =================
        warnings = []
        llm_issues = []
        display_report = agent_output
        if task_type == "review":
            text = agent_output.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
            try:
                data = json.loads(text)
                if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
                    raise ValueError("缺少 issues 数组")
                display_report = str(data.get("summary", "审查完成"))
                for item in data["issues"]:
                    try:
                        issue = CodeSmellItem.model_validate(item)
                        if issue.line is None or not 1 <= issue.line <= len(code_content.splitlines()):
                            raise ValueError("行号超出源码范围")
                        issue.snippet = code_content.splitlines()[issue.line - 1].strip()
                        issue.fix_code = None
                        llm_issues.append(issue)
                    except (ValueError, TypeError) as e:
                        warnings.append(f"忽略无效模型问题：{e}")
            except (ValueError, TypeError) as e:
                warnings.append(f"模型未返回有效结构化问题，评分仅基于静态线索：{e}")
        final_issues = self.verifier.dedup_and_sort(phase1_result["issues"] + llm_issues)
        notify("pipeline_finish", {"task_type": task_type, "status": "success"})

        return {
            "success": True,
            "task_type": task_type,
            "target": file_path_str or "inline_code",
            "issues": [i.model_dump(mode="json") for i in final_issues],
            "warnings": warnings,
            "phase1": {
                "syntax_valid": phase1_result["syntax_valid"],
                "functions": phase1_result["functions"],
                "classes": phase1_result["classes"],
                "rule_issues": [i.model_dump(mode="json") for i in phase1_result["issues"]],
            },
            "phase2": {
                "agent_name": selected_agent.name,
                "report": display_report,
                "raw_report": agent_output,
                "llm_issues": [i.model_dump(mode="json") for i in llm_issues],
            },
        }
