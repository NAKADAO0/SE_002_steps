"""Compatibility import: CLI and analyzer use one LangChain client."""
from code_analyzer.core.llm_client import LLMClient, LLMResponse

__all__ = ["LLMClient", "LLMResponse"]
