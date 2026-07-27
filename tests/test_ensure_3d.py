"""Unit tests for 3-D dimensionality normalization (utils/mri.py).

Some scanners emit anatomicals with a trailing singleton frame axis, e.g.
(144, 144, 60, 1) with dim[0] == 4. These are geometrically 3-D but break any code
that assumes ndim == 3 — notably nibabel's resample_to_output, which raises. The
same class of bug previously bit the functional path; see
test_confounds.py::test_compute_confounds_accepts_4d_singleton_mask.
"""

from pathlib import Path

import numpy as np
import nibabel as nib
import pytest

from nhp_mri_prep.utils.mri import as_3d_image, ensure_3d


# Deliberately anisotropic, so the affine is not the identity and a dropped or
# reordered axis would be visible in the assertions below.
_AFFINE = np.diag([0.5, 0.5, 1.5, 1.0])


def _img(shape, dtype=np.int16, intent=None, seed=0):
    """Build an in-memory NIfTI with unscaled data (so equality can be exact)."""
    rng = np.random.RandomState(seed)
    data = rng.randint(0, 4096, size=shape).astype(dtype)
    img = nib.Nifti1Image(data, _AFFINE)
    img.header.set_data_dtype(dtype)
    img.set_qform(_AFFINE, code=2)
    img.set_sform(_AFFINE, code=2)
    if intent is not None:
        img.header["intent_code"] = intent
    return img


# --------------------------------------------------------------------------
# as_3d_image — in-memory semantics
# --------------------------------------------------------------------------


def test_3d_input_is_returned_untouched():
    img = _img((8, 8, 6), dtype=np.float32)
    out, action = as_3d_image(img)

    assert action == "unchanged"
    # Same object: no data read, no rewrite, no dtype change, no re-quantization.
    assert out is img
    assert out.get_data_dtype() == np.float32


def test_trailing_singleton_is_squeezed_losslessly():
    img = _img((8, 8, 6, 1))
    raw = np.asanyarray(img.dataobj)

    out, action = as_3d_image(img)

    assert action == "squeezed"
    assert out.shape == (8, 8, 6)
    assert out.get_data_dtype() == np.int16  # no float upcast
    assert np.array_equal(out.affine, _AFFINE)
    assert int(out.header["qform_code"]) == 2
    assert int(out.header["sform_code"]) == 2
    assert out.header.get_zooms() == pytest.approx((0.5, 0.5, 1.5))
    assert np.array_equal(np.asanyarray(out.dataobj), raw[..., 0])


def test_multi_volume_is_mean_collapsed_as_float32():
    img = _img((8, 8, 6, 3))
    raw = np.asanyarray(img.dataobj)

    out, action = as_3d_image(img)

    assert action == "mean"
    assert out.shape == (8, 8, 6)
    # float32, not the int16 source dtype — Nifti1Image honours the header's
    # dtype, so without an explicit override the mean would be truncated.
    assert out.get_data_dtype() == np.float32
    assert np.allclose(np.asanyarray(out.dataobj), raw.mean(axis=-1), rtol=1e-5)
    assert out.header.get_zooms() == pytest.approx((0.5, 0.5, 1.5))


def test_vector_intent_is_refused():
    # ANTs displacement field: (X, Y, Z, 1, 3), NIFTI_INTENT_VECTOR.
    img = _img((8, 8, 6, 1, 3), intent=1007)
    with pytest.raises(ValueError, match="intent"):
        as_3d_image(img)


def test_five_dimensional_is_refused_even_without_intent():
    img = _img((8, 8, 6, 1, 3))
    with pytest.raises(ValueError):
        as_3d_image(img)


def test_fewer_than_three_dimensions_is_refused():
    img = _img((8, 8))
    with pytest.raises(ValueError):
        as_3d_image(img)


# --------------------------------------------------------------------------
# ensure_3d — file behaviour
# --------------------------------------------------------------------------


def test_3d_file_writes_nothing_and_returns_input_path(tmp_path):
    src = tmp_path / "anat.nii.gz"
    nib.save(_img((8, 8, 6)), str(src))
    dst = tmp_path / "out.nii.gz"

    out_path, action = ensure_3d(src, dst)

    assert action == "unchanged"
    assert out_path == src
    assert not dst.exists()


def test_4d_file_is_collapsed_without_modifying_the_input(tmp_path):
    src = tmp_path / "anat.nii.gz"
    nib.save(_img((8, 8, 6, 1)), str(src))
    dst = tmp_path / "input_3d" / "anat.nii.gz"

    out_path, action = ensure_3d(src, dst)

    assert action == "squeezed"
    assert out_path == dst
    written = nib.load(str(dst))
    assert written.shape == (8, 8, 6)
    assert int(written.header["dim"][0]) == 3
    assert written.get_data_dtype() == np.int16

    # Nextflow stages task inputs read-only, so the source must be untouched.
    assert nib.load(str(src)).shape == (8, 8, 6, 1)


def test_rewrite_without_a_destination_is_refused(tmp_path):
    src = tmp_path / "anat.nii.gz"
    nib.save(_img((8, 8, 6, 1)), str(src))

    with pytest.raises(ValueError, match="no output path"):
        ensure_3d(src)


def test_accepts_str_paths(tmp_path):
    src = tmp_path / "anat.nii.gz"
    nib.save(_img((8, 8, 6, 1)), str(src))
    dst = tmp_path / "out.nii.gz"

    out_path, action = ensure_3d(str(src), str(dst))

    assert action == "squeezed"
    assert isinstance(out_path, Path)
    assert nib.load(str(out_path)).shape == (8, 8, 6)
