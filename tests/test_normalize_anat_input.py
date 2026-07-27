"""Unit tests for the ingest normalizer (utils/mri.py::normalize_anat_input).

This is the single path-level entry point every anatomical passes through. It
composes the pure repairs in memory so a file needing three of them still costs
one load and one save, forces the container to .nii.gz, and reports the header
defects that have no safe automatic fix.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import nibabel as nib
import pytest

from nhp_mri_prep.utils.mri import ensure_3d, inspect_header, normalize_anat_input


_AFFINE = np.diag([0.5, 0.5, 1.5, 1.0])


def _img(shape=(8, 8, 6), affine=_AFFINE, code=2, dtype=np.int16):
    data = np.random.RandomState(0).randint(0, 4096, size=shape).astype(dtype)
    img = nib.Nifti1Image(data, affine)
    img.header.set_data_dtype(dtype)
    img.set_qform(affine, code=code)
    img.set_sform(affine, code=code)
    return img


# --------------------------------------------------------------------------
# The no-op path: well-formed input must stay byte-for-byte identical
# --------------------------------------------------------------------------


def test_wellformed_gzipped_input_writes_nothing(tmp_path):
    src = tmp_path / "sub-01_T1w.nii.gz"
    nib.save(_img(), str(src))
    dst_dir = tmp_path / "input_normalized"

    out, report = normalize_anat_input(src, dst_dir / src.name)

    assert out == src
    assert not dst_dir.exists()
    assert report == {
        "dim": "unchanged",
        "orientation": "unchanged",
        "geometry": "unchanged",
        "warnings": [],
    }


# --------------------------------------------------------------------------
# Container format
# --------------------------------------------------------------------------


def test_uncompressed_input_is_gzipped_even_when_otherwise_clean(tmp_path):
    src = tmp_path / "sub-01_T1w.nii"
    nib.save(_img(), str(src))

    out, report = normalize_anat_input(src, tmp_path / "norm" / src.name)

    assert out == tmp_path / "norm" / "sub-01_T1w.nii.gz"
    assert out.exists()
    # No repair fired; the rewrite is purely the container.
    assert report["dim"] == report["orientation"] == report["geometry"] == "unchanged"
    with open(out, "rb") as f:
        assert f.read(2) == b"\x1f\x8b"
    assert np.array_equal(
        np.asanyarray(nib.load(str(src)).dataobj),
        np.asanyarray(nib.load(str(out)).dataobj),
    )


def test_output_extension_is_forced_to_nii_gz(tmp_path):
    """A caller naming a .nii destination still gets a gzipped file."""
    src = tmp_path / "sub-01_T1w.nii.gz"
    nib.save(_img(shape=(8, 8, 6, 1)), str(src))

    out, _ = normalize_anat_input(src, tmp_path / "norm" / "sub-01_T1w.nii")

    assert out.name == "sub-01_T1w.nii.gz"
    assert out.exists()


def test_bids_stem_is_preserved(tmp_path):
    """Synthesis parses BIDS entities out of the basename, so it must survive."""
    src = tmp_path / "sub-01_ses-a_run-2_T1w.nii"
    nib.save(_img(), str(src))

    out, _ = normalize_anat_input(src, tmp_path / "norm" / src.name)

    assert out.name == "sub-01_ses-a_run-2_T1w.nii.gz"


# --------------------------------------------------------------------------
# Composition: several defects, one read and one write
# --------------------------------------------------------------------------


def test_all_three_repairs_compose_into_one_written_file(tmp_path):
    src = tmp_path / "sub-01_T1w.nii"
    # 4D singleton frame axis + no stored orientation, in an uncompressed container.
    img = _img(shape=(8, 8, 6, 1), code=0)
    nib.save(img, str(src))
    dst_dir = tmp_path / "input_normalized"

    out, report = normalize_anat_input(src, dst_dir / src.name)

    assert report["dim"] == "squeezed"
    assert report["orientation"] == "assumed-LAS-centered"
    assert out == dst_dir / "sub-01_T1w.nii.gz"

    # Exactly one file written, not one per repair.
    assert [p.name for p in dst_dir.iterdir()] == ["sub-01_T1w.nii.gz"]

    written = nib.load(str(out))
    assert written.shape == (8, 8, 6)
    assert int(written.header["qform_code"]) == 2
    assert int(written.header["sform_code"]) == 2


def test_orientation_repair_precedes_geometry_reconciliation(tmp_path):
    """After stamping both codes the forms agree, so reconciliation is a no-op."""
    src = tmp_path / "sub-01_T1w.nii.gz"
    nib.save(_img(code=0), str(src))

    _, report = normalize_anat_input(src, tmp_path / "norm" / src.name)

    assert report["orientation"] == "assumed-LAS-centered"
    assert report["geometry"] == "unchanged"


def test_disagreeing_forms_are_reported_as_geometry(tmp_path):
    src = tmp_path / "sub-01_T1w.nii.gz"
    img = _img(code=1)
    # Same voxel sizes, shifted origin — a disagreement no shape or resolution
    # check would catch.
    qform = _AFFINE.copy()
    qform[0, 3] += 11.0
    img.set_qform(qform, code=1)
    nib.save(img, str(src))

    out, report = normalize_anat_input(src, tmp_path / "norm" / src.name)

    assert report["geometry"] == "qform-set-from-sform"
    written = nib.load(str(out))
    assert np.allclose(written.get_qform(), written.get_sform(), atol=1e-3)


# --------------------------------------------------------------------------
# Header inspection: reported, never repaired
# --------------------------------------------------------------------------


def test_metre_units_are_reported_not_rescaled(tmp_path):
    src = tmp_path / "sub-01_T1w.nii.gz"
    img = _img(affine=np.diag([0.0005, 0.0005, 0.0015, 1.0]))
    img.header.set_xyzt_units(xyz="meter")
    nib.save(img, str(src))

    out, report = normalize_anat_input(src, tmp_path / "norm" / src.name)

    assert len(report["warnings"]) == 1
    assert "not mm" in report["warnings"][0]
    # Reported, not repaired: nothing was rewritten and the zooms are untouched.
    assert out == src
    assert nib.load(str(out)).header.get_zooms()[0] == pytest.approx(0.0005)


def test_pixdim_affine_mismatch_is_reported():
    img = _img()
    # Corrupt pixdim without touching the affine — the self-inconsistency that
    # FastSurfer aborts on during segmentation.
    img.header["pixdim"][1:4] = [9.0, 9.0, 9.0]

    findings = inspect_header(img)

    assert len(findings) == 1
    assert "disagrees with the affine" in findings[0]


def test_clean_header_reports_nothing():
    assert inspect_header(_img()) == []


def test_stamped_orientation_does_not_trip_the_pixdim_check():
    """The base affine is derived from pixdim, so the two agree by construction."""
    src = _img(code=0)

    from nhp_mri_prep.utils.mri import as_oriented_image

    out, _ = as_oriented_image(src)

    assert inspect_header(out) == []


# --------------------------------------------------------------------------
# The in-place guard
# --------------------------------------------------------------------------


def test_writing_onto_the_input_is_refused(tmp_path):
    src = tmp_path / "sub-01_T1w.nii.gz"
    nib.save(_img(shape=(8, 8, 6, 1)), str(src))

    with pytest.raises(ValueError, match="onto itself"):
        normalize_anat_input(src, src)


def test_ensure_3d_also_refuses_to_write_onto_the_input(tmp_path):
    src = tmp_path / "anat.nii.gz"
    nib.save(_img(shape=(8, 8, 6, 1)), str(src))

    with pytest.raises(ValueError, match="onto itself"):
        ensure_3d(src, src)


def _run_in_subprocess(tmp_path, name, body):
    """Run a snippet that builds a 4D, orientation-less .nii at *name* then acts on it.

    A subprocess because the failure being guarded against is SIGBUS, not an
    exception: nibabel mmaps an uncompressed .nii, np.asanyarray hands back a view
    onto that mapping, and nib.save truncates the file underneath it. The
    interpreter dies on the next page fault with exit 135 and no traceback — nothing
    a caller could catch, and nothing pytest could survive in-process.
    """
    script = (
        textwrap.dedent(
            f"""
        import numpy as np, nibabel as nib
        from pathlib import Path
        from nhp_mri_prep.utils.mri import ensure_3d, normalize_anat_input

        p = Path({str(tmp_path)!r}) / {name!r}
        aff = np.diag([0.5, 0.5, 1.5, 1.0])
        data = np.random.RandomState(0).randint(0, 4096, (64, 64, 40, 1)).astype(np.int16)
        img = nib.Nifti1Image(data, aff)
        img.header.set_data_dtype(np.int16)
        img.set_qform(aff, code=0); img.set_sform(aff, code=0)
        nib.save(img, str(p))
    """
        )
        + textwrap.dedent(body)
    )
    return subprocess.run([sys.executable, "-c", script], capture_output=True)


def test_ensure_3d_in_place_on_nii_raises_instead_of_killing_the_process(tmp_path):
    """ensure_3d takes its output path verbatim, so the guard is what saves it."""
    result = _run_in_subprocess(
        tmp_path,
        "e3d.nii",
        """
        try:
            ensure_3d(p, p)
        except ValueError:
            raise SystemExit(0)
        raise SystemExit(1)
        """,
    )

    assert result.returncode == 0, (
        f"expected a ValueError (exit 0); got exit {result.returncode}. "
        f"Exit 135 means the SIGBUS guard regressed. stderr:\n"
        f"{result.stderr.decode(errors='replace')}"
    )


def test_normalize_anat_input_on_nii_is_structurally_safe_from_the_same_path(tmp_path):
    """Forcing .nii.gz means the output can never be the .nii input, mmap and all.

    This is the stronger protection — not a guard that catches the mistake, but a
    shape that cannot make it. Pinned here because removing the extension forcing
    would silently reintroduce the SIGBUS, and the in-process tests would not notice.
    """
    result = _run_in_subprocess(
        tmp_path,
        "norm.nii",
        """
        out, report = normalize_anat_input(p, p)
        assert out == p.with_suffix(".nii.gz"), out
        assert out.exists() and p.exists()
        assert nib.load(str(out)).shape == (64, 64, 40)
        raise SystemExit(0)
        """,
    )

    assert result.returncode == 0, (
        f"expected a clean run (exit 0); got exit {result.returncode}. "
        f"Exit 135 means the .nii.gz forcing regressed. stderr:\n"
        f"{result.stderr.decode(errors='replace')}"
    )


def test_accepts_str_paths(tmp_path):
    src = tmp_path / "sub-01_T1w.nii.gz"
    nib.save(_img(shape=(8, 8, 6, 1)), str(src))

    out, report = normalize_anat_input(str(src), str(tmp_path / "norm" / src.name))

    assert isinstance(out, Path)
    assert report["dim"] == "squeezed"
