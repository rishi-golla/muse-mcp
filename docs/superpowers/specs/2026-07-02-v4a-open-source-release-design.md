# V4-A Open Source Release Foundation Design

## Goal

Prepare muse for a credible public open-source release. This slice should make the repository understandable, installable, and safe to evaluate by someone who is not already part of the project.

## Recommended Approach

Ship the minimum public-release foundation now: license, contribution and security docs, issue/PR templates, example environment files, pricing example, package metadata, and a README first-run path. This should not add new engine behavior or change the MCP contract.

This is better than polishing live quality first because open-source users need trust and setup clarity before they can help validate quality. It is also better than building hosted/commercial features now because the core middleware still needs public credibility.

## Scope

V4-A includes:

- MIT license and matching package metadata.
- `CONTRIBUTING.md`, `SECURITY.md`, and `CODE_OF_CONDUCT.md`.
- `.github` issue templates and PR template.
- `.env.example` with safe placeholders for OpenAI, search providers, runtime defaults, and dogfood checks.
- `openai-pricing.example.json` with the current pricing-table schema and non-secret sample model prices.
- README open-source quickstart that starts with deterministic no-key MCP smoke and dogfood quality checks, then explains live setup.
- Tests that enforce public-readiness files, metadata, examples, and no obvious committed secrets.

## Non-Goals

- No package publishing automation.
- No hosted SaaS or paid tier.
- No live provider quality tuning.
- No default behavior change.
- No claim that deterministic output is production-quality creativity.

## License Choice

Use MIT for the core. It maximizes adoption and lowers friction for agent builders and developer-tool teams. Monetization remains possible later through hosted workflows, team traces, policy packs, managed provider/search setup, and enterprise support.

## Testing

Tests should prove:

- Required public files exist.
- `pyproject.toml` exposes license, classifiers, and repository URLs.
- `.env.example` includes expected variables and contains no real-looking secrets.
- `openai-pricing.example.json` parses with `PricingTable`.
- README mentions deterministic install/smoke, dogfood quality, MCP, and live setup.
- GitHub templates exist and mention quality/test evidence.

## Documentation

README should make the first-run path copy-pasteable:

1. `python -m pip install -e ".[dev]"`
2. `muse-mcp-smoke ... --provider-mode deterministic`
3. `muse-dogfood-quality ... --provider-mode deterministic`
4. optional live env setup using `.env.example` and `openai-pricing.example.json`

The docs should preserve the product positioning: open-source middleware for AI coding agents, not a CLI replacement.
