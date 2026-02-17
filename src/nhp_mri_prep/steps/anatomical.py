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
    apply_segmentation,
    generate_t1wt2wcombined
)
from ..operations.registration import ants_register, ants_apply_transforms, flirt_register, flirt_apply_transforms
from ..utils.templates import discover_atlases_in_space
from ..utils.mri import get_image_shape, shape_to_ants_input_type
from fastsurfer_surfrecon.config import AtlasConfig, ReconSurfConfig
from fastsurfer_surfrecon.pipeline import ReconSurfPipeline

logger = logging.getLogger(__name__)



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
        skip_skullstripping=skip_skullstripping,
        padding_percentage=input.config.get("anat.conform.padding_percentage"),
    )
    
    output_file = Path(result["imagef_conformed"]) if result.get("imagef_conformed") else input.input_file
    additional_files = {}
    
    if result.get("forward_xfm"):
        additional_files["forward_transform"] = Path(result["forward_xfm"])
    if result.get("inverse_xfm"):
        additional_files["inverse_transform"] = Path(result["inverse_xfm"])
    if result.get("template_f"):
        additional_files["template_resampled"] = Path(result["template_f"])  # template_f is already the resampled template
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "conform",
            "modality": "anat",
            "template_file": str(template_file)
        },
        additional_files=additional_files
    )


def anat_bias_correction(input: StepInput, brain_mask: Optional[Path] = None) -> StepOutput:
    """
    Perform bias field correction on anatomical image.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        brain_mask: Optional brain mask file (if provided and not dummy, will be used for bias correction)
        
    Returns:
        StepOutput with bias-corrected file and optionally brain-only file
    """
    if not input.config.get("anat.bias_correction.enabled", True):
        logger.info("Step: bias correction skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "bias_correction", "skipped": True}
        )
    
    # Use mask if provided (mask is already validated as real in workflow)
    mask_path = brain_mask if brain_mask else None
    if mask_path:
        logger.info(f"Step: using brain mask for bias correction - {brain_mask.name}")
    
    # Call operation
    result = bias_correction(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        modal="anat",
        output_name=input.output_name or "anat_bias_corrected.nii.gz",
        config=input.config,
        logger=logger,
        maskf=str(mask_path) if mask_path else None
    )
    
    output_file = Path(result["imagef_bias_corrected"])
    additional_files = {}
    
    # Add brain-only file if generated
    if result.get("imagef_brain"):
        additional_files["brain"] = Path(result["imagef_brain"])
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "bias_correction",
            "modality": "anat",
            "algorithm": input.config.get("anat", {}).get("bias_correction", {}).get("algorithm", "N4BiasFieldCorrection"),
            "mask_used": str(mask_path) if mask_path else None
        },
        additional_files=additional_files
    )


