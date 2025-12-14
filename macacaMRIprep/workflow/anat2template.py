"""
Simplified anatomical processor using serial step-by-step structure.
"""

import os
import sys
import time
import logging
import multiprocessing
from pathlib import Path
from typing import Dict, Any, Optional, List
import json

from .base import BasePreprocessingWorkflow
from ..operations import bias_correction, apply_skullstripping, ants_register, reorient, correct_orientation_mismatch
from ..utils import run_command
from ..utils import resolve_template, get_filename_stem
from ..utils import log_workflow_start, log_workflow_end
from ..utils.bids import parse_bids_entities
from ..utils.system import set_numerical_threads
from ..quality_control import create_skullstripping_qc
from ..quality_control.snapshots import (
    create_bias_correction_qc,
    create_registration_qc
)

# Add the project root to sys.path to enable FastSurferRecon imports
# Similar to how FastSurferCNN is handled in preprocessing.py
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# %%
class AnatomicalProcessor(BasePreprocessingWorkflow):
    """Simplified anatomical processor with serial step execution."""
    
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
        
        # Start with original anatomical file
        anatf_cur = str(self.anat_file)
        
        try:
            # ANAT ORIENTATION CORRECTION
            # ------------------------------------------------------------
            if self.config.get("anat.orientation_correction.enabled", True):
                step_name = self.pipeline.add_step(
                    name="anat_orientation_correction",
                    func=correct_orientation_mismatch,
                    inputs={
                        "imagef": anatf_cur,
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
                    anatf_cur = result.output_files["imagef_orientation_corrected"]
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_cur)}")
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
                        "imagef": anatf_cur,
                        "output_name": "anat_reoriented.nii.gz"
                    }
                )
                # Get target_file, or default to RAS orientation if no template
                target_file = str(self.template_file) if self.template_file is not None else None
                target_orientation = "RAS" if target_file is None else None
                
                result = self.pipeline.run_step(
                    step_name,
                    target_file=target_file,
                    target_orientation=target_orientation,
                    generate_tmean=False
                )
                if result.output_files["imagef_reoriented"] is not None:
                    anatf_cur = result.output_files["imagef_reoriented"]
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_cur)}")
                else:
                    # This should rarely happen since we default to RAS, but kept for defensive programming
                    self.logger.info(f"Step: {step_name} skipped - no reorientation performed")
            else:
                self.logger.info("Step: reorient skipped (disabled in configuration)")

            # ANAT BIAS CORRECTION
            # ------------------------------------------------------------
            if self.config.get("anat.bias_correction.enabled", True):
                step_name = self.pipeline.add_step(
                    name="anat_bias_correction",
                    func=bias_correction,
                    inputs={
                        "imagef": str(anatf_cur),
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
                            image_original=anatf_cur,
                            image_corrected=anatf_corrected,
                            save_f=str(bias_qc_path),
                            modality="anat",
                            logger=self.logger
                        )
                        self.logger.info("QC: anatomical bias correction overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: anatomical bias correction failed - {e}")
                
                # update anatf_cur
                anatf_cur = anatf_corrected
            else:
                self.logger.info("Step: bias correction skipped (disabled in configuration)")

            # Still save anatomical file even if bias correction was skipped
            outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-preproc_{self.modality}.nii.gz"
            cmd_output = ["cp", anatf_cur, str(outputf)]
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
                # Store the image before skull stripping for QC
                anatf_with_skull = anatf_cur
                
                # Store T1w image for surface reconstruction
                outpuf_f_for_surfrecon["t1w_image"] = anatf_with_skull

                step_name = self.pipeline.add_step(
                    name="anat_skullstripping", 
                    func=apply_skullstripping,
                    inputs={
                        "imagef": anatf_cur,
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
                    
                    # Update anatf_with_skull to use cropped version for QC consistency
                    # (mask is in cropped space, so underlay should also be in cropped space)
                    anatf_with_skull = str(input_cropped_path)
                    self.logger.info(f"QC: updated underlay to cropped version for spatial consistency")

                    # Update T1w image for surface reconstruction to cropped version
                    outpuf_f_for_surfrecon["t1w_image"] = anatf_with_skull

                # Update the anatomical file to skull-stripped version
                # Note: If two-pass refinement was used, the skull-stripped image is already in cropped space
                anatf_cur = result.output_files["imagef_skullstripped"]
                anat_brain_mask = result.output_files["brain_mask"]
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_cur)}")
                self.logger.info(f"Output: brain mask generated - {os.path.basename(anat_brain_mask)}")

                # output to output_dir
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-preproc_{self.modality}_brain.nii.gz"
                cmd_output = ["cp", anatf_cur, str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: skull stripped anatomical file saved")

                # save the brain mask
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_mask.nii.gz"
                cmd_output = ["cp", anat_brain_mask, str(outputf)]
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
                    cmd_output = ["cp", result.output_files["segmentation"], str(outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(outputf))
                    self.logger.info(f"Output: atlas file saved")

                    outpuf_f_for_surfrecon["segmentation"] = outputf
                    outpuf_f_for_surfrecon["atlas_name"] = atlas_name

                if result.output_files.get("hemimask") is not None:
                    outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_hemimask.nii.gz"
                    cmd_output = ["cp", result.output_files["hemimask"], str(outputf)]
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
                            underlay_file=anatf_with_skull,
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
            # Skip template registration if output_space is native
            # Use dot notation for Config class compatibility
            output_space = self.config.get("template.output_space", "")
            if not output_space:
                # Fallback: try accessing via nested dict (for dict configs)
                template_dict = self.config.get("template", {})
                if isinstance(template_dict, dict):
                    output_space = template_dict.get("output_space", "")
            skip_template_registration = (output_space and output_space.lower() == "native")
            
            # Also skip if template_file is not available (should be None when output_space is native)
            if skip_template_registration or self.template_file is None:
                skip_template_registration = True
            
            if self.config.get("registration.enabled", True) and not skip_template_registration and self.template_file is not None:
                qc_modality = "anat2template"
                step_name = self.pipeline.add_step(
                    name="anat2template_registration",
                    func=ants_register,
                    inputs={
                        "movingf": anatf_cur,
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

                # output to output_dir
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_space-{self.template_name}_desc-preproc_{self.modality}.nii.gz"
                cmd_output = ["cp", result.output_files["imagef_registered"], str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: registered anatomical file saved")

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
                cmd_output = ["cp", result.output_files["forward_transform"], str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: forward transform saved")

                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_from-{self.template_name}_to-{self.modality}_mode-image_xfm.h5"
                cmd_output = ["cp", result.output_files["inverse_transform"], str(outputf)]
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
                        
                        create_registration_qc(
                            image_file=result.output_files["imagef_registered"],
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
