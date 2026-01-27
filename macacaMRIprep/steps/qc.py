"""
Standalone QC step functions for Nextflow integration.

These functions generate quality control visualizations as separate steps.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

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

logger = logging.getLogger(__name__)


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

