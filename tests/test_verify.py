import asyncio
import json
from pathlib import Path

from codesight.findings import Confidence, Verdict
from codesight.providers.base import LLMResponse
from codesight.verify import (
    parse_sarif_alerts,
    preview_sarif_contexts,
    read_sarif,
    verify_sarif_file,
    verify_sarif_file_with_judge,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeCompleter:
    async def complete_messages(self, messages, max_tokens=None, temperature=None):
        return LLMResponse(
            content=json.dumps(
                {
                    "title": "SQL injection",
                    "verdict": "exploitable",
                    "severity": "high",
                    "confidence": "high",
                    "cwe_id": "CWE-89",
                    "owasp_category": "A03:2021 Injection",
                    "source": 'request.args["q"]',
                    "sink": "db.execute",
                    "missing_guard": "No parameterized query.",
                    "evidence_path": [
                        {
                            "location": "app.py:6",
                            "evidence": "Input is interpolated into SQL.",
                        }
                    ],
                    "attack_scenario": "Send a crafted q parameter.",
                    "impact": "SQL injection.",
                    "fix": "Use parameters.",
                    "false_positive_reason": "",
                    "uncertainty": "",
                    "exploitability_score": {
                        "attacker_control": 25,
                        "reachability": 20,
                        "missing_guard": 20,
                        "impact": 18,
                        "exploit_complexity": 8,
                        "confidence_bonus": 5,
                    },
                }
            ),
            model="fake-model",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            provider="fake",
        )


def test_parse_sarif_alerts_normalizes_semgrep_result():
    payload = read_sarif(FIXTURES / "semgrep_sample.sarif")

    alerts = parse_sarif_alerts(payload)

    assert len(alerts) == 1
    assert alerts[0].tool_name == "Semgrep"
    assert alerts[0].cwe_id == "CWE-89"
    assert alerts[0].location == "app.py:6"


def test_parse_sarif_alerts_normalizes_codeql_cwe_tags():
    payload = read_sarif(FIXTURES / "codeql_sample.sarif")

    alerts = parse_sarif_alerts(payload)

    assert len(alerts) == 1
    assert alerts[0].tool_name == "CodeQL"
    assert alerts[0].rule_id == "py/sql-injection"
    assert alerts[0].cwe_id == "CWE-89"


def test_verify_sarif_file_keeps_alert_uncertain_until_semantic_judge_exists():
    result = verify_sarif_file(
        FIXTURES / "semgrep_sample.sarif",
        source_root=FIXTURES / "sample_project",
        context_lines=1,
    )

    assert len(result.alerts) == 1
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.verdict == Verdict.UNCERTAIN
    assert finding.confidence == Confidence.MEDIUM
    assert finding.severity.value == "high"
    assert finding.file_path == "app.py"
    assert finding.cwe_id == "CWE-89"
    assert "Local code" in finding.evidence_path[0].evidence


def test_preview_sarif_contexts_shows_snippet_before_model_use():
    preview = preview_sarif_contexts(
        FIXTURES / "semgrep_sample.sarif",
        source_root=FIXTURES / "sample_project",
        context_lines=1,
    )

    assert preview["scanner_alert_count"] == 1
    assert preview["contexts"][0]["context"]["display_path"] == "app.py"
    assert preview["contexts"][0]["security_profile"]["name"] == "flask"
    assert "SELECT" in preview["contexts"][0]["context"]["snippet"]


def test_verification_result_serializes_counts():
    result = verify_sarif_file(
        FIXTURES / "semgrep_sample.sarif",
        source_root=FIXTURES / "sample_project",
    )

    payload = result.to_dict()

    assert payload["scanner_alert_count"] == 1
    assert payload["finding_count"] == 1
    assert json.dumps(payload)


def test_verify_sarif_file_with_judge_can_confirm_alert():
    result = asyncio.run(
        verify_sarif_file_with_judge(
            FIXTURES / "semgrep_sample.sarif",
            source_root=FIXTURES / "sample_project",
            completer=FakeCompleter(),
        )
    )

    finding = result.findings[0]

    assert finding.verdict == Verdict.EXPLOITABLE
    assert finding.confidence == Confidence.HIGH
    assert finding.source == 'request.args["q"]'
    assert finding.provider == "fake"
