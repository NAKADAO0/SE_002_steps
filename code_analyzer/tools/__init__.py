"""
工具层导出：提供统一的工具注册与调用机制
"""

from codemate.tools.registry import ToolRegistry, tool
from codemate.tools.file_tools import read_file, write_file, list_directory
from codemate.tools.exec_tools import execute_python_code, run_pytest
from codemate.tools.analysis_tools import lint_code


def get_analyzer_tool_registry(workspace_dir=None, allow_execution=False) -> ToolRegistry:
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
    "get_analyzer_tool_registry",
]
