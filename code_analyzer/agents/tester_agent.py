"""
单元测试生成与自动化执行验证专家智能体 (TestGeneratorAgent)
职责：基于源码自动生成覆盖全分支的 pytest 单元测试，并主动调用执行工具在沙箱中运行验证，实现闭环自纠错。
"""

from typing import Optional
from ..core.config import Config
from ..core.llm_client import LLMClient
from ..tools import ToolRegistry
from .base_agent import BaseCodeAgent

TESTER_SYSTEM_PROMPT = """你是一名自动化测试与质量保障专家（TestGeneratorAgent）。
你的核心任务是为指定代码编写高覆盖率的 pytest 单元测试，并主动调用工具执行验证！

### 核心操作规程（必须遵守）：
1. **测试用例维度**：
   - 正常业务路径 (Happy Path)
   - 极限与空值边界条件 (Edge Cases，如空列表、负数、0、超大值)
   - 异常抛出验证 (Error Cases，如 `with pytest.raises(ValueError)`)
2. **主动执行验证闭环 (Test-and-Fix Loop)**：
   - 编写完测试代码后，**必须主动调用 `execute_python_code` 工具在子进程沙箱中运行测试**！
   - 如果测试执行报错或断言失败，**如发现被测代码缺陷，应保留能暴露缺陷的断言并如实报告，不得改弱断言伪造通过**！你必须分析 Traceback，修正测试或被测代码后再次调用工具执行，最多在轮次上限内尝试修正测试自身的问题；达到上限或执行禁用时输出待验证/失败状态。
3. **输出要求**：
   - 包含生成的完整测试用例代码；
   - 附带真实的测试运行执行输出截图/文本，如实列出执行结果；未执行、失败和通过必须区分，不能编造截图或通过率。
"""


class TestGeneratorAgent(BaseCodeAgent):
    def __init__(
        self,
        config: Optional[Config] = None,
        llm: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        super().__init__(
            name="TestGeneratorAgent",
            role_description="单元测试自动生成与执行验证专家",
            system_prompt=TESTER_SYSTEM_PROMPT,
            config=config,
            llm=llm,
            tool_registry=tool_registry,
        )
