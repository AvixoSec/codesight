from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .context import SourceContext


@dataclass(frozen=True)
class SecurityProfile:
    name: str
    title: str
    attacker_sources: tuple[str, ...]
    risky_sinks: tuple[str, ...]
    expected_guards: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "attacker_sources": list(self.attacker_sources),
            "risky_sinks": list(self.risky_sinks),
            "expected_guards": list(self.expected_guards),
            "notes": list(self.notes),
        }


BUILTIN_PROFILES: dict[str, SecurityProfile] = {
    "generic": SecurityProfile(
        name="generic",
        title="Generic web/security code",
        attacker_sources=(
            "request parameters, body, headers, cookies, uploaded files",
            "environment variables controlled by deployment or CI",
            "webhook payloads and queue messages",
        ),
        risky_sinks=(
            "SQL/query execution",
            "template rendering or raw HTML output",
            "file path reads/writes",
            "shell/process execution",
            "network fetches to user-controlled URLs",
            "authorization or tenant boundary decisions",
        ),
        expected_guards=(
            "input validation",
            "parameterized queries",
            "authorization and tenant membership checks",
            "path normalization under a trusted root",
            "allowlists for outbound hosts or commands",
        ),
    ),
    "flask": SecurityProfile(
        name="flask",
        title="Python Flask application",
        attacker_sources=(
            "flask.request.args",
            "flask.request.form",
            "flask.request.json",
            "flask.request.data",
            "flask.request.headers",
            "route path parameters",
        ),
        risky_sinks=(
            "db.execute, cursor.execute, raw SQL strings",
            "render_template_string and direct HTML responses",
            "send_file and filesystem reads",
            "requests.get/post with request-controlled URL",
            "subprocess/os.system",
        ),
        expected_guards=(
            "parameterized SQL",
            "Jinja autoescaping or explicit escaping",
            "safe_join/path allowlist",
            "auth and tenant checks before data access",
            "host allowlist for outbound fetches",
        ),
    ),
    "fastapi": SecurityProfile(
        name="fastapi",
        title="Python FastAPI application",
        attacker_sources=(
            "path/query/body parameters",
            "Request.json/body/headers/cookies",
            "UploadFile content and filename",
            "dependency-injected user or tenant ids",
        ),
        risky_sinks=(
            "raw SQL execution",
            "FileResponse/path reads",
            "BackgroundTasks with user-controlled commands",
            "httpx/requests outbound fetch",
            "authorization dependencies and tenant lookups",
        ),
        expected_guards=(
            "Pydantic validation is not authorization",
            "dependency-based auth checks",
            "tenant membership checks before object access",
            "parameterized queries",
            "path normalization under a trusted root",
        ),
    ),
    "express": SecurityProfile(
        name="express",
        title="Node.js Express application",
        attacker_sources=(
            "req.params",
            "req.query",
            "req.body",
            "req.headers",
            "req.cookies",
            "uploaded files",
        ),
        risky_sinks=(
            "db.query/raw SQL strings",
            "res.send with raw HTML",
            "fs.readFile/writeFile paths",
            "child_process exec/spawn",
            "fetch/axios/request with user-controlled URLs",
        ),
        expected_guards=(
            "parameterized queries",
            "output encoding",
            "auth middleware and tenant checks",
            "path.resolve plus root containment",
            "URL host allowlist",
        ),
    ),
    "django": SecurityProfile(
        name="django",
        title="Python Django application",
        attacker_sources=(
            "request.GET",
            "request.POST",
            "request.body",
            "request.headers",
            "URL route parameters",
            "uploaded files",
        ),
        risky_sinks=(
            "raw SQL/cursor.execute",
            "mark_safe and raw HTML",
            "FileResponse/filesystem paths",
            "requests/httpx outbound fetch",
            "object lookup before permission check",
        ),
        expected_guards=(
            "ORM filtering is not authorization by itself",
            "permission checks before object access",
            "template autoescaping unless bypassed",
            "parameterized SQL",
            "safe path handling",
        ),
    ),
    "github-actions": SecurityProfile(
        name="github-actions",
        title="GitHub Actions workflow",
        attacker_sources=(
            "pull_request fields",
            "issue/comment text",
            "workflow_dispatch inputs",
            "untrusted branch names",
            "artifact contents",
        ),
        risky_sinks=(
            "run shell steps",
            "github-script eval-like code",
            "secrets exposure",
            "checkout of untrusted refs",
            "write-token permissions",
        ),
        expected_guards=(
            "read-only permissions for untrusted events",
            "avoid interpolating untrusted values into shell",
            "pin actions by SHA for sensitive workflows",
            "separate pull_request from pull_request_target risk",
        ),
    ),
    "ai-agent": SecurityProfile(
        name="ai-agent",
        title="AI agent or tool-calling code",
        attacker_sources=(
            "model output",
            "tool call arguments",
            "retrieved documents",
            "chat/user messages",
            "browser/page content",
        ),
        risky_sinks=(
            "shell/process tools",
            "filesystem write/delete tools",
            "HTTP clients with credentials",
            "database/admin tools",
            "prompt/tool routing decisions",
        ),
        expected_guards=(
            "treat model output as untrusted",
            "schema validation for tool arguments",
            "allowlists for commands, hosts, and paths",
            "human approval for destructive tools",
            "secret redaction before model/tool calls",
        ),
    ),
}


PROFILE_CHOICES = ("auto", *BUILTIN_PROFILES.keys())


def profile_names() -> list[str]:
    return list(PROFILE_CHOICES)


def get_profile(name: str) -> SecurityProfile:
    normalized = name.strip().lower()
    if normalized == "auto":
        normalized = "generic"
    try:
        return BUILTIN_PROFILES[normalized]
    except KeyError as exc:
        allowed = ", ".join(PROFILE_CHOICES)
        raise ValueError(f"Unknown security profile: {name}. Expected one of: {allowed}") from exc


def profile_for_context(context: SourceContext, requested: str = "auto") -> SecurityProfile:
    normalized = requested.strip().lower()
    if normalized != "auto":
        return get_profile(normalized)

    haystack = f"{context.display_path}\n{context.snippet}".lower()
    if _looks_like_github_actions(haystack):
        return BUILTIN_PROFILES["github-actions"]
    if _contains_any(haystack, ("fastapi", "apirouter", "depends(", "uploadfile")):
        return BUILTIN_PROFILES["fastapi"]
    if _contains_any(haystack, ("from flask", "import flask", "@app.route", "request.args")):
        return BUILTIN_PROFILES["flask"]
    if _contains_any(haystack, ("express()", "app.get(", "app.post(", "req.query", "req.body")):
        return BUILTIN_PROFILES["express"]
    if _contains_any(haystack, ("django", "request.get", "request.post", "urlpatterns")):
        return BUILTIN_PROFILES["django"]
    if _contains_any(haystack, ("tool_calls", "function_call", "openai", "anthropic", "agent")):
        return BUILTIN_PROFILES["ai-agent"]
    return BUILTIN_PROFILES["generic"]


def _looks_like_github_actions(value: str) -> bool:
    return (
        ".github/workflows/" in value
        or "runs-on:" in value
        or "github.event." in value
        or "pull_request_target" in value
    )


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)
