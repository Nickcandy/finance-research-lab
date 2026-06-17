"""LLM adapter interfaces for finance-research-lab."""

from .base import LLMClient, LLMResponse
from .mock_client import MockLLMClient

__all__ = ["LLMClient", "LLMResponse", "MockLLMClient"]
