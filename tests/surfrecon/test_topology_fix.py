"""Tests for pymeshfix-based topology repair.

These double as a *dependency guard*. pymeshfix is a declared core dependency,
but its repair API is only reachable at call time -- brainana never imports
pyvista by name, so no import smoke test can see that pymeshfix's MeshFix
constructor probes for it. On 2026-06-02 pyvista was dropped from the
dependency set on the strength of ``grep "import pyvista" src/``, and topology
repair silently no-opped for 55 days. Constructing the repair here is what makes
that class of breakage a red build instead of a warning in a log nobody reads.
"""

import subprocess
import sys

import nibabel.freesurfer.io as fs
import numpy as np
import pytest

from fastsurfer_surfrecon.processing.topology_fix import (
    get_euler_number,
    repair_surface_pymeshfix,
)


class _BlockImport:
    """meta_path finder that makes a module look uninstalled."""

    def __init__(self, blocked):
        self.blocked = blocked

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.blocked or fullname.startswith(self.blocked + "."):
            raise ModuleNotFoundError(f"No module named {fullname!r}")
        return None


def test_repair_closes_an_open_mesh(open_cube, write_surf, tmp_path):
    """The core promise: boundary edges are closed and the result is genus 0."""
    src = write_surf("lh.orig.premesh", *open_cube)
    dst = tmp_path / "lh.orig.premesh.pymeshfix"

    info = repair_surface_pymeshfix(src, dst)

    assert info["is_closed"], "repair left boundary edges"
    assert info["is_oriented"]
    assert info["euler"] == 2
    assert info["n_vertices"] > 0 and info["n_faces"] > 0


def test_repair_does_not_need_pyvista(open_cube, write_surf, tmp_path):
    """Regression guard for the 2026-06-02 removal.

    pyvista is only a ``pymeshfix[extras]`` dependency, so no resolver installs
    it for us. The repair must work regardless -- which it does because we drive
    PyTMesh rather than the MeshFix wrapper, whose constructor probes
    find_spec("pyvista.core") and *raises* when pyvista is absent.
    """
    src = write_surf("lh.orig.premesh", *open_cube)
    dst = tmp_path / "out"

    blocker = _BlockImport("pyvista")
    sys.meta_path.insert(0, blocker)
    try:
        for name in [
            m for m in sys.modules if m == "pyvista" or m.startswith("pyvista.")
        ]:
            del sys.modules[name]
        info = repair_surface_pymeshfix(src, dst)
    finally:
        sys.meta_path.remove(blocker)

    assert info["is_closed"] and info["euler"] == 2


def test_repair_is_quiet(open_cube, write_surf, tmp_path, capfd):
    """PyTMesh honours set_quiet; clean_from_arrays does not.

    The alternative implementation (`_meshfix.clean_from_arrays`) produces
    byte-identical geometry but prints "MeshFix could not fix everything" to
    stderr regardless of the quiet flag, which would appear in every run log.
    """
    import warnings

    src = write_surf("lh.orig.premesh", *open_cube)
    with warnings.catch_warnings():
        # nibabel's own UserWarnings are not what this test is about.
        warnings.simplefilter("ignore")
        repair_surface_pymeshfix(src, tmp_path / "out")

    captured = capfd.readouterr()
    assert "MeshFix" not in captured.err and "MeshFix" not in captured.out


def test_repair_preserves_volume_info(open_cube, write_surf, tmp_path):
    """volume_info carries the surfaceRAS header; losing it shifts the surface."""
    volume_info = {
        "head": np.array([2, 0, 20], dtype=np.int32),
        "valid": "1  # volume info valid",
        "filename": "/some/pretess.mgz",
        "volume": np.array([256, 256, 256], dtype=np.int32),
        "voxelsize": np.array([1.0, 1.0, 1.0]),
        "xras": np.array([-1.0, 0.0, 0.0]),
        "yras": np.array([0.0, 0.0, -1.0]),
        "zras": np.array([0.0, 1.0, 0.0]),
        "cras": np.array([0.0, 0.0, 0.0]),
    }
    src = write_surf("lh.orig.premesh", *open_cube, volume_info=volume_info)
    dst = tmp_path / "out"

    repair_surface_pymeshfix(src, dst)

    _, _, meta = fs.read_geometry(dst, read_metadata=True)
    assert meta["filename"] == "/some/pretess.mgz"
    np.testing.assert_array_equal(meta["volume"], [256, 256, 256])


