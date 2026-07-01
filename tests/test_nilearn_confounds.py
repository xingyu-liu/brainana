"""Integration tests: brainana confounds with nilearn load_confounds + clean_img.

Mirrors the thalamus postprocessing workflow (motion + tissue nuisance regression and
Butterworth bandpass via clean_img) for strategies brainana actually produces.
"""

import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

pytest.importorskip("nilearn")
from nilearn.image import clean_img
from nilearn.interfaces.fmriprep import load_confounds

from nhp_mri_prep.operations.confounds import compute_confounds

_BIDS_PREFIX = "sub-test_task-rest_run-1"
_BOLD_NAME = f"{_BIDS_PREFIX}_space-T1w_desc-preproc_bold.nii.gz"
_N_VOLUMES = 20
_TR = 2.0


def _write_par(path: Path, n: int = _N_VOLUMES, spike_frame: int = None) -> None:
    rng = np.random.RandomState(0)
    if spike_frame is None:
        arr = np.cumsum(rng.normal(0, 0.01, size=(n, 6)), axis=0)
    else:
        # FSL .par columns are rotations (rad) then translations (mm); brainana scales rotations by
        # the 27 mm macaque radius, so even small base motion easily exceeds FD 0.25 mm. Use a tiny
        # sub-threshold baseline and inject one large translation jump so exactly one frame crosses
        # the threshold, forcing a single censored frame in nilearn's scrub strategy.
        arr = np.cumsum(rng.normal(0, 0.0003, size=(n, 6)), axis=0)
        arr[spike_frame:, 3] += 1.0  # trans_x jump of 1 mm at spike_frame
    np.savetxt(str(path), arr)


def _write_bids_run(tmp_path: Path, *, with_seg: bool = False, spike_frame: int = None) -> Path:
    """Write a minimal BIDS func derivative tree and return the BOLD path."""
    func_dir = tmp_path / "func"
    func_dir.mkdir(parents=True)

    rng = np.random.RandomState(3)
    affine = np.eye(4)
    shape = (8, 8, 8, _N_VOLUMES)
    bold_data = rng.normal(100, 5, size=shape).astype(np.float32)
    bold_f = func_dir / _BOLD_NAME
    nib.save(nib.Nifti1Image(bold_data, affine), str(bold_f))

    sidecar = Path(str(bold_f).replace(".nii.gz", ".json"))
    sidecar.write_text(json.dumps({"RepetitionTime": _TR}))

    par = func_dir / "mc.par"
    _write_par(par, spike_frame=spike_frame)

    mask_f = func_dir / f"{_BIDS_PREFIX}_space-T1w_desc-brain_mask.nii.gz"
    nib.save(nib.Nifti1Image(np.ones(shape[:3], dtype=np.uint8), affine), str(mask_f))

    seg_file = None
    seg_lut = None
    if with_seg:
        seg = np.zeros((10, 10, 10), dtype=np.int16)
        seg[2:8, 2:8, 2:8] = 2
        seg[0:3, 0:3, 0:3] = 4
        seg_file = func_dir / "aseg.nii.gz"
        nib.save(nib.Nifti1Image(seg, affine), str(seg_file))
        seg_lut = func_dir / "lut.tsv"
        import pandas as pd

        pd.DataFrame(
            {
                "index": [0, 2, 4],
                "name": ["Background", "Left-Cerebral-White-Matter", "Left-Lateral-Ventricle"],
            }
        ).to_csv(seg_lut, sep="\t", index=False)

    compute_confounds(
        bold_file=bold_f,
        motion_par_file=par,
        working_dir=func_dir / "work",
        output_prefix=str(func_dir / f"{_BIDS_PREFIX}_desc-confounds_timeseries"),
        brain_mask_file=mask_f,
        seg_file=seg_file,
        seg_lut_file=seg_lut,
    )
    return bold_f


