import json
import re
from dataclasses import dataclass


@dataclass
class Finding:
    severity: str
    title: str
    cwe_id: str | None
    line: int
    file_path: str
    description: str
    fix: str


SEVERITY_TO_SARIF = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
}


def parse_findings(content: str, file_path: str) -> list[Finding]:
    findings = []
    blocks = re.split(r"###\s+", content)
    for block in blocks[1:]:
        lines = block.strip().split("\n")
        if not lines:
            continue
        header = lines[0]
        sev_pat = r"\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?\s*(.+?)(?:\s*[-—]\s*(CWE-\d+))?$"
        sev_match = re.match(sev_pat, header)
        if not sev_match:
            continue
        severity = sev_match.group(1)
        title = sev_match.group(2).strip()
        cwe_id = sev_match.group(3)
        body = "\n".join(lines[1:])
        line_match = re.search(r"(?:line|ln|:)\s*(\d+)", body, re.IGNORECASE)
        line_num = int(line_match.group(1)) if line_match else 1
        fix_match = re.search(r"\*\*Fix:\*\*\s*(.*?)(?:\n\n|\Z)", body, re.DOTALL)
        fix = fix_match.group(1).strip() if fix_match else ""
        desc_match = re.search(r"\*\*Description:\*\*\s*(.*?)(?:\n\*\*|\Z)", body, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else title

        findings.append(Finding(
            severity=severity,
            title=title,
            cwe_id=cwe_id,
            line=line_num,
            file_path=file_path,
            description=description,
            fix=fix,
        ))
    return findings


def to_sarif(findings: list[Finding]) -> dict:
    rules = []
    results = []
    rule_ids = {}

    for i, f in enumerate(findings):
        rule_id = f.cwe_id or f"CS{i+1:03d}"
        if rule_id not in rule_ids:
            rule_ids[rule_id] = len(rules)
            rule = {
                "id": rule_id,
                "shortDescription": {"text": f.title},
                "helpUri": f"https://cwe.mitre.org/data/definitions/{f.cwe_id.split('-')[1]}.html"
                if f.cwe_id else "https://codesight.is-a.dev",
            }
            rules.append(rule)

        results.append({
            "ruleId": rule_id,
            "ruleIndex": rule_ids[rule_id],
            "level": SEVERITY_TO_SARIF.get(f.severity, "warning"),
            "message": {"text": f"{f.description}\n\nFix: {f.fix}" if f.fix else f.description},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.file_path},
                    "region": {"startLine": f.line},
                }
            }],
        })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "CodeSight",
                    "informationUri": "https://github.com/AvixoSec/codesight",
                    "rules": rules,
                }
            },
            "results": results,
        }],
    }


def to_sarif_json(findings: list[Finding], indent: int = 2) -> str:
    return json.dumps(to_sarif(findings), indent=indent)
