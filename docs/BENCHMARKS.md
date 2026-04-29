# Benchmarks

This page stays conservative on purpose.

The current benchmark is a smoke test. It checks that providers respond, that
CWE extraction still works, and that clean examples do not get flagged too
easily. It is not a public comparison against Semgrep, CodeQL, or any other
scanner.

## Current Dataset

`codesight benchmark` runs 10 vulnerable Python cases and 2 clean traps:

- SQL injection: CWE-89
- Reflected XSS: CWE-79
- Path traversal: CWE-22
- Hardcoded secret: CWE-798
- Command injection: CWE-78
- Auth bypass: CWE-287
- SSRF: CWE-918
- Insecure deserialization: CWE-502
- Tenant auth bypass: CWE-862
- AI-agent unvalidated tool call: CWE-20
- Clean parameterized query: none expected
- Clean safe path join: none expected

Run it:

```bash
codesight benchmark --models gpt-5.4 llama3
codesight benchmark --json > benchmark-results.json
```

## What It Measures

- detection rate
- true positives
- false negatives
- false positives on clean cases
- clean-case false-positive rate
- response time
- token usage
- provider errors

## What It Does Not Measure Yet

- exploitability verdict quality
- source-to-sink evidence quality
- SARIF alert verification
- framework-specific behavior
- multi-file context
- repeatability across multiple runs

## Next Dataset

The v1 benchmark needs:

- more clean traps
- AI-generated code mistakes
- auth and tenant-isolation bugs
- privacy and data-flow cases
- expected evidence paths
- expected verdicts
- Semgrep and CodeQL SARIF fixtures
- checked-in verified reports

Only then should the docs make public comparison claims.

## Rule For Claims

Any benchmark claim must point to:

1. exact cases
2. command used
3. model and provider
4. expected verdicts
5. raw result file
6. run date
