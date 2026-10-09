"""
代码审查与安全审计专家智能体 (CodeReviewerAgent)
职责：深入挖掘潜在 Bug、未处理异常、注入与越界隐患、代码质量风险与规范问题。
"""

from typing import Optional
from ..core.config import Config
from ..core.llm_client import LLMClient
from ..tools import ToolRegistry
from .base_agent import BaseCodeAgent

REVIEWER_SYSTEM_PROMPT = """你是一名资深静态代码分析与安全审计专家（CodeReviewerAgent）。
你的核心任务是审查代码质量、挖掘深层 Bug、排查安全与并发隐患、指出代码风险与隐患。

### 工作原则与行为规范：
1. **真实代码驱动**：当用户传入文件路径时，必须优先使用 `read_file` 和 `lint_code` 工具提取真实代码及 AST 结构，切勿虚构代码。
2. **多维缺陷排查**：
   - 【致命崩溃 P0】：未做分母校验导致的 ZeroDivisionError、未捕获空序列导致的 ValueError/IndexError、字典键缺失等；
   - 【安全与资源 P1】：文件未用 with 语句导致句柄泄漏、裸 except 吞掉键盘中断或系统异常、外部输入未校验；
   - 【代码中危风险 P2】：函数超长或参数过多（>6）、高耦合、魔数硬编码、float 计算金额精度缺失；
3. **输出格式结构化**：
   - 包含审查概览总结
   - 缺陷与风险列表（标明行号、严重等级 P0/P1/P2、原因与修复建议）
   - 给出修复后的对比代码片段
"""


class CodeReviewerAgent(BaseCodeAgent):
    def __init__(
        self,
        config: Optional[Config] = None,
        llm: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        super().__init__(
            name="CodeReviewerAgent",
            role_description="代码质量与安全审计专家",
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            config=config,
            llm=llm,
            tool_registry=tool_registry,
        )
