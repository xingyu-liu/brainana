"""The pipeline's stage order and the driver scripts' step lists must agree.

Before this, `pipeline.py` hard-coded its stage lists in three places and the
driver scripts hard-coded a fourth and fifth copy -- so a stage added to one
could silently be missing from another. `pipeline.py` is now the single source
of truth for *what runs*, and `stages/ordering.py` derives step ids from
the stage modules on disk. These tests assert the two views still line up.
"""

from types import SimpleNamespace

from fastsurfer_surfrecon.pipeline import ReconSurfPipeline
from fastsurfer_surfrecon.stages.ordering import (
    ALL_STEPS,
    POST_SURFACE_STEPS,
    SURFACE_STEPS,
    VOLUME_STEPS,
)


def _bare_pipeline():
    """A pipeline whose stage factories work without touching the filesystem.

    The factories only pass self.config / self.sd through to stage
    constructors, which merely store them, so no real config is needed.
    """
    pipeline = ReconSurfPipeline.__new__(ReconSurfPipeline)
    pipeline.config = SimpleNamespace()
    pipeline.sd = SimpleNamespace()
    return pipeline


def _step_ids(stages):
    """Map stage instances back to their 's##' ids via their defining module."""
    return [
        stage.__class__.__module__.split(".stages.")[-1].split("_", 1)[0]
        for stage in stages
    ]


def test_volume_stage_order_matches_step_list():
    assert _step_ids(_bare_pipeline().volume_stages()) == VOLUME_STEPS


def test_surface_stage_order_matches_step_list():
    assert _step_ids(_bare_pipeline().surface_stages("lh")) == SURFACE_STEPS


def test_post_surface_stage_order_matches_step_list():
    assert _step_ids(_bare_pipeline().post_surface_stages()) == POST_SURFACE_STEPS


def test_every_stage_module_is_reachable():
    """No stage module may be orphaned from every group.

    s18 (cortical ribbon) and s19 (statistics) run between the hemisphere loop
    and the post-surface group because they need both hemispheres, so they are
    intentionally in no group list -- but they must still be known steps.
    """
    grouped = set(VOLUME_STEPS) | set(SURFACE_STEPS) | set(POST_SURFACE_STEPS)
    ungrouped = set(ALL_STEPS) - grouped

    assert ungrouped == {"s18", "s19"}, (
        "stage modules are neither in a group nor a known both-hemisphere "
        f"stage: {sorted(ungrouped)}"
    )


def test_step_ids_are_sorted_and_unique():
    assert ALL_STEPS == sorted(set(ALL_STEPS))
    # The 's07' < 's07b' < 's08' case is the one plain string sort could get
    # wrong if a stage were ever named e.g. 's7'.
    assert ALL_STEPS.index("s07") < ALL_STEPS.index("s07b") < ALL_STEPS.index("s08")
