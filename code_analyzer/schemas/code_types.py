"""
领域强类型数据模型：定义代码审查、测试执行、复杂度与重构的数据契约。
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RiskSeverity(str, Enum):
    CRITICAL = "CRITICAL"  # 致命Bug (如 ZeroDivisionError、IndexError、未捕获异常)
    HIGH = "HIGH"          # 高危安全/资源风险 (如文件泄漏、注入、死循环)
    MEDIUM = "MEDIUM"      # 代码中危风险 (如超长函数、过多参数、深层嵌套)
    LOW = "LOW"            # 编码规范与PEP8建议


class CodeSmellItem(BaseModel):
    """代码风险 / 潜在缺陷实体"""
    line: Optional[int] = Field(None, description="问题发生行号")
    category: str = Field(..., description="缺陷分类，如 除零风险/资源泄露/语法错误/参数过多")
    severity: RiskSeverity = Field(RiskSeverity.MEDIUM, description="风险等级")
    description: str = Field(..., description="问题详细分析")
    suggestion: str = Field(..., description="修改或重构建议")
    snippet: Optional[str] = Field(None, description="问题代码切片")
    fix_code: Optional[str] = Field(None, description="推荐修复代码片段")


CodeRiskItem = CodeSmellItem  # 别名兼容


class ReviewReport(BaseModel):
    """代码审查综合报告"""
    file_path: Optional[str] = Field(None, description="分析的目标文件路径")
    syntax_valid: bool = Field(True, description="语法是否合法")
    summary: str = Field(..., description="整体质量评估摘要")
    issues: List[CodeSmellItem] = Field(default_factory=list, description="代码缺陷与风险列表")
    refactored_code: Optional[str] = Field(None, description="推荐重构后的完整参考代码")


class TestExecutionResult(BaseModel):
    """单元测试生成与执行报告"""
    test_code: str = Field(..., description="生成的测试代码片段")
    executed: bool = Field(False, description="是否在隔离沙箱中执行")
    success: bool = Field(False, description="测试套件是否全部通过")
    output: str = Field("", description="执行标准输出与错误Traceback")
    passed_cases: int = Field(0, description="通过的测试用例数")
    failed_cases: int = Field(0, description="失败的测试用例数")


class ExplanationReport(BaseModel):
    """代码解释分析报告"""
    function_or_class: str = Field(..., description="被解释的目标函数或模块")
    algorithm_summary: str = Field(..., description="核心算法思路精要")
    time_complexity: str = Field(..., description="时间复杂度评估，如 O(n)")
    space_complexity: str = Field(..., description="空间复杂度评估，如 O(1)")
    step_by_step: List[str] = Field(default_factory=list, description="逐步骤执行逻辑拆解")


class RefactorPlan(BaseModel):
    """架构重构方案"""
    target: str = Field(..., description="重构对象")
    smells_resolved: List[str] = Field(default_factory=list, description="消除的代码风险隐患清单")
    patterns_used: List[str] = Field(default_factory=list, description="应用的设计模式")
    original_snippet: str = Field(..., description="重构前关键代码")
    refactored_code: str = Field(..., description="重构后规范代码")
    explanation: str = Field(..., description="重构收益与向后兼容性说明")
