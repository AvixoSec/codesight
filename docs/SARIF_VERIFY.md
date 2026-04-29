# SARIF Verify

`codesight verify` takes scanner SARIF, finds the matching source, and turns
each alert into a CodeSight finding with context and a clear verdict.

Use the guided UI when you do not want to remember flags:

```bash
codesight
```

Choose `verify SARIF`, then pick the SARIF file, source root, output, profile,
artifact folder, and judge options.

## Basic Flow

```bash
semgrep scan --config auto --sarif > semgrep.sarif
codesight verify semgrep.sarif --source . --output markdown
```

Other useful modes:

```bash
codesight verify semgrep.sarif --source . --output json
codesight verify semgrep.sarif --source . --output sarif > verified.sarif
codesight verify semgrep.sarif --source . --preview-context
codesight verify semgrep.sarif --source . --fail-on likely_exploitable
codesight verify semgrep.sarif --source . --judge --skeptic --profile auto --provider openai
codesight verify semgrep.sarif --source . --artifact-dir .codesight-proof
```

## What It Keeps

CodeSight reads SARIF 2.1.0 style `runs[].results[]` and keeps the scanner
fields that matter:

- rule id
- tool name
- message
- level
- file path
- line number
- CWE tags when present

Then it adds local source context around the alert.

## Verdicts

- `exploitable` - enough evidence to block
- `likely_exploitable` - strong evidence, small uncertainty
- `uncertain` - imported or partially checked, needs review
- `probably_false_positive` - probably safe, with a reason
- `not_exploitable` - dismissed with evidence

Plain import mode only returns `uncertain`. That is intentional. A scanner alert
is not proof by itself.

Judge mode can change the verdict. Skeptic mode reviews serious judge findings
again and can downgrade weak evidence.

## Profiles

Profiles give the judge framework hints. They do not replace evidence.

Supported values:

- `generic`
- `flask`
- `fastapi`
- `express`
- `django`
- `github-actions`
- `ai-agent`

Default is `auto`.

## Path Safety

SARIF paths are resolved under the source root.

CodeSight rejects:

- parent-directory escapes
- absolute paths outside the source root
- unsupported URI schemes
- remote file URI hosts

Missing files are still reported, but confidence drops because local context is
not available.

Use preview mode before judge mode when you want to see exactly what context
would be sent to the configured provider.

## CI Threshold

`fail-on` controls the exit code:

- `exploitable` - fail only on confirmed exploitable findings
- `likely_exploitable` - fail on confirmed and likely exploitable findings
- `uncertain` - also fail on imported or partially verified findings
- `never` - always exit zero after writing the report

Default is `exploitable`.

## Local Demo

```bash
codesight verify examples/semgrep-verify/semgrep.sarif \
  --source examples/semgrep-verify/project \
  --profile flask \
  --output markdown
```

More fixtures live in `examples/framework-profiles`:

- FastAPI tenant boundary
- Express path traversal
- AI-agent tool validation

## GitHub Action

```yaml
- run: |
    python -m pip install semgrep
    semgrep scan --config auto --sarif --output semgrep.sarif

- uses: your-org/codesight@v0.3.0
  with:
    mode: verify
    path: .
    sarif-input: semgrep.sarif
    output: sarif
    fail-on: exploitable
    judge: "true"
    skeptic: "true"
    profile: auto
```
