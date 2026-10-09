"""
代码静态分析工具：利用 Python AST 语法树对代码进行语法合规性检查、结构剖析与基础代码异味检测。
"""

import ast
from pathlib import Path
from typing import Dict, Any, List
from .registry import tool
from .policy import resolve_workspace_path


@tool(name="lint_code", description="静态分析 Python 代码的语法合法性，并解析函数、类定义及检测常见代码风险缺陷")
def lint_code(code: str = "", file_path: str = "") -> Dict[str, Any]:
    """静态语法分析"""
    target_code = code
    if file_path:
        try:
            p = resolve_workspace_path(file_path)
        except (OSError, ValueError) as e:
            return {"success": False, "output": str(e)}
        if not p.exists():
            return {"success": False, "output": f"文件不存在: {file_path}"}
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                target_code = f.read()
        except Exception as e:
            return {"success": False, "output": f"读取分析文件失败: {str(e)}"}

    if not target_code.strip():
        return {"success": False, "output": "分析内容为空"}

    # 统一静态规则，避免工具报告与流水线产生不同结论。
    from code_analyzer.query.rule_engine import RuleEngine
    result = RuleEngine().analyze_source(target_code)
    if not result["syntax_valid"]:
        return {"success": False, "output": "SyntaxError: " + result["error"], "syntax_valid": False}
    smells = [f"行 {i.line}: {i.category} — {i.description}" for i in result["issues"]]
    output = "语法检查通过。\n函数: " + ", ".join(result["functions"])
    output += "\n类: " + ", ".join(result["classes"])
    output += "\n" + ("\n".join(smells) if smells else "静态规则未发现风险线索；这不保证代码无缺陷。")
    return {"success": True, "output": output, "syntax_valid": True, "smells": smells}
