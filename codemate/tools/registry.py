"""
工具注册中心：负责工具函数的元数据提取（JSON Schema自动生成）、集中管理与安全分发执行。
"""

import inspect
import json
from functools import wraps
from typing import Any, Callable, Dict, List, Optional
from .policy import tool_workspace, tool_execution


def _py_type_to_json_schema(py_type: Any) -> str:
    """Python 类型映射到 JSON Schema 类型"""
    if py_type in (int,):
        return "integer"
    elif py_type in (float,):
        return "number"
    elif py_type in (bool,):
        return "boolean"
    elif py_type in (list, List):
        return "array"
    elif py_type in (dict, Dict):
        return "object"
    return "string"


def tool(name: Optional[str] = None, description: Optional[str] = None):
    """
    工具装饰器：标注一个普通 Python 函数为 Agent 可调用的工具。
    自动解析参数类型与默认值，生成 OpenAI 兼容的 Function Calling Schema。
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_desc = description or inspect.getdoc(func) or f"Execute {tool_name}"

        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                param_type = _py_type_to_json_schema(param.annotation)

            properties[param_name] = {
                "type": param_type,
                "description": f"参数 {param_name}",
            }

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        func_schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_desc.strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

        # 挂载元信息到函数对象
        func.__tool_name__ = tool_name
        func.__tool_schema__ = func_schema
        return func

    return decorator


class ToolRegistry:
    """工具注册中心"""

    def __init__(self, workspace_dir=None, allow_execution=False):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self.workspace_dir = workspace_dir
        self.allow_execution = allow_execution

    def register(self, func: Callable):
        """注册一个带有 @tool 装饰器的函数"""
        tool_name = getattr(func, "__tool_name__", func.__name__)
        tool_schema = getattr(func, "__tool_schema__", None)

        if not tool_schema:
            # 如果没有预先装饰，进行动态包装
            func = tool()(func)
            tool_schema = func.__tool_schema__

        @wraps(func)
        def scoped_tool(*args, **kwargs):
            workspace_token = tool_workspace.set(self.workspace_dir)
            execution_token = tool_execution.set(self.allow_execution)
            try:
                return func(*args, **kwargs)
            except (PermissionError, OSError, ValueError) as e:
                return {"success": False, "output": str(e)}
            finally:
                tool_workspace.reset(workspace_token)
                tool_execution.reset(execution_token)

        self._tools[tool_name] = scoped_tool
        self._schemas[tool_name] = tool_schema

    def get_tool(self, name: str) -> Optional[Callable]:
        """根据名称获取工具函数"""
        return self._tools.get(name)

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """获取所有已注册工具的 JSON Schema 定义"""
        return list(self._schemas.values())

    def execute(self, name: str, arguments: Dict[str, Any] | str) -> Dict[str, Any]:
        """
        统一执行工具调用，具备参数反序列化与严格异常隔离
        """
        if name not in self._tools:
            return {
                "success": False,
                "output": f"错误：未找到名为 '{name}' 的工具。",
            }

        # 解析参数（应对 LLM 传入的 JSON 字符串）
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except Exception as e:
                return {
                    "success": False,
                    "output": f"工具参数 JSON 解析失败：{str(e)}，入参内容为：{arguments}",
                }

        func = self._tools[name]
        try:
            res = func(**arguments)
            if isinstance(res, dict) and "success" in res and "output" in res:
                return res
            return {"success": True, "output": res}
        except TypeError as te:
            return {
                "success": False,
                "output": f"工具调用参数类型或数量不匹配：{str(te)}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"工具执行异常：{str(e)}",
            }

    def to_langchain_tools(self) -> List[Any]:
        """将注册的所有工具转换为 LangChain 标准的 StructuredTool 实例"""
        try:
            from langchain_core.tools import StructuredTool
            lc_tools = []
            for name, func in self._tools.items():
                schema = self._schemas.get(name, {}).get("function", {})
                desc = schema.get("description", inspect.getdoc(func) or f"Execute {name}")

                lc_tool = StructuredTool.from_function(
                    func=func,
                    name=name,
                    description=desc,
                )
                lc_tools.append(lc_tool)
            return lc_tools
        except Exception:
            return []
