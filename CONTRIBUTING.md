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
- For dependency changes, ensure the `Dependencies` workflow passes — not just `Docs`.
- Do **not** bump the version in a feature PR. Edit `CHANGELOG.md` under `[Unreleased]` only;
  the version bump happens on `main` at release time.

## Bumping the version

Run `python scripts/bump_version.py X.Y.Z` — never edit the version by hand. It updates
every site the release touches (`pyproject.toml`, the `CHANGELOG.md` heading, the Brainana
Lite `BRAINANA_REF`, the `docs/*.rst` example Docker tags and the scratch runners), then
reports anything still on the old version. `--dry-run` previews without writing.

`tests/test_version.py` enforces the one site where staleness breaks users: a
`BRAINANA_REF` pinned to a `vX.Y.Z` tag must match `pyproject.toml`, because Colab clones
that ref. Dev refs (`main`, a SHA, `feat/<topic>`) are skipped, so the Brainana Lite smoke
workflow is unaffected.

Full reference: `docs_temp/update_instruction/version_guideline.md`.

## Removing or moving a dependency

`grep "import <pkg>" src/` is **not** sufficient evidence that a dependency is unused.
A dependency can be needed *transitively, at call time*. On 2026-06-02 `pyvista` was
dropped on exactly that evidence and silently broke surface topology repair for 55 days,
because `pymeshfix.MeshFix.__init__` probes for pyvista rather than brainana importing it.
`tensorboard` was removed in the same commit for the same reason (reached via
`torch.utils.tensorboard`) and had to be hotfixed 20 minutes later.

Before removing a dependency:

1. Run the `Dependencies` workflow. It installs for real; `docs.yml` uses
   `pip install --no-deps` and can never see a missing dependency.
2. If the dependency is only reachable at call time, add a test that *calls* it —
   see `tests/surfrecon/test_topology_fix.py` for the pattern.
3. If a module legitimately needs an extra, register it in both
   `tests/tools/import_all.py::OPTIONAL` and
   `tests/test_dependency_declarations.py::OPTIONAL` (a test asserts they agree).

## Documentation update checklist

Use this checklist for PRs that change behavior:

- [ ] `README.md` links/instructions are still accurate.
- [ ] Relevant pages under `docs/` are updated.
- [ ] `CHANGELOG.md` is updated (or marked as not applicable).
- [ ] Docs build succeeds locally.
