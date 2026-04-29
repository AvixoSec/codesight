# Semgrep Verify Demo

This fixture shows the new CodeSight path:

1. Semgrep finds a suspicious line.
2. CodeSight opens the local source file.
3. CodeSight writes a structured finding instead of pretending the alert is
   already proven.

Preview the context first:

```bash
codesight verify examples/semgrep-verify/semgrep.sarif \
  --source examples/semgrep-verify/project \
  --profile flask \
  --preview-context
```

Run the conservative import:

```bash
codesight verify examples/semgrep-verify/semgrep.sarif \
  --source examples/semgrep-verify/project \
  --profile flask \
  --output markdown
```

Plain import keeps the alert as `uncertain`. That is the expected result.

Checked-in artifacts:

- `sample-preview-context.json`
- `expected-import-report.md`
- `expected-import.sarif`
- `proof-manifest.json`

Run semantic judge mode with your configured provider:

```bash
codesight verify examples/semgrep-verify/semgrep.sarif \
  --source examples/semgrep-verify/project \
  --judge \
  --skeptic \
  --profile flask \
  --provider openai \
  --output markdown
```

Judge mode asks for source, sink, missing guard, evidence path, fix, and
uncertainty. Skeptic mode can downgrade serious findings when the evidence is
thin.
