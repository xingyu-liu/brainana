"""Every module-scope third-party import in src/ must be declared.

This is the check that was missing on 2026-06-02, when ``grep "import pyvista"
src/`` was used as the criterion for removing a dependency. Five were removed
that day; two of them were needed. tensorboard broke ``import nhp_mri_prep``
and was hotfixed 20 minutes later, and pyvista silently disabled surface
topology repair for 55 days.

Scope, stated honestly -- this catches the *sibling* class (a shipped module
importing something that lives only in an extra), not the pyvista case itself:

  * It cannot see transitive call-time needs. pyvista was never imported by
    our code; it is reached inside pymeshfix's constructor. Only a test that
    *calls* the third-party API can catch that -- see
    tests/surfrecon/test_topology_fix.py.
  * It cannot see importlib.import_module("x"). Those are guarded by
    construction, so that is the correct blind spot to have.

It is deliberately conservative: only module-scope, non-try-wrapped imports
count. Anything inside a function or under ``try: ... except ImportError:`` is
an optional import and is exempt.

Runs with no install, no network, and no extras, which matters -- the local
venv is exactly where the pyvista bug hid for 55 days.
"""

import ast
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

# Packages defined in this repo.
LOCAL_PACKAGES = {
    "nhp_mri_prep",
    "fastsurfer_nn",
    "fastsurfer_surfrecon",
    "nhp_skullstrip_nn",
}

# Import name -> distribution name, where they differ.
IMPORT_TO_DISTRIBUTION = {
    "PIL": "pillow",
    "yaml": "pyyaml",
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "sksparse": "scikit-sparse",
    "bids": "pybids",
    "mpl_toolkits": "matplotlib",
    "cv2": "opencv-python",
    "attr": "attrs",
}

# Modules allowed to import from an extra rather than from core.
# Keep in sync with tests/tools/import_all.py::OPTIONAL.
OPTIONAL = {
    "nhp_mri_prep/steps/bids_discovery.py": "func",
    "fastsurfer_nn/training/step2_create_hdf5.py": "train",
    "nhp_skullstrip_nn/train/step2_create_hdf5.py": "train",
}


def _distribution_name(requirement: str) -> str:
    """'brainana[surf]>=1.0' -> 'brainana'; 'scikit-learn>=1.3' -> 'scikit-learn'."""
    name = requirement.strip()
    for separator in ("[", ">", "<", "=", "!", "~", ";", " "):
        name = name.split(separator)[0]
    return name.strip().lower().replace("_", "-")


def _load_declared_dependencies():
    """Return (core, extras) as sets/dict of normalised distribution names."""
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    core = {_distribution_name(r) for r in project["dependencies"]}

    # Extras may reference each other, e.g. full = ["brainana[surf]",
    # "brainana[func]", "psutil"]. Expand those transitively.
    def resolve(name, seen=()):
        if name in seen:
            return set()
        resolved = set()
        for requirement in project["optional-dependencies"].get(name, []):
            dist = _distribution_name(requirement)
            if dist == "brainana":
                inner = requirement[requirement.index("[") + 1 : requirement.index("]")]
                for part in inner.split(","):
                    resolved |= resolve(part.strip(), seen + (name,))
            else:
                resolved.add(dist)
        return resolved

    extras = {name: resolve(name) for name in project.get("optional-dependencies", {})}
    return core, extras


def _module_scope_imports(path: Path):
    """Yield top-level import names, skipping guarded and function-local ones.

    Only ``tree.body`` is walked: an import nested in try/except or inside a
    function is an optional import by construction.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, i.e. our own package
                continue
            yield (node.module or "").split(".")[0]


def _iter_source_files():
    for path in sorted(SRC.rglob("*.py")):
        parts = set(path.parts)
        if "__pycache__" in parts or any(p.endswith(".egg-info") for p in path.parts):
            continue
        yield path


def test_every_unguarded_import_is_declared():
    core, extras = _load_declared_dependencies()
    problems = []

    for path in _iter_source_files():
        relative = path.relative_to(SRC).as_posix()
        allowed_extra = OPTIONAL.get(relative)

        for import_name in _module_scope_imports(path):
            if not import_name:
                continue
            if import_name in sys.stdlib_module_names or import_name in LOCAL_PACKAGES:
                continue

            distribution = IMPORT_TO_DISTRIBUTION.get(import_name, import_name)
            distribution = distribution.lower().replace("_", "-")

            if distribution in core:
                continue
            if allowed_extra and distribution in extras.get(allowed_extra, set()):
                continue

            where = (
                f" nor in [{allowed_extra}]"
                if allowed_extra
                else " (and it is not listed in OPTIONAL)"
            )
            problems.append(
                f"{relative}: imports {import_name!r} -> "
                f"distribution {distribution!r} is not in core dependencies{where}"
            )

    assert not problems, (
        "Shipped modules import undeclared distributions:\n  "
        + "\n  ".join(problems)
        + "\n\nFix by one of: (a) declare it in [project.dependencies], "
        "(b) guard the import with try/except ImportError, (c) move the module "
        "out of src/ if it is a dev script, or (d) add it to OPTIONAL above "
        "with the extra that provides it."
    )


def test_optional_tables_agree():
    """The two OPTIONAL tables describe the same contract and must not drift."""
    sys.path.insert(0, str(REPO_ROOT / "tests" / "tools"))
    try:
        import import_all
    finally:
        sys.path.pop(0)

    here = {
        path.replace("/", ".").removesuffix(".py"): extra
        for path, extra in OPTIONAL.items()
    }
    there = {module: extra for module, (extra, _probe) in import_all.OPTIONAL.items()}

    assert here == there, (
        "tests/test_dependency_declarations.py::OPTIONAL and "
        "tests/tools/import_all.py::OPTIONAL disagree:\n"
        f"  only here:  {sorted(set(here) - set(there))}\n"
        f"  only there: {sorted(set(there) - set(here))}"
    )


def test_optional_entries_point_at_real_files():
    """A stale OPTIONAL entry would silently exempt nothing."""
    missing = [rel for rel in OPTIONAL if not (SRC / rel).exists()]
    assert not missing, f"OPTIONAL names files that do not exist: {missing}"
