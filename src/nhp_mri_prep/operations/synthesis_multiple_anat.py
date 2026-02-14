"""
T1w/T2w synthesis operations for nhp_mri_prep.

This module provides functions for synthesizing multiple anatomical runs
into a single image through coregistration and averaging.
"""

import os
import re
import logging
import traceback
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import nibabel as nib
import numpy as np
import json

from .registration import ants_register, ants_apply_transforms
from .validation import validate_input_file, ensure_working_directory, validate_output_file
from ..config import get_config
from ..utils.bids import BIDSFile


def synthesize_multiple_anatomical(
    anat_files: List[BIDSFile],
    working_dir: Union[str, Path],
    logger: logging.Logger,
    config: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Synthesize multiple anatomical images (T1w or T2w) for a session by coregistering and averaging them.
    
    Args:
        anat_files: List of BIDSFile objects for anatomical images (all same modality)
        base_output_dir: Base output directory (deprecated, kept for compatibility)
        dataset_dir: BIDS dataset directory (deprecated, kept for compatibility)
        working_dir: Working directory for intermediate and output files
        logger: Logger instance
        config: Optional configuration dictionary (uses default if None)
        
    Returns:
        Path to synthesized anatomical image, or None if synthesis failed
    """
    if len(anat_files) <= 1:
        return None
    
    if config is None:
        config = get_config().to_dict()
    
    # Determine modality from the first file
    modality = anat_files[0].suffix  # T1w or T2w
    logger.info(f"Workflow: starting {modality} synthesis")
    logger.info(f"Data: synthesizing {len(anat_files)} {modality} images")
    logger.info(f"Source runs: {[f.run or 'None' for f in anat_files]}")
    logger.info(f"Reference image (run-{anat_files[0].run or '01'}): {anat_files[0].path}")
    
    try:
        # Validate and ensure working directory exists
        work_dir = ensure_working_directory(working_dir, logger)
        logger.info(f"System: working directory - {work_dir}")
        
        # Use the first image as reference
        reference_file = anat_files[0]
        reference_path = validate_input_file(reference_file.path, logger)
        
        # Use working directory directly - Nextflow already isolates each process
        synthesis_work_dir = work_dir
        
        # Load reference image
        logger.info(f"Data: using reference {modality} - {os.path.basename(reference_path)}")
        reference_img = nib.load(str(reference_path))
        
        # Storage for coregistered images
        coregistered_images = [reference_img]
        
        # Coregister all other images to the reference
        for i, anat_file in enumerate(anat_files[1:], 1):
            logger.info(f"Step: coregistering {modality} {i+1}/{len(anat_files)} - {os.path.basename(anat_file.path)}")
            
            moving_path = validate_input_file(anat_file.path, logger)
            
            # Use the ses and run ids when available
            reference_run = anat_files[0].run or "01"
            moving_run = anat_file.run or f"{i+1:02d}"
            reference_id_parts = []
            moving_id_parts = []
            if anat_files[0].ses:
                reference_id_parts.append(f"ses-{anat_files[0].ses}")
            if anat_file.ses:
                moving_id_parts.append(f"ses-{anat_file.ses}")
            reference_id_parts.append(f"run-{reference_run}")
            moving_id_parts.append(f"run-{moving_run}")
            reference_id = "_".join(reference_id_parts)
            moving_id = "_".join(moving_id_parts)
            
            # Output prefix using the ses and run ids
            output_prefix = f"{moving_id}_to_{reference_id}_{modality}_coreg"
            
            try:
                # Compute transforms with ANTs registration (rigid only)
                registration_result = ants_register(
                    fixedf=str(reference_path),
                    movingf=str(moving_path),
                    working_dir=str(synthesis_work_dir),
                    output_prefix=output_prefix,
                    config=config,
                    logger=logger,
                    xfm_type='rigid'  # Use only linear registration (affine)
                )
                
                forward_transform = registration_result.get("forward_transform")
                if not forward_transform:
                    raise RuntimeError("ANTs registration did not produce a forward transform")

                # Remove the output image, because we are going to recompute it
                registered_path = synthesis_work_dir / f"{output_prefix}_registered.nii.gz"
                if registered_path.exists():
                    registered_path.unlink()

                # Apply transform (interpolation from config)
                interpolation = config.get("registration", {}).get("interpolation", "BSpline")
                apply_result = ants_apply_transforms(
                    movingf=str(moving_path),
                    moving_type=0,
                    interpolation=interpolation,
                    outputf_name=f"{output_prefix}_registered.nii.gz",
                    fixedf=str(reference_path),
                    working_dir=str(synthesis_work_dir),
                    transformf=[str(forward_transform)],
                    logger=logger,
                    reff=str(reference_path),
                    generate_tmean=False
                )

                coregistered_path = apply_result.get("imagef_registered")
                if not coregistered_path:
                    raise RuntimeError("ANTs apply transforms did not produce output image")

                logger.info(f"Step: successfully coregistered - {os.path.basename(coregistered_path)}")
                
                # Load and store the coregistered image
                coregistered_img = nib.load(coregistered_path)
                coregistered_images.append(coregistered_img)
                    
            except Exception as e:
                logger.error(f"Step: coregistration failed for {os.path.basename(anat_file.path)} - {e}")
                continue
        
        # Average all coregistered images
        if len(coregistered_images) < len(anat_files):
            logger.warning(f"Data: only {len(coregistered_images)}/{len(anat_files)} images successfully coregistered")
        
        if len(coregistered_images) > 1:
            logger.info(f"Step: averaging {len(coregistered_images)} coregistered images")
            
            # Incremental mean calculation to avoid loading all images into memory at once
            # Process images one by one: accumulate sum, then divide by count
            sum_data = None
            valid_count = 0
            
            for img in coregistered_images:
                try:
                    img_data = img.get_fdata()
                    
                    # Initialize sum with first valid image
                    if sum_data is None:
                        sum_data = img_data.astype(np.float64)  # Use float64 for accumulation precision
                    else:
                        # Accumulate sum incrementally
                        sum_data += img_data
                    
                    valid_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load image data: {e}, skipping")
                    continue
            
            if valid_count == 0:
                logger.error("No valid images could be loaded for averaging")
                return None
            
            # Calculate mean by dividing accumulated sum by count
            mean_data = (sum_data / valid_count).astype(np.float32)
            
            # Create synthesized image using reference header
            synthesized_img = nib.Nifti1Image(
                mean_data,
                affine=reference_img.affine,
                header=reference_img.header
            )
            
            # Generate output filename - write directly to working directory
            # Use consistent naming pattern like preprocessing.py
            output_name = f"anat_synthesized_{modality.lower()}.nii.gz"
            synthesized_path = work_dir / output_name
            
            # Save synthesized image
            nib.save(synthesized_img, str(synthesized_path))
            
            # Validate output file
            validate_output_file(synthesized_path, logger)
            logger.info(f"Output: synthesized {modality} saved - {os.path.basename(synthesized_path)}")
            logger.info(f"Workflow: synthesis completed - {len(coregistered_images)}/{len(anat_files)} images successfully coregistered and averaged")
            
            # Create a metadata sidecar JSON file
            metadata = {
                "Description": f"Synthesized {modality} image from multiple acquisitions",
                "Sources": [str(Path(f.path).name) for f in anat_files],
                "SourceRuns": [f.run for f in anat_files],
                "SynthesisMethod": "Linear coregistration followed by averaging",
                "NumberOfInputs": len(anat_files),
                "NumberOfSuccessfulCoregistrations": len(coregistered_images),
                "CoregistrationTool": "ANTs",
                "CoregistrationMethod": "Affine",
                "ReferenceImage": str(Path(anat_files[0].path).name),
                "ReferenceRun": anat_files[0].run,
                "ProcessingNote": "Run identifier removed from filename as this represents a synthesis of multiple runs",
                "OutputFilename": output_name,
                "Modality": modality
            }
            
            metadata_path = work_dir / output_name.replace('.nii.gz', '.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Output: synthesis metadata saved - {os.path.basename(metadata_path)}")
            
            return str(synthesized_path)
        else:
            logger.error("No successfully coregistered images to average")
            return None
            
    except Exception as e:
        logger.error(f"{modality} synthesis failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

