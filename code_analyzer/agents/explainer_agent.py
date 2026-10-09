"""
代码逻辑解释与算法分析专家智能体 (CodeExplainerAgent)
职责：深入剖析复杂代码逻辑、算法推导过程、核心变量流转与时间/空间复杂度评估。
"""

from typing import Optional
from ..core.config import Config
from ..core.llm_client import LLMClient
from ..tools import ToolRegistry
from .base_agent import BaseCodeAgent

EXPLAINER_SYSTEM_PROMPT = """你是一名计算机算法与代码逻辑解构专家（CodeExplainerAgent）。
你的核心任务是深入剖析代码执行流、核心数据结构流转，并评估算法的时空复杂度。

### 分析维度：
1. **算法与设计核心**：用通俗易懂且专业的语言解释算法思想（如双指针、动态规划、递归分支、哈希查表等）；
2. **逐步逻辑流拆解**：梳理各条件分支在什么输入下被激活，关键变量如何变化；
3. **复杂度理论评估**：
   - 时间复杂度：最好情况、最坏情况与平均情况分析（如 O(1), O(log n), O(n), O(n^2)）；
   - 空间复杂度：辅助数据结构开销、调用栈深度；
4. **代码注释与可读性建议**：指出晦涩代码段并补充高质量 Docstring。
"""


class CodeExplainerAgent(BaseCodeAgent):
    def __init__(
        self,
        config: Optional[Config] = None,
        llm: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        super().__init__(
            name="CodeExplainerAgent",
            role_description="代码逻辑与算法复杂度分析专家",
            system_prompt=EXPLAINER_SYSTEM_PROMPT,
            config=config,
            llm=llm,
            tool_registry=tool_registry,
        )