def test_repair_returns_a_report_not_a_bool(open_cube, write_surf, tmp_path):
    """A repair that merely did not raise is not a repair that worked.

    The old signature returned True on "no exception", which the caller could
    not distinguish from a verified genus-0 result.
    """
    src = write_surf("lh.orig.premesh", *open_cube)
    info = repair_surface_pymeshfix(src, tmp_path / "out")

    assert isinstance(info, dict)
    assert {"is_closed", "is_oriented", "euler", "n_vertices"} <= set(info)


def test_repair_propagates_unexpected_errors(
    open_cube, write_surf, tmp_path, monkeypatch
):
    """A MemoryError is an environment fault, not "this mesh was unrepairable"."""
    from pymeshfix import _meshfix

    src = write_surf("lh.orig.premesh", *open_cube)

    def _boom(*args, **kwargs):
        raise MemoryError("out of memory")

    monkeypatch.setattr(_meshfix, "PyTMesh", _boom)

    with pytest.raises(MemoryError):
        repair_surface_pymeshfix(src, tmp_path / "out")


def test_repair_propagates_corrupt_input(tmp_path):
    """A truncated surface file must raise, not return a falsy 'failed' value."""
    bad = tmp_path / "lh.orig.premesh"
    bad.write_bytes(b"\xff\xff\xfe not a surface")

    with pytest.raises(Exception):
        repair_surface_pymeshfix(bad, tmp_path / "out")


# --- get_euler_number: every path that used to silently return None ----------


def _fake_run(returncode=0, stdout="", stderr=""):
    def _run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], returncode, stdout, stderr)

    return _run


def test_euler_parses_valid_output(monkeypatch, tmp_path):
    stdout = "euler # = v-e+f = 2g-2: 10288 - 30858 + 20572 = 2 --> 0 holes"
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=stdout))
    assert get_euler_number(tmp_path / "lh.orig") == 2


def test_euler_parses_negative(monkeypatch, tmp_path):
    stdout = "euler # = v-e+f = 2g-2: 1 - 2 + 3 = -32 --> 17 holes"
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=stdout))
    assert get_euler_number(tmp_path / "lh.orig") == -32


def test_euler_raises_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess, "run", _fake_run(returncode=1, stderr="could not read")
    )
    with pytest.raises(RuntimeError, match="could not read"):
        get_euler_number(tmp_path / "lh.orig")


def test_euler_raises_on_unparseable_output(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout="something else entirely"))
    with pytest.raises(RuntimeError, match="Could not parse"):
        get_euler_number(tmp_path / "lh.orig")


def test_euler_raises_when_binary_missing(monkeypatch, tmp_path):
    def _missing(*args, **kwargs):
        raise FileNotFoundError("mris_euler_number")

    monkeypatch.setattr(subprocess, "run", _missing)
    with pytest.raises(RuntimeError, match="FREESURFER_HOME"):
        get_euler_number(tmp_path / "lh.orig")


def test_euler_raises_on_timeout(monkeypatch, tmp_path):
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="mris_euler_number", timeout=60)

    monkeypatch.setattr(subprocess, "run", _timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        get_euler_number(tmp_path / "lh.orig")


def test_repair_never_returns_inside_out(open_cube, write_surf, tmp_path):
    """pymeshfix can invert a mesh; the repair must normalise the sign.

    On a non-oriented input pymeshfix may return a consistently-wound but
    entirely inside-out mesh. That passes closed/oriented/Euler checks while
    inverting everything downstream that samples along the normal. Observed on
    a real subject whose gray/white intensity means came out swapped.
    """
    vertices, faces = open_cube
    faces = faces.copy()
    faces[0] = faces[0][::-1]  # non-oriented input, the case that triggers it
    src = write_surf("lh.orig.premesh", vertices, faces)

    info = repair_surface_pymeshfix(src, tmp_path / "out")

    assert info["is_closed"]
    assert info["is_outward"] is True, "repair returned an inverted surface"
    assert info["signed_volume"] > 0
