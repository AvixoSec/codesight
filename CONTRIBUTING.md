# Contributing to CodeSight

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/AvixoSec/codesight.git
cd codesight
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting:

```bash
ruff check codesight/
ruff format codesight/
```

## Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit your changes with clear messages
4. Push to your fork and open a Pull Request

## Reporting Issues

Use GitHub Issues. Please include:
- Python version
- OS
- Minimal reproduction steps
- Full error traceback
