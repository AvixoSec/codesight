from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import SourceContext, extract_context
from .findings import Confidence, EvidencePathStep, ExploitabilityScore, Severity, VerifiedFinding
from .judge import MessageCompleter, judge_alert
from .profiles import profile_for_context


class VerificationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedAlert:
    rule_id: str
    tool_name: str
    title: str
    message: str
    level: str
    uri: str
    start_line: int
    end_line: int | None = None
    cwe_id: str | None = None

    @property
    def location(self) -> str:
        if not self.uri:
            return ""
        if self.end_line and self.end_line != self.start_line:
            return f"{self.uri}:{self.start_line}-{self.end_line}"
        return f"{self.uri}:{self.start_line}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "tool_name": self.tool_name,
            "title": self.title,
            "message": self.message,
            "level": self.level,
            "uri": self.uri,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "cwe_id": self.cwe_id,
        }


@dataclass(frozen=True)
class VerificationResult:
    sarif_path: Path
    source_root: Path
    alerts: list[NormalizedAlert]
    findings: list[VerifiedFinding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sarif_path": str(self.sarif_path),
            "source_root": str(self.source_root),
            "scanner_alert_count": len(self.alerts),
            "finding_count": len(self.findings),
            "alerts": [alert.to_dict() for alert in self.alerts],
            "findings": [finding.to_dict() for finding in self.findings],
        }


def preview_sarif_contexts(
    sarif_path: str | Path,
    source_root: str | Path = ".",
    *,
    context_lines: int = 20,
    profile: str = "auto",
) -> dict[str, Any]:
    resolved_sarif = Path(sarif_path).resolve()
    resolved_root = Path(source_root).resolve()
    payload = read_sarif(resolved_sarif)
    alerts = parse_sarif_alerts(payload)
    contexts = []
    for alert in alerts:
        context = _alert_context(alert, resolved_root, context_lines)
        security_profile = profile_for_context(context, profile)
        contexts.append(
            {
                "alert": alert.to_dict(),
                "security_profile": security_profile.to_dict(),
                "context": {
                    "display_path": context.display_path,
                    "start_line": context.start_line,
                    "end_line": context.end_line,
                    "missing": context.missing,
                    "reason": context.reason,
                    "snippet": context.snippet,
                },
            }
        )
    return {
        "sarif_path": str(resolved_sarif),
        "source_root": str(resolved_root),
        "scanner_alert_count": len(alerts),
        "contexts": contexts,
    }


