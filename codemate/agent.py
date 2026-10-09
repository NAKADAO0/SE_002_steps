"""
核心智能体模块：基于主流 Agent 框架 LangChain 实现 ReAct 循环驱动、
多工具自主调度、异常自我纠错与状态观察者机制。
"""

import json
from typing import Optional, Callable, Dict, Any, List
from .config import Config
from .llm import LLMClient, LLMResponse
from .memory import ConversationMemory
from .prompts import get_system_prompt_for_mode
from .tools import ToolRegistry, get_default_tool_registry


class CodeMateAgent:
    """基于 LangChain 的全能代码助手智能体 (CodeMate-Agent)"""

    def __init__(
        self,
        config: Optional[Config] = None,
        llm: Optional[LLMClient] = None,
        memory: Optional[ConversationMemory] = None,
        tool_registry: Optional[ToolRegistry] = None,
        mode: str = "general",
    ):
        self.config = config or Config.from_env()
        self.llm = llm or LLMClient(self.config)
        self.current_mode = mode
        initial_prompt = get_system_prompt_for_mode(self.current_mode)
        self.memory = memory or ConversationMemory(system_prompt=initial_prompt)
        self.tool_registry = tool_registry or get_default_tool_registry(workspace_dir=self.config.workspace_dir, allow_execution=self.config.allow_execution)
        self.langchain_tools = self.tool_registry.to_langchain_tools()
        self.last_run_status = "idle"

    def switch_mode(self, mode: str):
        """切换专属策略模式（如 review / generation / testing 等）"""
        self.current_mode = mode
        new_prompt = get_system_prompt_for_mode(mode)
        self.memory.set_system_prompt(new_prompt)

    def reset(self):
        """重置对话记忆"""
        self.memory.clear()

    def run(
        self,
        user_prompt: str,
        on_step: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> str:
        """
        核心执行入口：驱动基于 LangChain 的 ReAct 循环 (Reasoning -> Action -> Observation -> Response)
        """
        def notify(event: str, data: Dict[str, Any]):
            if on_step:
                try:
                    on_step(event, data)
                except Exception:
                    pass

        # 1. 记录用户输入至上下文记忆
        self.last_run_status = "running"
        self.memory.add_user_message(user_prompt)
        notify("start", {"prompt": user_prompt, "mode": self.current_mode})

        iteration = 0
        tools_to_bind = self.langchain_tools if self.langchain_tools else self.tool_registry.get_tools_schema()

        while iteration < self.config.max_iterations:
            iteration += 1
            messages = self.memory.get_messages()
            if not self.config.allow_execution:
                messages[0] = dict(messages[0])
                messages[0]["content"] += "\n当前禁止执行代码或pytest，不得声称测试已运行或通过。"

            # 2. 调用基于 LangChain 的大模型服务
            try:
                response: LLMResponse = self.llm.chat(
                    messages=messages,
                    tools=tools_to_bind if tools_to_bind else None,
                )
            except Exception as e:
                detail = str(e).replace(self.config.api_key, "[REDACTED]") if self.config.api_key else str(e)
                err_msg = f"LangChain 模型调用异常: {detail}"
                self.last_run_status = "model_error"
                notify("error", {"error": err_msg})
                return f"【系统错误】{err_msg}。请检查 API Key、Base URL 或网络连接配置。"

            has_tools = getattr(response, "has_tool_calls", None)
            if has_tools is None:
                has_tools = bool(getattr(response, "tool_calls", []))

            # 3. 如果没有工具调用，推理完成
            if not has_tools:
                final_content = response.content or "（任务执行完成，无附加说明）"
                self.memory.add_assistant_message(final_content)
                self.last_run_status = "success"
                notify("finish", {"content": final_content, "iterations": iteration})
                return final_content

            # 4. 记录 Assistant 思考与工具意图
            self.memory.add_assistant_message(
                content=response.content,
                tool_calls=response.tool_calls,
            )

            # 5. 执行工具并反馈
            for tc in response.tool_calls:
                call_id = tc["id"]
                fn_info = tc["function"]
                fn_name = fn_info["name"]
                fn_args = fn_info["arguments"]

                notify("call_tool", {
                    "iteration": iteration,
                    "tool": fn_name,
                    "arguments": fn_args,
                    "call_id": call_id,
                })

                exec_result = self.tool_registry.execute(fn_name, fn_args)
                is_success = exec_result.get("success", False)
                raw_output = exec_result.get("output", "")
                output_str = str(raw_output)

                notify("tool_result", {
                    "tool": fn_name,
                    "success": is_success,
                    "output": output_str,
                    "call_id": call_id,
                })

                self.memory.add_tool_result(
                    tool_call_id=call_id,
                    tool_name=fn_name,
                    content=output_str,
                )

        # 超过最大迭代轮数，触发熔断保护
        timeout_msg = (
            f"【熔断提醒】已达到预设的最大思考与工具调用轮次上限 ({self.config.max_iterations} 轮)。"
            "为防止进入死循环，系统已自动停止进一步工具调用。建议细化提示词或检查相关执行环境。"
        )
        self.memory.add_assistant_message(timeout_msg)
        self.last_run_status = "max_iterations"
        notify("max_iterations", {"max_iterations": self.config.max_iterations})
        return timeout_msg
