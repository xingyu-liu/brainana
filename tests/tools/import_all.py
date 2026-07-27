#!/usr/bin/env python3
"""Import every module brainana ships, under a named dependency profile.

Why this exists
---------------
A module that is *shipped* but imports something not declared for the profile
the user installed is a broken install, even if no test ever touches it. grep
cannot see this; only actually importing the tree can.

The OPTIONAL table is the load-bearing part. A module may be skipped only if
it is listed there with the extra it needs -- and this script also asserts the
*positive*: when that extra IS installed, the module MUST import. So the table
is a contract, not an exemption list, and a stale entry is reported rather than
quietly tolerated.

Deliberately stdlib-only: this runs in the core-dependency-only CI job, where
pytest is not installed.

Usage:
    python tests/tools/import_all.py --profile core
"""

import argparse
import importlib
import importlib.util
import pkgutil
import sys
import traceback

# Top-level packages this project ships (see [tool.setuptools] in pyproject.toml).
PACKAGES = [
    "nhp_mri_prep",
    "fastsurfer_nn",
    "fastsurfer_surfrecon",
    "nhp_skullstrip_nn",
]

# module -> (extra that makes it importable, the import name it needs).
#
# The probe name matters: the "profile" is a declaration of what CI *intended*
# to install, not a measurement. Running --profile core inside a full venv
# would otherwise report every entry as stale, because the packages are in
# fact present. Probing the actual import name keeps the staleness check
# honest in any environment.
#
# Keep in sync with tests/test_dependency_declarations.py::OPTIONAL.
OPTIONAL = {
    # pybids, imported at module scope by bids_discovery.py
    "nhp_mri_prep.steps.bids_discovery": ("func", "bids"),
    # psutil, imported unguarded by the training data-prep scripts
    "fastsurfer_nn.training.step2_create_hdf5": ("train", "psutil"),
    "nhp_skullstrip_nn.train.step2_create_hdf5": ("train", "psutil"),
}

# Extras installed by each CI profile. Must match the `uv sync` flags in
# .github/workflows/deps.yml.
PROFILES = {
    "core": set(),
    "lite": {"lite"},
    "full": {"surf", "func", "full", "train", "dev"},
}


def _is_available(module_name: str) -> bool:
    """True if `module_name` can be found without importing it.

    Note importlib.util.find_spec RAISES ModuleNotFoundError when a parent
    package is missing rather than returning None -- which is the exact
    behaviour that hid the pyvista bug this guard exists to catch. Hence the
    try/except rather than a bare `is not None` check.
    """
    if not module_name:
        return False
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES))
    args = parser.parse_args()
    installed_extras = PROFILES[args.profile]

    failures = []
    stale_entries = []
    checked = 0

    for package_name in PACKAGES:
        try:
            package = importlib.import_module(package_name)
        except BaseException:
            failures.append((package_name, None, traceback.format_exc()))
            continue

        for module_info in pkgutil.walk_packages(
            package.__path__, prefix=f"{package_name}."
        ):
            name = module_info.name
            entry = OPTIONAL.get(name)
            needs, probe = entry if entry else (None, None)
            checked += 1
            try:
                importlib.import_module(name)
            except BaseException:
                # Only a failure if the module was expected to import here.
                if needs is None or needs in installed_extras:
                    failures.append((name, needs, traceback.format_exc()))
            else:
                # It imported. That only proves the table is stale if the
                # dependency it claims to need is genuinely absent -- otherwise
                # we are just in an environment that happens to have it.
                if (
                    needs is not None
                    and needs not in installed_extras
                    and not _is_available(probe)
                ):
                    stale_entries.append((name, needs, probe))

    for name, needs, tb in failures:
        note = (
            f" (OPTIONAL says it needs [{needs}], which IS installed)" if needs else ""
        )
        print(f"FAIL {name}{note}\n{tb}", file=sys.stderr)

    for name, needs, probe in stale_entries:
        print(
            f"STALE OPTIONAL entry: {name} imports fine with {probe!r} absent, "
            f"so it does not need [{needs}] -- remove it from the table",
            file=sys.stderr,
        )

    problems = len(failures) + len(stale_entries)
    extras = ", ".join(sorted(installed_extras)) or "(none)"
    print(
        f"profile={args.profile} extras={extras}: "
        f"{checked} modules checked, {problems} problem(s)"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