def anat_skullstripping(input: StepInput) -> StepOutput:
    """
    Perform skull stripping on anatomical image using fastsurfer_nn.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        
    Returns:
        StepOutput with skull-stripped file, brain mask, segmentation,
        atlas LUT (ColorLUT TSV, same base as segmentation), and optional hemimask
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
    additional_files = {}
    
    if result.get("brain_mask"):
        additional_files["brain_mask"] = Path(result["brain_mask"])
    if result.get("segmentation"):
        additional_files["segmentation"] = Path(result["segmentation"])
    if result.get("hemimask"):
        additional_files["hemimask"] = Path(result["hemimask"])
    if result.get("input_cropped"):
        additional_files["input_cropped"] = Path(result["input_cropped"])
    if result.get("atlas_lut"):
        additional_files["atlas_lut"] = Path(result["atlas_lut"])
    
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
    additional_files = {}
    
    if result.get("forward_transform"):
        additional_files["forward_transform"] = Path(result["forward_transform"])
    if result.get("inverse_transform"):
        additional_files["inverse_transform"] = Path(result["inverse_transform"])
    
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
    

def anat_backproject_atlases(
    inverse_xfm: Path,
    t1w_reference: Path,
    bids_name: Path,
    working_dir: Path,
    config: Dict[str, Any],
    template_dir: Optional[Path] = None,
) -> StepOutput:
    """
    Backproject atlases from template space to T1w space using inverse transform.

    Discovers atlases in the template space (from config output_space), applies
    the inverse T1w->template transform to each, and writes outputs to
    working_dir/atlas/ with naming: atlas-{atlas_name}_{t1w_stem}.nii.gz.
    The t1w_stem is derived from bids_name by stripping _desc-preproc_T1w.

    Args:
        inverse_xfm: Inverse transform (template -> T1w)
        t1w_reference: T1w image defining output grid (anat_after_bias)
        bids_name: BIDS filename of T1w output (e.g. sub-X_ses-Y_run-Z_desc-preproc_T1w.nii.gz)
        working_dir: Working directory; atlas outputs go to working_dir/atlas/
        config: Configuration dict (uses template.output_space)
        template_dir: Optional custom template zoo path

    Returns:
        StepOutput with output_file=atlas_dir, additional_files={atlas_name: path}
    """
    effective_output_space = config.get("template", {}).get(
        "output_space", "NMT2Sym:res-05"
    )
    parts = effective_output_space.split(":")
    space_name = parts[0] if parts else "NMT2Sym"
    template_res = parts[1] if len(parts) > 1 else None

    atlases = discover_atlases_in_space(
        space_name=space_name,
        template_res=template_res,
        template_dir=str(template_dir) if template_dir else None,
    )
    if not atlases:
        logger.info(f"Step: no atlases found in space {space_name}, skipping backproject")
        atlas_dir = working_dir / "atlas"
        atlas_dir.mkdir(parents=True, exist_ok=True)
        return StepOutput(
            output_file=atlas_dir,
            metadata={
                "step": "backproject_atlases",
                "atlases_found": 0,
                "space": space_name,
            },
            additional_files={},
        )

    # Build output stem from bids_name: strip .nii then _desc-preproc_T1w or _T1w
    bids_stem = Path(bids_name).stem
    if bids_stem.endswith(".nii"):
        bids_stem = bids_stem[:-4]
    if bids_stem.endswith("_T1w"):
        output_stem = bids_stem[: -len("_T1w")]
    else:
        output_stem = bids_stem

    atlas_dir = working_dir / "atlas"
    atlas_dir.mkdir(parents=True, exist_ok=True)

    additional_files: Dict[str, Path] = {}
    for atlas_name, atlas_path in atlases:
        output_name = f"atlas-{atlas_name}_{output_stem}.nii.gz"
        shape = get_image_shape(str(atlas_path), logger=logger)
        moving_type = shape_to_ants_input_type(shape)

        result = ants_apply_transforms(
            movingf=str(atlas_path),
            moving_type=moving_type,
            interpolation="NearestNeighbor",
            outputf_name=output_name,
            fixedf=str(t1w_reference),
            working_dir=str(atlas_dir),
            transformf=[str(inverse_xfm)],
            logger=logger,
            reff=str(t1w_reference),
            generate_tmean=False,
        )
        out_path = Path(result["imagef_registered"])
        additional_files[atlas_name] = out_path

    return StepOutput(
        output_file=atlas_dir,
        metadata={
            "step": "backproject_atlases",
            "atlases_found": len(additional_files),
            "space": space_name,
        },
        additional_files=additional_files,
    )


def anat_t2w_to_t1w_registration(input: StepInput, t1w_reference: Path) -> StepOutput:
    """
    Register T2w image to T1w space.
    
    Args:
        input: StepInput with input_file (reoriented T2w), working_dir, config, metadata
        t1w_reference: Path to T1w reference
        
    Returns:
        StepOutput with registered T2w file and transform files
    """
    # Step 1: ANTs rigid registration from T2w to T1w
    try:
        registration_result = ants_register(
            fixedf=str(t1w_reference),
            movingf=str(input.input_file),
            working_dir=str(input.working_dir),
            output_prefix="t2w_to_t1w_coreg",
            logger=logger,
            xfm_type="rigid"
        )
        forward_transform = registration_result.get("forward_transform")
        if not forward_transform:
            raise RuntimeError("ANTs registration did not produce a forward transform")
        xfm_forward_f = Path(forward_transform)
        xfm_inverse_f = Path(registration_result.get("inverse_transform")) if registration_result.get("inverse_transform") else None
    except Exception as e:
        logger.error(f"Error during ANTs registration: {e}")
        raise RuntimeError(
            f"T2w to T1w registration failed during ANTs registration: {e}"
        )
    
    # Step 2: Apply the transform (interpolation from config)
    interpolation = input.config.get("registration", {}).get("interpolation", "BSpline")
    try:
        apply_result = ants_apply_transforms(
            movingf=str(input.input_file),
            outputf_name="t2w_to_t1w_coreg_registered.nii.gz",
            fixedf=str(t1w_reference),
            working_dir=str(input.working_dir),
            transformf=[str(xfm_forward_f)],
            logger=logger,
            moving_type=0,
            interpolation=interpolation,
            reff=str(t1w_reference),
            generate_tmean=False
        )
        output_file = Path(apply_result['imagef_registered'])
    except Exception as e:
        logger.error(f"Error during ANTs transformation application: {e}")
        raise RuntimeError(
            f"T2w to T1w registration failed when applying transformation: {e}"
        )
    
    additional_files = {}
    if xfm_forward_f.exists():
        additional_files["forward_transform"] = xfm_forward_f
    if xfm_inverse_f is not None and xfm_inverse_f.exists():
        additional_files["inverse_transform"] = xfm_inverse_f
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "t2w_to_t1w_registration",
            "modality": "T2w",
            "target": "T1w",
            "xfm_type": "rigid"
        },
        additional_files=additional_files
    )


def anat_surface_reconstruction(input: StepInput, t1w_file: Path, segmentation_file: Path, brain_mask: Optional[Path] = None) -> StepOutput:
    """
    Perform surface reconstruction using fastsurfer_surfrecon.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        t1w_file: T1w image file (any T1w file, independent of preprocessing pipeline)
        segmentation_file: Segmentation file (from skullstripping step)
        brain_mask: Brain mask file (required for surface reconstruction)
        
    Returns:
        StepOutput with surface reconstruction directory path
    """
    if not input.config.get("anat.surface_reconstruction.enabled", True):
        logger.info("Step: surface reconstruction skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "surface_reconstruction", "skipped": True}
        )
    
    # Validate required inputs
    if not brain_mask:
        raise ValueError("brain_mask is required for surface reconstruction")
    
    # Get subject ID from metadata or derive from input
    base_subject_id = input.metadata.get("subject_id") or "unknown"
    if not base_subject_id.startswith("sub-"):
        base_subject_id = f"sub-{base_subject_id}"
    
    # Get session information from metadata
    session_id = input.metadata.get("session_id")
    session_count = input.metadata.get("session_count", 1)
    
    # Determine subject ID for FastSurfer based on session count and session_id
    # Logic:
    # - If session_id is None/empty: subject-level synthesis → use sub-XXX
    # - If session_id is not empty:
    #   - If session_count > 1: multiple sessions exist → use sub-XXX_ses-XXX
    #   - If session_count == 1: only one session → use sub-XXX
    if not session_id or session_id == "":
        # Subject-level synthesis (no session identifier)
        subject_id = base_subject_id
    elif session_count > 1:
        # Multiple sessions exist: use session identifier to avoid collisions
        # Extract session ID without 'ses-' prefix if present
        ses_id = session_id if not session_id.startswith("ses-") else session_id[4:]
        subject_id = f"{base_subject_id}_ses-{ses_id}"
    else:
        # Only one session: no need for session identifier
        subject_id = base_subject_id
    
    # Get atlas name from config (default to ARM2 for macaque)
    atlas_name = input.config.get("anat", {}).get("skullstripping_segmentation", {}).get("atlas_name", "ARM2")
    
    # Create subjects directory structure
    subjects_dir = Path(input.working_dir) / "fastsurfer"
    subject_dir = subjects_dir / subject_id
    
    logger.info(f"Step: Surface reconstruction for {subject_id}")
    logger.info(f"Step: Atlas = {atlas_name}")
    logger.info(f"Step: Subjects directory = {subjects_dir}")
    
    # Get LUT path using fastsurfer_surfrecon's AtlasConfig (has built-in fallbacks)
    atlas_config = AtlasConfig(name=atlas_name)
    lut_path = atlas_config.colorlut_path
    
    if lut_path is None or not lut_path.exists():
        raise FileNotFoundError(
            f"LUT file not found for atlas {atlas_name}. "
            f"AtlasConfig searched but could not locate ColorLUT file."
        )
    
    logger.info(f"Step: LUT path = {lut_path}")
    
    # Validate required files exist before processing
    for path, name in [(t1w_file, "T1w image"), (segmentation_file, "segmentation"), (brain_mask, "mask")]:
        if not path.exists():
            raise FileNotFoundError(f"Step: Required file not found: {name} at {path}")
    
    logger.info("Step: All required files validated")
    
    # Step 1: Prepare files for FreeSurfer using postprocess_for_freesurfer
    logger.info("Step: Preparing files for FreeSurfer format")
    try:
        from fastsurfer_nn.postprocessing.prepping_for_surfrecon import postprocess_for_freesurfer
        
        prep_result = postprocess_for_freesurfer(
            t1w_image=str(t1w_file),
            segmentation=str(segmentation_file),
            mask=str(brain_mask),
            lut_path=str(lut_path),
            subject_dir=str(subject_dir),
            vox_size="min",
            orientation="lia"
        )
        
        if prep_result != 0:
            raise RuntimeError(f"File preparation failed: {prep_result}")
        
        logger.info("Step: File preparation completed successfully")
    except ImportError as e:
        logger.error(f"Step: Failed to import postprocess_for_freesurfer - {e}")
        raise
    except Exception as e:
        logger.error(f"Step: File preparation failed - {e}")
        raise
    
    # Step 2: Run surface reconstruction pipeline
    logger.info("Step: Running surface reconstruction pipeline")
    try:
        # Get thread count from config
        threads = input.config.get("processing", {}).get("threads", 1)
        
        # Create configuration using defaults from YAML, only override non-default values
        recon_config = ReconSurfConfig.with_defaults(
            subject_id=subject_id,
            subjects_dir=str(subjects_dir),
            atlas={"name": atlas_name},
            processing={"threads": threads, "skip_cc": True, "skip_talairach": True},  # Default for macaque
            verbose=1,
        )
        
        # Run pipeline
        pipeline = ReconSurfPipeline(recon_config)
        pipeline.run()
        
        logger.info("Step: Surface reconstruction completed successfully")
        
    except Exception as e:
        logger.error(f"Step: Pipeline execution failed - {e}")
        raise
    
    return StepOutput(
        output_file=subject_dir,  # Return subject directory as output
        metadata={
            "step": "surface_reconstruction",
            "modality": "anat",
            "subject_id": subject_id,
            "atlas_name": atlas_name,
            "subjects_dir": str(subjects_dir)
        }
    )


def anat_t1wt2wcombined(
    t1w_file: Path,
    t2w_file: Path,
    segmentation_file: Path,
    segmentation_lut_file: Path,
    output_file: Path,
    metadata: Optional[Dict[str, Any]] = None
) -> StepOutput:
    """
    Generate T1wT2wCombined image from T1w, T2w, and segmentation.
    
    This is a step-level wrapper around generate_t1wt2wcombined() that provides
    standardized input/output for Nextflow integration.
    
    Args:
        t1w_file: Path to T1w image file
        t2w_file: Path to T2w image file (must be in same space as T1w)
        segmentation_file: Path to segmentation file (e.g., aparc+aseg.orig.nii.gz)
        segmentation_lut_file: Path to segmentation LUT TSV file
        output_file: Path for output combined image
        config: Configuration dictionary
        metadata: Optional metadata dictionary (subject_id, session_id, etc.)
        
    Returns:
        StepOutput with combined image file and metadata
    """
    if metadata is None:
        metadata = {}
    
    logger.info(f"Step: generating T1wT2wCombined image")
    logger.info(f"  T1w: {t1w_file.name}")
    logger.info(f"  T2w: {t2w_file.name}")
    logger.info(f"  Segmentation: {segmentation_file.name}")
    
    # Call the preprocessing function
    result = generate_t1wt2wcombined(
        t1w_file=t1w_file,
        t2w_file=t2w_file,
        segmentation_file=segmentation_file,
        segmentation_lut_file=segmentation_lut_file,
        output_file=output_file,
        logger=logger
    )
    
    output_path = Path(result["combined_image"])
    
    return StepOutput(
        output_file=output_path,
        metadata={
            "step": "t1wt2w_combined",
            "modality": "anat",
            "t1w_file": str(t1w_file),
            "t2w_file": str(t2w_file),
            "segmentation_file": str(segmentation_file),
            "t1w_gm_intensity": result.get("t1w_gm_intensity"),
            "t2w_gm_intensity": result.get("t2w_gm_intensity"),
            **metadata
        }
    )

