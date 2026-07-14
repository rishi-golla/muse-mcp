# Muse Agent-First README Design

## Goal

Make the public README communicate Muse as an MCP-native creative planning layer
for coding agents and let a new user reach a working live setup without reading
maintainer material first.

## Reference Influence

Use the public presentation pattern from the referenced ZeroGravity README:
centered identity, concise capability badges, an agent-readable onboarding block,
strong quick start, and an honest high-level roadmap. Do not copy its words,
branding, assets, compatibility claims, or product positioning.

## Information Architecture

1. Centered product identity: `Muse`, a one-sentence statement of the outcome,
   and badges for MCP, live OpenAI, Python, and license only when each has a
   stable project source.
2. A concise outcome section explaining that Muse gives an existing coding agent
   independent creative search and an operational plan; it does not replace the
   agent, a repository workflow, or repository-owned verification.
3. An agent-first onboarding block that a user can paste into a coding agent.
   It tells the agent to read this README, install Muse, run the configuration
   doctor, generate host configuration and project instructions, restart the
   host, and verify the first live call. It must never ask the agent to reveal
   or commit secrets.
4. A manual quick start for PowerShell users: install, required live OpenAI
   environment values, configuration check, host configuration generation,
   project initialization, and the first task to ask an agent.
5. A short usage section that explains the two public modes:
   `normal` for routine planning and `extensive` for high-impact or ambiguous
   tasks. It intentionally does not surface seed, generation, or budget knobs
   to end users.
6. A compact expected-output example showing operational fields, not a giant
   raw JSON dump.
7. Separate reference sections for privacy, live configuration, quality evidence,
   development, contributor guidance, roadmap, and license. Maintainership-only
   fixture CLI and calibration material moves below the public path or links to
   dedicated documents.

## Content Rules

- Every promise must match an existing command, MCP tool, or tested behavior.
- Describe public Muse usage as live OpenAI only. Deterministic facilities are
  maintainer fixtures and must not appear in the public onboarding path.
- State that repo facts and verification remain the calling agent's responsibility.
- Do not claim benchmark superiority; link the benchmarking guide for the
  evidence workflow.
- Avoid lengthy explanations before a user can complete setup.

## Verification

- README links resolve to repository files.
- Every documented executable command exists in `pyproject.toml` or the source.
- README examples avoid real secrets and include Windows/PowerShell-safe syntax.
- Run the repository documentation tests if present plus `python -m pytest -q`
  and `python -m ruff check .` after the README change.

## Non-Goals

- No product UI, website, logo generation, release automation, or protocol
  changes.
- No change to MCP runtime behavior, model pricing, or benchmark methodology.
