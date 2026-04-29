from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .formatters import format_json_report, format_markdown_report
from .sarif import to_sarif_json
from .verify import VerificationResult


def verification_payload(
    result: VerificationResult,
    *,
    fail_on: str,
    judge_enabled: bool,
    skeptic_enabled: bool,
    profile: str,
) -> dict[str, Any]:
    payload = json.loads(format_json_report(result.findings))
    payload["scanner_alert_count"] = len(result.alerts)
    payload["sarif_path"] = str(result.sarif_path)
    payload["source_root"] = str(result.source_root)
    payload["fail_on"] = fail_on
    payload["judge_enabled"] = judge_enabled
    payload["skeptic_enabled"] = skeptic_enabled
    payload["profile"] = profile
    return payload


def write_verification_artifacts(
    result: VerificationResult,
    output_dir: str | Path,
    *,
    fail_on: str,
    judge_enabled: bool,
    skeptic_enabled: bool,
    profile: str,
    preview: dict[str, Any] | None = None,
) -> dict[str, str]:
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    report_md = target / "report.md"
    report_json = target / "report.json"
    sarif_json = target / "results.sarif"
    manifest_json = target / "manifest.json"

    report_md.write_text(format_markdown_report(result.findings), encoding="utf-8")
    report_json.write_text(
        json.dumps(
            verification_payload(
                result,
                fail_on=fail_on,
                judge_enabled=judge_enabled,
                skeptic_enabled=skeptic_enabled,
                profile=profile,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    sarif_json.write_text(to_sarif_json(result.findings) + "\n", encoding="utf-8")

    artifacts = {
        "report_markdown": str(report_md),
        "report_json": str(report_json),
        "sarif": str(sarif_json),
    }
    if preview is not None:
        preview_json = target / "preview-context.json"
        preview_json.write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
        artifacts["preview_context"] = str(preview_json)

    manifest = {
        "tool": "codesight verify",
        "sarif_path": str(result.sarif_path),
        "source_root": str(result.source_root),
        "scanner_alert_count": len(result.alerts),
        "finding_count": len(result.findings),
        "fail_on": fail_on,
        "judge_enabled": judge_enabled,
        "skeptic_enabled": skeptic_enabled,
        "profile": profile,
        "artifacts": artifacts,
    }
    manifest_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    artifacts["manifest"] = str(manifest_json)
    return artifacts
