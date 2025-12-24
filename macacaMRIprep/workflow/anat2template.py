"""
Simplified anatomical processor using serial step-by-step structure.
"""

import os
import sys
import time
import logging
import multiprocessing
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import json

from .base import BasePreprocessingWorkflow
from ..operations import bias_correction, apply_segmentation, reorient, correct_orientation_mismatch, conform_to_template
from ..operations.registration import ants_register, ants_apply_transforms
from ..utils import run_command
from ..utils import resolve_template, get_filename_stem
from ..utils import log_workflow_start, log_workflow_end
from ..utils.bids import parse_bids_entities
from ..utils.system import set_numerical_threads
from ..quality_control import create_skullstripping_qc
from ..quality_control.snapshots import (
    create_bias_correction_qc,
    create_registration_qc,
    create_conform_qc,
    create_atlas_segmentation_qc,
    create_surf_recon_tissue_seg_qc,
    create_cortical_surf_and_measures_qc
)
from ..config import get_output_space

# Add the project root to sys.path to enable FastSurferRecon imports
# Similar to how FastSurferCNN is handled in preprocessing.py
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# %%
class AnatomicalProcessor(BasePreprocessingWorkflow):
    """Simplified anatomical processor with serial step execution."""
    
    # Default template for conform step (used when output_space is native or template_file is None)
    DEFAULT_CONFORM_TEMPLATE = "NMT2Sym:res-025"
    
    def __init__(
        self,
        anat_file: str,
        output_dir: str,
        working_dir: Optional[str] = None,
        template_spec: Optional[str] = None,
        template_file: Optional[str] = None,
        template_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
        qc_dir: Optional[str] = None,
        modality: str = "T1w",
        output_root: Optional[str] = None
    ):
        super().__init__(output_dir, working_dir, config, logger)
        
        self.anat_file = Path(anat_file)
        self.modality = modality
        self.template_spec = template_spec
        
        # Store output_root for fastsurfer directory (dataset-level, not subject-level)
        if output_root:
            self.output_root = Path(output_root)
        else:
            raise ValueError("output_root is required")
        # Template resolution with override logic
        # Priority: 1) template_file+template_name (direct), 2) template_spec (resolve), 3) native (skip)
        self.template_file = None
        self.template_name = None
        
        if template_file and template_name:
            # Direct template file and name provided - use them and override template_spec
            self.template_file = template_file
            self.template_name = template_name
            self.logger.info(f"Template: using direct file {os.path.basename(template_file)}")
            
        elif template_spec and template_spec.lower() != "native":
            # Standard template spec resolution
            try:
                self.template_file = resolve_template(template_spec)
                self.template_name = template_spec.split(":")[0]
                if not self.template_name:
                    raise ValueError(f"Failed to extract template name from template_spec: {template_spec}")
                self.logger.info(f"Template: resolved {template_spec} -> {os.path.basename(self.template_file)}")
            except Exception as e:
                self.logger.error(f"Template: failed to resolve {template_spec} - {e}")
                raise
        elif template_spec and template_spec.lower() == "native":
            self.logger.info(f"Template: output space is native - skipping resolution")
        
        # Set up QC directory
        if qc_dir:
            self.qc_dir = Path(qc_dir)
        else:
            # Fallback to default if not provided - don't create until needed
            self.qc_dir = self.working_dir / "figures"

        # Use original filename stem as prefix to preserve exact input structure
        self.bids_prefix = get_filename_stem(self.anat_file)
        self.bids_prefix_wo_modality = self.bids_prefix.replace(f"_{modality}", "")
        
        # Track generated output files for caching
        self.generated_files = []
    
    def run(self) -> Dict[str, Any]:
        """Run anatomical processing pipeline with serial steps."""
        workflow_name = "Anat2Template"
        start_time = time.time()
        
        # Log workflow start
        log_workflow_start(self.workflow_logger, workflow_name, self.config.to_dict())
        self.logger.info("Workflow: starting anatomical to template registration pipeline")
        
        # Only create QC directory if quality control is enabled
        if self.config.get("quality_control.enabled", True):
            self.qc_dir.mkdir(parents=True, exist_ok=True)
        
        # Maintain two versions of anatomical file: with skull (full-brain) and without skull (brain-only)
        anatf_w_skull = str(self.anat_file)  # Full-brain version (always maintained)
        anatf_wo_skull = None  # Skull-stripped version (None until skull stripping)
        
        try:
            # ANAT ORIENTATION CORRECTION
            # ------------------------------------------------------------
            if self.config.get("anat.orientation_correction.enabled", True):
                step_name = self.pipeline.add_step(
                    name="anat_orientation_correction",
                    func=correct_orientation_mismatch,
                    inputs={
                        "imagef": anatf_w_skull,
                        "output_name": "anat_orientation_corrected.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    logger=self.logger,
                    config=self.config.to_dict(),
                    generate_tmean=False
                )
                if result.output_files["imagef_orientation_corrected"] is not None:
                    anatf_w_skull = result.output_files["imagef_orientation_corrected"]
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_w_skull)}")
                else:
                    self.logger.info(f"Step: {step_name} skipped - no orientation correction performed")
            else:
                self.logger.info("Step: orientation correction skipped (disabled in configuration)")

            # ANAT REORIENT
            # ------------------------------------------------------------
            if self.config.get("anat.reorient.enabled", True):
                step_name = self.pipeline.add_step(
                    name="anat_reorient",
                    func=reorient,
                    inputs={
                        "imagef": anatf_w_skull,
                        "output_name": "anat_reoriented.nii.gz"
                    }
                )
                # Get target_file, or default to RAS orientation if no template
                # Use template_file if available, otherwise default to RAS
                target_file = str(self.template_file) if self.template_file is not None else None
                target_orientation = "RAS" if target_file is None else None
                
                result = self.pipeline.run_step(
                    step_name,
                    target_file=target_file,
                    target_orientation=target_orientation,
                    generate_tmean=False
                )
                if result.output_files["imagef_reoriented"] is not None:
                    anatf_w_skull = result.output_files["imagef_reoriented"]
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_w_skull)}")
                else:
                    # This should rarely happen since we default to RAS, but kept for defensive programming
                    self.logger.info(f"Step: {step_name} skipped - no reorientation performed")
            else:
                self.logger.info("Step: reorient skipped (disabled in configuration)")


            # ANAT CONFORM TO TEMPLATE
            # ------------------------------------------------------------
            if self.config.get("anat.conform.enabled", True):
                # Determine conform template file
                # Priority: 1) template_file (already resolved), 2) template_spec (resolve now), 3) default
                if self.template_file is not None:
                    conform_template_file = str(self.template_file)
                    self.logger.info(f"Conform: using specified template: {os.path.basename(self.template_file)}")
                elif self.template_spec and self.template_spec.lower() != "native":
                    # Resolve template_spec if it wasn't resolved in __init__ (shouldn't happen, but safe fallback)
                    try:
                        conform_template_file = resolve_template(self.template_spec)
                        self.logger.info(f"Conform: resolved template_spec: {self.template_spec} -> {os.path.basename(conform_template_file)}")
                    except Exception as e:
                        self.logger.error(f"Conform: failed to resolve template_spec {self.template_spec} - {e}")
                        raise
                else:
                    # Use default template for conform (when output_space is native or no template specified)
                    try:
                        conform_template_file = resolve_template(self.DEFAULT_CONFORM_TEMPLATE)
                        self.logger.info(f"Conform: using default template: {self.DEFAULT_CONFORM_TEMPLATE} -> {os.path.basename(conform_template_file)}")
                    except Exception as e:
                        self.logger.error(f"Conform: failed to resolve default template {self.DEFAULT_CONFORM_TEMPLATE} - {e}")
                        raise
                
                # run conform to template
                # Check if skullstripping is disabled - if so, skip internal skullstripping in conform
                skip_skullstripping = not self.config.get("anat.skullstripping.enabled", True)
                
                step_name = self.pipeline.add_step(
                    name="anat_conform",
                    func=conform_to_template,
                    inputs={
                        "imagef": anatf_w_skull,
                        "template_file": conform_template_file,
                        "output_name": "anat_conformed.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    logger=self.logger,
                    skip_skullstripping=skip_skullstripping
                )
                
                if result.output_files["imagef_conformed"] is not None:
                    anatf_conformed = result.output_files["imagef_conformed"]
                    conform_template_f = result.output_files["template_f"]
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_conformed)}")
                    
                    # Update anatf_w_skull to conformed image
                    anatf_w_skull = anatf_conformed

                    # save the xfm files with from-scanner_to-{self.modality}
                    forward_xfm = result.output_files.get("forward_xfm")
                    inverse_xfm = result.output_files.get("inverse_xfm")
                    
                    if forward_xfm:
                        # Generate BIDS-compliant filename for forward transform
                        filename_stem = get_filename_stem(self.anat_file)
                        filename_stem = filename_stem.replace(f"_{self.modality}", "")
                        forward_xfm_outputf = self.output_dir / f"{filename_stem}_from-scanner_to-{self.modality}_mode-image_xfm.mat"
                        
                        # Copy the transform file to output directory
                        shutil.copy2(forward_xfm, str(forward_xfm_outputf))
                        self.generated_files.append(str(forward_xfm_outputf))
                        self.logger.info(f"Output: forward transform saved - {os.path.basename(forward_xfm_outputf)}")
                    
                    if inverse_xfm:
                        # Generate BIDS-compliant filename for inverse transform
                        filename_stem = get_filename_stem(self.anat_file)
                        filename_stem = filename_stem.replace(f"_{self.modality}", "")
                        inverse_xfm_outputf = self.output_dir / f"{filename_stem}_from-{self.modality}_to-scanner_mode-image_xfm.mat"
                        
                        # Copy the transform file to output directory
                        shutil.copy2(inverse_xfm, str(inverse_xfm_outputf))
                        self.generated_files.append(str(inverse_xfm_outputf))
                        self.logger.info(f"Output: inverse transform saved - {os.path.basename(inverse_xfm_outputf)}")
                    
                    # Generate QC
                    if self.config.get("quality_control.enabled", True):
                        try:
                            # Generate BIDS-compliant filename for conform QC
                            filename_stem = get_filename_stem(self.anat_file)
                            filename_stem = filename_stem.replace(f"_{self.modality}", "")
                            conform_qc_filename = f"{filename_stem}_desc-conform_{self.modality}.png"
                            conform_qc_path = self.qc_dir / conform_qc_filename
                            
                            create_conform_qc(
                                conformed_file=anatf_conformed,
                                template_file=conform_template_f,
                                save_f=str(conform_qc_path),
                                modality="anat",
                                logger=self.logger
                            )
                            self.logger.info("QC: anatomical conform overlay created")
                        except Exception as e:
                            self.logger.warning(f"QC: anatomical conform failed - {e}")
                else:
                    self.logger.warning(f"Step: {step_name} returned None - conform may have been skipped")
            else:
                self.logger.info("Step: conform skipped (disabled in configuration)")

            # ANAT BIAS CORRECTION
            # ------------------------------------------------------------
            if self.config.get("anat.bias_correction.enabled", True):
                step_name = self.pipeline.add_step(
                    name="anat_bias_correction",
                    func=bias_correction,
                    inputs={
                        "imagef": str(anatf_w_skull),
                        "output_name": "anat_bias_corrected.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    modal="anat"
                )
                
                # Update the anatomical file
                anatf_corrected = result.output_files["imagef_bias_corrected"]
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_corrected)}")
                
                # Generate QC
                if self.config.get("quality_control.enabled", True):
                    try:
                        # Generate BIDS-compliant filename for bias correction QC
                        filename_stem = get_filename_stem(self.anat_file)
                        filename_stem = filename_stem.replace(f"_{self.modality}", "")
                        bias_qc_filename = f"{filename_stem}_desc-biasCorrection_{self.modality}.png"
                        bias_qc_path = self.qc_dir / bias_qc_filename
                        
                        create_bias_correction_qc(
                            image_original=anatf_w_skull,
                            image_corrected=anatf_corrected,
                            save_f=str(bias_qc_path),
                            modality="anat",
                            logger=self.logger
                        )
                        self.logger.info("QC: anatomical bias correction overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: anatomical bias correction failed - {e}")
                
                # update anatf_w_skull
                anatf_w_skull = anatf_corrected
            else:
                self.logger.info("Step: bias correction skipped (disabled in configuration)")

            # Still save anatomical file even if bias correction was skipped (full-brain version)
            outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-preproc_{self.modality}.nii.gz"
            cmd_output = ["cp", str(anatf_w_skull), str(outputf)]
            run_command(cmd_output)
            self.generated_files.append(str(outputf))
            self.logger.info(f"Output: preprocessed anatomical file saved")

            # Initialize surface reconstruction file dictionary
            # This will be populated during skull stripping if enabled
            outpuf_f_for_surfrecon = {
                "t1w_image": None,
                "segmentation": None,
                "mask": None,
                "atlas_name": None
            }

            # ANAT SKULL STRIPPING 
            # ------------------------------------------------------------
            # if config.get(anat.surface_reconstruction.enabled) is True, force to run skullstripping
            if self.config.get("anat.skullstripping.enabled", True):
                # Store T1w image for surface reconstruction (full-brain version)
                outpuf_f_for_surfrecon["t1w_image"] = anatf_w_skull

                step_name = self.pipeline.add_step(
                    name="anat_segmentation", 
                    func=apply_segmentation,
                    inputs={
                        "imagef": anatf_w_skull,
                        "modal": "anat",
                        "output_name": "anat_brain.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict()
                )

                # Handle cropped input if two-pass refinement was used
                if result.output_files.get("input_cropped") is not None:
                    input_cropped_path = result.output_files["input_cropped"]
                    self.logger.info(f"Step: two-pass refinement detected - cropped input available")

                    # Move the original preprocessed file to desc-preprocOrigSize
                    outputf_pre = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-preproc_{self.modality}.nii.gz"
                    outputf_post = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-preprocOrigSize_{self.modality}.nii.gz"
                    if outputf_pre.exists():
                        cmd_output = ["mv", str(outputf_pre), str(outputf_post)]
                        run_command(cmd_output)
                        self.generated_files.append(str(outputf_post))
                        self.logger.info(f"Output: original size anatomical file renamed to {outputf_post.name}")
                    
                    # Save the cropped input as desc-preproc
                    # Note: input_cropped is already bias-corrected (it's cropped from the bias-corrected image)
                    cmd_output = ["cp", str(input_cropped_path), str(outputf_pre)]
                    run_command(cmd_output)
                    self.generated_files.append(str(outputf_pre))
                    self.logger.info(f"Output: cropped input saved as {outputf_pre.name}")
                    
                    # Update anatf_w_skull to use cropped version (for QC consistency and surface recon)
                    # (mask is in cropped space, so underlay should also be in cropped space)
                    anatf_w_skull = str(input_cropped_path)
                    self.logger.info(f"QC: updated full-brain version to cropped version for spatial consistency")

                    # Update T1w image for surface reconstruction to cropped version
                    outpuf_f_for_surfrecon["t1w_image"] = anatf_w_skull

                # After skull stripping: wo_skull gets the skull-stripped version, w_skull remains unchanged
                # Note: If two-pass refinement was used, the skull-stripped image is already in cropped space
                anatf_wo_skull = result.output_files["imagef_skullstripped"]
                anat_brain_mask = result.output_files["brain_mask"]
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_wo_skull)}")
                self.logger.info(f"Output: brain mask generated - {os.path.basename(anat_brain_mask)}")

                # output to output_dir
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-preproc_{self.modality}_brain.nii.gz"
                cmd_output = ["cp", str(anatf_wo_skull), str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: skull stripped anatomical file saved")

                # save the brain mask
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_mask.nii.gz"
                cmd_output = ["cp", str(anat_brain_mask), str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: brain mask file saved")

                outpuf_f_for_surfrecon["mask"] = outputf

                # if segmentation and hemimask are provided, save them as well
                if result.output_files.get("segmentation") is not None:
                    # Use atlas_name if available, otherwise use default name
                    atlas_name = result.output_files.get("atlas_name")
                    if atlas_name:
                        outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_atlas{atlas_name}.nii.gz"
                    else:
                        outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_atlas.nii.gz"
                    cmd_output = ["cp", str(result.output_files["segmentation"]), str(outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(outputf))
                    self.logger.info(f"Output: atlas file saved")

                    outpuf_f_for_surfrecon["segmentation"] = outputf
                    outpuf_f_for_surfrecon["atlas_name"] = atlas_name

                    # generate QC
                    if self.config.get("quality_control.enabled", True):
                        try:
                            # Generate BIDS-compliant filename for atlas segmentation QC
                            filename_stem = get_filename_stem(self.anat_file)
                            filename_stem = filename_stem.replace(f"_{self.modality}", "")
                            atlas_qc_filename = f"{filename_stem}_desc-atlasSegmentation_{self.modality}.png"
                            atlas_qc_path = self.qc_dir / atlas_qc_filename
                            
                            create_atlas_segmentation_qc(
                                underlay_file=str(anatf_w_skull),
                                atlas_file=str(outputf),
                                save_f=str(atlas_qc_path),
                                modality="anat",
                                logger=self.logger
                            )
                            self.logger.info("QC: atlas segmentation overlay created")
                        except Exception as e:
                            self.logger.warning(f"QC: atlas segmentation overlay failed - {e}")

                if result.output_files.get("hemimask") is not None:
                    outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_hemimask.nii.gz"
                    cmd_output = ["cp", str(result.output_files["hemimask"]), str(outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(outputf))
                    self.logger.info(f"Output: hemimask file saved")

                # Generate QC
                if self.config.get("quality_control.enabled", True):
                    try:
                        # Generate BIDS-compliant filename for skull stripping QC
                        filename_stem = get_filename_stem(self.anat_file)
                        filename_stem = filename_stem.replace(f"_{self.modality}", "")
                        skull_qc_filename = f"{filename_stem}_desc-skullStripping_{self.modality}.png"
                        skull_qc_path = self.qc_dir / skull_qc_filename
                        
                        create_skullstripping_qc(
                            underlay_file=anatf_w_skull,
                            mask_file=anat_brain_mask,
                            save_f=str(skull_qc_path),
                            modality="anat",
                            logger=self.logger
                        )
                        self.logger.info("QC: anatomical skull stripping overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: anatomical skull stripping failed - {e}")
                elif self.config.get("quality_control.enabled", True) and anat_brain_mask is None:
                    self.logger.warning("QC: skull stripping skipped - brain mask not available")
            else:
                self.logger.info("Step: skull stripping skipped (disabled in configuration)")
                anat_brain_mask = None

            # ANAT REGISTRATION TO TEMPLATE
            # ------------------------------------------------------------
            # Skip template registration if output_space is native or template_file is not available
            output_space = get_output_space(self.config)
            skip_template_registration = (
                (output_space and output_space.lower() == "native") or 
                self.template_file is None
            )
            
            if self.config.get("registration.enabled", True) and not skip_template_registration:
                # Validate template_file and template_name exist before use
                if self.template_file is None:
                    raise ValueError("Template registration enabled but template_file is None")
                if self.template_name is None:
                    raise ValueError("Template registration enabled but template_name is None")
                qc_modality = "anat2template"
                
                # Save original full-brain version before registration (needed for registered full-brain output)
                anatf_w_skull_original = anatf_w_skull
                
                # Use skull-stripped version for registration if available (better alignment), otherwise use full-brain
                anatf_for_registration = anatf_wo_skull if anatf_wo_skull is not None else anatf_w_skull
                
                step_name = self.pipeline.add_step(
                    name="anat2template_registration",
                    func=ants_register,
                    inputs={
                        "movingf": anatf_for_registration,
                        "fixedf": str(self.template_file),
                        "output_prefix": qc_modality
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    xfm_type=self.config.get("registration.anat2template_xfm_type", "syn")
                )
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(result.output_files['imagef_registered'])}")

                # Get registration outputs
                forward_transform = result.output_files["forward_transform"]
                inverse_transform = result.output_files["inverse_transform"]
                
                # Update the version that was registered
                if anatf_wo_skull is not None:
                    anatf_wo_skull = result.output_files["imagef_registered"]
                else:
                    anatf_w_skull = result.output_files["imagef_registered"]
                
                # Apply transform to full-brain version to create registered full-brain output
                # Registration was done with skull-stripped version (if available), but output should be full-brain
                if anatf_wo_skull is not None:
                    # Registration used wo_skull, so transform the original full-brain version
                    step_name_fullbrain = self.pipeline.add_step(
                        name="anat2template_fullbrain_transform",
                        func=ants_apply_transforms,
                    )
                    
                    result_fullbrain = self.pipeline.run_step(
                        step_name_fullbrain,
                        movingf=anatf_w_skull_original,
                        moving_type=3,
                        interpolation=self.config.get("registration", {}).get("interpolation", "trilinear"),
                        outputf_name=f"anat2template_fullbrain.nii.gz",
                        fixedf=str(self.template_file),
                        transformf=[forward_transform],
                        reff=str(self.template_file),
                        generate_tmean=False,
                    )
                    
                    # Save space-{template} preprocessed file (full-brain version)
                    anatf_w_skull_registered = result_fullbrain.output_files["imagef_registered"]
                else:
                    # Registration used w_skull, so w_skull is already registered - use it directly
                    anatf_w_skull_registered = anatf_w_skull
                
                # output to output_dir
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_space-{self.template_name}_desc-preproc_{self.modality}.nii.gz"
                cmd_output = ["cp", str(anatf_w_skull_registered), str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: registered anatomical file saved (full-brain)")

                # also save a json file that records the reference file
                ref_info_outputf = f"{str(outputf).split('.nii.gz')[0]}.json"
                ref_info = {
                    "target_file": str(self.template_file),
                }
                try:
                    with open(ref_info_outputf, 'w') as f:
                        json.dump(ref_info, f, indent=2)
                except (IOError, PermissionError) as e:
                    self.logger.error(f"Output: failed to write reference info JSON - {e}")

                # save the xfm files
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_from-{self.modality}_to-{self.template_name}_mode-image_xfm.h5"
                cmd_output = ["cp", str(forward_transform), str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: forward transform saved")

                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_from-{self.template_name}_to-{self.modality}_mode-image_xfm.h5"
                cmd_output = ["cp", str(inverse_transform), str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: inverse transform saved")

                # Generate QC
                if self.config.get("quality_control.enabled", True):
                    try:
                        # Generate BIDS-compliant filename for registration QC
                        filename_stem = get_filename_stem(self.anat_file)
                        filename_stem = filename_stem.replace(f"_{self.modality}", "")
                        reg_qc_filename = f"{filename_stem}_desc-{qc_modality}_{self.modality}.png"
                        reg_qc_path = self.qc_dir / reg_qc_filename
                        
                        # Use the version that was registered for QC
                        anatf_for_qc = anatf_wo_skull if anatf_wo_skull is not None else anatf_w_skull
                        create_registration_qc(
                            image_file=anatf_for_qc,
                            template_file=str(self.template_file),
                            save_f=str(reg_qc_path),
                            modality=qc_modality,
                            logger=self.logger
                        )
                        self.logger.info("QC: registration overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: registration failed - {e}")
            elif skip_template_registration:
                self.logger.info("Step: template registration skipped (output_space is native)")
                # No need to create space-native file - preprocessed files are already in native space
            else:
                self.logger.info("Step: template registration skipped (disabled in configuration)")


            # SURFACE RECONSTRUCTION
            # ------------------------------------------------------------
            if self.config.get("anat.surface_reconstruction.enabled", True):
                # Only run if we have the required files from skull stripping
                if (outpuf_f_for_surfrecon.get("t1w_image") is not None and
                    outpuf_f_for_surfrecon.get("segmentation") is not None and 
                    outpuf_f_for_surfrecon.get("mask") is not None and
                    outpuf_f_for_surfrecon.get("atlas_name") is not None):
                    
                    try:
                        self.logger.info("=" * 80)
                        self.logger.info("Surface Reconstruction: Starting")
                        self.logger.info("=" * 80)
                        
                        # Extract BIDS subject ID
                        bids_entities = parse_bids_entities(self.anat_file.name)
                        subject_id = bids_entities.get("sub")
                        if not subject_id:
                            raise ValueError(
                                f"Could not extract BIDS subject ID from filename: {self.anat_file.name}. "
                                f"Expected 'sub-XX' entity in filename."
                            )
                        if not subject_id.startswith("sub-"):
                            subject_id = f"sub-{subject_id}"
                        
                        # Setup FreeSurfer subjects directory at dataset level
                        # Structure: {dataset_root}/fastsurfer/sub-XXX
                        fs_subjects_dir = self.output_root / "fastsurfer"
                        fs_subjects_dir.mkdir(parents=True, exist_ok=True)
                        fs_subject_dir = fs_subjects_dir / subject_id
                        
                        self.logger.info(f"Surface Recon: Subject ID = {subject_id}")
                        self.logger.info(f"Surface Recon: Subjects directory = {fs_subjects_dir}")
                        
                        # Get atlas name
                        atlas_name = outpuf_f_for_surfrecon["atlas_name"]
                        self.logger.info(f"Surface Recon: Atlas = {atlas_name}")
                        
                        # Import FastSurferRecon modules (needed for both LUT path and pipeline config)
                        from FastSurferRecon.fastsurfer_recon.config import ReconSurfConfig, AtlasConfig, ProcessingConfig  # type: ignore
                        from FastSurferRecon.fastsurfer_recon.pipeline import ReconSurfPipeline  # type: ignore
                        
                        # Get LUT path using FastSurferRecon's AtlasConfig (has built-in fallbacks)
                        atlas_config = AtlasConfig(name=atlas_name)
                        lut_path = atlas_config.colorlut_path
                        
                        if lut_path is None or not lut_path.exists():
                            raise FileNotFoundError(
                                f"LUT file not found for atlas {atlas_name}. "
                                f"AtlasConfig searched but could not locate ColorLUT file."
                            )
                        
                        self.logger.info(f"Surface Recon: LUT path = {lut_path}")
                        
                        # Validate required files exist before processing
                        t1w_path = Path(outpuf_f_for_surfrecon["t1w_image"])
                        seg_path = Path(outpuf_f_for_surfrecon["segmentation"])
                        mask_path = Path(outpuf_f_for_surfrecon["mask"])
                        
                        for path, name in [(t1w_path, "T1w image"), (seg_path, "segmentation"), (mask_path, "mask")]:
                            if not path.exists():
                                raise FileNotFoundError(f"Surface Recon: Required file not found: {name} at {path}")
                        
                        self.logger.info("Surface Recon: All required files validated")
                        
                        # Step 1: Prepare files for FreeSurfer using postprocess_for_freesurfer
                        self.logger.info("Surface Recon: Step 1 - Preparing files for FreeSurfer format")
                        try:
                            from FastSurferCNN.postprocessing.prepping_for_surfrecon import postprocess_for_freesurfer
                            
                            prep_result = postprocess_for_freesurfer(
                                t1w_image=str(t1w_path),
                                segmentation=str(seg_path),
                                mask=str(mask_path),
                                lut_path=str(lut_path),
                                subject_dir=str(fs_subject_dir),
                                vox_size="min",
                                orientation="lia"
                            )
                            
                            if prep_result != 0:
                                raise RuntimeError(f"File preparation failed: {prep_result}")
                            
                            self.logger.info("Surface Recon: File preparation completed successfully")
                        except ImportError as e:
                            self.logger.error(f"Surface Recon: Failed to import postprocess_for_freesurfer - {e}")
                            raise
                        except Exception as e:
                            self.logger.error(f"Surface Recon: File preparation failed - {e}")
                            raise
                        
                        # Step 2: Run surface reconstruction pipeline
                        self.logger.info("Surface Recon: Step 2 - Running surface reconstruction pipeline")
                        try:

                            # Get thread count from config
                            n_threads = self.config.get("anat.surface_reconstruction.threads")
                            set_numerical_threads(n_threads, include_itk=False)
                            self.logger.info(f"Surface Recon: Using {n_threads} threads for numerical libraries and hemisphere parallelism")
                            
                            # self.verbose is guaranteed to be int (0, 1, or 2) after normalization
                            # FastSurferRecon expects verbose: 0 or 1, so map >=2 to 1
                            recon_verbose = 1 if self.verbose >= 2 else 0
                            
                            # Create configuration using defaults from YAML, only override non-default values
                            recon_config = ReconSurfConfig.with_defaults(
                                subject_id=subject_id,
                                subjects_dir=fs_subjects_dir,
                                atlas={"name": atlas_name},
                                processing={"threads": n_threads},  # Only override threads (default is 1)
                                verbose=recon_verbose,
                            )
                            
                            # Run pipeline
                            pipeline = ReconSurfPipeline(recon_config)
                            pipeline.run()
                            
                            self.logger.info("Surface Recon: Surface reconstruction completed successfully")
                            
                            # Add FreeSurfer subject directory to generated files
                            self.generated_files.append(str(fs_subject_dir))
                            
                        except ImportError as e:
                            self.logger.error(f"Surface Recon: Failed to import FastSurferRecon modules - {e}")
                            raise
                        except Exception as e:
                            self.logger.error(f"Surface Recon: Pipeline execution failed - {e}")
                            raise
                        
                        self.logger.info("=" * 80)
                        self.logger.info("Surface Reconstruction: Completed Successfully")
                        self.logger.info("=" * 80)
                        
                    except Exception as e:
                        # Log error but don't break the main pipeline
                        self.logger.warning(f"Surface Reconstruction failed - {e}")
                        self.logger.warning("Continuing with main pipeline...")
                else:
                    missing = []
                    if outpuf_f_for_surfrecon.get("t1w_image") is None:
                        missing.append("t1w_image")
                    if outpuf_f_for_surfrecon.get("segmentation") is None:
                        missing.append("segmentation")
                    if outpuf_f_for_surfrecon.get("mask") is None:
                        missing.append("mask")
                    if outpuf_f_for_surfrecon.get("atlas_name") is None:
                        missing.append("atlas_name")
                    self.logger.info(f"Surface Reconstruction: Skipped - missing required files: {', '.join(missing)}")
            else:
                self.logger.info("Surface Reconstruction: Skipped (disabled in configuration)")

            # SURFACE RECONSTRUCTION QC
            # ------------------------------------------------------------
            if self.qc_dir and self.config.get("anat.surface_reconstruction.enabled", True):
                try:
                    # Check if surface reconstruction was successful by checking if fs_subject_dir exists
                    # We need to reconstruct fs_subject_dir path from the same logic used above
                    bids_entities = parse_bids_entities(self.anat_file.name)
                    subject_id = bids_entities.get("sub")
                    if subject_id and not subject_id.startswith("sub-"):
                        subject_id = f"sub-{subject_id}"
                    
                    if subject_id:
                        fs_subjects_dir = self.output_root / "fastsurfer"
                        fs_subject_dir = fs_subjects_dir / subject_id
                        surf_dir = fs_subject_dir / "surf"
                        
                        # Check if surface reconstruction completed successfully
                        if fs_subject_dir.exists() and surf_dir.exists():
                            self.logger.info("QC: generating surface reconstruction QC snapshots...")
                            
                            # Get atlas name
                            atlas_name = outpuf_f_for_surfrecon.get("atlas_name", "ARM2atlas")
                            
                            # Generate surface reconstruction tissue segmentation QC
                            try:
                                filename_stem = get_filename_stem(self.anat_file)
                                filename_stem = filename_stem.replace(f"_{self.modality}", "")
                                surf_seg_qc_filename = f"{filename_stem}_desc-surfReconTissueSeg_{self.modality}.png"
                                surf_seg_qc_path = self.qc_dir / surf_seg_qc_filename
                                
                                create_surf_recon_tissue_seg_qc(
                                    fs_subject_dir=str(fs_subject_dir),
                                    save_f=str(surf_seg_qc_path),
                                    modality=self.modality,
                                    logger=self.logger
                                )
                                self.logger.info("QC: surface reconstruction tissue segmentation overlay created")
                            except Exception as e:
                                self.logger.warning(f"QC: surface reconstruction tissue segmentation failed - {e}")
                            
                            # Generate cortical surface and measures QC
                            try:
                                filename_stem = get_filename_stem(self.anat_file)
                                filename_stem = filename_stem.replace(f"_{self.modality}", "")
                                cortical_surf_qc_filename = f"{filename_stem}_desc-corticalSurfAndMeasures_{self.modality}.png"
                                cortical_surf_qc_path = self.qc_dir / cortical_surf_qc_filename
                                
                                create_cortical_surf_and_measures_qc(
                                    fs_subject_dir=str(fs_subject_dir),
                                    save_f=str(cortical_surf_qc_path),
                                    atlas_name=atlas_name,
                                    modality=self.modality,
                                    logger=self.logger
                                )
                                self.logger.info("QC: cortical surface and measures plot created")
                            except Exception as e:
                                self.logger.warning(f"QC: cortical surface and measures plot failed - {e}")
                        else:
                            self.logger.info("QC: surface reconstruction QC skipped - surface reconstruction not completed")
                except Exception as e:
                    self.logger.warning(f"QC: surface reconstruction QC generation failed - {e}")

            # ------------------------------------------------------------
            # Calculate workflow duration
            duration = time.time() - start_time
            
            # Log successful completion
            log_workflow_end(self.workflow_logger, workflow_name, True, duration)
            
            self.logger.info(f"Workflow: Anat2Template pipeline completed successfully")
            
            # Return results including generated files
            return {
                "status": "success",
                "output_dir": str(self.output_dir),
                "generated_files": self.generated_files,
                "duration": duration
            }
            
        except Exception as e:
            # Calculate workflow duration
            duration = time.time() - start_time
            
            # Log failure
            log_workflow_end(self.workflow_logger, workflow_name, False, duration)
            
            self.logger.error(f"Workflow: Anat2Template pipeline failed - {str(e)}")
            raise
    
# %%
