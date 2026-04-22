# CodeSight for VS Code

Code analysis and security review inside VS Code.

## Requirements

- Python 3.10+
- `pip install codesight`
- At least one configured provider (or Ollama for offline)

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
| `codesight.provider` | `openai` | LLM provider |
| `codesight.pythonPath` | `python` | Python path with codesight |
| `codesight.outputFormat` | `markdown` | Output format |

## Development

```bash
cd vscode-extension
npm install
npm run compile
```

Press F5 in VS Code to launch the extension in debug mode.
