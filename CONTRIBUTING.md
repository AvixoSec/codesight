# Contributing

Thanks for helping CodeSight. Keep changes small, tested, and easy to review.

## Setup

```bash
git clone https://github.com/AvixoSec/codesight.git
cd codesight
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Tests

```bash
pytest tests -v
python -m ruff check codesight tests
python -m mypy codesight/ --ignore-missing-imports
```

## Style

Use [Ruff](https://docs.astral.sh/ruff/) for linting. Match the existing code
before adding new abstractions.

## Pull Requests

1. Fork the repository
2. Create a focused branch (`git checkout -b feat/my-feature`)
3. Commit your changes with clear messages
4. Push to your fork and open a pull request

Good pull requests include:

- what changed
- why it matters
- how you tested it
- screenshots or sample output when the UI or docs change

## Reporting Issues

Use GitHub Issues. Please include:

- Python version
- OS
- Minimal reproduction steps
- Full error traceback
