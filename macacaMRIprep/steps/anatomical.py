"""
Standalone anatomical processing step functions.

These functions wrap the existing operations to provide standardized
inputs/outputs for Nextflow integration.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .types import StepInput, StepOutput
from ..operations.preprocessing import (
    reorient,
    conform_to_template,
    bias_correction,
    apply_segmentation
)
from ..operations.registration import ants_register


logger = logging.getLogger(__name__)


def anat_reorient(input: StepInput, template_file: Optional[Path] = None) -> StepOutput:
    """
    Reorient anatomical image to template orientation or RAS.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        template_file: Optional template file for reorientation target
        
    Returns:
        StepOutput with reoriented file
    """
    if not input.config.get("anat.reorient.enabled", True):
        logger.info("Step: reorient skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "reorient", "skipped": True}
        )
    
    # Determine target for reorientation
    target_file = None
    target_orientation = None
    
    if template_file:
        target_file = str(template_file)
    else:
        target_orientation = "RAS"
    
    # Call operation
    result = reorient(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        output_name=input.output_name or "anat_reoriented.nii.gz",
        logger=logger,
        target_file=target_file,
        target_orientation=target_orientation,
        generate_tmean=False
    )
    
    output_file = Path(result["imagef_reoriented"]) if result.get("imagef_reoriented") else input.input_file
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "reorient",
            "modality": "anat",
            "target_file": str(template_file) if template_file else None,
            "target_orientation": target_orientation
        }
    )


def anat_conform(input: StepInput, template_file: Path) -> StepOutput:
    """
    Conform anatomical image to template space.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        template_file: Template file for conforming
        
    Returns:
        StepOutput with conformed file and transform files
    """
    if not input.config.get("anat.conform.enabled", True):
        logger.info("Step: conform skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "conform", "skipped": True}
        )
    
    # Check if skullstripping is disabled - if so, skip internal skullstripping in conform
    skip_skullstripping = not input.config.get("anat.skullstripping_segmentation.enabled", True)
    
    # Call operation
    result = conform_to_template(
        imagef=str(input.input_file),
        template_file=str(template_file),
        working_dir=str(input.working_dir),
        output_name=input.output_name or "anat_conformed.nii.gz",
        logger=logger,
        modal="anat",
        skip_skullstripping=skip_skullstripping
    )
    
    output_file = Path(result["imagef_conformed"]) if result.get("imagef_conformed") else input.input_file
    additional_files = []
    
    if result.get("forward_xfm"):
        additional_files.append(Path(result["forward_xfm"]))
    if result.get("inverse_xfm"):
        additional_files.append(Path(result["inverse_xfm"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "conform",
            "modality": "anat",
            "template_file": str(template_file)
        },
        additional_files=additional_files
    )


def anat_bias_correction(input: StepInput) -> StepOutput:
    """
    Perform bias field correction on anatomical image.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        
    Returns:
        StepOutput with bias-corrected file
    """
    if not input.config.get("anat.bias_correction.enabled", True):
        logger.info("Step: bias correction skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "bias_correction", "skipped": True}
        )
    
    # Call operation
    result = bias_correction(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        modal="anat",
        output_name=input.output_name or "anat_bias_corrected.nii.gz",
        config=input.config,
        logger=logger
    )
    
    output_file = Path(result["imagef_bias_corrected"])
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "bias_correction",
            "modality": "anat",
            "algorithm": input.config.get("anat", {}).get("bias_correction", {}).get("algorithm", "N4BiasFieldCorrection")
        }
    )


def anat_skullstripping(input: StepInput) -> StepOutput:
    """
    Perform skull stripping on anatomical image using FastSurferCNN.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        
    Returns:
        StepOutput with skull-stripped file, brain mask, and segmentation
    """
    if not input.config.get("anat.skullstripping_segmentation.enabled", True):
        logger.info("Step: skull stripping skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "skullstripping", "skipped": True}
        )
    
    # Call operation
    result = apply_segmentation(
        imagef=str(input.input_file),
        modal="anat",
        working_dir=str(input.working_dir),
        output_name=input.output_name or "anat_brain.nii.gz",
        config=input.config,
        logger=logger
    )
    
    output_file = Path(result["imagef_skullstripped"])
    additional_files = []
    
    if result.get("brain_mask"):
        additional_files.append(Path(result["brain_mask"]))
    if result.get("segmentation"):
        additional_files.append(Path(result["segmentation"]))
    if result.get("hemimask"):
        additional_files.append(Path(result["hemimask"]))
    if result.get("input_cropped"):
        additional_files.append(Path(result["input_cropped"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "skullstripping",
            "modality": "anat",
            "method": "fastSurferCNN",
            "atlas_name": result.get("atlas_name")
        },
        additional_files=additional_files
    )


def anat_registration(input: StepInput, template_file: Path, template_name: str) -> StepOutput:
    """
    Register anatomical image to template space.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        template_file: Template file for registration
        template_name: Template name (e.g., "NMT2Sym")
        
    Returns:
        StepOutput with registered file and transform files
    """
    if not input.config.get("registration.enabled", True):
        logger.info("Step: registration skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "registration", "skipped": True}
        )
    
    # Get transform type from config
    xfm_type = input.config.get("registration", {}).get("anat2template_xfm_type", "syn")
    
    # Call operation
    result = ants_register(
        movingf=str(input.input_file),
        fixedf=str(template_file),
        working_dir=str(input.working_dir),
        output_prefix="anat2template",
        config=input.config,
        logger=logger,
        xfm_type=xfm_type
    )
    
    output_file = Path(result["imagef_registered"])
    additional_files = []
    
    if result.get("forward_transform"):
        additional_files.append(Path(result["forward_transform"]))
    if result.get("inverse_transform"):
        additional_files.append(Path(result["inverse_transform"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "registration",
            "modality": "anat",
            "target": template_name,
            "xfm_type": xfm_type
        },
        additional_files=additional_files
    )


def anat_synthesis(anat_files: List[Path], working_dir: Path, config: Dict[str, Any]) -> StepOutput:
    """
    Synthesize multiple anatomical runs (T1w, T2w, etc.) into a single image.
    
    This function coregisters and averages multiple anatomical runs from the same
    subject/session to create a single synthesized image for processing.
    
    Args:
        anat_files: List of anatomical file paths to synthesize (all same modality)
        working_dir: Working directory for intermediate files
        config: Configuration dictionary
        
    Returns:
        StepOutput with synthesized anatomical file
    """
    if len(anat_files) <= 1:
        # No synthesis needed
        return StepOutput(
            output_file=anat_files[0] if anat_files else None,
            metadata={"step": "anat_synthesis", "synthesized": False, "num_runs": len(anat_files)}
        )
    
    # Determine modality from first file
    from ..utils.bids import parse_bids_entities, get_filename_stem
    first_stem = get_filename_stem(anat_files[0])
    modality = "T1w"  # default
    if "_T2w" in first_stem or first_stem.endswith("_T2w"):
        modality = "T2w"
    elif "_T1w" in first_stem or first_stem.endswith("_T1w"):
        modality = "T1w"
    
    logger.info(f"Step: synthesizing {len(anat_files)} {modality} runs")
    
    # Import synthesis function and BIDSFile
    from ..operations.synthesis_multiple_anat import synthesize_multiple_anatomical
    from ..utils.bids import BIDSFile
    
    bids_files = []
    for anat_file in anat_files:
        entities = parse_bids_entities(anat_file.name)
        bids_files.append(BIDSFile(
            path=str(anat_file),
            sub=entities.get("sub", "unknown"),
            ses=entities.get("ses"),
            modality="anat",
            suffix=modality,
            entities=entities,
            run=entities.get("run")
        ))
    
    # Call synthesis function
    # The synthesis function now handles all file management internally using working_dir
    synthesized_file = synthesize_multiple_anatomical(
        anat_files=bids_files,
        working_dir=working_dir,
        logger=logger,
        config=config
    )
    
    if not synthesized_file:
        raise RuntimeError(f"Anatomical synthesis failed for {len(anat_files)} files")
    
    return StepOutput(
        output_file=Path(synthesized_file),
        metadata={
            "step": "anat_synthesis",
            "synthesized": True,
            "num_runs": len(anat_files)
        }
    )

