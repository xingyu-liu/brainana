"""Unit tests for qform/sform reconciliation (utils/mri.py).

A NIfTI can store its geometry twice, and nothing enforces that the two agree.
When they disagree, which one wins is the *reader's* policy: nibabel, FSL and
every other brainana step read the sform, while FastSurfer's
``check_affine_in_nifti`` detects the mismatch and resolves toward the qform.
Left unreconciled, brainana registers against one grid and segments against
another.
"""

import numpy as np
import nibabel as nib

from nhp_mri_prep.utils.mri import reconcile_qform_sform


_SFORM = np.diag([0.5, 0.5, 1.5, 1.0])
# Same voxel sizes, different origin — a plausible disagreement rather than a
# contrived one, and one that no shape or resolution check would catch.
_QFORM = np.array(
    [
        [0.5, 0.0, 0.0, 12.0],
        [0.0, 0.5, 0.0, -7.0],
        [0.0, 0.0, 1.5, 3.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)


def _img(sform=_SFORM, qform=_SFORM, s_code=1, q_code=1, shape=(8, 8, 6)):
    data = np.random.RandomState(0).randint(0, 4096, size=shape).astype(np.int16)
    img = nib.Nifti1Image(data, sform)
    img.header.set_data_dtype(np.int16)
    img.set_sform(sform, code=s_code)
    img.set_qform(qform, code=q_code)
    return img


def test_agreeing_forms_are_returned_untouched():
    src = _img(sform=_SFORM, qform=_SFORM)

    out, action = reconcile_qform_sform(src)

    assert action == "unchanged"
    assert out is src


def test_sform_only_is_untouched():
    """One form present is unambiguous — there is nothing to reconcile."""
    src = _img(qform=_QFORM, q_code=0)

    out, action = reconcile_qform_sform(src)

    assert action == "unchanged"
    assert out is src


def test_qform_only_is_untouched():
    src = _img(sform=_SFORM, s_code=0, qform=_QFORM, q_code=1)

    out, action = reconcile_qform_sform(src)

    assert action == "unchanged"
    assert out is src


def test_neither_form_is_untouched():
    """The no-orientation-at-all case belongs to as_oriented_image, not here."""
    src = _img(s_code=0, q_code=0)

    out, action = reconcile_qform_sform(src)

    assert action == "unchanged"
    assert out is src


def test_disagreement_resolves_toward_the_sform():
    src = _img(sform=_SFORM, qform=_QFORM, s_code=1, q_code=1)

    out, action = reconcile_qform_sform(src)

    assert action == "qform-set-from-sform"
    assert np.allclose(out.get_sform(), _SFORM)
    assert np.allclose(out.get_qform(), _SFORM, atol=1e-4)
    # img.affine is the sform, so the pipeline's view of the geometry is unchanged —
    # that is exactly why the sform is the safe side to resolve toward.
    assert np.allclose(out.affine, src.affine)


def test_the_sform_code_is_preserved_not_forced():
    """sform_code carries meaning (1 scanner, 2 aligned, 4 MNI); keep it."""
    src = _img(sform=_SFORM, qform=_QFORM, s_code=4, q_code=1)

    out, _ = reconcile_qform_sform(src)

    assert int(out.header["sform_code"]) == 4
    assert int(out.header["qform_code"]) == 4


def test_reconciliation_is_header_only():
    src = _img(sform=_SFORM, qform=_QFORM)

    out, _ = reconcile_qform_sform(src)

    assert np.array_equal(np.asanyarray(src.dataobj), np.asanyarray(out.dataobj))
    assert out.get_data_dtype() == np.int16


def test_source_image_is_never_mutated():
    src = _img(sform=_SFORM, qform=_QFORM)

    reconcile_qform_sform(src)

    assert np.allclose(src.get_qform(), _QFORM, atol=1e-4)


def test_tiny_differences_are_tolerated():
    """Round-trip noise in the quaternion encoding must not trigger a rewrite."""
    noisy = _SFORM.copy()
    noisy[0, 3] += 1e-5
    src = _img(sform=_SFORM, qform=noisy)

    _, action = reconcile_qform_sform(src)

    assert action == "unchanged"
