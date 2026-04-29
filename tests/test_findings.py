import json

import pytest

from codesight.findings import (
    Confidence,
    EvidencePathStep,
    ExploitabilityScore,
    Verdict,
    VerifiedFinding,
)


def sample_finding(**overrides):
    data = {
        "id": "CS-AUTH-001",
        "title": "Tenant isolation bypass",
        "verdict": "exploitable",
        "severity": "high",
        "confidence": "high",
        "file_path": "api/projects.py",
        "start_line": 88,
        "cwe_id": "CWE-862",
        "owasp_category": "A01:2021 Broken Access Control",
        "exploitability": ExploitabilityScore(
            attacker_control=25,
            reachability=18,
            missing_guard=20,
            impact=18,
            exploit_complexity=6,
            confidence_bonus=4,
        ),
        "source": 'request.path_params["org_id"]',
        "sink": "Project.query.filter_by(org_id=org_id)",
        "missing_guard": "No membership check before project lookup.",
        "evidence_path": [
            EvidencePathStep(
                location="api/projects.py:82",
                evidence="The route accepts org_id from the request path.",
            ),
            EvidencePathStep(
                location="api/projects.py:88",
                evidence="The query trusts org_id before checking membership.",
            ),
        ],
        "attack_scenario": "A user can request another org id and read its projects.",
        "impact": "Cross-tenant project exposure.",
        "fix": "Check membership before loading projects for the org.",
        "uncertainty": "Route middleware was not included in the inspected context.",
    }
    data.update(overrides)
    return VerifiedFinding(**data)


def test_verified_finding_serializes_evidence():
    finding = sample_finding()

    payload = finding.to_dict()

    assert payload["verdict"] == "exploitable"
    assert payload["exploitability_score"]["total"] == 91
    assert payload["evidence_path"][0]["location"] == "api/projects.py:82"
    assert json.loads(finding.to_json())["id"] == "CS-AUTH-001"


def test_exploitable_without_evidence_downgrades_to_uncertain():
    finding = sample_finding(evidence_path=[])

    assert finding.verdict == Verdict.UNCERTAIN
    assert finding.confidence == Confidence.LOW
    assert "No evidence path" in finding.uncertainty


def test_high_confidence_without_line_downgrades_to_medium():
    finding = sample_finding(start_line=None)

    assert finding.confidence == Confidence.MEDIUM


def test_missing_source_sink_or_guard_downgrades_confidence():
    finding = sample_finding(source="", sink="")

    assert finding.confidence == Confidence.MEDIUM
    assert "incomplete" in finding.uncertainty


def test_false_positive_reason_dismisses_serious_finding():
    finding = sample_finding(false_positive_reason="The route is test-only.")

    assert finding.verdict == Verdict.PROBABLY_FALSE_POSITIVE
    assert finding.confidence == Confidence.MEDIUM


def test_score_rejects_out_of_range_component():
    with pytest.raises(ValueError):
        ExploitabilityScore(attacker_control=26)
