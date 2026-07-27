"""The pipeline's stage ids, in execution order.

Used by the manual driver scripts under ``scripts/dev/fastsurfer_recon/`` to
resolve ``--step``-style arguments, and by
``tests/surfrecon/test_stage_ordering.py``.

The ordered step list is *derived from the stage modules themselves* rather
than hand-maintained, so adding ``stages/s23_foo.py`` cannot leave this module
stale. The grouping into volume / surface / post-surface mirrors
``ReconSurfPipeline.volume_stages()`` / ``surface_stages()`` /
``post_surface_stages()``; the test above asserts the two agree.

Deliberately import-light: no stage class is imported here, so resolving an
ordering never pulls in FreeSurfer wrappers or torch.
"""

from __future__ import annotations

from pathlib import Path

# This module lives inside stages/, so the directory to scan is its own.
_STAGES_DIR = Path(__file__).resolve().parent


def _discover_steps() -> list[str]:
    """All stage ids (e.g. 's07b'), in execution order.

    Module filenames are numerically prefixed and that prefix *is* the order.
    Plain string sort is correct here, including for the 's07' < 's07b' < 's08'
    case.
    """
    ids = []
    for path in _STAGES_DIR.glob("s*.py"):
        stem = path.stem
        if "_" not in stem:
            continue
        ids.append(stem.split("_", 1)[0])
    return sorted(set(ids))


ALL_STEPS: list[str] = _discover_steps()

# Group boundaries mirror the phases in pipeline.py. s18 (cortical ribbon) and
# s19 (statistics) sit between the per-hemisphere and post-surface groups
# because they need both hemispheres, so they belong to neither list.
VOLUME_STEPS: list[str] = [s for s in ALL_STEPS if s < "s08"]
SURFACE_STEPS: list[str] = [s for s in ALL_STEPS if "s08" <= s < "s18"]
POST_SURFACE_STEPS: list[str] = [s for s in ALL_STEPS if s >= "s20"]


def validate_step(step: str) -> str:
    """Return `step` if it names a real stage, else raise ValueError."""
    if step not in ALL_STEPS:
        raise ValueError(
            f"Unknown stage {step!r}. Valid stages: {', '.join(ALL_STEPS)}"
        )
    return step


def stage_order_value(step: str) -> int:
    """Position of `step` in execution order; comparable with < and >=."""
    return ALL_STEPS.index(validate_step(step))
