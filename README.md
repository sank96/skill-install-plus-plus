<p align="center">
  <img
    src="https://raw.githubusercontent.com/sank96/skill-install-plus-plus/main/assets/skillpp-mark.svg"
    alt="Skill Install ++ wordmark"
    width="560"
    height="137"
  >
</p>

<p align="center">
  <strong>Audit-first skill and plugin management for Codex, Claude Code, and Copilot CLI.</strong>
</p>

<p align="center">
  Keep <code>~/.skills</code> as the source of truth, export only the discovery surfaces each client should see, and repair drift without guessing hidden client state.
</p>

<p align="center">
  <a href="https://github.com/sank96/skill-install-plus-plus/actions/workflows/ci.yml">
    <img alt="CI" src="https://img.shields.io/github/actions/workflow/status/sank96/skill-install-plus-plus/ci.yml?branch=main&label=CI">
  </a>
  <a href="https://github.com/sank96/skill-install-plus-plus/releases">
    <img alt="Release" src="https://img.shields.io/github/v/release/sank96/skill-install-plus-plus?label=release">
  </a>
  <a href="https://pypi.org/project/skillpp/">
    <img alt="PyPI" src="https://img.shields.io/pypi/v/skillpp">
  </a>
  <a href="https://pypi.org/project/skillpp/">
    <img alt="Python" src="https://img.shields.io/pypi/pyversions/skillpp">
  </a>
  <a href="LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/sank96/skill-install-plus-plus">
  </a>
</p>

<p align="center">
  Repository: <code>skill-install-plus-plus</code> | Package: <code>skillpp</code> | CLI: <code>skillpp</code>
</p>

## Table of Contents

- [Why This Exists](#why-this-exists)
- [What Skillpp Manages](#what-skillpp-manages)
- [Highlights](#highlights)
- [Support Matrix](#support-matrix)
- [Install](#install)
- [Quick Start](#quick-start)
- [Source-of-Truth Model](#source-of-truth-model)
- [Why Audit-First Matters](#why-audit-first-matters)
- [Development](#development)
- [Release Model](#release-model)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Why This Exists

AI assistant skill setups drift quickly once you mix:

- standalone local skill folders
- Git-backed skill repositories
- hybrid repositories that export skills plus bundle metadata
- plugin bundles with manifests, agents, hooks, and runtime files

Copies go stale, links diverge, and it becomes unclear which files are managed
versus accidental.

`skillpp` gives those assets one managed home under `~/.skills`, then projects
only the explicit `SKILL.md` surfaces into client discovery roots.

It is intentionally conservative: audit first, mutate second.

## What Skillpp Manages

- Standalone local skills normalized into `~/.skills/custom`
- Git-backed skill repositories stored under `~/.skills/repos/<owner>/<repo>`
- Plugin bundles stored under `~/.skills/plugins/<publisher>/<name>`
- Explicit skill exposures for Codex, Claude Code, and Copilot CLI
- Non-destructive alignment when client discovery roots drift away from managed state

## Highlights

- One managed source-of-truth tree under `~/.skills`
- Supports standalone skills, Git-backed repos, hybrid repos, and plugin bundles
- Audit-first workflow for drift, broken links, legacy copies, and missing exposures
- Safe alignment that creates missing links without rewriting unrelated client state
- Public Python CLI available through `uvx`, `uv tool install`, and `pipx`
- GitHub Actions CI plus PyPI release automation via Trusted Publishing

## Support Matrix

| Client | Status | Discovery root | Notes |
| --- | --- | --- | --- |
| Codex | Supported | `~/.agents/skills` | Respects existing aggregate custom exposures where already in place |
| Claude Code | Supported | `~/.claude/skills` | Injects explicit skill surfaces only |
| Copilot CLI | Supported | `~/.copilot/skills` | Injects explicit skill surfaces only |

## Install

### Try it without installing

```powershell
uvx skillpp audit
```

### Persistent install with uv

```powershell
uv tool install skillpp
```

### Persistent install with pipx

```powershell
pipx install skillpp
```

## Quick Start

1. Audit the current managed state:

```powershell
skillpp audit
```

2. Bootstrap the current project into the managed tree:

```powershell
skillpp bootstrap --source .
```

3. Install a skill from GitHub:

```powershell
skillpp install --repo jackwener/OpenCLI --path skills/opencli-browser
```

4. Install a plugin bundle:

```powershell
skillpp install-plugin --publisher acme --name suite --repo acme/suite
```

5. Create missing non-destructive exposures:

```powershell
skillpp align --apply
```

6. Refresh managed repositories and git-backed bundles:

```powershell
skillpp update
```

## Source-of-Truth Model

Everything managed by `skillpp` lives under `~/.skills`:

```text
~/.skills/
|- custom/
|- repos/<owner>/<repo>/
|- plugins/<publisher>/<name>/
`- registry.json
```

Client discovery roots stay separate:

- Codex: `~/.agents/skills`
- Claude Code: `~/.claude/skills`
- Copilot CLI: `~/.copilot/skills`

This keeps the managed tree explicit while preserving each client's discovery
model.

## Why Audit-First Matters

Blind installers are convenient until they overwrite something you needed.

`skillpp` treats that as a design problem, not a user problem. The tool:

- inventories managed sources before mutating discovery roots
- surfaces legacy copies and mismatched links explicitly
- creates only safe missing links during alignment
- avoids guessing undocumented client plugin registries

That boundary matters most for larger bundles where exported `SKILL.md` files
are only one part of the package surface.

## Development

Run the test suite:

```powershell
uv run python -m unittest tests.test_manager tests.test_cli -v
```

Build the package:

```powershell
uv run --with build python -m build
```

Check built artifacts:

```powershell
uv run --with twine python -m twine check dist/*
```

## Release Model

`skillpp` is PyPI-first.

Recommended usage modes:

- `uvx skillpp ...` for ephemeral runs
- `uv tool install skillpp` for persistent installs
- `pipx install skillpp` as a familiar Python CLI alternative

There is no npm package or `npx` wrapper in `v1`.

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for
development workflow, test expectations, and contribution scope.

## Security

Security reporting guidance lives in [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
