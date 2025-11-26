"""
Simplified functional processor using serial step-by-step structure.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
import logging
import time
import numpy as np
import json

from .base import BasePreprocessingWorkflow
from ..operations.preprocessing import (
    precheck,
    slice_timing_correction, 
    motion_correction, 
    despike,
    bias_correction,
)
from ..operations.registration import (
    ants_register,
    ants_apply_transforms
)
from ..quality_control import (
    create_motion_correction_qc,
    create_skullstripping_qc,
    create_registration_qc
)
from ..utils import (
    log_workflow_start, 
    log_workflow_end, 
    resolve_template, 
    run_command, 
    calculate_func_tmean, 
    check_image_resolution,
    get_filename_stem
)
from ..operations import apply_skullstripping

# %%
class FunctionalProcessor(BasePreprocessingWorkflow):
    """Simplified functional processor with serial step execution."""
    
    def __init__(
        self,
        func_file: str,
        target_file: str,
        output_dir: str,
        working_dir: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
        target_type: Literal['template', 'anat'] = 'template',
        target2template: Optional[bool] = False,
        target2template_transform: Optional[str] = None,
        qc_dir: Optional[str] = None,
        template_spec: Optional[str] = None,
    ):
        """
        Initialize the functional processor.

        Args:
            func_file: The path to the functional file.
            target_file: The path to the target file.
            output_dir: The path to the output directory.
            working_dir: The path to the working directory.
            config: The configuration dictionary.
            logger: The logger to use.
            target_type: The type of target to register to.
            target2template: Whether to register to the template after registration to the target.
            target2template_transform: The transformation to apply to the target to register to the template.
            qc_dir: The path to the QC directory.
            template_spec: The specification of the template to register to.
        """

        super().__init__(output_dir, working_dir, config, logger)
        
        # set up func and target files
        self.func_file = Path(func_file)
        self.target_type = target_type
        self.target2template = target2template
        self.target2template_transform = target2template_transform

        # set up template file
        self.template_file = None
        self.template_name = None
        if (self.target_type == 'template' or self.target2template) and template_spec and template_spec.lower() != "native":
            try:
                self.template_file = resolve_template(template_spec)
                self.template_name = template_spec.split(':')[0]
                self.logger.info(f"Template: resolved {template_spec} -> {os.path.basename(self.template_file)}")
            except Exception as e:
                self.logger.error(f"Template: failed to resolve {template_spec} - {e}")
                raise
        elif template_spec and template_spec.lower() == "native":
            self.logger.info(f"Template: output space is native - skipping resolution")

        # set up target file
        self.target_file = Path(target_file) if target_file else None
        if self.target_type == 'template':
            self.target_file = self.template_file

        # if target2template is True, then target2template_transform is required (except for native space)
        if self.target2template:
            if target2template_transform is None and (not template_spec or template_spec.lower() != "native"):
                raise ValueError("target2template_transform is required when target2template is True")

        # Set up QC directory
        if qc_dir:
            self.qc_dir = Path(qc_dir)
        else:
            # Fallback to default if not provided - don't create until needed
            self.qc_dir = self.pipeline.output_dir / "figures"
        
        # Extract BIDS identifiers from input filename for consistent naming - DEPRECATED
        self.func_stem = str(self.func_file.name).split(".nii")[0].replace('_bold', '')
        
        # Use original filename stem as prefix to preserve exact input structure
        self.bids_prefix = get_filename_stem(self.func_file)
        self.bids_prefix_wobold = self.bids_prefix.replace("_bold", "")
    
    def run(self) -> Dict[str, Any]:
        """Run functional processing pipeline with serial steps - just like the original!"""

        workflow_name = f"func2{self.target_type}"
        start_time = time.time()
        
        # Log workflow start
        log_workflow_start(self.workflow_logger, workflow_name, self.config.to_dict())
        self.logger.info("Workflow: starting functional processing pipeline")
        
        # Only create QC directory if quality control is enabled
        if self.config.get("quality_control.enabled", True):
            self.qc_dir.mkdir(parents=True, exist_ok=True)

        # Track generated output files for caching
        self.generated_files = []

        # initialize the functional data
        funcf_all = str(self.func_file)
        funcf_tmean = None

        try:
            # FUNC PRECHECK
            # ------------------------------------------------------------
            step_name = self.pipeline.add_step(
                name="func_precheck",
                func=precheck,
                inputs={
                    "imagef": funcf_all,
                }
            )
            result = self.pipeline.run_step(
                step_name,
                modal="func",
                target_file=self.target_file,
                generate_tmean=True
            )
        
            if result.output_files["imagef_reoriented"]:
                funcf_all = result.output_files["imagef_reoriented"]
            if result.output_files["imagef_tmean"]:
                funcf_tmean = result.output_files["imagef_tmean"]

            self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_tmean) if funcf_tmean else 'no tmean generated'}")

            # SLICE TIMING CORRECTION
            # ------------------------------------------------------------
            if self.config.get("func.slice_timing_correction.enabled"):
                step_name = self.pipeline.add_step(
                    name="func_slice_timing_correction",
                    func=slice_timing_correction,
                    inputs={
                        "imagef": funcf_all,
                        "output_name": "func_slice_timed.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    generate_tmean=True
                )
                
                if result.output_files["imagef_slice_time_corrected"]:
                    funcf_all = result.output_files["imagef_slice_time_corrected"]
                else:
                    self.logger.warning("Step: slice timing correction skipped - unknown pattern")

                if result.output_files["imagef_slice_time_corrected_tmean"]:
                    funcf_tmean = result.output_files["imagef_slice_time_corrected_tmean"]
                else:
                    self.logger.warning("Step: slice timing correction tmean not generated")
                
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_all)}")
            else:
                self.logger.info("Step: slice timing correction skipped (disabled in configuration)")

            # MOTION CORRECTION
            # ------------------------------------------------------------
            if self.config.get("func.motion_correction.enabled", True):
                step_name = self.pipeline.add_step(
                    name="func_motion_correction",
                    func=motion_correction,
                    inputs={
                        "imagef": funcf_all,
                        "output_name": "func_motion_corrected.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    generate_tmean=True
                )
                
                if result.output_files["imagef_motion_corrected"] is not None:
                    funcf_all = result.output_files["imagef_motion_corrected"]
                else:
                    self.logger.warning("Step: motion correction skipped - no output generated")

                if result.output_files["imagef_motion_corrected_tmean"] is not None:
                    funcf_tmean = result.output_files["imagef_motion_corrected_tmean"]
                else:
                    self.logger.warning("Step: motion correction tmean not generated")

                motion_params = result.output_files.get("motion_parameters")

                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_all)}")
                if motion_params:
                    self.logger.info(f"Output: motion parameters generated - {os.path.basename(motion_params)}")
                    
                    # Save motion parameters as confounds timeseries immediately
                    confounds_outputf = self.output_dir / f"{self.bids_prefix_wobold}_desc-confounds_timeseries.tsv"
                    cmd_output = ["cp", motion_params, str(confounds_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(confounds_outputf))
                    self.logger.info(f"Output: motion confounds saved")

                # Generate motion QC
                if (self.config.get("quality_control.enabled", True) and motion_params):
                    try:
                        # Generate BIDS-compliant filename for motion QC
                        filename_stem = get_filename_stem(self.func_file)
                        # Remove original suffix and add motion QC suffix
                        filename_stem = filename_stem.replace("_bold", "")
                        motion_qc_filename = f"{filename_stem}_desc-motion_bold.png"
                        motion_qc_path = self.qc_dir / motion_qc_filename
                        
                        create_motion_correction_qc(
                            motion_params=motion_params,
                            save_f=str(motion_qc_path),
                            input_file=str(self.func_file),
                            logger=self.logger
                        )
                        self.logger.info("QC: motion correction overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: motion correction failed - {e}")
                else:
                    self.logger.info("QC: motion correction skipped - no motion parameters available")
            else:
                self.logger.info("Motion correction skipped (disabled in configuration)")
                motion_params = None

            # DESPIKING
            # ------------------------------------------------------------
            if self.config.get("func.despike.enabled", True):
                step_name = self.pipeline.add_step(
                    name="func_despike",
                    func=despike,
                    inputs={
                        "imagef": funcf_all,
                        "output_name": "func_despike.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    generate_tmean=True
                )
                
                if result.output_files["imagef_despiked"] is not None:
                    funcf_all = result.output_files["imagef_despiked"]
                else:
                    self.logger.warning("Step: despiking skipped - no output generated")

                if result.output_files["imagef_despiked_tmean"] is not None:
                    funcf_tmean = result.output_files["imagef_despiked_tmean"]
                else:
                    self.logger.warning("Step: despiking tmean not generated")

                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_all)}")
            else:
                self.logger.info("Step: despiking skipped (disabled in configuration)")

            # FUNC BIAS CORRECTION
            # ------------------------------------------------------------
            if self.config.get("func.bias_correction.enabled", True):
                step_name = self.pipeline.add_step(
                    name="func_bias_correction",
                    func=bias_correction,
                    inputs={
                        "imagef": funcf_tmean,
                        "output_name": "func_bias_corrected.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    modal="func"
                )

                funcf_tmean = result.output_files["imagef_bias_corrected"]
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_tmean)}")
                
            else:
                self.logger.info("Step: functional bias correction skipped (disabled in configuration)")
                
            # Still save boldref even if bias correction was skipped
            if funcf_tmean:
                boldref_outputf = self.output_dir / f"{self.bids_prefix_wobold}_boldref.nii.gz"
                cmd_output = ["cp", funcf_tmean, str(boldref_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(boldref_outputf))
                self.logger.info(f"Output: BOLD reference saved")

            # FUNC SKULL STRIPPING (optional)
            # ------------------------------------------------------------
            if self.config.get("func.skullstripping.enabled"):
                # Store the original (unskullstripped) image for QC
                funcf_tmean_original = funcf_tmean
                
                step_name = self.pipeline.add_step(
                    name="func_skullstripping",
                    func=apply_skullstripping,
                    inputs={
                        "imagef": funcf_tmean,
                        "modal": "func",
                        "output_name": "func_brain.nii.gz",
                    }
                )

                # set the enable_crop_2round to False for func skull stripping
                config_cur = self.config.to_dict()
                config_cur["func"]["skullstripping"]["fastsurfercnn"]["enable_crop_2round"] = False

                result = self.pipeline.run_step(
                    step_name,
                    config=config_cur
                )
                funcf_tmean = result.output_files["imagef_skullstripped"]
                funcf_brain_mask = result.output_files["brain_mask"]
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_tmean)}")
                self.logger.info(f"Output: functional brain mask generated - {os.path.basename(funcf_brain_mask)}")

                # Save brain mask 
                brainmask_outputf = self.output_dir / f"{self.bids_prefix_wobold}_desc-brain_mask.nii.gz"
                cmd_output = ["cp", funcf_brain_mask, str(brainmask_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(brainmask_outputf))
                self.logger.info(f"Output: functional brain mask saved")

                # Generate functional skull stripping QC snapshots
                if self.config.get("quality_control.enabled", True):
                    try:
                        # Generate BIDS-compliant filename for skull stripping QC
                        filename_stem = get_filename_stem(self.func_file)
                        filename_stem = filename_stem.replace("_bold", "")
                        skull_qc_filename = f"{filename_stem}_desc-skullStripping_bold.png"
                        skull_qc_path = self.qc_dir / skull_qc_filename
                        
                        create_skullstripping_qc(
                            underlay_file=funcf_tmean_original,
                            mask_file=funcf_brain_mask,
                            save_f=str(skull_qc_path),
                            modality="func",
                            logger=self.logger
                        )
                        self.logger.info("QC: functional skull stripping overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: functional skull stripping failed - {e}")

            # FUNC REGISTRATION TO TARGET
            # ------------------------------------------------------------
            if self.config.get("registration.enabled", True):
                # if target_type is template, then the moving image is the target file and the fixed image is the functional tmean
                # otherwise, the moving image is the functional tmean and the fixed image is the target file

                # resample the target to the functional resolution if requested (before registration)
                fixedf = str(self.target_file)
                if self.config.get("registration.keep_original_func_resolution", True):
                    reff = self.working_dir / "target_res-func_for_registration.nii.gz"
                    func_res = np.round(check_image_resolution(funcf_all, logger=self.logger), 1)
                    cmd_resample = ['3dresample', 
                                    '-input', str(self.target_file), '-prefix', str(reff), 
                                    '-rmode', 'Cu',
                                    '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])]
                    run_command(cmd_resample)
                    self.logger.info(f"Output: target resampled to func resolution for registration")
                    fixedf = str(reff)

                step_name = self.pipeline.add_step(
                    name=f"func2{self.target_type}_registration",
                    func=ants_register,
                    inputs={
                        "movingf": funcf_tmean,
                        "fixedf": fixedf,
                        "output_prefix": f"func2{self.target_type}_tmean"
                    }
                )
                
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    xfm_type=self.config.get(f"registration.func2{self.target_type}_xfm_type", "syn")
                )

                # Get registration outputs and save them
                funcf_tmean = result.output_files["imagef_registered"]
                forward_transform = result.output_files["forward_transform"]
                inverse_transform = result.output_files["inverse_transform"]
                
                # Save registered boldref and transforms immediately
                if self.target_type == "anat":
                    target_name = "T1w"
                elif self.target_type == "template":
                    target_name = self.template_name or "native"  # fallback for safety
                
                # Save space-{target} boldref
                space_boldref_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{target_name}_boldref.nii.gz"
                cmd_output = ["cp", funcf_tmean, str(space_boldref_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(space_boldref_outputf))
                self.logger.info(f"Output: registered BOLD reference saved")

                # also save a json file that records the reference file
                ref_info_outputf = f"{str(space_boldref_outputf).split('.nii.gz')[0]}.json"
                ref_info = {
                    "target_file": str(self.target_file),
                }
                try:
                    with open(ref_info_outputf, 'w') as f:
                        json.dump(ref_info, f, indent=2)
                except (IOError, PermissionError) as e:
                    self.logger.error(f"Output: failed to write reference info JSON - {e}")
                
                # Save forward transform
                forward_xfm_outputf = self.output_dir / f"{self.bids_prefix_wobold}_from-scanner_to-{target_name}_mode-image_xfm.h5"
                cmd_output = ["cp", forward_transform, str(forward_xfm_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(forward_xfm_outputf))
                self.logger.info(f"Output: forward transform saved")
                
                # Save inverse transform
                inverse_xfm_outputf = self.output_dir / f"{self.bids_prefix_wobold}_from-{target_name}_to-scanner_mode-image_xfm.h5"
                cmd_output = ["cp", inverse_transform, str(inverse_xfm_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(inverse_xfm_outputf))
                self.logger.info(f"Output: inverse transform saved")

                self.logger.info(f"Step: {step_name} completed - {os.path.basename(result.output_files['imagef_registered'])}")

                # Generate QC
                if self.config.get("quality_control.enabled", True):
                    try:
                        # Generate BIDS-compliant filename for registration QC
                        filename_stem = get_filename_stem(self.func_file)
                        filename_stem = filename_stem.replace("_bold", "")
                        reg_qc_filename = f"{filename_stem}_desc-func2{self.target_type}_bold.png"
                        reg_qc_path = self.qc_dir / reg_qc_filename
                        
                        create_registration_qc(
                            image_file=funcf_tmean,
                            template_file=fixedf,
                            save_f=str(reg_qc_path),
                            modality=f"func2{self.target_type}",
                            logger=self.logger
                        )
                        self.logger.info("QC: functional registration overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: functional registration failed - {e}")
            else:
                if not self.target_file:
                    self.logger.info("Step: registration skipped - no target file provided")
                else:
                    self.logger.info("Step: registration skipped (disabled in configuration)")

            # APPLY FUNC2TARGET REGISTRATION TO TARGET TO FUNC_ALL
            # ------------------------------------------------------------
            if self.config.get("registration.enabled", True):
                if self.target2template:
                    fixedf = self.template_file
                    transform_files = [forward_xfm_outputf, self.target2template_transform]

                    qc_modality = f'func2template'
                    target_name = self.template_name or "native"  # fallback for safety
                else:
                    fixedf = self.target_file
                    transform_files = [forward_xfm_outputf]
                    qc_modality = f"func2{self.target_type}"

                # use the same resampled target that was used for registration
                if self.config.get("registration.keep_original_func_resolution", True):
                    # Use the same resampled target file created for registration
                    if not self.target2template:
                        # For func2anat, use the resampled file from registration
                        self.logger.info(f"Output: using resampled target from registration for apply transforms")
                    else:
                        # For func2template, still need to resample the template
                        reff = self.working_dir / "target_res-func_for_apply_transforms.nii.gz"
                        func_res = np.round(check_image_resolution(funcf_all, logger=self.logger), 1)
                        cmd_resample = ['3dresample', 
                                        '-input', str(fixedf), '-prefix', str(reff), 
                                        '-rmode', 'Cu',
                                        '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])]
                        run_command(cmd_resample)
                        self.logger.info(f"Output: template resampled to func resolution")
                else:
                    reff = fixedf

                # run ants_apply_transforms
                step_name = self.pipeline.add_step(
                    name=f"func2target_registration_apply_to_all",
                    func=ants_apply_transforms,
                )

                # run for funcf_all
                result = self.pipeline.run_step(
                    step_name,
                    movingf=funcf_all,
                    moving_type=3,
                    interpolation=self.config.get("registration", {}).get("interpolation"),
                    outputf_name=f"func2{target_name}.nii.gz",
                    fixedf=fixedf,
                    transformf=transform_files,
                    reff=reff,
                    generate_tmean=True,
                )
                
                # Get transformed functional data
                funcf_all = result.output_files["imagef_registered"]
                self.logger.info(f"Output: functional data transformed to {self.target_type} space")
                funcf_tmean = result.output_files["imagef_registered_tmean"]
                self.logger.info(f"Output: functional tmean calculated")
                
                # Save functional data
                funcf_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{target_name}_desc-preproc_bold.nii.gz"
                cmd_output = ["cp", funcf_all, str(funcf_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(funcf_outputf))
                self.logger.info(f"Output: registered functional data saved")

                # run ants_apply_transforms for the brain mask if provided
                if self.config.get("func.skullstripping.enabled", True):
                    
                    result = self.pipeline.run_step(
                        step_name,
                        movingf=funcf_brain_mask,
                        moving_type=0,
                        interpolation='NearestNeighbor',
                        outputf_name=f"func2{target_name}_brainmask.nii.gz",
                        fixedf=fixedf,
                        transformf=transform_files,
                        reff=reff,
                        generate_tmean=False,
                    )

                    funcf_brain_mask_registered = result.output_files["imagef_registered"]
                    brainmask_registered_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{target_name}_desc-brain_mask.nii.gz"
                    cmd_output = ["cp", funcf_brain_mask_registered, str(brainmask_registered_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(brainmask_registered_outputf))
                    self.logger.info(f"Output: registered brain mask saved")

                # generate snapshot of the registered functional data
                if self.config.get("quality_control.enabled", True):
                    try:
                        # Generate BIDS-compliant filename for registered data QC
                        filename_stem = get_filename_stem(self.func_file)
                        filename_stem = filename_stem.replace("_bold", "")
                        reg_final_qc_filename = f"{filename_stem}_desc-{qc_modality}_bold.png"
                        reg_final_qc_path = self.qc_dir / reg_final_qc_filename
                        
                        create_registration_qc(
                            image_file=str(funcf_tmean),
                            template_file=str(reff),
                            save_f=str(reg_final_qc_path),
                            modality=qc_modality,
                            logger=self.logger
                        )
                        self.logger.info("QC: registered functional data overlay created")
                    except Exception as e:
                        self.logger.warning(f"QC: registered functional data failed - {e}")
            else:
                self.logger.info("Step: transform application skipped (registration disabled)")

            # ------------------------------------------------------------
            # Calculate workflow duration
            duration = time.time() - start_time
            
            # Log successful completion
            log_workflow_end(self.workflow_logger, workflow_name, True, duration)

            self.logger.info("Workflow: functional processing pipeline completed successfully")
            
            # Return the pipeline results
            return {
                "status": "success",
                "output_dir": str(self.pipeline.output_dir),
                "generated_files": self.generated_files,
                "reports": getattr(self, 'reports', [])
            }
        
        except Exception as e:
            # Calculate workflow duration
            duration = time.time() - start_time
            
            # Log failure
            log_workflow_end(self.workflow_logger, workflow_name, False, duration)
            
            self.logger.error(f"Workflow: functional processing failed - {e}")
            raise
