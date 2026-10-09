"""
智能体基类：基于主流 Agent 框架 LangChain (langchain-core, langchain-openai) 驱动。
提供统一的 ReAct (Reasoning -> Acting -> Observation -> Reflection) 循环、
LangChain 消息上下文流转、工具链绑定与事件监听机制。
"""

import json
from typing import Optional, Callable, Dict, Any, List
from langchain_core.messages import BaseMessage
from ..core.config import Config
from ..core.llm_client import LLMClient, LLMResponse
from ..core.memory import ConversationMemory
from ..tools import ToolRegistry, get_analyzer_tool_registry


class BaseCodeAgent:
    """基于 LangChain 驱动的智能体基类"""

    def __init__(
        self,
        name: str,
        role_description: str,
        system_prompt: str,
        config: Optional[Config] = None,
        llm: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.name = name
        self.role_description = role_description
        self.config = config or Config.from_env()
        self.llm = llm or LLMClient(self.config)
        self.memory = ConversationMemory(system_prompt=system_prompt)
        self.tool_registry = tool_registry or get_analyzer_tool_registry(workspace_dir=self.config.workspace_dir, allow_execution=self.config.allow_execution)

        # 获取注册工具的 LangChain 标准 StructuredTool 集合
        self.langchain_tools = self.tool_registry.to_langchain_tools()
        self.last_run_status = "idle"

    def reset(self):
        """重置智能体记忆"""
        self.memory.clear()

    def run(
        self,
        user_prompt: str,
        on_step: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> str:
        """
        核心执行入口：基于 LangChain 消息协议与工具调用的 ReAct 循环
        (Reasoning -> Acting -> Observation -> Self-Correction)
        """
        def notify(event: str, data: Dict[str, Any]):
            if on_step:
                try:
                    payload = dict(data)
                    payload["agent_name"] = self.name
                    on_step(event, payload)
                except Exception:
                    pass

        self.last_run_status = "running"
        self.memory.add_user_message(user_prompt)
        notify("start", {"prompt": user_prompt, "role": self.role_description})

        iteration = 0
        tools_to_bind = self.langchain_tools if self.langchain_tools else self.tool_registry.get_tools_schema()

        while iteration < self.config.max_iterations:
            iteration += 1
            messages = self.memory.get_messages()
            if not self.config.allow_execution:
                messages[0] = dict(messages[0])
                messages[0]["content"] += "\n当前禁止执行代码或pytest，不得声称测试已运行或通过。"

            try:
                # 统一通过基于 LangChain (ChatOpenAI + bind_tools) 驱动的 llm 客户端交互
                response: LLMResponse = self.llm.chat(
                    messages=messages,
                    tools=tools_to_bind if tools_to_bind else None,
                )
            except Exception as e:
                detail = str(e).replace(self.config.api_key, "[REDACTED]") if self.config.api_key else str(e)
                err_msg = f"[{self.name}] LangChain 模型调用异常: {detail}"
                self.last_run_status = "model_error"
                notify("error", {"error": err_msg})
                return f"【系统错误】{err_msg}"

            has_tools = getattr(response, "has_tool_calls", None)
            if has_tools is None:
                has_tools = bool(getattr(response, "tool_calls", []))

            # 如果没有工具调用，说明智能体已完成推理，输出最终回答
            if not has_tools:
                final_content = response.content or "（分析完毕，无补充说明）"
                self.memory.add_assistant_message(final_content)
                self.last_run_status = "success"
                notify("finish", {"content": final_content, "iterations": iteration})
                return final_content

            # 处理工具调用
            self.memory.add_assistant_message(
                content=response.content,
                tool_calls=response.tool_calls,
            )

            # 依次执行工具并收集结果
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

                # 通过工具中心安全沙箱执行
                exec_result = self.tool_registry.execute(fn_name, fn_args)
                is_success = exec_result.get("success", False)
                output_str = str(exec_result.get("output", ""))

                notify("tool_result", {
                    "tool": fn_name,
                    "success": is_success,
                    "output": output_str,
                    "call_id": call_id,
                })

                # 将工具执行结果以 Tool 角色写入记忆
                self.memory.add_tool_result(
                    tool_call_id=call_id,
                    tool_name=fn_name,
                    content=output_str,
                )

        # 达到最大思考轮次安全熔断
        timeout_msg = f"[{self.name}] 达到最大思考轮次 ({self.config.max_iterations})，自动安全熔断。"
        self.memory.add_assistant_message(timeout_msg)
        self.last_run_status = "max_iterations"
        notify("max_iterations", {"max_iterations": self.config.max_iterations})
        return timeout_msg
