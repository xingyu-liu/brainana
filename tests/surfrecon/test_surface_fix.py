"""Tests for surface validation and orientation fixing.

The central point: Euler characteristic alone does not characterise a good
surface. ``badwind_cube`` is closed with Euler 2 and still broken, which is why
the pipeline checks closed AND oriented AND euler together.
"""

import pytest

from fastsurfer_surfrecon.processing.surface_fix import (
    SurfaceInvariantError,
    assert_surface_invariants,
    fix_surface_orientation,
    validate_surface,
)


# --- validate_surface --------------------------------------------------------


def test_validate_reports_healthy_mesh(closed_cube, write_surf):
    info = validate_surface(write_surf("lh.orig", *closed_cube))

    assert info["exists"] and info["readable"]
    assert info["is_closed"] and info["is_oriented"]
    assert info["euler"] == 2
    assert info["n_vertices"] == 8 and info["n_faces"] == 12
    assert info["error"] is None


def test_validate_reports_open_mesh(open_cube, write_surf):
    info = validate_surface(write_surf("lh.orig", *open_cube))
    assert info["readable"]
    assert not info["is_closed"]
    assert info["euler"] == 1


def test_validate_detects_bad_winding_that_euler_misses(badwind_cube, write_surf):
    """Closed and Euler 2, yet not oriented -- the case euler-only checks pass."""
    info = validate_surface(write_surf("lh.orig", *badwind_cube))

    assert info["is_closed"] is True
    assert info["euler"] == 2
    assert info["is_oriented"] is False


def test_validate_missing_file(tmp_path):
    info = validate_surface(tmp_path / "nope")
    assert info["exists"] is False and info["readable"] is False


def test_validate_distinguishes_unreadable_from_broken(tmp_path):
    """A read failure must be reported as such, not as 'this mesh is bad'."""
    corrupt = tmp_path / "lh.orig"
    corrupt.write_bytes(b"\xff\xff\xfe garbage")

    info = validate_surface(corrupt)

    assert info["exists"] is True
    assert info["readable"] is False
    assert info["error"], "cause of the read failure was not recorded"


def test_validate_returns_builtin_types(closed_cube, write_surf):
    """lapy returns numpy scalars; the report must stay JSON-serialisable."""
    import json

    info = validate_surface(write_surf("lh.orig", *closed_cube))
    json.dumps(info)  # must not raise
    assert type(info["is_closed"]) is bool
    assert type(info["euler"]) is int


# --- assert_surface_invariants -----------------------------------------------


def test_assert_passes_on_healthy_mesh(closed_cube, write_surf):
    info = assert_surface_invariants(
        write_surf("lh.orig", *closed_cube), min_vertices=0
    )
    assert info["euler"] == 2


def test_assert_raises_on_open_mesh(open_cube, write_surf):
    with pytest.raises(SurfaceInvariantError, match="not closed"):
        assert_surface_invariants(write_surf("lh.orig", *open_cube), min_vertices=0)


def test_assert_raises_on_bad_winding(badwind_cube, write_surf):
    with pytest.raises(SurfaceInvariantError, match="not consistently oriented"):
        assert_surface_invariants(write_surf("lh.orig", *badwind_cube), min_vertices=0)


def test_assert_message_names_the_actual_state(open_cube, write_surf):
    """The error must be diagnosable without re-running anything."""
    with pytest.raises(SurfaceInvariantError) as excinfo:
        assert_surface_invariants(
            write_surf("lh.orig", *open_cube), min_vertices=0, context="rh pre-orig"
        )

    message = str(excinfo.value)
    assert "rh pre-orig" in message
    assert "V=8" in message and "F=10" in message
    assert "closed=False" in message and "euler=1" in message


def test_assert_catches_near_empty_mesh(closed_cube, write_surf):
    """A 'successful' run that produced 8 vertices is not a success."""
    with pytest.raises(SurfaceInvariantError, match="only 8 vertices"):
        assert_surface_invariants(write_surf("lh.orig", *closed_cube))


def test_assert_strict_false_logs_instead_of_raising(open_cube, write_surf, caplog):
    info = assert_surface_invariants(
        write_surf("lh.orig", *open_cube), min_vertices=0, strict=False
    )
    assert info["is_closed"] is False
    assert "not closed" in caplog.text


def test_assert_skips_euler_when_none(open_cube, write_surf):
    """euler=None is for surfaces legitimately not yet genus 0 (e.g. orig.nofix)."""
    with pytest.raises(SurfaceInvariantError) as excinfo:
        assert_surface_invariants(
            write_surf("lh.orig", *open_cube), euler=None, min_vertices=0
        )
    assert "euler" not in str(excinfo.value).split("violations:")[1].split("actual:")[0]


