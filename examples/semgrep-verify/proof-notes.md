# Proof Notes

This example is intentionally small and reproducible.

What it proves:

- CodeSight can read scanner SARIF.
- It resolves alert paths under the source root.
- It can preview provider-bound context before running a judge.
- It adds Flask profile hints.
- Plain import mode stays conservative and reports `uncertain`.

What it does not prove:

- Real false-positive reduction.
- Real exploitability confirmation by a live model.
- Performance on a larger repo.

Next artifact to add after a provider key works:

```bash
codesight verify examples/semgrep-verify/semgrep.sarif \
  --source examples/semgrep-verify/project \
  --profile flask \
  --judge \
  --skeptic \
  --provider openai \
  --output markdown > examples/semgrep-verify/judge-report.md
```
