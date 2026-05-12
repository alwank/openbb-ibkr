# Contributing

Contributions are welcome! Here's how to get started.

## Setup

```bash
git clone https://github.com/alwanalkautsar/openbb-ibkr.git
cd openbb-ibkr
python -m venv venv
source venv/bin/activate
pip install -e .[dev]
```

## Running Tests

```bash
pytest tests/ -v
```

Tests mock the IBKR client — no live TWS/IB Gateway connection is needed.

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting:

```bash
ruff check .
```

## Pull Requests

1. Fork the repo and create a feature branch
2. Make your changes
3. Ensure tests pass and linting is clean
4. Open a PR with a clear description of the change

## Reporting Issues

Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (Python version, OpenBB version, TWS/IB Gateway version)
