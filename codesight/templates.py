import json
import re
from pathlib import Path

from .config import CONFIG_DIR

TEMPLATES_DIR = CONFIG_DIR / "templates"

_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _safe_template_path(name: str) -> Path:
    if not _VALID_NAME.match(name):
        raise ValueError(f"Invalid template name: {name!r}")
    path = (TEMPLATES_DIR / f"{name}.json").resolve()
    root = TEMPLATES_DIR.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path traversal detected in template name: {name!r}")
    return path


DEFAULT_TEMPLATES = {
    "quick-review": {
        "name": "Quick Review",
        "description": "Fast review focusing on critical issues only",
        "system": (
            "You are a senior engineer doing a fast code review. "
            "Only report critical and high-severity issues. Skip minor stuff. "
            "For each issue: line number, severity, one-line description, fix. "
            "No summaries, no praise, just the issues."
        ),
    },
    "pr-review": {
        "name": "PR Review",
        "description": "Review formatted for pull request comments",
        "system": (
            "You are reviewing a pull request. Be constructive and specific. "
            "For each issue: severity [blocking/suggestion/nit], line number, "
            "what's wrong, and a concrete fix. "
            "Start with a one-line verdict: APPROVE, REQUEST_CHANGES, or COMMENT. "
            "Format as a numbered list."
        ),
    },
    "security-owasp": {
        "name": "OWASP Top 10 Audit",
        "description": "Security audit mapped to OWASP Top 10 (2021)",
        "system": (
            "You are a security auditor. Analyze this code strictly against the "
            "OWASP Top 10 (2021). For each finding:\n"
            "- OWASP category (A01-A10)\n"
            "- CWE ID\n"
            "- Severity: CRITICAL / HIGH / MEDIUM / LOW\n"
            "- Line number\n"
            "- Description\n"
            "- Fix\n\n"
            "Only report findings that map to OWASP Top 10. "
            "End with a compliance summary."
        ),
    },
    "api-docs": {
        "name": "API Documentation",
        "description": "Generate REST API documentation from route handlers",
        "system": (
            "Extract and document all API endpoints from this code. "
            "For each endpoint: HTTP method, path, description, request params/body, "
            "response format, status codes, and authentication requirements. "
            "Output in markdown with a table of contents."
        ),
    },
    "performance": {
        "name": "Performance Review",
        "description": "Find performance bottlenecks and optimization opportunities",
        "system": (
            "Analyze this code for performance issues. Focus on: "
            "N+1 queries, unnecessary allocations, blocking I/O in async contexts, "
            "missing caching opportunities, O(n^2) loops that could be O(n), "
            "large memory copies, and inefficient data structures. "
            "For each issue: line number, impact (high/medium/low), "
            "what's slow, and a concrete optimization."
        ),
    },
}


def _ensure_dir() -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def list_templates() -> dict[str, dict]:
    templates = dict(DEFAULT_TEMPLATES)

    if TEMPLATES_DIR.exists():
        for f in TEMPLATES_DIR.glob("*.json"):
            if f.is_symlink() or not _VALID_NAME.match(f.stem):
                continue
            if f.stem in DEFAULT_TEMPLATES:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            required = {"name", "description", "system"}
            if not required.issubset(data) or not all(isinstance(data[k], str) for k in required):
                continue
            templates[f.stem] = {k: data[k] for k in required}

    return templates


def get_template(name: str) -> dict | None:
    templates = list_templates()
    return templates.get(name)


def save_template(name: str, display_name: str, description: str, system_prompt: str) -> Path:
    _ensure_dir()
    path = _safe_template_path(name)
    data = {
        "name": display_name,
        "description": description,
        "system": system_prompt,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def delete_template(name: str) -> bool:
    path = _safe_template_path(name)
    if path.exists() and not path.is_symlink():
        path.unlink()
        return True
    return False
