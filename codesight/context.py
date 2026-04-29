from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class SourceContext:
    file_path: Path | None
    display_path: str
    start_line: int
    end_line: int
    snippet: str
    missing: bool = False
    reason: str = ""


def resolve_artifact_path(source_root: str | Path, uri: str) -> Path | None:
    root = Path(source_root).resolve()
    raw_path = _uri_to_path(uri)
    if raw_path is None:
        return None

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate

    resolved = candidate.resolve(strict=False)
    if not _is_relative_to(resolved, root):
        return None
    return resolved


def extract_context(
    source_root: str | Path,
    uri: str,
    *,
    start_line: int = 1,
    end_line: int | None = None,
    before: int = 20,
    after: int = 20,
) -> SourceContext:
    root = Path(source_root).resolve()
    target = resolve_artifact_path(root, uri)
    safe_start = max(1, start_line)
    safe_end = max(safe_start, end_line or safe_start)

    if target is None:
        return SourceContext(
            file_path=None,
            display_path=uri,
            start_line=safe_start,
            end_line=safe_end,
            snippet="",
            missing=True,
            reason="SARIF artifact path is outside the source root or uses an unsupported URI.",
        )

    display_path = _display_path(target, root)
    if not target.is_file():
        return SourceContext(
            file_path=target,
            display_path=display_path,
            start_line=safe_start,
            end_line=safe_end,
            snippet="",
            missing=True,
            reason="Referenced source file was not found.",
        )

    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return SourceContext(
            file_path=target,
            display_path=display_path,
            start_line=1,
            end_line=1,
            snippet="",
            missing=False,
        )

    safe_start = min(safe_start, len(lines))
    safe_end = min(max(safe_start, safe_end), len(lines))
    window_start = max(1, safe_start - max(0, before))
    window_end = min(len(lines), safe_end + max(0, after))
    snippet = "\n".join(
        f"{line_no:>4}: {lines[line_no - 1]}" for line_no in range(window_start, window_end + 1)
    )

    return SourceContext(
        file_path=target,
        display_path=display_path,
        start_line=safe_start,
        end_line=safe_end,
        snippet=snippet,
        missing=False,
    )


def _uri_to_path(uri: str) -> str | None:
    cleaned = uri.strip()
    if not cleaned:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            return None
        if len(path) >= 4 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return path

    if parsed.scheme:
        return None

    return unquote(cleaned)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
