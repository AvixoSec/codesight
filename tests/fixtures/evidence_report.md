# CodeSight security report

## Verdict

- Blocked: 1 exploitable issue(s)
- Likely exploitable: 0
- Needs review: 0
- Dismissed: 0

## Findings

### CS-AUTH-001: Tenant isolation bypass

- Verdict: `exploitable`
- Severity: `high`
- Confidence: `high`
- Exploitability: `91/100`
- Location: `api/projects.py:88`
- CWE: `CWE-862`
- OWASP: `A01:2021 Broken Access Control`

#### Evidence

- Source: `request.path_params["org_id"]`
- Sink: `Project.query.filter_by(org_id=org_id)`
- Missing guard: No membership check before project lookup.
- Impact: Cross-tenant project exposure.

#### Evidence path

1. `api/projects.py:82` - The route accepts org_id from the request path.
2. `api/projects.py:88` - The query trusts org_id before checking membership.

#### Attack scenario

A user can request another org id and read its projects.

#### Fix

Check membership before loading projects for the org.

#### Uncertainty

Route middleware was not included in the inspected context.
