"""
工具模块导出与默认注册中心工厂
"""

from .registry import ToolRegistry, tool
from .file_tools import read_file, write_file, list_directory
from .exec_tools import execute_python_code, run_pytest
from .analysis_tools import lint_code


def get_default_tool_registry(workspace_dir=None, allow_execution=False) -> ToolRegistry:
    """初始化并注册全部核心代码工具的注册中心实例"""
    registry = ToolRegistry(workspace_dir=workspace_dir, allow_execution=allow_execution)
    registry.register(read_file)
    registry.register(write_file)
    registry.register(list_directory)
    registry.register(execute_python_code)
    registry.register(run_pytest)
    registry.register(lint_code)
    return registry


__all__ = [
    "ToolRegistry",
    "tool",
    "read_file",
    "write_file",
    "list_directory",
    "execute_python_code",
    "run_pytest",
    "lint_code",
    "get_default_tool_registry",
]
