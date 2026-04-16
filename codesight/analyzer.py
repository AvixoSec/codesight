import fnmatch
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import get_provider_config
from .providers import create_provider
from .providers.base import Message

SCAN_EXTENSIONS = {".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c", ".h"}
DEFAULT_MAX_SIZE = 500  # KB


def collect_files(directory, extensions=None, ignore=None, max_size_kb=DEFAULT_MAX_SIZE):
    root = Path(directory).resolve()
    if not root.is_dir():
        return []
    exts = extensions or SCAN_EXTENSIONS
    skip = ignore or []
    found = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in exts:
            continue
        rel = str(p.relative_to(root))
        if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(p.name, pat) for pat in skip):
            continue
        if any(fnmatch.fnmatch(part, pat) for pat in skip for part in Path(rel).parts):
            continue
        if any(part.startswith(".") for part in Path(rel).parts):
            continue
        if p.stat().st_size / 1024 > max_size_kb:
            continue
        found.append(str(p))
    return found


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
        "Code review. Find issues, tag severity [crit/warn/info], suggest fixes. "
        "Sections: Summary, Issues, Suggestions."
    ),
    TaskType.BUGS: (
        "Find runtime bugs: logic errors, null access, resource leaks, races. "
        "Skip style. Sections: Bugs Found, Risk."
    ),
    TaskType.DOCS: (
        "Generate docs. Follow language conventions. Document all public APIs. "
        "Return full file with docs."
    ),
    TaskType.EXPLAIN: (
        "Explain this code. What it does, data flow, why structured this way. "
        "Reference specific lines."
    ),
    TaskType.REFACTOR: (
        "Suggest refactors. Show before/after. Focus on: extract logic, "
        "reduce nesting, better names."
    ),
}


class AnalysisError(Exception):
    pass


class Analyzer:

    def __init__(self, config, provider_name=None):
        pconfig = get_provider_config(config, provider_name)
        self._provider = create_provider(pconfig)
        self._max_tokens = pconfig.max_tokens
        self._temperature = pconfig.temperature
        self._max_size = config.max_file_size_kb

    def _check_file(self, path):
        p = Path(path)
        if not p.is_file():
            raise AnalysisError(f"Not found: {path}")
        if p.stat().st_size / 1024 > self._max_size:
            sz = p.stat().st_size / 1024
            raise AnalysisError(f"Too big: {sz:.0f}KB (max {self._max_size}KB)")
        return p

    async def analyze_file(self, file_path, task, extra_context=None):
        p = self._check_file(file_path)
        src = p.read_text(encoding="utf-8", errors="replace")
        ext = p.suffix.lstrip(".")

        content = f"File: `{file_path}`\n\n```{ext}\n{src}\n```"
        if extra_context:
            content += f"\n\nContext: {extra_context}"

        msgs = [Message(role="system", content=SYSTEM_PROMPTS[task]),
                Message(role="user", content=content)]

        try:
            resp = await self._provider.complete(msgs, max_tokens=self._max_tokens,
                                                  temperature=self._temperature)
        except Exception as e:
            raise AnalysisError(f"API failed: {e}") from e

        return AnalysisResult(
            task=task, file_path=file_path, content=resp.content,
            model=resp.model, provider=resp.provider,
            tokens_used=resp.usage.get("prompt_tokens", 0) + resp.usage.get("completion_tokens", 0)
        )

    async def analyze_files(self, paths, task):
        out = []
        for p in paths:
            out.append(await self.analyze_file(p, task))
        return out

    async def health(self):
        return await self._provider.health_check()
