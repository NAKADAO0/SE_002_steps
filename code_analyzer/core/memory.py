"""
上下文记忆与滑动窗口模块
"""

import json
from typing import List, Dict, Any, Optional


class ConversationMemory:
    """多轮对话记忆管理器"""

    def __init__(
        self,
        system_prompt: str = "你是一个全能代码智能体助手。",
        max_messages: int = 30,
    ):
        self.system_prompt = system_prompt
        self.max_messages = max(4, max_messages)
        self.history: List[Dict[str, Any]] = []

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def add_user_message(self, content: str):
        self.history.append({"role": "user", "content": content})

    def add_assistant_message(
        self,
        content: Optional[str] = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ):
        msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.history.append(msg)

    def add_tool_result(self, tool_call_id: str, tool_name: str, content: str):
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": str(content),
        })

    def clear(self):
        self.history.clear()

    def get_messages(self) -> List[Dict[str, Any]]:
        system_msg = {"role": "system", "content": self.system_prompt}
        effective_max = self.max_messages - 1

        if len(self.history) <= effective_max:
            return [system_msg] + list(self.history)

        truncated = self.history[-effective_max:]
        while truncated and truncated[0].get("role") == "tool":
            truncated.pop(0)

        return [system_msg] + truncated

    def to_langchain_messages(self) -> List[Any]:
        """将内部历史消息转换为 LangChain 标准的 BaseMessage 序列 (SystemMessage, HumanMessage, AIMessage, ToolMessage)"""
        try:
            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
        except ImportError:
            return self.get_messages()

        raw_msgs = self.get_messages()
        lc_msgs = []
        for m in raw_msgs:
            role = m.get("role")
            content = m.get("content", "") or ""
            if role == "system":
                lc_msgs.append(SystemMessage(content=content))
            elif role == "user":
                lc_msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                tc_raw = m.get("tool_calls")
                if tc_raw:
                    formatted_tcs = []
                    for tc in tc_raw:
                        if "function" in tc:
                            fn = tc["function"]
                            args = fn.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args) if args.strip() else {}
                                except Exception:
                                    args = {}
                            formatted_tcs.append({
                                "name": fn.get("name", ""),
                                "args": args,
                                "id": tc.get("id", ""),
                            })
                        elif "name" in tc and "args" in tc:
                            formatted_tcs.append(tc)
                    lc_msgs.append(AIMessage(content=content, tool_calls=formatted_tcs))
                else:
                    lc_msgs.append(AIMessage(content=content))
            elif role == "tool":
                lc_msgs.append(ToolMessage(
                    content=content,
                    tool_call_id=m.get("tool_call_id", ""),
                    name=m.get("name", ""),
                ))
        return lc_msgs
