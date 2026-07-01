"""Tests for aligned frame-index x-axes between motion and confounds QC figures."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from nhp_mri_prep.quality_control.mri_plotting import (
    CONFOUNDS_QC_MARGINS,
    TIMESERIES_QC_MARGINS,
    create_confounds_plot,
    create_motion_plot,
    frame_xlim,
    frame_xticks,
    save_timeseries_qc_figure,
)


def _apply_timeseries_margins(fig: plt.Figure) -> None:
    fig.subplots_adjust(**TIMESERIES_QC_MARGINS)


def _apply_confounds_margins(fig: plt.Figure) -> None:
    fig.subplots_adjust(**CONFOUNDS_QC_MARGINS)


@pytest.mark.parametrize("n_frames", [8, 120])
def test_motion_and_confounds_share_bottom_axis_geometry(n_frames: int) -> None:
    rng = np.random.RandomState(0)
    motion_data = np.cumsum(rng.normal(0, 0.01, size=(n_frames, 6)), axis=0)
    motion_fig = create_motion_plot(motion_data, title="")
    _apply_timeseries_margins(motion_fig)

    confounds_df = pd.DataFrame(
        {
            "framewise_displacement": np.abs(rng.normal(0, 0.05, n_frames)),
            "std_dvars": np.abs(rng.normal(1, 0.1, n_frames)),
            "global_signal": rng.normal(1000, 50, n_frames),
        }
    )
    confounds_fig = create_confounds_plot(confounds_df)
    _apply_confounds_margins(confounds_fig)

    motion_ax = motion_fig.axes[1]
    confounds_ax = confounds_fig.axes[-1]

    motion_pos = motion_ax.get_position()
    confounds_pos = confounds_ax.get_position()
    assert motion_pos.x0 == pytest.approx(confounds_pos.x0, abs=1e-6)
    assert motion_pos.width == pytest.approx(confounds_pos.width, abs=1e-6)
    assert motion_ax.get_xlim() == pytest.approx(confounds_ax.get_xlim(), abs=1e-6)
    assert motion_ax.get_xlim() == pytest.approx(frame_xlim(n_frames), abs=1e-6)
    assert np.allclose(motion_ax.get_xticks(), confounds_ax.get_xticks())
    assert confounds_ax.get_xlabel() == ""
    assert motion_fig.axes[1].spines["left"].get_visible()
    assert not confounds_fig.axes[0].spines["left"].get_visible()

    motion_fig.set_dpi(200)
    confounds_fig.set_dpi(200)
    motion_fig.canvas.draw()
    confounds_fig.canvas.draw()
    motion_frame0_px = motion_fig.axes[1].transData.transform((0, 0))[0]
    confounds_frame0_px = confounds_fig.axes[0].transData.transform((0, 0))[0]
    motion_last_px = motion_fig.axes[1].transData.transform((n_frames - 1, 0))[0]
    confounds_last_px = confounds_fig.axes[0].transData.transform((n_frames - 1, 0))[0]
    assert motion_frame0_px == pytest.approx(confounds_frame0_px, abs=1e-6)
    assert motion_last_px == pytest.approx(confounds_last_px, abs=1e-6)

    plt.close(motion_fig)
    plt.close(confounds_fig)


def test_frame_xticks_rule() -> None:
    assert np.array_equal(frame_xticks(5), np.arange(5))
    assert len(frame_xticks(120)) == 10
    assert frame_xticks(120)[0] == 0
    assert frame_xticks(120)[-1] == 119
    assert frame_xlim(120) == (0.0, 119.5)
    assert frame_xlim(1) == (0.0, 0.0)


def test_save_timeseries_qc_figure_writes_png(tmp_path: Path) -> None:
    motion_data = np.zeros((20, 6))
    fig = create_motion_plot(motion_data, title="")
    out = tmp_path / "motion.png"
    save_timeseries_qc_figure(fig, out)
    plt.close(fig)
    assert out.is_file()
    assert out.stat().st_size > 0
