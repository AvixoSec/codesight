import fnmatch
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .compression import compress_for_prompt
from .config import AppConfig, get_provider_config
from .providers import create_provider
from .providers.base import BaseLLMProvider, LLMResponse, Message

SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".rb",
    ".java", ".kt", ".cs", ".cpp", ".c", ".h", ".hpp",
    ".php", ".swift", ".scala", ".sh", ".bash",
    ".sol", ".vy",
}

PROMPT_COMPRESSION_MAX_LINES = 1200


def collect_files(
    directory: str,
    extensions: set[str] | None = None,
    ignore: list[str] | None = None,
    max_size_kb: int = 500,
) -> list[str]:
    root = Path(directory).resolve(strict=False)
    if not root.is_dir():
        return []
    exts = extensions or SCAN_EXTENSIONS
    ignore = ignore or []
    found = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.is_symlink():
            continue
        try:
            real = p.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        try:
            real.relative_to(root)
        except ValueError:
            continue
        if p.suffix not in exts:
            continue
        rel_parts = p.relative_to(root).parts
        rel = str(p.relative_to(root))
        if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(p.name, pat) for pat in ignore):
            continue
        if any(fnmatch.fnmatch(part, pat) for pat in ignore for part in rel_parts):
            continue
        if any(part.startswith(".") for part in rel_parts):
            continue
        if p.stat().st_size / 1024 > max_size_kb:
            continue
        found.append(str(real))
    return found


class TaskType(Enum):
    REVIEW = "review"
    BUGS = "bugs"
    SECURITY = "security"
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
    usage: dict = None


SYSTEM_PROMPTS = {
    TaskType.REVIEW: (
        "You are a senior engineer doing a code review. Be direct and specific. "
        "For every issue: state the line number, severity "
        "[crit/warn/info], what's wrong, and how to fix it. "
        "Start with a one-line summary. Don't pad with praise. "
        "Sections: ## Summary, ## Issues, ## Suggestions"
    ),
    TaskType.BUGS: (
        "Find bugs in this code. Focus on things that will actually break at runtime: "
        "logic errors, off-by-ones, null access, unclosed resources, race conditions, "
        "unhandled edge cases. For each bug: line number, root cause, fix. "
        "Skip style nitpicks. Sections: ## Bugs Found, ## Risk Assessment"
    ),
    TaskType.SECURITY: (
        "You are a security auditor. Analyze this code for security vulnerabilities. "
        "For EACH finding, provide:\n"
        "- Severity: CRITICAL / HIGH / MEDIUM / LOW\n"
        "- CWE ID (e.g. CWE-89 for SQL injection)\n"
        "- OWASP category (e.g. A03:2021 Injection)\n"
        "- Line number(s)\n"
        "- Description of the vulnerability\n"
        "- Proof of concept or attack scenario\n"
        "- Recommended fix with code example\n\n"
        "Focus on: injection (SQL, command, XSS), broken authentication, "
        "sensitive data exposure, broken access control, security misconfiguration, "
        "SSRF, path traversal, deserialization, race conditions (TOCTOU), "
        "hardcoded secrets, and insecure cryptography.\n\n"
        "Output format:\n"
        "## Security Findings\n"
        "### [SEVERITY] Title - CWE-XXX\n"
        "**OWASP:** Category\n"
        "**Location:** file:line\n"
        "**Description:** ...\n"
        "**Fix:** ...\n\n"
        "## Summary\n"
        "Total findings by severity. Overall risk assessment."
    ),
    TaskType.DOCS: (
        "Generate documentation for this code. Follow the language conventions "
        "(Google-style docstrings for Python, JSDoc for JS/TS). "
        "Document every public function/class. Include param types, return types, "
        "and a brief description. Return the full file with docs added."
    ),
    TaskType.EXPLAIN: (
        "Explain this code to someone seeing it for the first time. "
        "Cover: what it does, how data flows through it, why it's structured this way, "
        "and anything non-obvious. Keep it concrete, reference specific lines."
    ),
    TaskType.REFACTOR: (
        "Suggest refactoring for this code. Be specific, show before/after diffs. "
        "Focus on: extracting repeated logic, reducing nesting, better naming, "
        "splitting large functions. Don't suggest changes that only affect style."
    ),
}


