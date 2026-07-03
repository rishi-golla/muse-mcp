from __future__ import annotations

from muse.models import FrozenModel


class AgentInstructionDocument(FrozenModel):
    target: str
    recommended_file: str
    content: str


def render_agent_instructions(*, target: str) -> AgentInstructionDocument:
    normalized_target = target.casefold()
    if normalized_target == "agents-md":
        return AgentInstructionDocument(
            target="agents-md",
            recommended_file="AGENTS.md",
            content=_agents_md_content(),
        )
    if normalized_target == "cursor-rules":
        return AgentInstructionDocument(
            target="cursor-rules",
            recommended_file=".cursor/rules/muse.mdc",
            content=_cursor_rules_content(),
        )
    if normalized_target == "claude-project":
        return AgentInstructionDocument(
            target="claude-project",
            recommended_file="Claude project instructions",
            content=_generic_content(
                opener="Use the Muse MCP tool when a task benefits from creative planning."
            ),
        )
    if normalized_target == "generic":
        return AgentInstructionDocument(
            target="generic",
            recommended_file="project instructions",
            content=_generic_content(
                opener="When a task needs creative planning, call the Muse MCP tool."
            ),
        )
    raise ValueError("target must be one of: agents-md, cursor-rules, claude-project, generic")


def _agents_md_content() -> str:
    return _generic_content(
        opener="## Muse MCP Usage\n\nWhen a task needs creative planning, call the Muse MCP tool."
    )


def _cursor_rules_content() -> str:
    return _generic_content(
        opener=(
            "Always call the Muse MCP tool for creative planning, failed verification "
            "recovery, architecture alternatives, or workflow design."
        )
    )


def _generic_content(*, opener: str) -> str:
    return (
        f"{opener}\n\n"
        "- Use `muse_plan` during planning, failed test recovery, architecture "
        "alternatives, workflow design, and before high-impact edits.\n"
        "- Pass observed repository facts through `repo_signals`: changed files, "
        "test commands, CI logs, dependency hints, languages, and frameworks.\n"
        "- Do not ask Muse to crawl the repo. Gather repo context yourself and pass "
        "only the facts needed for the current task.\n"
        "- Do not treat finalists as applied code. Treat them as planning options.\n"
        "- Pick one bounded next action from a finalist, then run repository-owned "
        "verification before continuing.\n"
        "- Start with `quick`. Escalate to `standard` after a failed verification or "
        "ambiguous context. Use `deep` only for high-impact planning or repeated "
        "failure loops.\n"
        "- If Muse returns `quality_action_policy.status = needs_retry`, add richer "
        "repo signals or use the recommended effort before editing.\n"
    )
