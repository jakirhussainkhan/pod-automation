"""Shared AI provider types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AIResult:
    """Immutable result of a single AI completion call."""

    text: str
    provider: str
    model: str
    tokens_used: Optional[int] = None


class BaseAIProvider(ABC):
    """Abstract interface every AI provider must implement."""

    name: str = ""
    model: str = ""

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> AIResult:
        """Send prompts to the model and return its completion."""
        raise NotImplementedError
