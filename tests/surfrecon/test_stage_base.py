"""Tests for the pipeline stage contract.

The stage base class has three gates: is_disabled() (config says no),
should_skip() (already done), and verify_outputs() (postcondition). These
tests pin down the interaction between the last two, which is where the
sub-01 resume hazard lived: s12 declared only `orig` as its skip signal, but
wrote `orig` at step 2 of 8 -- so a run that died at step 8 looked complete on
the next invocation and its remaining steps were silently skipped.
"""

import logging
from types import SimpleNamespace

import pytest

from fastsurfer_surfrecon.stages.base import PipelineStage, StageOutputError


class FakeStage(PipelineStage):
    """Minimal stage whose behaviour the tests drive directly."""

    name = "fake_stage"

    def __init__(self, tmp_path, writes=(), declares=None, hemi=None):
        super().__init__(
            config=SimpleNamespace(
                processing=SimpleNamespace(threads=1, parallel_hemis=False)
            ),
            subjects_dir=SimpleNamespace(subject_dir=tmp_path),
            hemi=hemi,
        )
        self.tmp_path = tmp_path
        self._writes = list(writes)
        self._declares = list(writes) if declares is None else list(declares)
        self.ran = False

    def expected_outputs(self):
        return [self.tmp_path / name for name in self._declares]

    def _run(self):
        self.ran = True
        for name in self._writes:
            (self.tmp_path / name).write_text("x")


def test_stage_completes_when_it_writes_everything(tmp_path, caplog):
    stage = FakeStage(tmp_path, writes=["a", "b"])

    with caplog.at_level(logging.INFO):
        stage.run()

    assert stage.ran
    assert "Completed" in caplog.text


def test_missing_output_raises_and_never_logs_completed(tmp_path, caplog):
    """A stage that produced nothing must not be able to report success.

    Regression for "Completed {stage}" firing purely because _run() returned
    without raising -- which is what let an external command exit 0 without
    writing and still be recorded as done.
    """
    stage = FakeStage(tmp_path, writes=["a"], declares=["a", "b"])

    with caplog.at_level(logging.INFO):
        with pytest.raises(StageOutputError, match="did not|without producing"):
            stage.run()

    assert stage.ran
    assert "Completed" not in caplog.text


def test_skips_when_all_declared_outputs_exist(tmp_path):
    for name in ("a", "b"):
        (tmp_path / name).write_text("done")
    stage = FakeStage(tmp_path, writes=["a", "b"])

    stage.run()

    assert not stage.ran, "stage re-ran despite complete outputs"


def test_partial_outputs_do_not_count_as_complete(tmp_path):
    """THE resume-hazard regression.

    Only the first of two declared outputs exists, i.e. a previous run died
    part-way. The stage must re-run rather than treat the leftover artifact as
    proof of completion.
    """
    (tmp_path / "a").write_text("from a crashed run")
    stage = FakeStage(tmp_path, writes=["a", "b"])

    stage.run()

    assert stage.ran, "stage was skipped on a partially-complete directory"
    assert (tmp_path / "b").exists()


def test_stage_declaring_nothing_always_runs(tmp_path):
    """Empty expected_outputs() means 'not cacheable', not 'always skip'."""
    stage = FakeStage(tmp_path, writes=[], declares=[])

    stage.run()
    assert stage.ran

    stage2 = FakeStage(tmp_path, writes=[], declares=[])
    stage2.run()
    assert stage2.ran


def test_disabled_stage_does_not_run_or_verify(tmp_path):
    """is_disabled() short-circuits before the postcondition."""

    class Disabled(FakeStage):
        def is_disabled(self):
            return True

    stage = Disabled(tmp_path, writes=[], declares=["never_written"])
    stage.run()  # must not raise StageOutputError

    assert not stage.ran
