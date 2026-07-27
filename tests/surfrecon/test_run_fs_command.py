"""Tests for the FreeSurfer command runner's output postcondition.

Every wrapper used to end `run_fs_command(...); return output_surf` with no
check that anything was written -- so a binary that exits 0 without producing
its output was indistinguishable from success, and the failure only surfaced
in whichever later stage tried to read the missing file.
"""

from pathlib import Path

import pytest

from fastsurfer_surfrecon.wrappers.base import FreeSurferError, run_fs_command


@pytest.fixture(autouse=True)
def _freesurfer_home(tmp_path, monkeypatch):
    """run_fs_command requires FREESURFER_HOME; the tests below use /bin/sh."""
    monkeypatch.setenv("FREESURFER_HOME", str(tmp_path))


def test_passes_when_output_is_written(tmp_path):
    target = tmp_path / "lh.white"
    run_fs_command(
        ["/bin/sh", "-c", f"echo data > {target}"],
        expect_outputs=[target],
    )
    assert target.exists()


def test_raises_when_command_exits_zero_without_writing(tmp_path):
    """The core regression: exit 0 is not proof of work."""
    target = tmp_path / "lh.white"

    with pytest.raises(FreeSurferError, match="exited 0 but did not produce"):
        run_fs_command(["/bin/sh", "-c", "true"], expect_outputs=[target])


def test_error_names_the_missing_file(tmp_path):
    target = tmp_path / "lh.pial"

    with pytest.raises(FreeSurferError) as excinfo:
        run_fs_command(["/bin/sh", "-c", "true"], expect_outputs=[target])

    assert "lh.pial" in str(excinfo.value)


def test_relative_outputs_resolve_against_subject_dir(tmp_path):
    """Wrappers relativise paths to subject_dir; the check must follow suit.

    A naive Path(p).exists() would resolve against the interpreter's cwd and
    report every relative output as missing.
    """
    surf = tmp_path / "surf"
    surf.mkdir()

    run_fs_command(
        ["/bin/sh", "-c", "echo data > surf/lh.white"],
        subject_dir=tmp_path,
        expect_outputs=[Path("surf/lh.white")],
    )

    assert (surf / "lh.white").exists()


def test_relative_output_missing_is_still_detected(tmp_path):
    with pytest.raises(FreeSurferError, match="exited 0 but did not produce"):
        run_fs_command(
            ["/bin/sh", "-c", "true"],
            subject_dir=tmp_path,
            expect_outputs=[Path("surf/lh.white")],
        )


def test_nonzero_exit_still_reported_as_command_failure(tmp_path):
    """A real failure must not be relabelled as a missing-output problem."""
    with pytest.raises(FreeSurferError, match="exit code 3"):
        run_fs_command(
            ["/bin/sh", "-c", "exit 3"],
            expect_outputs=[tmp_path / "never"],
        )


def test_no_expectations_means_no_check(tmp_path):
    """Callers that pass nothing keep the previous behaviour exactly."""
    run_fs_command(["/bin/sh", "-c", "true"])  # must not raise
