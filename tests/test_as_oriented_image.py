"""Unit tests for orientation recovery (utils/mri.py::as_oriented_image).

A NIfTI with ``qform_code == 0`` and ``sform_code == 0`` stores no spatial
orientation. Readers do not fail on it — they each invent a different fallback
(nibabel/FSL: centred LAS; ITK/ANTs: corner-origin LPS), so one grid silently
means two geometries to two steps of the same pipeline. Observed in the wild on
a dataset whose anatomicals had been stripped of both codes by an upstream FSL
5.0.11 step, while the bolds from the same sessions kept ``sform_code == 2``.

These exercise the pure image->image layer. The path-level behaviour that composes
it lives in test_normalize_anat_input.py.
"""

import numpy as np
import nibabel as nib

from nhp_mri_prep.utils.mri import as_oriented_image


# Deliberately anisotropic and non-identity, so a dropped or reordered axis would
# be visible in the assertions below.
_AFFINE = np.diag([0.5, 0.5, 1.5, 1.0])


def _img(shape, affine=_AFFINE, code=2, dtype=np.int16, seed=0, scl_nan=False):
    """Build an in-memory NIfTI with unscaled data (so equality can be exact).

    ``code=0`` produces the defect under test: no qform and no sform.
    """
    rng = np.random.RandomState(seed)
    data = rng.randint(0, 4096, size=shape).astype(dtype)
    img = nib.Nifti1Image(data, affine)
    img.header.set_data_dtype(dtype)
    img.set_qform(affine, code=code)
    img.set_sform(affine, code=code)
    if scl_nan:
        # The real files carry nan scaling; nibabel reads that as "no scaling",
        # but it must survive a rewrite without corrupting the voxel values.
        img.header["scl_slope"] = np.nan
        img.header["scl_inter"] = np.nan
    return img


# --------------------------------------------------------------------------
# Images that already declare an orientation are left alone
# --------------------------------------------------------------------------


def test_image_with_sform_is_returned_untouched():
    src = _img((8, 8, 6), code=2)

    out, action = as_oriented_image(src)

    assert action == "unchanged"
    # Same object, so nothing is read, re-quantized, or copied.
    assert out is src


def test_qform_alone_is_enough_to_be_left_alone():
    """Only one of the two codes needs to be set for the header to be usable."""
    src = _img((8, 8, 6), code=0)
    src.set_qform(_AFFINE, code=2)

    out, action = as_oriented_image(src)

    assert action == "unchanged"
    assert out is src


# --------------------------------------------------------------------------
# Images with neither code get the fallback stamped in
# --------------------------------------------------------------------------


def test_missing_orientation_is_stamped_with_the_base_affine():
    src = _img((8, 8, 6), code=0)

    out, action = as_oriented_image(src)

    assert action == "assumed-LAS-centered"
    assert int(out.header["qform_code"]) == 2
    assert int(out.header["sform_code"]) == 2
    assert "".join(nib.aff2axcodes(out.affine)) == "LAS"

    # The whole point: the geometry written is the one nibabel/FSL were already
    # assuming, so nothing downstream shifts. Only ITK's view of it changes.
    assert np.allclose(out.affine, src.header.get_base_affine())
    assert np.allclose(out.affine, src.affine)


def test_repair_is_header_only_and_leaves_voxels_bit_identical():
    src = _img((8, 8, 6), code=0)

    out, _ = as_oriented_image(src)

    assert np.array_equal(np.asanyarray(src.dataobj), np.asanyarray(out.dataobj))
    assert out.get_data_dtype() == np.int16


def test_nan_scaling_does_not_corrupt_the_voxel_data(tmp_path):
    """The real inputs carry scl_slope=nan/scl_inter=nan alongside int16 data.

    Round-tripping through get_fdata() would rescale to float and change the
    stored values; this pins that it does not happen, through a real save/load
    since the nan scaling only materializes on disk.
    """
    src_path = tmp_path / "anat.nii.gz"
    nib.save(_img((8, 8, 6), code=0, scl_nan=True), str(src_path))
    src = nib.load(str(src_path))

    out, action = as_oriented_image(src)

    dst = tmp_path / "out.nii.gz"
    nib.save(out, str(dst))

    assert action == "assumed-LAS-centered"
    before = np.asanyarray(nib.load(str(src_path)).dataobj)
    after = np.asanyarray(nib.load(str(dst)).dataobj)
    assert np.array_equal(before, after)
    assert nib.load(str(dst)).get_data_dtype() == np.int16


def test_source_image_is_never_mutated():
    src = _img((8, 8, 6), code=0)

    as_oriented_image(src)

    # The caller's image must be left alone; only the returned copy is repaired.
    assert int(src.header["qform_code"]) == 0
    assert int(src.header["sform_code"]) == 0


# --------------------------------------------------------------------------
# Regression pin against the dataset that motivated this
# --------------------------------------------------------------------------


def test_recovers_the_convention_the_matching_bold_stored_explicitly():
    """The affine we assume must equal the one the site actually wrote elsewhere.

    In the motivating dataset the anatomicals had no orientation, but the bolds
    from the same sessions carried an explicit sform_code=2 whose matrix is
    exactly this centred-LAS form. That agreement is what justifies the
    assumption, so it is pinned here on the bold's real grid.
    """
    shape = (88, 88, 32)
    zooms = (1.215909, 1.2159091, 1.235288)
    # The matrix observed in the raw bold's stored sform.
    expected = np.array(
        [
            [-zooms[0], 0.0, 0.0, (shape[0] - 1) / 2 * zooms[0]],
            [0.0, zooms[1], 0.0, -(shape[1] - 1) / 2 * zooms[1]],
            [0.0, 0.0, zooms[2], -(shape[2] - 1) / 2 * zooms[2]],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    src = _img(shape, affine=np.diag(list(zooms) + [1.0]), code=0)

    out, _ = as_oriented_image(src)

    assert np.allclose(out.affine, expected, atol=1e-4)
