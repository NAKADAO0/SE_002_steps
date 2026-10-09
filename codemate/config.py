"""
配置管理模块：负责 API 凭证、模型参数和工程运行环境的集中加载与验证。
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 自动定位并加载当前工程根目录的 .env 文件
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


class Config:
    """系统全局配置类"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        max_iterations: int = 10,
        temperature: float = 0.2,
        timeout: int = 60,
        workspace_dir: Optional[str] = None,
        allow_execution: Optional[bool] = None,
    ):
        # 优先读取传入参数，次之读取 DEEPSEEK 环境变量，最后读取 OPENAI 环境变量
        self.api_key = (
            api_key
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
        self.base_url = (
            base_url
            or os.getenv("DEEPSEEK_BASE_URL")
            or (
                "https://api.openai.com/v1"
                if os.getenv("OPENAI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY")
                else "https://api.deepseek.com/v1"
            )
        )
        self.model_name = (
            model_name
            or os.getenv("DEEPSEEK_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "deepseek-flash"
        )
        self.max_iterations = int(os.getenv("AGENT_MAX_ITERATIONS", max_iterations))
        self.temperature = float(os.getenv("AGENT_TEMPERATURE", temperature))
        self.timeout = int(os.getenv("AGENT_TIMEOUT", timeout))

        raw_workspace = workspace_dir or os.getenv("WORKSPACE_DIR", ".")
        self.workspace_dir = Path(raw_workspace).resolve()
        self.allow_execution = (os.getenv("AGENT_ALLOW_EXECUTION", "0") == "1"
                                if allow_execution is None else allow_execution)

    def has_valid_api_key(self) -> bool:
        """检查是否已配置有效的 API Key"""
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

    @classmethod
    def from_env(cls) -> "Config":
        """从当前环境变量构造配置实例"""
        return cls()
