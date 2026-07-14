from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from muse.agent_instructions import render_agent_instructions
from muse.live_preflight import check_live_openai_environment
from muse.mcp_config import HostConfigFormat, render_mcp_config
from muse.models import FrozenModel


class ProjectBootstrapReport(FrozenModel):
    project_path: str
    host: str
    instruction_target: str
    dry_run: bool
    planned_files: tuple[str, ...]
    written_files: tuple[str, ...]
    skipped_existing_files: tuple[str, ...]
    doctor_status: str
    ready_for_manual_agent_test: bool
    next_steps: tuple[str, ...]


def run_project_bootstrap(
    *,
    project_path: Path,
    host: str = "generic-json",
    instruction_target: str = "agents-md",
    include_env: bool = False,
    dry_run: bool = False,
    force: bool = False,
    environ: Mapping[str, str] | None = None,
) -> ProjectBootstrapReport:
    target = project_path.expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise ValueError(f"project path must be a directory: {target}")

    config = render_mcp_config(host=host, include_env=include_env)
    instructions = render_agent_instructions(target=instruction_target)
    files = (
        _BootstrapFile(
            relative_path=_host_config_relative_path(host=config.host, format=config.format),
            content=config.content,
        ),
        _BootstrapFile(
            relative_path=_instruction_relative_path(instructions.recommended_file),
            content=instructions.content,
        ),
    )

    planned_files = tuple(file.relative_path for file in files)
    existing_files = tuple(
        file.relative_path for file in files if (target / file.relative_path).exists()
    )
    if existing_files and not (force or dry_run):
        formatted = ", ".join(existing_files)
        raise ValueError(f"refusing to overwrite existing files: {formatted}")

    written_files: list[str] = []
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)
        for file in files:
            destination = target / file.relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(file.content, encoding="utf-8")
            written_files.append(file.relative_path)

    preflight = check_live_openai_environment(environ)
    return ProjectBootstrapReport(
        project_path=str(target),
        host=config.host,
        instruction_target=instructions.target,
        dry_run=dry_run,
        planned_files=planned_files,
        written_files=tuple(written_files),
        skipped_existing_files=existing_files if dry_run else (),
        doctor_status=preflight.status.value,
        ready_for_manual_agent_test=preflight.ok,
        next_steps=_next_steps(
            project_path=target,
            ready_for_manual_agent_test=preflight.ok,
        ),
    )


class _BootstrapFile(FrozenModel):
    relative_path: str
    content: str


def _host_config_relative_path(*, host: str, format: HostConfigFormat) -> str:
    if host == "codex":
        return ".codex/config.toml"
    if format is HostConfigFormat.JSON:
        return ".mcp.json"
    return "muse-mcp-config.toml"


def _instruction_relative_path(recommended_file: str) -> str:
    if recommended_file in {"project instructions", "Claude project instructions"}:
        return "MUSE_INSTRUCTIONS.md"
    return recommended_file.replace("\\", "/")


def _next_steps(
    *,
    project_path: Path,
    ready_for_manual_agent_test: bool,
) -> tuple[str, ...]:
    steps = [
        f"cd {project_path}",
        "Run muse-mcp-doctor --json",
        "Restart your MCP-capable agent host so it reloads project config.",
        "Ask the agent to use muse_plan during planning or failed-test recovery.",
    ]
    if not ready_for_manual_agent_test:
        steps.insert(1, "Set OPENAI_API_KEY, OPENAI_ECONOMY_MODEL, and OPENAI_STRONG_MODEL.")
    return tuple(steps)