SOLIDITY_SECURITY_PROMPT = (
    "You are a smart contract security auditor. Analyze this Solidity code. "
    "For EACH finding, provide:\n"
    "- Severity: CRITICAL / HIGH / MEDIUM / LOW\n"
    "- SWC ID (e.g. SWC-107 for reentrancy)\n"
    "- CWE ID if applicable\n"
    "- Line number(s)\n"
    "- Description of the vulnerability\n"
    "- Attack scenario with example transaction sequence\n"
    "- Recommended fix with code example\n\n"
    "Focus on: reentrancy (SWC-107), integer overflow/underflow (SWC-101), "
    "unchecked external calls (SWC-104), tx.origin authentication (SWC-115), "
    "delegatecall injection (SWC-112), front-running / MEV, "
    "access control issues, flash loan attack vectors, "
    "price oracle manipulation, storage collision, "
    "selfdestruct abuse, and gas griefing.\n\n"
    "Output format:\n"
    "## Security Findings\n"
    "### [SEVERITY] Title - SWC-XXX\n"
    "**Location:** contract:function:line\n"
    "**Description:** ...\n"
    "**Attack Scenario:** ...\n"
    "**Fix:** ...\n\n"
    "## Summary\n"
    "Total findings by severity. Overall risk assessment."
)


class AnalysisError(Exception):
    pass


class Analyzer:

    def __init__(self, config: AppConfig, provider_name: str | None = None) -> None:
        pconfig = get_provider_config(config, provider_name)
        self.provider_config = pconfig
        self._provider: BaseLLMProvider = create_provider(pconfig)
        self._max_tokens = pconfig.max_tokens
        self._temperature = pconfig.temperature
        self._max_file_size_kb = config.max_file_size_kb

    def _validate_file(self, file_path: str) -> Path:
        p = Path(file_path)
        if not p.is_file():
            raise AnalysisError(f"File not found: {file_path}")
        size_kb = p.stat().st_size / 1024
        if size_kb > self._max_file_size_kb:
            raise AnalysisError(
                f"File too large: {size_kb:.0f}KB (limit: {self._max_file_size_kb}KB). "
                f"Adjust max_file_size_kb in config to override."
            )
        return p

    async def analyze_file(
        self,
        file_path: str,
        task: TaskType,
        extra_context: str | None = None,
    ) -> AnalysisResult:
        p = self._validate_file(file_path)
        source = p.read_text(encoding="utf-8", errors="replace")
        ext = p.suffix

        display_source = compress_for_prompt(
            file_path,
            source,
            max_lines=PROMPT_COMPRESSION_MAX_LINES,
        )
        is_compressed = display_source != source
        user_content = f"File: `{file_path}` ({ext})\n\n```{ext.lstrip('.')}\n{display_source}\n```"
        if is_compressed:
            user_content += (
                "\n\nNOTE: This file was compressed into a code map because it is large. "
                "Only make high-confidence observations based on the visible structure. "
                "Do not invent line-specific issues for code bodies that are not shown."
            )
        if extra_context:
            user_content += f"\n\nAdditional context: {extra_context}"

        system_prompt = SYSTEM_PROMPTS[task]
        if ext == ".sol" and task == TaskType.SECURITY:
            system_prompt = SOLIDITY_SECURITY_PROMPT

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

        try:
            response: LLMResponse = await self._provider.complete(
                messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:
            error_text = str(exc)
            if ".services.ai.azure.com" in error_text and "PermissionDenied" in error_text:
                raise AnalysisError(
                    f"API call failed: {exc}\n"
                    "Azure Foundry rejected the request. Check these 3 things:\n"
                    "1. Use the resource root only (for example `https://your-resource.services.ai.azure.com`)\n"
                    "2. Do not use `/api/projects/...` or paste the full "
                    "`/anthropic/v1/messages` path\n"
                    "3. The API key must come from Foundry → Endpoints & keys"
                ) from exc
            if ".services.ai.azure.com" in error_text and "DeploymentNotFound" in error_text:
                raise AnalysisError(
                    f"API call failed: {exc}\n"
                    "Azure Foundry could not find that deployment. "
                    "Check the exact deployment name in the portal."
                ) from exc
            raise AnalysisError(
                f"API call failed: {exc}\n"
                f"Check your API key and network connection."
            ) from exc

        usage = response.usage
        return AnalysisResult(
            task=task,
            file_path=file_path,
            content=response.content,
            model=response.model,
            provider=response.provider,
            tokens_used=usage.get("prompt_tokens", 0)
            + usage.get("completion_tokens", 0),
            usage=usage,
        )

    async def analyze_files(
        self,
        file_paths: list[str],
        task: TaskType,
    ) -> list[AnalysisResult]:
        results = []
        for fp in file_paths:
            results.append(await self.analyze_file(fp, task))
        return results

    async def complete_messages(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        return await self._provider.complete(
            messages,
            max_tokens=self._max_tokens if max_tokens is None else max_tokens,
            temperature=self._temperature if temperature is None else temperature,
        )

    async def health(self) -> bool:
        return await self._provider.health_check()
