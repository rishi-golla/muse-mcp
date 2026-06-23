# Creativity Layer

A research prototype for testing whether evolutionary creative search produces ideas
that humans judge as simultaneously more original and useful than strong prompting.

The first implementation milestone is intentionally deterministic. It validates the
core orchestration, data contracts, budget accounting, selection behavior, and trace
reproducibility before paid model and search providers are introduced.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```
