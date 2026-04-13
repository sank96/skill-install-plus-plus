# skill-install-plus-plus

`skillpp` is an audit-first skill and plugin manager for Codex, Claude Code,
and Copilot CLI.

It keeps `~/.skills` as the source of truth, inventories drift before making
changes, and helps normalize skills, hybrid repositories, and plugin bundles
into a predictable local layout.

## Why this exists

Managing AI assistant skills becomes messy quickly once you mix:

- standalone skills
- Git-backed skill repositories
- hybrid repositories that export skills and bundle metadata
- plugin bundles with agents, hooks, manifests, and runtime code

`skillpp` gives those objects one managed home and exposes only the safe,
explicit skill surfaces into client discovery directories.

## Supported clients

- Codex
- Claude Code
- Copilot CLI

## Installation

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

## Quick start

Audit the current managed state:

```powershell
skillpp audit
```

Bootstrap the current project into your local managed skill tree:

```powershell
skillpp bootstrap --source .
```

Install a skill from a GitHub repository:

```powershell
skillpp install --repo jackwener/OpenCLI --path skills/opencli-browser
```

Install a plugin bundle from GitHub:

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

## Source-of-truth layout

Everything managed by `skillpp` lives under `~/.skills`:

- `~/.skills/custom`
  Local standalone skills.
- `~/.skills/repos/<owner>/<repo>`
  Git-backed skill repositories.
- `~/.skills/plugins/<publisher>/<name>`
  Managed plugin bundles.
- `~/.skills/registry.json`
  Registry for repo installs and plugin bundle installs.

Client discovery roots stay separate:

- Codex: `~/.agents/skills`
- Claude Code: `~/.claude/skills`
- Copilot CLI: `~/.copilot/skills`

## Mental model

Use `custom` for small standalone skills.

Use `repos` for repositories that primarily publish skills, even if they also
carry plugin metadata.

Use `plugins` for bundle-style installs that may include:

- exported skills under `skills/*`
- plugin manifests such as `.claude-plugin/plugin.json`
- agents
- hooks
- runtime code

## Current behavior

`skillpp` is intentionally conservative:

- it audits before changing discovery roots
- it auto-creates missing safe links
- it surfaces legacy copies and mismatched links
- it does not guess undocumented client plugin registries

That boundary matters for larger bundles where exported `SKILL.md` files are
only one part of the system.

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

## Release

The public package name is `skillpp`, while the repository remains
`skill-install-plus-plus`.

The first public release flow is:

1. push the repository to GitHub
2. configure PyPI Trusted Publishing
3. create tag `v0.1.0`
4. publish

## Limitations

- the tool is currently Windows-first because it manages junction-based client
  exposures there
- bundle-level plugin runtime behavior is intentionally not auto-mutated
- no npm package or `npx` wrapper is shipped in v1

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
