import json
import re
import warnings
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


class SarifParseError(ValueError):
    """Raised in strict mode when parse_findings encounters unparseable sections."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(
            f"SARIF parser rejected {len(errors)} section(s): "
            + "; ".join(errors[:5])
            + (" ..." if len(errors) > 5 else "")
        )


SEVERITY_TO_SARIF = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
}

# Anchored so narrative [HIGH] text mid-section cannot match.
# [-—] accepts both hyphen and em-dash (LLMs emit either).
_HEADER_RE = re.compile(
    r"^\s*\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?\s*(.{1,500}?)(?:\s*[-—]\s*(CWE-\d{1,6}))?\s*$"
)


def parse_findings(
    content: str,
    file_path: str,
    *,
    strict: bool = False,
) -> list[Finding]:
    # strict=True raises SarifParseError with every rejected section.
    # strict=False warns and returns what parsed (legacy behavior).
    findings: list[Finding] = []
    errors: list[str] = []
    blocks = re.split(r"###\s+", content)
    for idx, block in enumerate(blocks[1:], start=1):
        lines = block.strip().split("\n")
        if not lines:
            errors.append(f"section {idx}: empty block")
            continue
        header = lines[0].strip()
        if not header:
            errors.append(f"section {idx}: empty header line")
            continue

        # Non-finding sections (Summary, False Positives) get skipped without error.
        if not re.match(r"^\s*\[?(CRITICAL|HIGH|MEDIUM|LOW)\b", header, re.IGNORECASE):
            continue

        sev_match = _HEADER_RE.match(header)
        if not sev_match:
            errors.append(
                f"section {idx}: header looks like a finding but did not match: {header!r}"
            )
            continue

        severity = sev_match.group(1).upper()
        title = sev_match.group(2).strip()
        cwe_id = sev_match.group(3)

        body = "\n".join(lines[1:])
        line_match = re.search(r"(?:line|ln|:)\s*(\d{1,9})", body, re.IGNORECASE)
        line_num = int(line_match.group(1)) if line_match else 1
        fix_match = re.search(r"\*\*Fix:\*\*\s*(.{1,4000}?)(?:\n\n|\Z)", body, re.DOTALL)
        fix = fix_match.group(1).strip() if fix_match else ""
        desc_match = re.search(r"\*\*Description:\*\*\s*(.{1,4000}?)(?:\n\*\*|\Z)", body, re.DOTALL)
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

    if errors:
        if strict:
            raise SarifParseError(errors)
        warnings.warn(
            f"SARIF parser skipped {len(errors)} section(s); "
            "re-run with strict=True to fail loudly. "
            f"First issue: {errors[0]}",
            stacklevel=2,
        )
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
