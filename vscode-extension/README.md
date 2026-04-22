# CodeSight for VS Code

Code analysis and security review inside VS Code. Backed by the `codesight` CLI, with support for OpenAI, Anthropic, Google Vertex AI, Ollama (offline), and any OpenAI-compatible endpoint (OpenRouter, Groq, Azure AI Foundry, and more).

## Requirements

- Python 3.10+
- `pip install codesight`
- At least one configured provider (run `codesight config`, or use Ollama for offline)

## Features

- Right-click any file → CodeSight → Review / Bugs / Security / Docs / Explain / Refactor
- Right-click a folder → CodeSight: Scan Directory
- Results open in a side panel
- Configurable provider and output format

## Commands

| Command | Description |
|---------|-------------|
| `CodeSight: Review File` | Full code review |
| `CodeSight: Find Bugs` | Bug detection |
| `CodeSight: Security Audit` | Security scan with CWE/OWASP |
| `CodeSight: Generate Docs` | Auto-generate documentation |
| `CodeSight: Explain Code` | Plain-language explanation |
| `CodeSight: Refactor Suggestions` | Refactoring with diffs |
| `CodeSight: Scan Directory` | Scan entire folder |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `codesight.provider` | `openai` | LLM provider (or any custom label from `~/.codesight/config.json`) |
| `codesight.pythonPath` | `python` | Python path with codesight |
| `codesight.outputFormat` | `markdown` | Output format |

Custom OpenAI-compatible providers (OpenRouter, Groq, Together, Mistral, xAI, Fireworks, DeepSeek, Perplexity, Cerebras, Cohere, Azure AI Foundry) are configured via the CLI: `codesight config`. The label you pick there (e.g. `openrouter`) can be used as the `codesight.provider` setting.

## Development

```bash
cd vscode-extension
npm install
npm run compile
```

Press F5 in VS Code to launch the extension in debug mode.
