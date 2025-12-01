"""
Simplified anatomical processor using serial step-by-step structure.
"""

import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import json

from .base import BasePreprocessingWorkflow
from ..operations import bias_correction, apply_skullstripping, ants_register, reorient
from ..utils import run_command
from ..utils import resolve_template, get_filename_stem
from ..utils import log_workflow_start, log_workflow_end
from ..quality_control import create_skullstripping_qc
from ..quality_control.snapshots import (
    create_bias_correction_qc,
    create_registration_qc
)

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
        modality: str = "T1w"
    ):
        super().__init__(output_dir, working_dir, config, logger)
        
        self.anat_file = Path(anat_file)
        self.modality = modality
        self.template_spec = template_spec
        
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
            # ANAT REORIENT
            # ------------------------------------------------------------
            if self.config.get("anat.reorient.enabled", True):
                step_name = self.pipeline.add_step(
                    name="anat_reorient",
                    func=reorient,
                    inputs={
                        "imagef": anatf_cur,
                    }
                )
                # if template file is not provided, keep the step but skip running it
                result = self.pipeline.run_step(
                    step_name,
                    modal="anat",
                    target_file=str(self.template_file) if self.template_file is not None else None,
                    generate_tmean=False
                )
                if result.output_files["imagef_reoriented"] is not None:
                    anatf_cur = result.output_files["imagef_reoriented"]
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(anatf_cur)}")
                else:
                    self.logger.info(f"Step: {step_name} skipped - reorientation not needed")
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

            # ANAT SKULL STRIPPING 
            # ------------------------------------------------------------
            if self.config.get("anat.skullstripping.enabled", True):
                # Store the image before skull stripping for QC
                anatf_with_skull = anatf_cur

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

                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_mask.nii.gz"
                cmd_output = ["cp", anat_brain_mask, str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: brain mask file saved")

                # if segmentation and hemimask are provided, save them as well
                if result.output_files.get("segmentation") is not None:
                    outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_desc-brain_segmentation.nii.gz"
                    cmd_output = ["cp", result.output_files["segmentation"], str(outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(outputf))
                    self.logger.info(f"Output: segmentation file saved")
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
            output_space = self.config.get("template", {}).get("output_space", "")
            skip_template_registration = (output_space.lower() == "native")
            
            if self.config.get("registration.enabled", True) and not skip_template_registration:
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
                
                # Save anatomical file in native space (copy current anatomical file)
                outputf = self.output_dir / f"{self.bids_prefix_wo_modality}_space-native_desc-preproc_{self.modality}.nii.gz"
                cmd_output = ["cp", anatf_cur, str(outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(outputf))
                self.logger.info(f"Output: native space anatomical file saved")
            else:
                self.logger.info("Step: template registration skipped (disabled in configuration)")

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
    