from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable

from .findings import SERIOUS_VERDICTS, Verdict, VerifiedFinding

VERDICT_LABELS = {
    Verdict.EXPLOITABLE: "Blocked",
    Verdict.LIKELY_EXPLOITABLE: "Likely exploitable",
    Verdict.UNCERTAIN: "Needs review",
    Verdict.PROBABLY_FALSE_POSITIVE: "Dismissed",
    Verdict.NOT_EXPLOITABLE: "Not exploitable",
}

VERDICT_ORDER = [
    Verdict.EXPLOITABLE,
    Verdict.LIKELY_EXPLOITABLE,
    Verdict.UNCERTAIN,
    Verdict.PROBABLY_FALSE_POSITIVE,
    Verdict.NOT_EXPLOITABLE,
]


def summarize_findings(findings: Iterable[VerifiedFinding]) -> dict[str, int]:
    counts = Counter(finding.verdict.value for finding in findings)
    return {verdict.value: counts.get(verdict.value, 0) for verdict in VERDICT_ORDER}


def format_json_report(findings: list[VerifiedFinding], *, indent: int | None = 2) -> str:
    payload = {
        "summary": summarize_findings(findings),
        "findings": [finding.to_dict() for finding in findings],
    }
    return json.dumps(payload, indent=indent)


def format_markdown_report(findings: list[VerifiedFinding]) -> str:
    lines = [
        "# CodeSight security report",
        "",
        "## Verdict",
        "",
    ]
    counts = summarize_findings(findings)
    lines.extend(_summary_lines(counts))

    serious = [
        finding
        for finding in findings
        if finding.verdict in SERIOUS_VERDICTS or finding.verdict == Verdict.UNCERTAIN
    ]
    dismissed = [
        finding
        for finding in findings
        if finding.verdict in {Verdict.PROBABLY_FALSE_POSITIVE, Verdict.NOT_EXPLOITABLE}
    ]

    if serious:
        lines.extend(["", "## Findings", ""])
        for finding in serious:
            lines.extend(_finding_lines(finding))
            lines.append("")

    if dismissed:
        lines.extend(["", "## Dismissed", ""])
        for finding in dismissed:
            reason = finding.false_positive_reason or finding.uncertainty or "No risk found."
            lines.append(f"- `{finding.id}` {finding.title}: {reason}")

    return "\n".join(lines).rstrip() + "\n"


def _summary_lines(counts: dict[str, int]) -> list[str]:
    blocked = counts[Verdict.EXPLOITABLE.value]
    likely = counts[Verdict.LIKELY_EXPLOITABLE.value]
    uncertain = counts[Verdict.UNCERTAIN.value]
    dismissed = (
        counts[Verdict.PROBABLY_FALSE_POSITIVE.value] + counts[Verdict.NOT_EXPLOITABLE.value]
    )
    return [
        f"- Blocked: {blocked} exploitable issue(s)",
        f"- Likely exploitable: {likely}",
        f"- Needs review: {uncertain}",
        f"- Dismissed: {dismissed}",
    ]


def _finding_lines(finding: VerifiedFinding) -> list[str]:
    lines = [
        f"### {finding.id}: {finding.title}",
        "",
        f"- Verdict: `{finding.verdict.value}`",
        f"- Severity: `{finding.severity.value}`",
        f"- Confidence: `{finding.confidence.value}`",
        f"- Exploitability: `{finding.exploitability.total}/100`",
        f"- Location: `{finding.location}`",
    ]
    if finding.cwe_id:
        lines.append(f"- CWE: `{finding.cwe_id}`")
    if finding.owasp_category:
        lines.append(f"- OWASP: `{finding.owasp_category}`")

    lines.extend(["", "#### Evidence", ""])
    if finding.source:
        lines.append(f"- Source: `{finding.source}`")
    if finding.sink:
        lines.append(f"- Sink: `{finding.sink}`")
    if finding.missing_guard:
        lines.append(f"- Missing guard: {finding.missing_guard}")
    if finding.impact:
        lines.append(f"- Impact: {finding.impact}")

    if finding.evidence_path:
        lines.extend(["", "#### Evidence path", ""])
        for idx, step in enumerate(finding.evidence_path, start=1):
            lines.append(f"{idx}. `{step.location}` - {step.evidence}")

    if finding.attack_scenario:
        lines.extend(["", "#### Attack scenario", "", finding.attack_scenario])
    if finding.fix:
        lines.extend(["", "#### Fix", "", finding.fix])
    if finding.uncertainty:
        lines.extend(["", "#### Uncertainty", "", finding.uncertainty])

    return lines
