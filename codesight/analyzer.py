"""Core analysis engine."""

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .config import AppConfig, get_provider_config
from .providers import create_provider
from .providers.base import BaseLLMProvider, LLMResponse, Message


class TaskType(Enum):
    REVIEW = "review"
    BUGS = "bugs"
    DOCS = "docs"
    EXPLAIN = "explain"
    REFACTOR = "refactor"


@dataclass
class AnalysisResult:
    task: TaskType
    file_path: str
    content: str
    model: str
    provider: str
    tokens_used: int


SYSTEM_PROMPTS = {
    TaskType.REVIEW: (
        "You are CodeSight, a senior software engineer performing a thorough code review. "
        "Analyze the provided source code for: correctness, performance, security vulnerabilities, "
        "code style, and maintainability. Structure your response with sections: "
        "## Summary, ## Issues (severity: critical/warning/info), ## Suggestions."
    ),
    TaskType.BUGS: (
        "You are CodeSight, a bug-detection specialist. Analyze the code for potential bugs, "
        "race conditions, off-by-one errors, null-pointer dereferences, resource leaks, and "
        "logic flaws. For each bug found, explain the root cause and propose a fix. "
        "Use sections: ## Bugs Found, ## Risk Assessment."
    ),
    TaskType.DOCS: (
        "You are CodeSight, a technical documentation generator. Given the source code, produce "
        "clean, comprehensive docstrings and module-level documentation in the style of the "
        "language's conventions (e.g. Google-style for Python, JSDoc for JS/TS). "
        "Return the full file with added documentation."
    ),
    TaskType.EXPLAIN: (
        "You are CodeSight, a patient code explainer. Break down the provided code for a "
        "developer who is seeing it for the first time. Explain the purpose, data flow, "
        "key design decisions, and any non-obvious patterns. Use clear headings."
    ),
    TaskType.REFACTOR: (
        "You are CodeSight, a refactoring advisor. Analyze the code and suggest concrete "
        "refactoring opportunities: extract functions, reduce complexity, improve naming, "
        "apply design patterns where appropriate. Show before/after snippets."
    ),
}


class Analyzer:
    """Main analysis orchestrator."""

    def __init__(self, config: AppConfig, provider_name: Optional[str] = None) -> None:
        pconfig = get_provider_config(config, provider_name)
        self._provider: BaseLLMProvider = create_provider(pconfig)
        self._max_tokens = pconfig.max_tokens
        self._temperature = pconfig.temperature

    async def analyze_file(
        self,
        file_path: str,
        task: TaskType,
        extra_context: Optional[str] = None,
    ) -> AnalysisResult:
        """Run a single analysis task on one file."""
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        ext = Path(file_path).suffix

        user_content = f"File: `{file_path}` ({ext})\n\n```{ext.lstrip('.')}\n{source}\n```"
        if extra_context:
            user_content += f"\n\nAdditional context: {extra_context}"

        messages = [
            Message(role="system", content=SYSTEM_PROMPTS[task]),
            Message(role="user", content=user_content),
        ]

        response: LLMResponse = await self._provider.complete(
            messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        return AnalysisResult(
            task=task,
            file_path=file_path,
            content=response.content,
            model=response.model,
            provider=response.provider,
            tokens_used=response.usage.get("prompt_tokens", 0)
            + response.usage.get("completion_tokens", 0),
        )

    async def analyze_files(
        self,
        file_paths: List[str],
        task: TaskType,
    ) -> List[AnalysisResult]:
        """Run analysis on multiple files concurrently."""
        tasks = [self.analyze_file(fp, task) for fp in file_paths]
        return await asyncio.gather(*tasks)

    async def health(self) -> bool:
        return await self._provider.health_check()
