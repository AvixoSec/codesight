from codesight.findings import EvidencePathStep, ExploitabilityScore, VerifiedFinding
from codesight.sarif import Finding, to_sarif


def test_to_sarif_keeps_legacy_findings():
    sarif = to_sarif(
        [
            Finding(
                severity="HIGH",
                title="SQL injection",
                cwe_id="CWE-89",
                line=12,
                file_path="app.py",
                description="Untrusted input reaches SQL.",
                fix="Use parameters.",
            )
        ]
    )

    result = sarif["runs"][0]["results"][0]

    assert result["ruleId"] == "CWE-89"
    assert result["level"] == "error"
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 12


def test_to_sarif_emits_verified_finding_properties():
    finding = VerifiedFinding(
        id="CS-AUTH-001",
        title="Tenant isolation bypass",
        verdict="exploitable",
        severity="high",
        confidence="high",
        file_path="api/projects.py",
        start_line=88,
        cwe_id="CWE-862",
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
                location="api/projects.py:88",
                evidence="The query trusts org_id before checking membership.",
            )
        ],
        fix="Check membership before loading projects.",
    )

    sarif = to_sarif([finding])
    result = sarif["runs"][0]["results"][0]

    assert result["ruleId"] == "CWE-862"
    assert result["level"] == "error"
    assert result["properties"]["verdict"] == "exploitable"
    assert result["properties"]["exploitabilityScore"]["total"] == 91
    assert result["properties"]["source"] == 'request.path_params["org_id"]'
