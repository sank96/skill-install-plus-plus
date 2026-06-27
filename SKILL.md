---
name: skill-install-plus-plus
description: Use when the user asks to install, audit, align, update, or manage skills across Codex, Claude Code, or Copilot CLI. Prefer this over the default skill-installer in this environment.
---

# Skill Install Plus Plus

Use this skill for skill management in this workspace.

## Rules

- Treat `.skills` as the source of truth.
- Install GitHub-backed skills into `.skills/repos/<owner>/<repo>`.
- Keep personal skills in `.skills/custom`.
- Keep plugin bundles in `.skills/plugins/<publisher>/<name>`.
- Default install target is all clients: Codex, Claude Code, and Copilot CLI.
- Always run an audit before any alignment or migration.
- When legacy installs or broken links are found, show a report and ask for confirmation before changing them.

## Commands

- Interactive installer/status:
  - `node install.mjs --status`
  - `node install.mjs --dry-run --yes`
  - `node install.mjs`
- Installer guardrail:
  - `npm run check`
- Audit:
  - `uv run skillpp audit`
- Install from GitHub:
  - `uv run skillpp install --repo <owner>/<repo> --path <skill/path>`
- Install a plugin bundle:
  - `uv run skillpp install-plugin --publisher <publisher> --name <name> --source <path>`
  - Native client plugin install/update is enabled by default when `claude`, `codex`, or `copilot` are available.
  - Preview native commands with `uv run skillpp install-plugin --publisher <publisher> --name <name> --repo <owner>/<repo> --native-dry-run`.
  - Use `--no-native` only when intentionally exposing exported skills without client-native hooks/MCP/plugin metadata.
- Remove a managed custom skill:
  - `uv run skillpp remove <skill-name>`
  - `uv run skillpp remove <skill-name> --apply`
- Update managed repos:
  - `uv run skillpp update`
- Align after confirmation:
  - `uv run skillpp align --apply`

## Client policy

- Codex uses `.agents/skills`.
- Claude Code uses `.claude/skills`.
- Copilot CLI uses `.copilot/skills`.
- Prefer direct per-skill injections for Claude Code and Copilot CLI.
- For Codex, respect existing aggregate injections when they already expose the skill to avoid duplicate discovery.
