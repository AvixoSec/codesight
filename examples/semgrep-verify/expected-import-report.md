# CodeSight security report

## Verdict

- Blocked: 0 exploitable issue(s)
- Likely exploitable: 0
- Needs review: 1
- Dismissed: 0

## Findings

### CS-VFY-001: Possible SQL injection

- Verdict: `uncertain`
- Severity: `high`
- Confidence: `medium`
- Exploitability: `0/100`
- Location: `app.py:9`
- CWE: `CWE-89`

#### Evidence path

1. `app.py:9` - Semgrep: User input may reach a SQL query. Local code: query = f"SELECT id, email FROM users WHERE email = '{term}'"

#### Fix

Review the local evidence and either add the missing guard or suppress the scanner alert with a clear reason.

#### Uncertainty

Imported from scanner SARIF. CodeSight collected local context, but judge mode was not enabled, so the alert stays uncertain.
