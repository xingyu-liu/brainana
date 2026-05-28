# Contributing to Brainana

Thanks for contributing to Brainana.

## Local setup

1. Create and activate a Python 3.11+ environment.
2. Install Brainana with development and docs dependencies:

```bash
uv pip install -e ".[dev,docs]"
```

## Common developer commands

Run lint/format checks:

```bash
ruff check .
black --check .
```

Build docs locally:

```bash
sphinx-build -b html -W --keep-going -c docs docs docs/_build
```

## Pull request expectations

- Keep changes scoped and reviewable.
- Add or update tests when behavior changes.
- Update docs for user-facing changes.
- Add a changelog entry in `CHANGELOG.md` (or explain why none is needed).
- Ensure docs build passes before requesting review.

## Documentation update checklist

Use this checklist for PRs that change behavior:

- [ ] `README.md` links/instructions are still accurate.
- [ ] Relevant pages under `docs/` are updated.
- [ ] `CHANGELOG.md` is updated (or marked as not applicable).
- [ ] Docs build succeeds locally.
