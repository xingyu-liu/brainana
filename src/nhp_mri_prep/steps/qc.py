"""
Standalone QC step functions for Nextflow integration.

These functions generate quality control visualizations as separate steps.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import StepInput, StepOutput
from ..quality_control import (
    create_bias_correction_qc,
    create_t1wt2w_combined_qc,
    create_skullstripping_qc,
    create_registration_qc,
    create_conform_qc,
    create_atlas_segmentation_qc,
    create_motion_correction_qc,
    create_surf_recon_tissue_seg_qc,
    create_cortical_surf_and_measures_qc
)
from ..quality_control.snapshots import _create_before_after_comparison
from ..quality_control.reports import generate_qc_report
from ..utils.nextflow import ensure_stderr_logging_if_unconfigured

logger = logging.getLogger(__name__)
ensure_stderr_logging_if_unconfigured()


def qc_bias_correction(
    original_file: Path,
    corrected_file: Path,
    output_path: Path,
    modality: str = "anat",
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate bias correction QC snapshot.
    
    Args:
        original_file: Original (uncorrected) image
        corrected_file: Bias-corrected image
        output_path: Output path for QC snapshot
        modality: Modality ('anat' or 'func')
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: bias correction QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_bias_correction", "skipped": True}
        )
    
    try:
        result = create_bias_correction_qc(
            image_original=str(original_file),
            image_corrected=str(corrected_file),
            save_f=str(output_path),
            modality=modality,
            logger=logger
        )
        
        qc_file = Path(result.get("snapshot_file", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_bias_correction",
                "modality": modality
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: bias correction QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_bias_correction", "error": str(e)}
        )


def qc_skullstripping(
    underlay_file: Path,
    mask_file: Path,
    output_path: Path,
    modality: str = "anat",
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate skull stripping QC snapshot.
    
    Args:
        underlay_file: Original image (underlay)
        mask_file: Brain mask file
        output_path: Output path for QC snapshot
        modality: Modality ('anat' or 'func')
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: skull stripping QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_skullstripping", "skipped": True}
        )
    
    try:
        result = create_skullstripping_qc(
            underlay_file=str(underlay_file),
            mask_file=str(mask_file),
            save_f=str(output_path),
            modality=modality,
            logger=logger
        )
        
        qc_file = Path(result.get("snapshot_file", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_skullstripping",
                "modality": modality
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: skull stripping QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_skullstripping", "error": str(e)}
        )


def qc_registration(
    image_file: Path,
    template_file: Path,
    output_path: Path,
    modality: str = "anat2template",
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate registration QC snapshot.
    
    Args:
        image_file: Registered image
        template_file: Template/reference image
        output_path: Output path for QC snapshot
        modality: Modality string (e.g., 'anat2template', 'func2anat')
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: registration QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_registration", "skipped": True}
        )
    
    try:
        result = create_registration_qc(
            image_file=str(image_file),
            template_file=str(template_file),
            save_f=str(output_path),
            modality=modality,
            logger=logger
        )
        
        qc_file = Path(result.get("snapshot_file", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_registration",
                "modality": modality
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: registration QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_registration", "error": str(e)}
        )


def qc_conform(
    conformed_file: Path,
    template_file: Path,
    output_path: Path,
    modality: str = "anat",
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate conform QC snapshot.
    
    Args:
        conformed_file: Path to conformed image
        template_file: Path to template image used for conforming
        output_path: Output path for QC snapshot
        modality: Modality ('anat' or 'func')
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: conform QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_conform", "skipped": True}
        )
    
    try:
        result = create_conform_qc(
            conformed_file=str(conformed_file),
            template_file=str(template_file),
            save_f=str(output_path),
            modality=modality,
            logger=logger
        )
        
        qc_file = Path(result.get(f"{modality}_conform_overlay", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_conform",
                "modality": modality
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: conform QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_conform", "error": str(e)}
        )


def qc_atlas_segmentation(
    underlay_file: Path,
    atlas_file: Path,
    output_path: Path,
    modality: str = "anat",
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate atlas segmentation QC snapshot.
    
    Args:
        underlay_file: Path to underlay image (e.g., T1w brain image)
        atlas_file: Path to atlas segmentation file
        output_path: Output path for QC snapshot
        modality: Modality ('anat' or 'func')
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: atlas segmentation QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_atlas_segmentation", "skipped": True}
        )
    
    try:
        result = create_atlas_segmentation_qc(
            underlay_file=str(underlay_file),
            atlas_file=str(atlas_file),
            save_f=str(output_path),
            modality=modality,
            logger=logger
        )
        
        qc_file = Path(result.get(f"{modality}_atlas_segmentation_overlay", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_atlas_segmentation",
                "modality": modality
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: atlas segmentation QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_atlas_segmentation", "error": str(e)}
        )


def qc_motion_correction(
    motion_params_file: Path,
    output_path: Path,
    input_file: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate motion correction QC plot.
    
    Args:
        motion_params_file: Motion parameters file (.tsv or .par)
        output_path: Output path for QC plot
        input_file: Optional input functional file (for metadata)
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: motion correction QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_motion_correction", "skipped": True}
        )
    
    try:
        result = create_motion_correction_qc(
            motion_params=str(motion_params_file),
            save_f=str(output_path),
            input_file=str(input_file) if input_file else None,
            logger=logger
        )
        
        qc_file = Path(result.get("snapshot_file", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_motion_correction"
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: motion correction QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_motion_correction", "error": str(e)}
        )


def qc_surf_recon_tissue_seg(
    fs_subject_dir: Path,
    output_path: Path,
    modality: str = "anat",
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate surface reconstruction tissue segmentation QC snapshot.
    
    Args:
        fs_subject_dir: Path to FreeSurfer subject directory
        output_path: Output path for QC snapshot
        modality: Modality ('anat' or 'func')
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: surface reconstruction tissue segmentation QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_surf_recon_tissue_seg", "skipped": True}
        )
    
    try:
        result = create_surf_recon_tissue_seg_qc(
            fs_subject_dir=str(fs_subject_dir),
            save_f=str(output_path),
            modality=modality,
            logger=logger
        )
        
        qc_file = Path(result.get(f"{modality}_surf_recon_tissue_seg_overlay", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_surf_recon_tissue_seg",
                "modality": modality
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: surface reconstruction tissue segmentation QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_surf_recon_tissue_seg", "error": str(e)}
        )


def qc_cortical_surf_and_measures(
    fs_subject_dir: Path,
    output_path: Path,
    atlas_name: str = "ARM2",
    modality: str = "anat",
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate cortical surface and measures QC snapshot.
    
    Args:
        fs_subject_dir: Path to FreeSurfer subject directory
        output_path: Output path for QC snapshot
        atlas_name: Atlas name (default: "ARM2")
        modality: Modality ('anat' or 'func')
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: cortical surface and measures QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_cortical_surf_and_measures", "skipped": True}
        )
    
    try:
        result = create_cortical_surf_and_measures_qc(
            fs_subject_dir=str(fs_subject_dir),
            save_f=str(output_path),
            atlas_name=atlas_name,
            modality=modality,
            logger=logger
        )
        
        qc_file = Path(result.get("snapshot_file", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_cortical_surf_and_measures",
                "modality": modality,
                "atlas_name": atlas_name
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: cortical surface and measures QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_cortical_surf_and_measures", "error": str(e)}
        )

def qc_generate_report(
    snapshot_dir: Path,
    report_path: Path,
    config: Dict[str, Any],
    snapshot_paths: Optional[list] = None
) -> StepOutput:
    """
    Generate comprehensive QC report from snapshots.
    
    Args:
        snapshot_dir: Directory containing QC snapshots
        report_path: Output path for HTML report
        config: Configuration dictionary
        snapshot_paths: Optional list of specific snapshot paths (None = auto-discover)
        
    Returns:
        StepOutput with report file
    """
    if not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: report generation skipped (disabled in configuration)")
        return StepOutput(
            output_file=report_path,
            metadata={"step": "qc_report", "skipped": True}
        )
    
    try:
        result = generate_qc_report(
            snapshot_dir=str(snapshot_dir),
            report_path=str(report_path),
            config=config,
            logger=logger,
            snapshot_paths=snapshot_paths,
            pipeline_state=None  # Can be enhanced later
        )
        
        report_file = Path(result.get("report_file", report_path))
        
        return StepOutput(
            output_file=report_file,
            metadata={
                "step": "qc_report",
                "num_snapshots": result.get("num_snapshots", 0)
            },
            qc_files=[report_file]
        )
    except Exception as e:
        logger.warning(f"QC: report generation failed - {e}")
        return StepOutput(
            output_file=report_path,
            metadata={"step": "qc_report", "error": str(e)}
        )


def qc_within_ses_coreg(
    tmean_run1: Path,
    tmean_averaged: Path,
    output_path: Path,
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate within-session coregistration QC snapshot.
    
    Shows comparison: first row = single run (tmean of run 1), 
    second row = coregistered average tmean.
    
    Args:
        tmean_run1: Tmean from first run (reference)
        tmean_averaged: Averaged tmean after coregistration
        output_path: Output path for QC snapshot
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: within-session coregistration QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_within_ses_coreg", "skipped": True}
        )
    
    try:
        # Validate inputs
        if not tmean_run1.exists():
            logger.error(f"QC: tmean_run1 file not found - {tmean_run1}")
            return StepOutput(
                output_file=output_path,
                metadata={"step": "qc_within_ses_coreg", "error": "tmean_run1 not found"}
            )
        
        if not tmean_averaged.exists():
            logger.error(f"QC: tmean_averaged file not found - {tmean_averaged}")
            return StepOutput(
                output_file=output_path,
                metadata={"step": "qc_within_ses_coreg", "error": "tmean_averaged not found"}
            )
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create before/after comparison (run1 vs averaged)
        _create_before_after_comparison(
            str(tmean_run1),  # Original: single run
            str(tmean_averaged),  # Corrected: averaged after coreg
            num_cols=6,
            perspectives=["axial"],
            before_after_labels=["single run ref", "avg run after coreg"],
            save_f=str(output_path),
            logger=logger
        )
        
        return StepOutput(
            output_file=output_path,
            metadata={
                "step": "qc_within_ses_coreg",
                "modality": "func"
            },
            qc_files=[output_path]
        )
    except Exception as e:
        logger.warning(f"QC: within-session coregistration QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_within_ses_coreg", "error": str(e)}
        )


def _tsnr_add_right_colorbar(
    fig,
    vmin: float,
    vmax: float,
    cmap_name: str,
    *,
    map_right: float = 0.9,
    bar_height_ratio: float = 0.5,
    bar_width_to_height: float = 0.06,
    gap_ratio: float = 0.05,
    text_color: str = "white",
) -> None:
    """Right-side colorbar for tSNR matplotlib figures (matches compute_tSNR script layout)."""
    from matplotlib import colors, cm

    fig.subplots_adjust(right=map_right)
    fig_width_in, fig_height_in = fig.get_size_inches()

    bar_height = bar_height_ratio
    bar_width = (
        bar_height * bar_width_to_height * (fig_height_in / fig_width_in)
        if fig_width_in > 0
        else 0.015
    )
    gap_frac = gap_ratio
    cbar_x = map_right + gap_frac
    cbar_x = min(cbar_x, 0.99 - bar_width)
    cbar_y = (1.0 - bar_height) / 2.0

    cax = fig.add_axes([cbar_x, cbar_y, bar_width, bar_height])
    norm = colors.Normalize(vmin=vmin, vmax=vmax)
    sm = cm.ScalarMappable(norm=norm, cmap=cmap_name)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax, label="tSNR")
    cb.ax.yaxis.set_label_position("left")
    cb.ax.yaxis.tick_left()
    cb.ax.yaxis.label.set_color(text_color)
    cb.ax.tick_params(colors=text_color)
    for spine in cb.ax.spines.values():
        spine.set_edgecolor(text_color)


def qc_tsnr(
    session_tsnr_vol: Path,
    lh_surf_gii: Optional[Path],
    rh_surf_gii: Optional[Path],
    fs_subject_dir: Optional[Path],
    output_path: Path,
    config: Optional[Dict[str, Any]] = None,
) -> StepOutput:
    """
    Combined QC figure: session-average tSNR volume (axial grid) and optional surface maps.

    Surface panel is omitted if gifti paths are missing/dummy, ``fs_subject_dir`` is missing,
    or optional dependencies (surfplot, PIL) are unavailable.
    """
    import numpy as np
    import matplotlib.pyplot as plt
    import nibabel as nib

    from ..quality_control.mri_plotting import create_grid_mri_image, PLOT_VOL_DPI

    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: tSNR QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_tsnr", "skipped": True},
        )

    try:
        # 1. Input checks and output directory.
        if not session_tsnr_vol.exists():
            logger.error("QC: session tSNR volume not found — %s", session_tsnr_vol)
            return StepOutput(
                output_file=output_path,
                metadata={"step": "qc_tsnr", "error": "session_tsnr_missing"},
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        colormap_name = "magma"

        # 2. Axial mosaic of the session-average tSNR volume (robust display range).
        volume_voxels = np.asarray(nib.load(str(session_tsnr_vol)).get_fdata(), dtype=np.float64)
        finite_voxels = volume_voxels[np.isfinite(volume_voxels)]
        if finite_voxels.size == 0:
            volume_vmin, volume_vmax = 0.0, 1.0
        else:
            volume_vmin, volume_vmax = np.percentile(finite_voxels, [2, 98])
            if volume_vmax <= volume_vmin:
                volume_vmax = volume_vmin + 1e-6

        figure_volume = create_grid_mri_image(
            underlay_data=session_tsnr_vol,
            overlay_data=None,
            num_cols=6,
            perspectives=["axial"],
            title="",
            alpha=0.7,
            underlay_cmap=colormap_name,
            show_title=False,
            underlay_vmin=volume_vmin,
            underlay_vmax=volume_vmax,
        )
        _tsnr_add_right_colorbar(
            figure_volume, volume_vmin, volume_vmax, colormap_name, text_color="white"
        )
        volume_png_fd, volume_png_path_str = tempfile.mkstemp(
            suffix="_tsnr_vol.png", dir=str(output_path.parent)
        )
        os.close(volume_png_fd)
        volume_png_path = Path(volume_png_path_str)
        figure_volume.savefig(
            volume_png_path, dpi=PLOT_VOL_DPI, bbox_inches="tight", pad_inches=0.0
        )
        plt.close(figure_volume)

        # 3. Optional surface panel: real gifti + inflated meshes + surfplot.
        surface_png_path: Optional[Path] = None
        left_surf_ready = (
            lh_surf_gii is not None
            and lh_surf_gii.exists()
            and ".dummy" not in str(lh_surf_gii).lower()
            and lh_surf_gii.stat().st_size > 0
        )
        right_surf_ready = (
            rh_surf_gii is not None
            and rh_surf_gii.exists()
            and ".dummy" not in str(rh_surf_gii).lower()
            and rh_surf_gii.stat().st_size > 0
        )
        freesurfer_subject_ready = fs_subject_dir is not None and fs_subject_dir.is_dir()

        if left_surf_ready and right_surf_ready and freesurfer_subject_ready:
            left_inflated_mesh = fs_subject_dir / "surf" / "lh.inflated"
            right_inflated_mesh = fs_subject_dir / "surf" / "rh.inflated"
            if left_inflated_mesh.is_file() and right_inflated_mesh.is_file():
                try:
                    from surfplot import Plot
                except Exception as exc:
                    logger.warning("QC: tSNR surf panel skipped (surfplot): %s", exc)
                    Plot = None  # type: ignore
                if Plot is not None:
                    try:
                        left_vertex_tsnr = np.asarray(
                            nib.load(str(lh_surf_gii)).darrays[0].data, dtype=np.float32
                        )
                        right_vertex_tsnr = np.asarray(
                            nib.load(str(rh_surf_gii)).darrays[0].data, dtype=np.float32
                        )
                        combined_vertices = np.concatenate(
                            [left_vertex_tsnr, right_vertex_tsnr]
                        )
                        combined_vertices = combined_vertices[np.isfinite(combined_vertices)]
                        if combined_vertices.size == 0:
                            surf_vmin, surf_vmax = 0.0, 1.0
                        else:
                            surf_vmin, surf_vmax = 0.0, float(np.percentile(combined_vertices, 98))
                            if surf_vmax <= surf_vmin:
                                surf_vmax = surf_vmin + 1e-6

                        surf_plot = Plot(
                            surf_lh=str(left_inflated_mesh),
                            surf_rh=str(right_inflated_mesh),
                            views=["lateral", "medial"],
                            layout="row",
                            size=(1600, 200),
                            zoom=2,
                        )
                        surf_plot.add_layer(
                            {
                                "left": np.clip(left_vertex_tsnr, surf_vmin, surf_vmax),
                                "right": np.clip(right_vertex_tsnr, surf_vmin, surf_vmax),
                            },
                            cmap=colormap_name,
                            cbar=False,
                        )
                        figure_surface = surf_plot.build()
                        figure_surface.patch.set_facecolor("black")
                        for axis in figure_surface.axes:
                            axis.set_facecolor("black")
                        _tsnr_add_right_colorbar(
                            figure_surface, surf_vmin, surf_vmax, colormap_name, text_color="white"
                        )
                        surface_png_fd, surface_png_path_str = tempfile.mkstemp(
                            suffix="_tsnr_surf.png", dir=str(output_path.parent)
                        )
                        os.close(surface_png_fd)
                        surface_png_path = Path(surface_png_path_str)
                        figure_surface.savefig(
                            surface_png_path,
                            dpi=PLOT_VOL_DPI,
                            bbox_inches="tight",
                            pad_inches=0.0,
                            facecolor="black",
                        )
                        plt.close(figure_surface)
                    except Exception as exc:
                        logger.warning("QC: tSNR surface rendering failed: %s", exc)
                        if surface_png_path and surface_png_path.exists():
                            surface_png_path.unlink(missing_ok=True)
                        surface_png_path = None

        # 4. Stack panels vertically with Pillow (or ship volume-only if Pillow is absent).
        try:
            from PIL import Image
        except ImportError:
            Image = None  # type: ignore

        if Image is None:
            import shutil

            shutil.move(str(volume_png_path), str(output_path))
            return StepOutput(
                output_file=output_path,
                metadata={"step": "qc_tsnr", "warning": "pillow_missing_vol_only"},
                qc_files=[output_path],
            )

        panel_image_paths = [
            panel_path
            for panel_path in (volume_png_path, surface_png_path)
            if panel_path is not None and panel_path.exists()
        ]
        if not panel_image_paths:
            volume_png_path.unlink(missing_ok=True)
            return StepOutput(
                output_file=output_path,
                metadata={"step": "qc_tsnr", "error": "no_panels"},
            )

        panel_rgba_images = [
            Image.open(panel_image_path).convert("RGB")
            for panel_image_path in panel_image_paths
        ]
        max_panel_width = max(image.width for image in panel_rgba_images)
        resized_panels: List[Any] = []
        for image in panel_rgba_images:
            if image.width != max_panel_width:
                new_height = int(image.height * (max_panel_width / image.width))
                image = image.resize(
                    (max_panel_width, new_height), resample=Image.Resampling.LANCZOS
                )
            resized_panels.append(image)

        vertical_gap_px = 0
        canvas_height = sum(image.height for image in resized_panels) + vertical_gap_px * (
            len(resized_panels) - 1
        )
        stacked_figure = Image.new("RGB", (max_panel_width, canvas_height), color="white")
        paste_y = 0
        for image in resized_panels:
            paste_x = (max_panel_width - image.width) // 2
            stacked_figure.paste(image, (paste_x, paste_y))
            paste_y += image.height + vertical_gap_px
        stacked_figure.save(output_path)

        for panel_image_path in panel_image_paths:
            Path(panel_image_path).unlink(missing_ok=True)

        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_tsnr", "modality": "func"},
            qc_files=[output_path],
        )
    except Exception as e:
        logger.warning("QC: tSNR QC failed — %s", e)
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_tsnr", "error": str(e)},
        )


def qc_t1wt2w_combined(
    t1w_before_file: Path,
    t1wt2w_combined_file: Path,
    output_path: Path,
    modality: str = "anat",
    mask_file: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate T1wT2wCombined QC snapshot.
    
    Shows before/after comparison: T1w after bias correction vs T1wT2wCombined image.
    Optionally applies a brain mask to both images before visualization.
    
    Args:
        t1w_before_file: T1w image after bias correction (before)
        t1wt2w_combined_file: T1wT2wCombined image (after)
        output_path: Output path for QC snapshot
        modality: Modality ('anat' or 'func')
        mask_file: Optional brain mask file (if provided, mask will be applied to both images)
        config: Configuration dictionary (optional)
        
    Returns:
        StepOutput with QC file
    """
    if not config or not config.get("quality_control", {}).get("enabled", True):
        logger.info("QC: T1wT2wCombined QC skipped (disabled in configuration)")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_t1wt2w_combined", "skipped": True}
        )
    
    try:
        result = create_t1wt2w_combined_qc(
            image_before=str(t1w_before_file),
            image_combined=str(t1wt2w_combined_file),
            save_f=str(output_path),
            modality=modality,
            mask_file=str(mask_file) if mask_file else None,
            logger=logger
        )
        
        qc_file = Path(result.get(f"{modality}_t1wt2w_combined_comparison", output_path))
        
        return StepOutput(
            output_file=qc_file,
            metadata={
                "step": "qc_t1wt2w_combined",
                "modality": modality,
                "mask_applied": mask_file is not None
            },
            qc_files=[qc_file]
        )
    except Exception as e:
        logger.warning(f"QC: T1wT2wCombined QC failed - {e}")
        return StepOutput(
            output_file=output_path,
            metadata={"step": "qc_t1wt2w_combined", "error": str(e)}
        )

