<p align="center">
  <img
    src="https://raw.githubusercontent.com/sank96/skill-install-plus-plus/main/assets/skillpp-mark.svg"
    alt="skillpp mark"
    width="120"
    height="120"
  >
</p>

<h1 align="center">skillpp</h1>

<p align="center">
  <strong>Audit-first skill and plugin management for Codex, Claude Code, and Copilot CLI.</strong>
</p>

<p align="center">
  Normalize standalone skills, hybrid repositories, and plugin bundles under one source-of-truth tree without guessing hidden client state.
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
  Repository: <code>skill-install-plus-plus</code> · Package: <code>skillpp</code> · CLI: <code>skillpp</code>
</p>

## Table of Contents

- [Why This Exists](#why-this-exists)
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

AI assistant skills get messy fast once you combine:

- standalone local skills
- Git-backed skill repositories
- hybrid repositories that export skills and bundle metadata
- plugin bundles with manifests, agents, hooks, and runtime code

`skillpp` gives those objects one managed home under `~/.skills`, then exposes
only the explicit, safe skill surfaces into client discovery directories.

It is intentionally conservative: audit first, mutate second.

## Highlights

- One managed source-of-truth tree under `~/.skills`
- Supports standalone skills, Git-backed repos, hybrid repos, and plugin bundles
- Audit-first workflow for drift, broken links, legacy copies, and missing exposures
- Non-destructive alignment for safe client-side repairs
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

Audit the current managed state:

```powershell
skillpp audit
```

Bootstrap the current project into the local managed skill tree:

```powershell
skillpp bootstrap --source .
```

Install a skill from GitHub:

```powershell
skillpp install --repo jackwener/OpenCLI --path skills/opencli-browser
```

Install a plugin bundle:

```powershell
skillpp install-plugin --publisher acme --name suite --repo acme/suite
```

Create missing non-destructive exposures:

```powershell
skillpp align --apply
```

Refresh managed repositories and git-backed bundles:

```powershell
skillpp update
```

## Source-of-Truth Model

Everything managed by `skillpp` lives under `~/.skills`:

```text
~/.skills/
├── custom/
├── repos/<owner>/<repo>/
├── plugins/<publisher>/<name>/
└── registry.json
```

Client discovery roots stay separate:

- Codex: `~/.agents/skills`
- Claude Code: `~/.claude/skills`
- Copilot CLI: `~/.copilot/skills`

This keeps the managed tree explicit while preserving each client's discovery
model.

## Why Audit-First Matters

Blind installers are fast until they overwrite something you needed.

`skillpp` treats that as a design problem, not a user problem. The tool:

- inventories managed sources before mutating discovery roots
- surfaces legacy copies and mismatched links explicitly
- creates only safe missing links automatically
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

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Security reporting guidance lives in [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