def read_sarif(path: str | Path) -> dict[str, Any]:
    sarif_path = Path(path)
    if not sarif_path.is_file():
        raise VerificationError(f"SARIF file not found: {sarif_path}")

    try:
        payload = json.loads(sarif_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise VerificationError(f"Invalid SARIF JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise VerificationError("SARIF root must be a JSON object.")
    return payload


def parse_sarif_alerts(payload: dict[str, Any]) -> list[NormalizedAlert]:
    alerts: list[NormalizedAlert] = []
    for run in _as_list(payload.get("runs")):
        if not isinstance(run, dict):
            continue
        driver = _driver(run)
        tool_name = _text(driver.get("name")) or "scanner"
        rules = _rules_by_id(driver)

        for result in _as_list(run.get("results")):
            if not isinstance(result, dict):
                continue
            rule_id = _text(result.get("ruleId")) or "scanner-alert"
            rule = rules.get(rule_id, {})
            uri, start_line, end_line = _location(result)
            title = _rule_title(rule, rule_id)
            message = _message_text(result.get("message")) or title
            alerts.append(
                NormalizedAlert(
                    rule_id=rule_id,
                    tool_name=tool_name,
                    title=title,
                    message=message,
                    level=_text(result.get("level")) or "warning",
                    uri=uri,
                    start_line=start_line,
                    end_line=end_line,
                    cwe_id=_extract_cwe(rule_id, rule, result),
                )
            )
    return alerts


def verify_sarif_file(
    sarif_path: str | Path,
    source_root: str | Path = ".",
    *,
    context_lines: int = 20,
) -> VerificationResult:
    resolved_sarif = Path(sarif_path).resolve()
    resolved_root = Path(source_root).resolve()
    payload = read_sarif(resolved_sarif)
    alerts = parse_sarif_alerts(payload)
    findings = [
        _alert_to_uncertain_finding(alert, idx, resolved_root, context_lines)
        for idx, alert in enumerate(alerts, start=1)
    ]
    return VerificationResult(
        sarif_path=resolved_sarif,
        source_root=resolved_root,
        alerts=alerts,
        findings=findings,
    )


async def verify_sarif_file_with_judge(
    sarif_path: str | Path,
    source_root: str | Path = ".",
    *,
    completer: MessageCompleter,
    context_lines: int = 20,
    skeptic: bool = False,
    profile: str = "auto",
) -> VerificationResult:
    resolved_sarif = Path(sarif_path).resolve()
    resolved_root = Path(source_root).resolve()
    payload = read_sarif(resolved_sarif)
    alerts = parse_sarif_alerts(payload)
    findings: list[VerifiedFinding] = []

    for idx, alert in enumerate(alerts, start=1):
        context = _alert_context(alert, resolved_root, context_lines)
        security_profile = profile_for_context(context, profile)
        if context.missing:
            findings.append(_uncertain_from_context(alert, idx, context))
            continue
        try:
            findings.append(
                await judge_alert(
                    completer,
                    alert,
                    context,
                    finding_id=f"CS-VFY-{idx:03d}",
                    skeptic=skeptic,
                    profile=security_profile,
                )
            )
        except Exception as exc:
            fallback = _uncertain_from_context(alert, idx, context)
            fallback.uncertainty = (
                f"{fallback.uncertainty} Judge pass failed: {type(exc).__name__}: {exc}"
            )
            findings.append(fallback)

    return VerificationResult(
        sarif_path=resolved_sarif,
        source_root=resolved_root,
        alerts=alerts,
        findings=findings,
    )


def _alert_to_uncertain_finding(
    alert: NormalizedAlert,
    index: int,
    source_root: Path,
    context_lines: int,
) -> VerifiedFinding:
    return _uncertain_from_context(
        alert,
        index,
        _alert_context(alert, source_root, context_lines),
    )


def _alert_context(
    alert: NormalizedAlert,
    source_root: Path,
    context_lines: int,
) -> SourceContext:
    return extract_context(
        source_root,
        alert.uri,
        start_line=alert.start_line,
        end_line=alert.end_line,
        before=context_lines,
        after=context_lines,
    )


def _uncertain_from_context(
    alert: NormalizedAlert,
    index: int,
    context: SourceContext,
) -> VerifiedFinding:
    location = _finding_location(alert, context)
    evidence = _evidence_text(alert, context)
    uncertainty = (
        "Imported from scanner SARIF. CodeSight collected local context, but judge "
        "mode was not enabled, so the alert stays uncertain."
    )
    if context.missing:
        uncertainty = f"{uncertainty} {context.reason}"

    return VerifiedFinding(
        id=f"CS-VFY-{index:03d}",
        title=_shorten(alert.title or alert.rule_id, 120),
        verdict="uncertain",
        severity=_severity(alert.level),
        confidence=Confidence.LOW if context.missing else Confidence.MEDIUM,
        file_path=context.display_path or alert.uri or "unknown",
        start_line=alert.start_line,
        end_line=alert.end_line,
        cwe_id=alert.cwe_id,
        exploitability=ExploitabilityScore(),
        evidence_path=[
            EvidencePathStep(
                location=location,
                evidence=evidence,
                kind="scanner",
            )
        ],
        fix="Review the local evidence and either add the missing guard or suppress the scanner "
        "alert with a clear reason.",
        uncertainty=uncertainty,
    )


def _driver(run: dict[str, Any]) -> dict[str, Any]:
    tool = run.get("tool")
    if not isinstance(tool, dict):
        return {}
    driver = tool.get("driver")
    return driver if isinstance(driver, dict) else {}


def _rules_by_id(driver: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for rule in _as_list(driver.get("rules")):
        if isinstance(rule, dict):
            rule_id = _text(rule.get("id"))
            if rule_id:
                rules[rule_id] = rule
    return rules


def _location(result: dict[str, Any]) -> tuple[str, int, int | None]:
    locations = _as_list(result.get("locations"))
    if not locations or not isinstance(locations[0], dict):
        return "", 1, None

    physical = locations[0].get("physicalLocation")
    if not isinstance(physical, dict):
        return "", 1, None
    artifact = physical.get("artifactLocation")
    region = physical.get("region")
    uri = _text(artifact.get("uri")) if isinstance(artifact, dict) else ""
    if not isinstance(region, dict):
        return uri, 1, None
    start_line = _positive_int(region.get("startLine"), default=1)
    end_line = _positive_int(region.get("endLine"), default=0) or None
    return uri, start_line, end_line


def _rule_title(rule: dict[str, Any], rule_id: str) -> str:
    for key in ("shortDescription", "fullDescription"):
        value = rule.get(key)
        if isinstance(value, dict):
            text = _message_text(value)
            if text:
                return _shorten(text, 120)
    return _text(rule.get("name")) or rule_id


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    return _text(value.get("text")) or _text(value.get("markdown"))


def _extract_cwe(rule_id: str, rule: dict[str, Any], result: dict[str, Any]) -> str | None:
    for value in _string_values(rule_id, rule, result):
        match = re.search(r"\bCWE[-_ ]?(\d{1,6})\b", value, flags=re.IGNORECASE)
        if match:
            return _format_cwe(match.group(1))
    return None


def _format_cwe(raw_id: str) -> str:
    normalized = raw_id.lstrip("0") or "0"
    return f"CWE-{normalized}"


def _string_values(*values: Any) -> list[str]:
    found: list[str] = []
    for value in values:
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, dict):
            found.extend(_string_values(*value.values()))
        elif isinstance(value, list):
            found.extend(_string_values(*value))
    return found


def _severity(level: str) -> Severity:
    normalized = level.lower()
    if normalized == "error":
        return Severity.HIGH
    if normalized == "warning":
        return Severity.MEDIUM
    if normalized == "note":
        return Severity.LOW
    return Severity.INFO


def _finding_location(alert: NormalizedAlert, context: SourceContext) -> str:
    display = context.display_path or alert.uri or "unknown"
    if alert.end_line and alert.end_line != alert.start_line:
        return f"{display}:{alert.start_line}-{alert.end_line}"
    return f"{display}:{alert.start_line}"


def _evidence_text(alert: NormalizedAlert, context: SourceContext) -> str:
    scanner_text = _shorten(f"{alert.tool_name}: {alert.message}", 240)
    focused_line = _focused_line(context.snippet, alert.start_line)
    if context.missing:
        return _join_sentence(
            scanner_text,
            f"Local source context was unavailable: {context.reason}",
        )
    if focused_line:
        return _join_sentence(scanner_text, f"Local code: {focused_line}")
    return scanner_text


def _join_sentence(prefix: str, suffix: str) -> str:
    separator = " " if prefix.endswith((".", "!", "?")) else ". "
    return f"{prefix}{separator}{suffix}"


def _focused_line(snippet: str, line_number: int) -> str:
    prefix = f"{line_number:>4}: "
    for line in snippet.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _shorten(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}..."


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    return default


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