# --- fix_surface_orientation -------------------------------------------------


def test_fix_orientation_repairs_bad_winding(badwind_cube, write_surf):
    surf = write_surf("lh.orig", *badwind_cube)
    backup = surf.parent / "lh.orig.noorient"

    fixed = fix_surface_orientation(surf, backup_path=backup)

    assert fixed is True
    assert backup.exists(), "backup was not created before mutating the surface"
    assert validate_surface(surf)["is_oriented"] is True


def test_fix_orientation_noop_on_healthy_mesh(closed_cube, write_surf):
    surf = write_surf("lh.orig", *closed_cube)
    before = surf.read_bytes()

    assert fix_surface_orientation(surf) is False
    assert surf.read_bytes() == before, "healthy surface was rewritten"


def test_fix_orientation_refuses_open_mesh(open_cube, write_surf):
    """Regression for the sub-01 failure: open AND non-oriented.

    This is exactly the state ``rh.orig`` was in (closed=False, oriented=False).
    orient_() cannot orient a mesh with boundary edges, so the old code ran it,
    changed nothing, logged "Fixed and saved", and returned True -- letting the
    broken mesh travel four more steps before dying somewhere less diagnosable.
    """
    vertices, faces = open_cube
    faces = faces.copy()
    faces[0] = faces[0][::-1]  # open *and* inconsistently wound
    surf = write_surf("lh.orig", vertices, faces)

    assert validate_surface(surf)["is_oriented"] is False, "fixture precondition"

    with pytest.raises(SurfaceInvariantError, match="not closed"):
        fix_surface_orientation(surf)


def test_fix_orientation_leaves_open_but_oriented_mesh_alone(open_cube, write_surf):
    """Contract boundary: this function fixes orientation, nothing else.

    An open mesh that is already consistently wound has nothing for this
    function to do. Closedness of `orig` is enforced separately, by the s12
    gate and postcondition -- not smuggled in here.
    """
    surf = write_surf("lh.orig", *open_cube)
    before = surf.read_bytes()

    assert fix_surface_orientation(surf) is False
    assert surf.read_bytes() == before


# --- inside-out detection ----------------------------------------------------


def _inverted(vertices, faces):
    """Same geometry, every face wound the other way: consistent but inside-out."""
    return vertices, faces[:, ::-1].copy()


def test_validate_reports_normal_direction(closed_cube, write_surf):
    info = validate_surface(write_surf("lh.orig", *closed_cube))
    assert info["is_outward"] is True
    assert info["signed_volume"] > 0


def test_validate_detects_inside_out(closed_cube, write_surf):
    """An inverted mesh passes every topology check but is still wrong.

    is_oriented() only tests that neighbouring faces agree, so it is True here;
    closedness and Euler are unaffected by winding direction. Only the sign of
    the enclosed volume distinguishes this from a healthy surface.
    """
    info = validate_surface(write_surf("lh.orig", *_inverted(*closed_cube)))

    assert info["is_closed"] is True
    assert info["is_oriented"] is True
    assert info["euler"] == 2
    assert info["is_outward"] is False
    assert info["signed_volume"] < 0


def test_assert_raises_on_inside_out(closed_cube, write_surf):
    with pytest.raises(SurfaceInvariantError, match="inside-out"):
        assert_surface_invariants(
            write_surf("lh.orig", *_inverted(*closed_cube)), min_vertices=0
        )


def test_fix_orientation_flips_inside_out_mesh(closed_cube, write_surf):
    """Regression: pymeshfix can return a consistent but inverted mesh.

    Anything sampling along the normal then reads inside for outside. This was
    observed in a real subject whose gray/white intensity means came out
    swapped, with no error reported anywhere.
    """
    import nibabel.freesurfer.io as fsio

    surf = write_surf("lh.orig", *_inverted(*closed_cube))
    backup = surf.parent / "lh.orig.noorient"

    assert validate_surface(surf)["is_oriented"] is True, "fixture precondition"

    flipped = fix_surface_orientation(surf, backup_path=backup)

    assert flipped is True
    assert validate_surface(surf)["is_outward"] is True
    assert backup.exists()

    # Winding changed, geometry did not.
    original_vertices = closed_cube[0]
    vertices, _ = fsio.read_geometry(surf)
    assert (vertices == original_vertices).all()


def test_fix_orientation_leaves_correct_mesh_untouched(closed_cube, write_surf):
    surf = write_surf("lh.orig", *closed_cube)
    before = surf.read_bytes()

    assert fix_surface_orientation(surf) is False
    assert surf.read_bytes() == before
