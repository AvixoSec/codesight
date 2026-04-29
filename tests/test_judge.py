import asyncio
import json

import pytest

from codesight.context import SourceContext
from codesight.findings import Verdict
from codesight.judge import JudgeParseError, finding_from_judge_json, judge_alert
from codesight.profiles import get_profile
from codesight.providers.base import LLMResponse
from codesight.verify import NormalizedAlert


class FakeCompleter:
    def __init__(self, *contents: str) -> None:
        self.contents = list(contents)
        self.calls = 0
        self.messages = []

    async def complete_messages(self, messages, max_tokens=None, temperature=None):
        self.calls += 1
        self.messages.append(messages)
        return LLMResponse(
            content=self.contents.pop(0),
            model="fake-model",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            provider="fake",
        )


def alert() -> NormalizedAlert:
    return NormalizedAlert(
        rule_id="python.sql.CWE-89",
        tool_name="Semgrep",
        title="Possible SQL injection",
        message="User input may reach SQL.",
        level="error",
        uri="app.py",
        start_line=6,
        cwe_id="CWE-89",
    )


def context() -> SourceContext:
    return SourceContext(
        file_path=None,
        display_path="app.py",
        start_line=5,
        end_line=6,
        snippet='   5: term = request.args["q"]\n   6: db.execute(f"SELECT {term}")',
    )


def serious_payload(**overrides):
    payload = {
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
                "location": "app.py:5",
                "evidence": "Request input is read from query string.",
            },
            {
                "location": "app.py:6",
                "evidence": "Input is interpolated into SQL.",
            },
        ],
        "attack_scenario": "Send crafted q to change the query.",
        "impact": "Database read/write through SQL injection.",
        "fix": "Use parameterized queries.",
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
    payload.update(overrides)
    return json.dumps(payload)


def test_finding_from_judge_json_builds_verified_finding():
    finding = finding_from_judge_json(
        serious_payload(),
        alert(),
        context(),
        finding_id="CS-VFY-001",
        provider="fake",
        model="fake-model",
    )

    assert finding.verdict == Verdict.EXPLOITABLE
    assert finding.exploitability.total == 96
    assert finding.source == 'request.args["q"]'
    assert finding.provider == "fake"


def test_judge_alert_runs_skeptic_for_serious_finding():
    skeptical = serious_payload(
        verdict="probably_false_positive",
        confidence="medium",
        false_positive_reason="The visible code is a test-only fixture.",
        uncertainty="No production route is shown.",
    )
    completer = FakeCompleter(serious_payload(), skeptical)

    finding = asyncio.run(
        judge_alert(
            completer,
            alert(),
            context(),
            finding_id="CS-VFY-001",
            skeptic=True,
        )
    )

    assert completer.calls == 2
    assert finding.verdict == Verdict.PROBABLY_FALSE_POSITIVE
    assert "test-only" in finding.false_positive_reason


def test_judge_alert_includes_profile_hints():
    completer = FakeCompleter(serious_payload())

    asyncio.run(
        judge_alert(
            completer,
            alert(),
            context(),
            finding_id="CS-VFY-001",
            profile=get_profile("flask"),
        )
    )

    user_payload = completer.messages[0][1].content

    assert '"security_profile"' in user_payload
    assert '"name": "flask"' in user_payload
    assert "flask.request.args" in user_payload


def test_judge_json_parser_rejects_missing_json():
    with pytest.raises(JudgeParseError):
        finding_from_judge_json(
            "not json",
            alert(),
            context(),
            finding_id="CS-VFY-001",
        )
