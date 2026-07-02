# Security Policy

## Supported Versions

The project is pre-1.0. Security fixes target the `main` branch until versioned
releases are introduced.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately to the repository owner rather
than opening a public issue with exploit details.

Include:

- affected commit or version;
- operating system and Python version;
- MCP host or CLI command involved;
- whether live providers, search providers, or trace files were enabled;
- reproduction steps that do not include real secrets.

## Secret Handling Expectations

Do not commit API keys, local `.env` files, raw provider responses containing
credentials, or traces that include private data. Use `.env.example` and
`openai-pricing.example.json` as safe templates.

MCP servers run with the permissions granted by the agent host. Review host MCP
configuration before enabling live provider calls or search providers.
