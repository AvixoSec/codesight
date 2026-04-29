# CodeSight

Security CLI for scanner alerts, code review, and CI reports.

CodeSight started as a direct code scanner. Now the main lane is stronger:
take alerts from Semgrep, CodeQL, or another SARIF tool, open the matching
source files, collect evidence, and decide what deserves attention.

It still scans files and folders directly. The bigger value is verification:
less noise, clearer proof, and reports that can go back into CI.

[![PyPI](https://img.shields.io/pypi/v/codesight?color=8b5cf6)](https://pypi.org/project/codesight/)
[![CI](https://github.com/AvixoSec/codesight/actions/workflows/ci.yml/badge.svg)](https://github.com/AvixoSec/codesight/actions)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-codesight.is--a.dev-c084fc)](https://codesight.is-a.dev)

## What It Is Now

CodeSight has three useful paths:

- guided terminal UI for people who do not want to remember commands
- direct scan for one file, a folder, or a git diff
- SARIF verify for scanner alerts that need real source context

The verify path is the important one.

Scanners are good at breadth. They find suspicious lines fast. CodeSight checks
what is behind the alert:

- where the input comes from
- which sink or trust boundary it reaches
- what guard is missing
- why the verdict is exploitable, likely exploitable, uncertain, or dismissed
- what fix would actually reduce risk

No evidence, no confident verdict.

## Quick Start

Guided UI:

```bash
pip install codesight
codesight
```

From the repo:

```bash
python -m codesight
```

Pick a path in the menu:

- scan a file
- scan a folder
- review a git diff
- verify a SARIF file
- build a proof bundle
- run judge and skeptic mode

Direct commands still work:

```bash
codesight security src/app.py
codesight scan src --task security --output sarif > codesight.sarif
codesight diff --task security
```

Local model:

```bash
ollama serve
codesight security src/app.py --provider ollama
```

## Verify Scanner Alerts

Run your scanner first:

```bash
semgrep scan --config auto --sarif > semgrep.sarif
```

Then let CodeSight import the alert and attach local source context:

```bash
codesight verify semgrep.sarif --source . --output markdown
```

Useful verify modes:

```bash
codesight verify semgrep.sarif --source . --preview-context
codesight verify semgrep.sarif --source . --fail-on likely_exploitable
codesight verify semgrep.sarif --source . --judge --skeptic --profile auto --provider openai
codesight verify semgrep.sarif --source . --artifact-dir .codesight-proof
```

Plain import mode is conservative. It keeps scanner alerts as `uncertain`.
Judge mode can promote, downgrade, or dismiss alerts. Skeptic mode checks
serious verdicts again before CI has to trust them.

Typical summary:

```text
Blocked: 0 exploitable issue(s)
Likely exploitable: 0
Needs review: 42
Dismissed: 0
```

Try the local fixture:

```bash
codesight verify examples/semgrep-verify/semgrep.sarif \
  --source examples/semgrep-verify/project \
  --output markdown
```

Framework fixtures are in `examples/framework-profiles`.

## Evidence Format

CodeSight uses structured verdicts:

- `exploitable`
- `likely_exploitable`
- `uncertain`
- `probably_false_positive`
- `not_exploitable`

Example:

```md
### CS-AUTH-001: Tenant isolation bypass

- Verdict: `exploitable`
- Severity: `high`
- Confidence: `high`
- Exploitability: `91/100`
- Location: `api/projects.py:88`
- CWE: `CWE-862`

#### Evidence

- Source: `request.path_params["org_id"]`
- Sink: `Project.query.filter_by(org_id=org_id)`
- Missing guard: no membership check before project lookup

#### Evidence path

1. `api/projects.py:82` - route accepts org_id from the request path
2. `api/projects.py:88` - query trusts org_id before checking membership
```

## Commands

Core:

- `codesight`
- `codesight ui`
- `codesight security <file>`
- `codesight scan <dir> --task security`
- `codesight diff --task security`
- `codesight verify <scanner.sarif> --source .`
- `codesight benchmark`

Secondary:

- `codesight review <file>`
- `codesight bugs <file>`
- `codesight docs <file>`
- `codesight explain <file>`
- `codesight refactor <file>`

## Providers

- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Google Vertex AI: `GOOGLE_CLOUD_PROJECT` and ADC
- Ollama: local `ollama serve`
- OpenAI-compatible: custom label from `codesight config`

OpenAI-compatible presets include OpenRouter, Groq, Together AI, Mistral, xAI,
Fireworks, DeepSeek, Perplexity, Cerebras, Cohere, and Azure AI Foundry.

## Output

```bash
codesight security app.py --output markdown
codesight security app.py --output json
codesight security app.py --output sarif > codesight.sarif
codesight verify semgrep.sarif --source . --output sarif > verified.sarif
```

SARIF can be uploaded to GitHub code scanning.

## Privacy

CodeSight does not need a hosted account or repo connection.

- Ollama keeps analysis local.
- BYOK providers use your own key.
- Project config cannot set `api_key`, `base_url`, or `default_provider`.
- Project config discovery is restricted to `$HOME`.
- Large files can be compressed into code maps before prompting.

Cloud providers still receive the selected code context. Use Ollama when code
must stay on the machine.

## Benchmarks

The built-in benchmark is a smoke test: 10 vulnerable Python cases and 2 clean
false-positive traps. It is useful for checking provider behavior and prompt
drift. It is not a public claim that CodeSight is better than another scanner.

```bash
codesight benchmark --models gpt-5.4 llama3
codesight benchmark --json > benchmark-results.json
```

Public benchmark claims need the exact cases, commands, expected verdicts, raw
results, model, provider, and run date.

## GitHub Action

Verify scanner SARIF:

```yaml
- run: |
    python -m pip install semgrep
    semgrep scan --config auto --sarif --output semgrep.sarif

- uses: AvixoSec/codesight@v0.3.1
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

Direct scan:

```yaml
- uses: AvixoSec/codesight@v0.3.1
  with:
    provider: openai
    api-key: ${{ secrets.OPENAI_API_KEY }}
    task: security
    path: .
    output: sarif
```

## Development

```bash
git clone https://github.com/AvixoSec/codesight.git
cd codesight
pip install -e ".[dev]"
pytest tests -v
ruff check .
```

## License

MIT. See [LICENSE](LICENSE).
