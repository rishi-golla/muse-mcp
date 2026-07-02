# V4-B Live Quality Pressure Design

## Purpose

V4-B aligns live OpenAI prompting with the MCP dogfood quality gates. The system
already has a repeatable way to flag generic finalists, but the live provider's
seed, transform, and evaluate instructions do not name those gates as a shared
contract. This slice makes the live model optimize against the same quality
failure modes that dogfood runs report.

## Scope

This slice changes prompt pressure only. It does not add a new API, change the
MCP protocol, call live providers in tests, or tune model pricing. The behavior
change is limited to the OpenAI creative provider instructions and the tests
that lock those instructions to the dogfood quality vocabulary.

## Design

Add a shared quality-pressure block in `src/creativity_layer/openai_provider.py`
that names the dogfood failure modes: generic titles, generic mechanisms,
missing required task/repo terms, missing operational fields, arbitrary stack
choices, and unsupported context invention. Append that block to seed,
transform, and evaluate instructions so all live generation stages receive the
same quality contract.

The block must stay static and deterministic. It may reference gate names and
examples, but it must not import the dogfood runner into the live provider or
make the provider depend on the MCP dogfood suite at runtime.

## Testing

Tests assert that the dogfood gate vocabulary exists and that live developer
instructions include it for seed, transform, and evaluate operations. Existing
provider tests continue to verify that task text remains user data rather than
static instructions.

## Documentation

Update the dogfood playbook with V4-B guidance: dogfood gates now act as live
prompt pressure, deterministic output is still protocol-only, and live quality
claims still require explicit live runs.
