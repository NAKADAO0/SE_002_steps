"""Shared construction for CLI and Web clients."""
from pathlib import Path
from code_analyzer.core.config import Config
from .agents import build_agents
from .demo import DemoLLM
from .engine import ReviewWorkflow
from .storage import RunStore

ROOT = Path(__file__).resolve().parent.parent


def create_workflow(mode="live", output_dir=None):
    config = Config(workspace_dir=str(ROOT), allow_execution=False)
    if mode == "live" and not config.has_valid_api_key():
        raise ValueError("真实模式需要 API Key，请按 .env.example 配置 .env；离线演示用 --demo")
    return ReviewWorkflow(build_agents(config, DemoLLM() if mode == "demo" else None),
                          RunStore(output_dir or ROOT / "runs"))
