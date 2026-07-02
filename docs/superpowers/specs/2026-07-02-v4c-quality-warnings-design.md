# V4-C Quality Warnings Design

## Purpose

V4-C makes quality gate feedback visible in the normal middleware/MCP response.
Right now, quality gates are available through the dogfood CLI, but an agent
calling `muse_plan` during normal coding only receives finalists. The agent
can therefore miss obvious warning signs such as generic titles, generic
mechanisms, or missing operational fields unless a separate dogfood run is
performed.

## Scope

This slice adds lightweight quality warnings to serialized middleware results.
It does not reject finalists, change finalist ranking, spend live tokens, or
make dogfood CLI policy stricter. Warnings are advisory fields for agent hosts.

## Design

Create a small `quality_warnings` module that owns reusable quality gate
vocabulary and pure functions for serialized finalist dictionaries. The module
checks for generic titles, generic mechanism phrases, empty operational fields,
and missing required terms when required terms are supplied.

The dogfood suite will use the shared module instead of keeping its own copy of
the generic gate logic. Middleware serialization will attach:

- `quality_warnings`: the union of finalist warning names for the run.
- `quality_summary`: counts by warning name plus the number of finalists with
  warnings.
- `finalists[*].quality_warnings`: warnings for that finalist.

Configuration-error responses keep the same response shape and return empty
quality warning fields.

## Required Terms

For ordinary middleware calls, required terms are derived from context tags
created from repo signals and search context. This stays repo-agnostic while
still allowing agents to see when a finalist ignores observed stack or workflow
facts such as `python`, `pytest`, `typescript`, `vitest`, or `playwright`.

## Testing

Add focused tests for the pure quality warning module, dogfood reuse, middleware
serialization, MCP structured output, and configuration-error shape.
