"""
上下文记忆模块：提供多轮对话追踪、工具调用链路维护与滑动窗口裁剪策略。
"""

import json
from typing import List, Dict, Any, Optional


class ConversationMemory:
    """对话记忆管理器"""

    def __init__(
        self,
        system_prompt: str = "你是一个全能代码智能体助手。",
        max_messages: int = 30,
    ):
        self.system_prompt = system_prompt
        self.max_messages = max(4, max_messages)
        self.history: List[Dict[str, Any]] = []

    def set_system_prompt(self, prompt: str):
        """更新系统提示词"""
        self.system_prompt = prompt

    def add_user_message(self, content: str):
        """追加用户消息"""
        self.history.append({"role": "user", "content": content})

    def add_assistant_message(
        self,
        content: Optional[str] = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ):
        """追加模型助理回复或工具调用意图"""
        msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.history.append(msg)

    def add_tool_result(self, tool_call_id: str, tool_name: str, content: str):
        """追加工具执行结果反馈"""
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": str(content),
        })

    def clear(self):
        """清空对话历史，保留当前系统提示词"""
        self.history.clear()

    def get_messages(self) -> List[Dict[str, Any]]:
        """
        获取当前待发送至 LLM 的完整消息列表。
        智能维护：系统提示词置顶 + 滑动窗口裁剪（保障工具调用的完整上下文关系）。
        """
        system_msg = {"role": "system", "content": self.system_prompt}
        
        # 预留 1 个位置给系统提示词
        effective_max = self.max_messages - 1
        
        if len(self.history) <= effective_max:
            return [system_msg] + list(self.history)

        # 进行滑动窗口截断，确保截断起始点不处于孤立的 tool 结果中
        truncated = self.history[-effective_max:]
        
        # 如果截断后的第一条消息是 tool 消息，向前推移以确保其关联的 assistant tool_calls 不被截断
        while truncated and truncated[0].get("role") == "tool":
            truncated.pop(0)

        return [system_msg] + truncated

    def to_json(self) -> str:
        """导出记忆为 JSON 字符串"""
        return json.dumps({
            "system_prompt": self.system_prompt,
            "history": self.history,
        }, ensure_ascii=False, indent=2)

    def load_from_json(self, json_str: str):
        """从 JSON 字符串恢复记忆"""
        data = json.loads(json_str)
        self.system_prompt = data.get("system_prompt", self.system_prompt)
        self.history = data.get("history", [])

    def to_langchain_messages(self) -> List[Any]:
        """将内部历史消息转换为 LangChain 标准的 BaseMessage 序列"""
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
