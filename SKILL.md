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

- Audit:
  - `uv run python skill-install-plus-plus/scripts/skill_install_plus_plus.py audit`
- Install from GitHub:
  - `uv run python skill-install-plus-plus/scripts/skill_install_plus_plus.py install --repo <owner>/<repo> --path <skill/path>`
- Install a plugin bundle:
  - `uv run python skill-install-plus-plus/scripts/skill_install_plus_plus.py install-plugin --publisher <publisher> --name <name> --source <path>`
- Update managed repos:
  - `uv run python skill-install-plus-plus/scripts/skill_install_plus_plus.py update`
- Align after confirmation:
  - `uv run python skill-install-plus-plus/scripts/skill_install_plus_plus.py align --apply`

## Client policy

- Codex uses `.agents/skills`.
- Claude Code uses `.claude/skills`.
- Copilot CLI uses `.copilot/skills`.
- Prefer direct per-skill injections for Claude Code and Copilot CLI.
- For Codex, respect existing aggregate injections when they already expose the skill to avoid duplicate discovery.
