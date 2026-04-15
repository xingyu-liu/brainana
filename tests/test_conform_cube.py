"""
Regression tests for img_size='cube' affine offset handling.

The key invariant is geometric: after cube padding, native-space points must land at
indices shifted by p_before = floor((cube_dim - native_dim) / 2) per axis.
"""

from __future__ import annotations

import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

_repo = Path(__file__).resolve().parent.parent
_src = _repo / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fastsurfer_nn.data_loader.conform import conform, map_image  # noqa: E402


def _make_ras_nifti(
    shape: tuple[int, int, int], zooms: tuple[float, float, float] = (1.0, 1.0, 1.0)
) -> nib.Nifti1Image:
    """Create a simple RAS NIfTI with random intensities."""
    affine = np.diag([zooms[0], zooms[1], zooms[2], 1.0]).astype(np.float64)
    data = np.random.default_rng(42).random(shape, dtype=np.float32)
    return nib.Nifti1Image(data, affine)


def _data_xyz(img: nib.spatialimages.SpatialImage) -> np.ndarray:
    arr = np.asarray(img.dataobj, dtype=np.float32)
    return np.squeeze(arr, axis=-1) if arr.ndim == 4 and arr.shape[-1] == 1 else arr


@pytest.mark.parametrize("shape", [(213, 96, 140), (11, 7, 9), (32, 24, 28)])
def test_cube_affine_maps_native_center_with_floor_half_padding(shape: tuple[int, int, int]) -> None:
    """
    Native center in world coordinates must map to p_before + native_center in cube voxels.

    This directly checks the floor-half padding contract and catches 0.5-voxel drift.
    """
    img = _make_ras_nifti(shape)
    out = conform(
        img,
        img_size="cube",
        vox_size="min",
        orientation="native",
        dtype=np.float32,
        rescale=None,
        order=1,
        verbose=False,
    )
    cube_shape = _data_xyz(out).shape
    assert cube_shape[0] == cube_shape[1] == cube_shape[2], "expected cubic output"

    p_before = np.array([(cube_shape[i] - shape[i]) // 2 for i in range(3)], dtype=np.float64)
    native_center = np.array(shape, dtype=np.float64) / 2.0
    expected_cube_center = p_before + native_center

    native_center_world = img.affine @ np.append(native_center, 1.0)
    cube_center = (np.linalg.inv(out.affine) @ native_center_world)[:3]

    np.testing.assert_allclose(
        cube_center,
        expected_cube_center,
        atol=1e-6,
        err_msg=f"shape={shape}: cube affine center mapping mismatch",
    )


def test_segmentation_order0_resample_uses_same_p_before_shift() -> None:
    """
    A binary block label should be translated by exactly p_before under order=0 resampling.
    """
    base = _make_ras_nifti((213, 96, 140))
    seg = np.zeros(base.shape, dtype=np.int16)
    # Small interior cuboid to avoid boundary artifacts.
    seg[40:44, 20:24, 30:34] = 42
    seg_img = nib.Nifti1Image(seg, base.affine, base.header)

    t1_c = conform(
        base,
        img_size="cube",
        vox_size="min",
        orientation="native",
        dtype=np.float32,
        rescale=None,
        order=1,
        verbose=False,
    )
    seg_c = map_image(
        seg_img,
        t1_c.affine,
        _data_xyz(t1_c).shape,
        order=0,
        dtype=np.int16,
    )

    hits = np.argwhere(seg_c == 42)
    assert hits.size > 0, "label block lost after resample"

    cube_shape = _data_xyz(t1_c).shape
    p_before = np.array([(cube_shape[i] - base.shape[i]) // 2 for i in range(3)], dtype=int)
    expected_min = np.array([40, 20, 30], dtype=int) + p_before
    expected_max = np.array([43, 23, 33], dtype=int) + p_before

    got_min = hits.min(axis=0)
    got_max = hits.max(axis=0)
    assert np.array_equal(got_min, expected_min), f"min corner mismatch: got={got_min}, expected={expected_min}"
    assert np.array_equal(got_max, expected_max), f"max corner mismatch: got={got_max}, expected={expected_max}"