def test_load_confounds_motion_full(tmp_path):
    bold_f = _write_bids_run(tmp_path, with_seg=False)

    confounds, sample_mask = load_confounds(str(bold_f), strategy=["motion"], motion="full")

    assert sample_mask is None
    assert confounds.shape == (_N_VOLUMES, 24)
    for base in ("trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"):
        assert base in confounds.columns
        assert f"{base}_derivative1" in confounds.columns
        assert f"{base}_power2" in confounds.columns
        assert f"{base}_derivative1_power2" in confounds.columns


def test_load_confounds_wm_csf_full(tmp_path):
    bold_f = _write_bids_run(tmp_path, with_seg=True)

    confounds, _ = load_confounds(
        str(bold_f),
        strategy=["motion", "wm_csf"],
        motion="full",
        wm_csf="full",
    )

    assert confounds.shape == (_N_VOLUMES, 32)
    for tissue in ("csf", "white_matter"):
        for suffix in ("", "_derivative1", "_power2", "_derivative1_power2"):
            assert f"{tissue}{suffix}" in confounds.columns


def test_load_confounds_global_signal(tmp_path):
    bold_f = _write_bids_run(tmp_path, with_seg=False)

    confounds, _ = load_confounds(
        str(bold_f),
        strategy=["motion", "global_signal"],
        motion="full",
        global_signal="full",
    )

    assert confounds.shape == (_N_VOLUMES, 28)
    for suffix in ("", "_derivative1", "_power2", "_derivative1_power2"):
        assert f"global_signal{suffix}" in confounds.columns


def test_load_confounds_wm_csf_without_seg_raises(tmp_path):
    # Tissue regressors (csf/white_matter) are only produced when a T1w segmentation is given.
    # Without it, requesting the wm_csf strategy must fail rather than silently return motion-only.
    bold_f = _write_bids_run(tmp_path, with_seg=False)

    with pytest.raises(ValueError, match="wm_csf"):
        load_confounds(
            str(bold_f),
            strategy=["motion", "wm_csf"],
            motion="full",
            wm_csf="full",
        )


def test_clean_img_with_brainana_confounds(tmp_path):
    bold_f = _write_bids_run(tmp_path, with_seg=True)

    confounds, _ = load_confounds(
        str(bold_f),
        strategy=["motion", "wm_csf"],
        motion="full",
        wm_csf="full",
    )
    cleaned = clean_img(
        str(bold_f),
        confounds=confounds,
        detrend=True,
        standardize="zscore_sample",
        high_pass=0.008,
        t_r=_TR,
    )

    assert cleaned.shape == nib.load(str(bold_f)).shape


def test_load_confounds_scrub_macaque_fd(tmp_path):
    spike_frame = 10
    bold_f = _write_bids_run(tmp_path, with_seg=False, spike_frame=spike_frame)

    # Use macaque FD threshold with scrub=0; set DVARS threshold high so only FD drives
    # outlier detection. The injected spike at `spike_frame` is the sole FD outlier, so nilearn
    # censors exactly that frame (scrub recomputes from framewise_displacement, not the
    # motion_outlier columns brainana writes).
    confounds, sample_mask = load_confounds(
        str(bold_f),
        strategy=["motion", "scrub"],
        motion="full",
        scrub=0,
        fd_threshold=0.25,
        std_dvars_threshold=1e9,
    )

    assert confounds.shape[0] == _N_VOLUMES
    motion_cols = [
        c
        for c in confounds.columns
        if c.startswith(("trans_", "rot_")) and "outlier" not in c
    ]
    assert len(motion_cols) == 24
    outlier_cols = [c for c in confounds.columns if c.startswith("motion_outlier")]
    assert len(outlier_cols) == confounds.shape[1] - 24

    # Censoring actually happened: the spiked frame is dropped, all others kept.
    assert sample_mask is not None
    assert sample_mask.ndim == 1
    assert len(sample_mask) == _N_VOLUMES - 1
    assert spike_frame not in sample_mask
