"""
文件系统工具：提供安全的文件读取、写入与目录检索能力。
"""

import os
from pathlib import Path
from typing import Dict, Any, List
from .registry import tool
from .policy import resolve_workspace_path


@tool(name="read_file", description="读取指定路径的代码或文本文件内容，支持按行切片读取")
def read_file(path: str, start_line: int = 1, end_line: int = -1) -> Dict[str, Any]:
    """读取文件内容"""
    try:
        file_path = resolve_workspace_path(path)
    except (OSError, ValueError) as e:
        return {"success": False, "output": str(e)}
    if not file_path.exists():
        return {"success": False, "output": f"文件不存在: {path}"}
    if not file_path.is_file():
        return {"success": False, "output": f"目标路径不是普通文件: {path}"}

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        if start_line < 1:
            start_line = 1
        
        if end_line == -1 or end_line > total_lines:
            actual_end = total_lines
        else:
            actual_end = end_line

        selected = lines[start_line - 1 : actual_end]
        numbered_lines = [f"{i}: {line}" for i, line in enumerate(selected, start=start_line)]
        return {
            "success": True,
            "output": "".join(numbered_lines),
            "total_lines": total_lines,
        }
    except Exception as e:
        return {"success": False, "output": f"读取文件失败: {str(e)}"}


@tool(name="write_file", description="将代码或文本写入指定文件，若文件不存在则自动创建，若存在则覆盖")
def write_file(path: str, content: str) -> Dict[str, Any]:
    """写入文件内容"""
    try:
        file_path = resolve_workspace_path(path)
    except (OSError, ValueError) as e:
        return {"success": False, "output": str(e)}
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "output": f"文件成功写入: {path} (共写入 {len(content)} 字符)",
        }
    except Exception as e:
        return {"success": False, "output": f"写入文件失败: {str(e)}"}


@tool(name="list_directory", description="列出指定目录下的文件和子目录树结构")
def list_directory(path: str = ".") -> Dict[str, Any]:
    """列出目录树"""
    try:
        dir_path = resolve_workspace_path(path)
    except (OSError, ValueError) as e:
        return {"success": False, "output": str(e)}
    if not dir_path.exists():
        return {"success": False, "output": f"目录不存在: {path}"}
    if not dir_path.is_dir():
        return {"success": False, "output": f"目标路径不是目录: {path}"}

    ignore_patterns = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules", ".idea", ".vscode"}
    items: List[str] = []

    try:
        for root, dirs, files in os.walk(dir_path):
            # 过滤不需要的目录
            dirs[:] = [d for d in dirs if d not in ignore_patterns]
            rel_root = os.path.relpath(root, dir_path)
            prefix = "" if rel_root == "." else rel_root + os.sep

            for f in files:
                if f.casefold().startswith(".env") and f.casefold() != ".env.example":
                    continue
                try:
                    resolve_workspace_path(Path(root) / f)
                except PermissionError:
                    continue
                if f.endswith((".pyc", ".pyo")):
                    continue
                items.append(prefix + f)

        return {
            "success": True,
            "output": items,
            "total_files": len(items),
        }
    except Exception as e:
        return {"success": False, "output": f"列出目录失败: {str(e)}"}
