import json

from codesight.findings import EvidencePathStep, ExploitabilityScore, VerifiedFinding
from codesight.formatters import format_json_report, format_markdown_report, summarize_findings


def finding():
    return VerifiedFinding(
        id="CS-AUTH-001",
        title="Tenant isolation bypass",
        verdict="exploitable",
        severity="high",
        confidence="high",
        file_path="api/projects.py",
        start_line=88,
        cwe_id="CWE-862",
        owasp_category="A01:2021 Broken Access Control",
        exploitability=ExploitabilityScore(
            attacker_control=25,
            reachability=18,
            missing_guard=20,
            impact=18,
            exploit_complexity=6,
            confidence_bonus=4,
        ),
        source='request.path_params["org_id"]',
        sink="Project.query.filter_by(org_id=org_id)",
        missing_guard="No membership check before project lookup.",
        evidence_path=[
            EvidencePathStep(
                location="api/projects.py:82",
                evidence="The route accepts org_id from the request path.",
            ),
            EvidencePathStep(
                location="api/projects.py:88",
                evidence="The query trusts org_id before checking membership.",
            ),
        ],
        attack_scenario="A user can request another org id and read its projects.",
        impact="Cross-tenant project exposure.",
        fix="Check membership before loading projects for the org.",
        uncertainty="Route middleware was not included in the inspected context.",
    )


def test_summarize_findings_counts_verdicts():
    summary = summarize_findings([finding()])

    assert summary["exploitable"] == 1
    assert summary["uncertain"] == 0


def test_markdown_report_renders_evidence_first():
    report = format_markdown_report([finding()])

    assert "Blocked: 1 exploitable issue" in report
    assert "### CS-AUTH-001: Tenant isolation bypass" in report
    assert 'Source: `request.path_params["org_id"]`' in report
    assert "#### Evidence path" in report
    assert "Route middleware was not included" in report


def test_json_report_is_stable():
    payload = json.loads(format_json_report([finding()]))

    assert payload["summary"]["exploitable"] == 1
    assert payload["findings"][0]["id"] == "CS-AUTH-001"
    assert payload["findings"][0]["exploitability_score"]["total"] == 91
