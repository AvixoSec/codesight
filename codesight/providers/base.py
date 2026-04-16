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
    async def complete(self, messages, max_tokens=4096, temperature=0.2): ...

    @abstractmethod
    async def health_check(self): ...

    @property
    @abstractmethod
    def name(self): ...
