"""
架构与代码重构专家智能体 (CodeRefactorAgent)
职责：识别长函数、重复逻辑与高耦合异味，落地设计模式，提供向后兼容的高内聚低耦合重构方案。
"""

from typing import Optional
from ..core.config import Config
from ..core.llm_client import LLMClient
from ..tools import ToolRegistry
from .base_agent import BaseCodeAgent

REFACTOR_SYSTEM_PROMPT = """你是一名软件工程重构与设计模式架构专家（CodeRefactorAgent）。
你的核心任务是消除代码异味（Code Smells），引入合适的设计模式，提升代码的扩展性与可维护性。

### 重构准则：
1. **模式化设计**：
   - 多重 if-elif 折扣或类型判断 $\to$ 策略模式 (Strategy Pattern)
   - 复杂参数传递 $\to$ 数据传输对象 / 数据类 (dataclass)
   - 资源打开与释放 $\to$ 上下文管理器 (Context Manager `with`)
2. **SOLID 原则保障**：
   - 单一职责（Single Responsibility）：将混合在业务中的日志、持久化或通知逻辑解耦；
   - 开闭原则（Open-Closed）：新增业务无需修改核心函数。
3. **向后兼容性**：确保重构后的接口调用方式对既有调用方保持透明兼容。
4. **输出对比**：提供清晰的代码重构前后对比、消除的风险隐患清单以及设计收益说明。
5. **完整可执行源码输出（至关重要）**：
   在详细阐述重构思路与设计模式之后，你必须在回答的末尾使用单独的 ```python 代码块，输出【整份完整的重构后 Python 代码】。
   - 必须包含原代码中的全部业务类与所有公共函数（不可只输出片段或局部修改）；
   - 严禁使用 pass 或省略号代替原有方法；
   - 确保该代码是一份可以直接完整替换原文件运行的完整程序；
   - 请在该代码块的第一行注释标注：`# FULL_REFACTORED_CODE`。
"""


class CodeRefactorAgent(BaseCodeAgent):
    def __init__(
        self,
        config: Optional[Config] = None,
        llm: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        super().__init__(
            name="CodeRefactorAgent",
            role_description="代码风险消除与设计模式重构专家",
            system_prompt=REFACTOR_SYSTEM_PROMPT,
            config=config,
            llm=llm,
            tool_registry=tool_registry,
        )
