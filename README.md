# CodeSight

**Token-optimized, AI-powered defensive security and code analysis CLI for modern development teams.**

CodeSight integrates with leading LLM providers — OpenAI, Anthropic (Claude), and Google Vertex AI (Gemini) — to deliver automated code reviews, **zero-day vulnerability detection**, semantic bug analysis, documentation generation, and refactoring suggestions directly from your terminal. Built with a context-compression architecture that reduces API token usage by up to **95%**.

![CI](https://github.com/AvixoSec/codesight/actions/workflows/ci.yml/badge.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

## The Problem

Manual code reviews are slow, inconsistent, and don't scale. Developers spend **~6 hours per week** reviewing pull requests, yet critical bugs still slip through. Static analysis tools catch syntax issues but miss **semantic** problems — logic errors, race conditions, security vulnerabilities, and architectural anti-patterns.

Meanwhile, existing AI coding assistants feed massive, unoptimized codebases into LLM context windows (26K–47K tokens per query), causing latency, high costs, and token waste.

## The Solution

CodeSight uses large language models to perform deep semantic analysis of your code with a **token-optimized architecture**:

- **Review** — comprehensive code review with severity-tagged issues
- **Bug Detection** — find logic errors, race conditions, resource leaks, zero-day patterns
- **Security Audit** — detect SQL injection, hardcoded secrets, auth flaws, and more
- **Documentation** — auto-generate docstrings and module docs
- **Explain** — plain-language breakdown of complex code
- **Refactor** — actionable refactoring suggestions with before/after

## Token Efficiency Architecture

CodeSight is engineered for **minimal API token consumption**:

```
Traditional approach:  Raw source → LLM context    = 26,000–47,000 tokens/query
CodeSight (code maps): Pre-compiled map → LLM      =  3,000– 5,000 tokens/query
CodeSight (--wiki):    Targeted index → LLM         =    200–   350 tokens/query
```

Pre-compiled code maps extract semantic structure (functions, classes, dependencies, call graphs) and send a compressed representation to the LLM instead of raw source files. This achieves **up to 95% context compression** while retaining full analytical capability — making AI-powered security auditing accessible and cost-effective at scale.

## Quick Start

```bash
# Install
pip install codesight

# Configure your provider
codesight config

# Run a review
codesight review src/main.py

# Detect bugs
codesight bugs lib/parser.py

# Generate docs
codesight docs utils/helpers.py
```

## Provider Support

| Provider | Models | Setup |
|----------|--------|-------|
| **OpenAI** | GPT-5.4, GPT-5.3-Codex | `OPENAI_API_KEY` |
| **Anthropic** | Claude Opus 4.6, Claude Sonnet 4.6 | `ANTHROPIC_API_KEY` |
| **Google Vertex AI** | Gemini 3.1 Pro, Gemini 3.1 Flash | `GOOGLE_CLOUD_PROJECT` + ADC |

## Configuration

CodeSight stores config in `~/.codesight/config.json`. You can configure it interactively:

```bash
codesight config
```

Or set environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export CODESIGHT_MODEL="gpt-5.4"
codesight review my_file.py
```

Switch providers on the fly:

```bash
codesight review my_file.py --provider anthropic
codesight bugs my_file.py --provider google
codesight explain my_file.py --provider openai
```

## Architecture

```
codesight/
├── __init__.py
├── __main__.py
├── cli.py
├── config.py
├── analyzer.py
└── providers/
    ├── base.py
    ├── factory.py
    ├── openai_provider.py
    ├── anthropic_provider.py
    └── google_provider.py
```

## Development

```bash
git clone https://github.com/AvixoSec/codesight.git
cd codesight
pip install -e ".[dev]"
pytest tests/ -v
ruff check codesight/
```

## Roadmap

- [ ] Git diff / PR integration (review only changed lines)
- [ ] VS Code extension
- [ ] Streaming output for large files
- [ ] Custom prompt templates
- [ ] Cost tracking dashboard
- [ ] Support for additional Gemini models (Gemini 3.1 Flash)
- [ ] Prompt caching for reduced latency and cost
- [ ] Intelligent model routing (simple tasks → Haiku/Flash, complex → Opus/GPT-5.4-Cyber)
- [ ] Batch analysis API for CI/CD pipelines

## Security Focus

CodeSight is a **defensive cybersecurity tool**. It helps developers and open-source maintainers identify vulnerabilities before they reach production:

- SQL injection and command injection patterns
- Hardcoded secrets and API key exposure
- Authentication and authorization flaws
- Race conditions and TOCTOU vulnerabilities
- Memory safety issues and resource leaks
- Cryptographic misuse (weak hashing, insufficient entropy)

Designed for the open-source maintainer community — helping bridge the gap between AI-generated code volume and human review capacity.

## License

MIT — see [LICENSE](LICENSE).
