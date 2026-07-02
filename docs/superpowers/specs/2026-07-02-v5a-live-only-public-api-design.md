# V5-A Live-Only Public API Design

## Goal

Make Muse's public MCP onboarding live-only. A normal user should connect Muse
to an agent host, set OpenAI configuration, and call `muse_plan` without seeing
or selecting the deterministic fixture provider.

## Decision

The deterministic provider remains in the codebase as an internal test fixture
for no-network CI, protocol checks, and regression coverage. It is not a public
product mode. Public MCP and smoke entrypoints reject `deterministic` unless the
caller explicitly sets `MUSE_ENABLE_TEST_PROVIDER=1`.

This keeps the open-source path honest: users test the actual live behavior they
care about, while maintainers keep cheap repeatable tests.

## Public Contract

- Omitted `provider_mode` resolves to `live_openai`.
- `MUSE_PROVIDER_MODE=deterministic` is rejected unless
  `MUSE_ENABLE_TEST_PROVIDER=1`.
- `provider_mode: "deterministic"` is rejected unless
  `MUSE_ENABLE_TEST_PROVIDER=1`.
- Configuration failures return structured `configuration_error` payloads from
  MCP and smoke tooling.
- README and MCP docs show live OpenAI setup first.

## Non-Goals

- Remove all internal deterministic tests.
- Remove historical design docs that mention deterministic milestones.
- Build a hosted API surface.
