"""Workspace boundaries for file tools; subprocess execution still requires trusted code."""
import os
from contextvars import ContextVar
from pathlib import Path


tool_workspace = ContextVar("tool_workspace", default=None)
tool_execution = ContextVar("tool_execution", default=None)


def workspace_root():
    return Path(tool_workspace.get() or os.getenv("WORKSPACE_DIR") or
                Path(__file__).resolve().parents[2]).resolve()


def resolve_workspace_path(path, workspace_dir=None):
    root = Path(workspace_dir).resolve() if workspace_dir else workspace_root()
    candidate = Path(path)
    candidate = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not candidate.is_relative_to(root):
        raise PermissionError("路径必须位于配置的工作目录内")
    relative = candidate.relative_to(root)
    if any(part.casefold() == ".git" or
           (part.casefold().startswith(".env") and part.casefold() != ".env.example")
           for part in relative.parts):
        raise PermissionError("禁止工具访问凭证或 Git 元数据")
    return candidate


def execution_enabled():
    value = tool_execution.get()
    return value if value is not None else os.getenv("AGENT_ALLOW_EXECUTION", "0") == "1"
