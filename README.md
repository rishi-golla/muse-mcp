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

## Deterministic research-spine demo

```powershell
creativity-layer "Invent a calmer way for distributed teams to make decisions" `
  --seed-count 4 `
  --finalist-count 3 `
  --generations 1 `
  --trace-dir .traces
```

The command prints a JSON summary containing the resolved absolute trace path and
writes the complete structured run trace to `.traces/<run-id>.json`. Exit status `0`
means at least one scored finalist is usable, including a valid frontier returned
after budget exhaustion. Provider failures, empty frontiers, and trace-write failures
return status `1`; invalid command input returns status `2`.

This milestone uses deterministic local providers; it makes no external model or
search calls.
