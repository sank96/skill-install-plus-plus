# Contributing

Thanks for contributing to `skillpp`.

## Before you start

- Open an issue for large changes before starting implementation.
- Keep scope tight. This project is intentionally conservative about mutating
  client state.
- Prefer small pull requests with focused commits.

## Development setup

1. Clone the repository.
2. Ensure Python 3.10+ is available.
3. Run the test suite:

```powershell
uv run python -m unittest tests.test_manager tests.test_cli -v
```

4. Build the package when touching packaging or release metadata:

```powershell
uv run --with build python -m build
uv run --with twine python -m twine check dist/*
```

## Contribution guidelines

- Preserve the audit-first behavior.
- Do not make destructive client changes without clear justification.
- Keep platform assumptions explicit in code and docs.
- Update tests and documentation together with behavior changes.

## Pull requests

Each PR should include:

- a clear summary
- test evidence
- any documentation updates required by the change

If your change affects install paths, discovery behavior, or release metadata,
include an example command and expected outcome in the PR description.
