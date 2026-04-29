from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Message:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict
    provider: str


class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
