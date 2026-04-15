"""
Shared stage utilities for test pipeline scripts.

Provides canonical stage validation and ordering, including support for
lettered stages such as s07b.
"""

# Canonical stage order used by test scripts.
ORDERED_STEPS = [
    # Volume
    "s01", "s02", "s03", "s04", "s05", "s06", "s07", "s07b",
    # Surface
    "s08", "s09", "s10", "s11", "s12", "s13", "s14", "s15", "s16", "s17",
    # Post-surface
    "s18", "s19", "s20", "s21", "s22",
]

VALID_STEPS = set(ORDERED_STEPS)

VOLUME_STEPS = set(ORDERED_STEPS[:8])
SURFACE_STEPS = set(ORDERED_STEPS[8:18])
POST_SURFACE_STEPS = set(ORDERED_STEPS[18:])


def stage_order_value(step: str) -> int:
    """
    Get sortable stage index from step string.

    Examples
    --------
    - ``s01`` -> ``0``
    - ``s07`` -> ``6``
    - ``s07b`` -> ``7`` (ordered between ``s07`` and ``s08``)
    """
    try:
        return ORDERED_STEPS.index(step)
    except ValueError as e:
        raise ValueError(f"Invalid step '{step}'. Must be one of: {', '.join(ORDERED_STEPS)}") from e


def validate_step(step: str) -> None:
    """Validate stage name and raise ValueError for unknown stages."""
    if step not in VALID_STEPS:
        raise ValueError(f"Invalid step '{step}'. Must be one of: {', '.join(ORDERED_STEPS)}")
