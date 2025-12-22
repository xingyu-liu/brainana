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
    reorient,
    correct_orientation_mismatch,
    slice_timing_correction, 
    motion_correction, 
    despike,
    bias_correction,
    conform_to_template,
)
from ..operations.registration import (
    ants_register,
    ants_apply_transforms,
    flirt_register,
    flirt_apply_transforms
)
from ..quality_control import (
    create_motion_correction_qc,
    create_skullstripping_qc,
    create_registration_qc
)
from ..quality_control.snapshots import create_conform_qc
from ..utils import (
    log_workflow_start, 
    log_workflow_end, 
    resolve_template, 
    run_command, 
    get_image_resolution,
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
        # Always resolve template_spec if provided (not "native") - needed for target2template transforms
        self.template_file = None
        self.template_name = None
        if template_spec and template_spec.lower() != "native":
            try:
                self.template_file = resolve_template(template_spec)
                self.template_name = template_spec.split(':')[0]
                if not self.template_name:
                    raise ValueError(f"Failed to extract template name from template_spec: {template_spec}")
                self.logger.info(f"Template: resolved {template_spec} -> {os.path.basename(self.template_file)}")
            except Exception as e:
                self.logger.error(f"Template: failed to resolve {template_spec} - {e}")
                raise
        elif template_spec and template_spec.lower() == "native":
            self.logger.info(f"Template: output space is native - skipping resolution")

        # set up target file
        self.target_file = Path(target_file) if target_file else None
        if self.target_type == 'template':
            if self.template_file is None:
                raise ValueError(f"target_type is 'template' but template_file is None. template_spec: {template_spec}")
            self.target_file = self.template_file

        # if target2template is True, then target2template_transform is required (except for native space)
        if self.target2template:
            if template_spec and template_spec.lower() == "native":
                # Native space: disable target2template
                self.logger.warning("target2template is True but output_space is native - disabling target2template")
                self.target2template = False
            elif target2template_transform is None:
                raise ValueError("target2template_transform is required when target2template is True")
            elif self.template_file is None:
                raise ValueError("target2template is True but template_file is None. template_spec may be invalid.")

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
        # Maintain two versions of temporal mean: with skull (full-brain) and without skull (brain-only)
        funcf_tmean_w_skull = None  # Full-brain version (always maintained)
        funcf_tmean_wo_skull = None  # Skull-stripped version (None until skull stripping)

        try:
            # FUNC ORIENTATION CORRECTION
            # ------------------------------------------------------------
            if self.config.get("func.orientation_correction.enabled", True):
                step_name = self.pipeline.add_step(
                    name="func_orientation_correction",
                    func=correct_orientation_mismatch,
                    inputs={
                        "imagef": funcf_all,
                        "output_name": "func_orientation_corrected.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    logger=self.logger,
                    config=self.config.to_dict(),
                    generate_tmean=False
                )
                if result.output_files["imagef_orientation_corrected"] is not None:
                    funcf_all = result.output_files["imagef_orientation_corrected"]
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_all)}")
                else:
                    self.logger.info(f"Step: {step_name} skipped - no orientation correction performed")
                
                # Update funcf_tmean_w_skull if available
                if result.output_files.get("imagef_tmean") is not None:
                    funcf_tmean_w_skull = result.output_files["imagef_tmean"]
            else:
                self.logger.info("Step: orientation correction skipped (disabled in configuration)")

            # FUNC REORIENT
            # ------------------------------------------------------------
            if self.config.get("func.reorient.enabled", True):
                step_name = self.pipeline.add_step(
                    name="func_reorient",
                    func=reorient,
                    inputs={
                        "imagef": funcf_all,
                        "output_name": "func_reoriented.nii.gz"
                    }
                )
                # Get target_file, or default to RAS orientation if no template
                # For template target_type, use template_file if available
                if self.target_type == 'template' and self.template_file is not None:
                    target_file = str(self.template_file)
                else:
                    target_file = str(self.target_file) if self.target_file is not None else None
                target_orientation = "RAS" if target_file is None else None
                
                result = self.pipeline.run_step(
                    step_name,
                    target_file=target_file,
                    target_orientation=target_orientation,
                    generate_tmean=True
                )
            
                if result.output_files["imagef_reoriented"]:
                    funcf_all = result.output_files["imagef_reoriented"]
                if result.output_files["imagef_tmean"]:
                    funcf_tmean_w_skull = result.output_files["imagef_tmean"]

                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_tmean_w_skull) if funcf_tmean_w_skull else 'no tmean generated'}")
            else:
                self.logger.info("Step: reorient skipped (disabled in configuration)")

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
                    funcf_tmean_w_skull = result.output_files["imagef_slice_time_corrected_tmean"]
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
                    funcf_tmean_w_skull = result.output_files["imagef_motion_corrected_tmean"]
                else:
                    self.logger.warning("Step: motion correction tmean not generated")

                motion_params = result.output_files.get("motion_parameters")

                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_all)}")
                if motion_params:
                    self.logger.info(f"Output: motion parameters generated - {os.path.basename(motion_params)}")
                    
                    # Save motion parameters as confounds timeseries immediately
                    confounds_outputf = self.output_dir / f"{self.bids_prefix_wobold}_desc-confounds_timeseries.tsv"
                    cmd_output = ["cp", str(motion_params), str(confounds_outputf)]
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
                    funcf_tmean_w_skull = result.output_files["imagef_despiked_tmean"]
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
                        "imagef": funcf_tmean_w_skull,
                        "output_name": "func_bias_corrected.nii.gz"
                    }
                )
                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict(),
                    modal="func"
                )

                funcf_tmean_w_skull = result.output_files["imagef_bias_corrected"]
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_tmean_w_skull)}")
                
            else:
                self.logger.info("Step: functional bias correction skipped (disabled in configuration)")
                
            # FUNC CONFORM TO TARGET
            # ------------------------------------------------------------
            if self.config.get("func.conform.enabled", True):
                # Validate target_file exists
                if self.target_file is None:
                    raise ValueError(f"Conform enabled but target_file is None (target_type: {self.target_type})")
                if not self.target_file.exists():
                    raise FileNotFoundError(f"Target file does not exist: {self.target_file}")
                
                # 1. do the conform to target for tmean image
                step_name = self.pipeline.add_step(
                    name="func_conform",
                    func=conform_to_template,
                    inputs={
                        "imagef": funcf_tmean_w_skull,
                        "template_file": str(self.target_file),
                        "output_name": "func_tmean_conformed.nii.gz"
                    }
                )
                
                result = self.pipeline.run_step(
                    step_name,
                    logger=self.logger,
                    modal='func'
                )
                
                if result.output_files["imagef_conformed"] is not None:
                    funcf_tmean_conformed = result.output_files["imagef_conformed"]
                    conform_template_f = result.output_files["template_f"]
                    forward_xfm = result.output_files.get("forward_xfm")
                    inverse_xfm = result.output_files.get("inverse_xfm")
                    
                    self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_tmean_conformed)}")
                    
                    # Save xfm files if available
                    # Note: This is initial conform step, not final registration, so name as "native"
                    if forward_xfm:
                        # Generate BIDS-compliant filename for forward transform
                        forward_xfm_outputf = self.output_dir / f"{self.bids_prefix_wobold}_from-scanner_to-bold_mode-image_xfm.mat"
                        cmd_output = ["cp", str(forward_xfm), str(forward_xfm_outputf)]
                        run_command(cmd_output)
                        self.generated_files.append(str(forward_xfm_outputf))
                        self.logger.info(f"Output: forward transform saved - {os.path.basename(forward_xfm_outputf)}")
                    
                    if inverse_xfm:
                        # Generate BIDS-compliant filename for inverse transform
                        inverse_xfm_outputf = self.output_dir / f"{self.bids_prefix_wobold}_from-native_to-bold_mode-image_xfm.mat"
                        cmd_output = ["cp", str(inverse_xfm), str(inverse_xfm_outputf)]
                        run_command(cmd_output)
                        self.generated_files.append(str(inverse_xfm_outputf))
                        self.logger.info(f"Output: inverse transform saved - {os.path.basename(inverse_xfm_outputf)}")
                    
                    # 2. apply the xfm to func all image with reference file being the conformed tmean image
                    if forward_xfm:
                        step_name_apply = self.pipeline.add_step(
                            name="func_apply_conform",
                            func=flirt_apply_transforms,
                            inputs={
                                "movingf": funcf_all,
                                "outputf_name": "func_conformed.nii.gz",
                                "reff": funcf_tmean_conformed,
                                "transformf": forward_xfm,
                            }
                        )
                        
                        result_apply = self.pipeline.run_step(
                            step_name_apply,
                            logger=self.logger,
                            interpolation='trilinear',
                            generate_tmean=True
                        )
                        
                        if result_apply.output_files["imagef_registered"] is not None:
                            funcf_all = result_apply.output_files["imagef_registered"]
                            self.logger.info(f"Step: {step_name_apply} completed - {os.path.basename(funcf_all)}")
                            
                            # Update funcf_tmean_w_skull if tmean was generated from conformed data, otherwise use conformed tmean
                            if result_apply.output_files.get("imagef_registered_tmean"):
                                funcf_tmean_w_skull = result_apply.output_files["imagef_registered_tmean"]
                                self.logger.info(f"Output: conformed tmean updated from 4D data - {os.path.basename(funcf_tmean_w_skull)}")
                            else:
                                # Fall back to conformed tmean if no new tmean was generated
                                funcf_tmean_w_skull = funcf_tmean_conformed
                                self.logger.info(f"Output: using conformed tmean (no new tmean generated from 4D data)")
                        else:
                            self.logger.warning(f"Step: {step_name_apply} returned None - transform application may have failed")
                            # Use conformed tmean as fallback
                            funcf_tmean_w_skull = funcf_tmean_conformed
                    else:
                        self.logger.warning("Step: conform forward transform not available - skipping transform application to full functional data")
                        # Use conformed tmean since transform application was skipped
                        funcf_tmean_w_skull = funcf_tmean_conformed
                    
                    # Generate QC
                    if self.config.get("quality_control.enabled", True):
                        try:
                            # Generate BIDS-compliant filename for conform QC
                            filename_stem = get_filename_stem(self.func_file)
                            filename_stem = filename_stem.replace("_bold", "")
                            conform_qc_filename = f"{filename_stem}_desc-conform_bold.png"
                            conform_qc_path = self.qc_dir / conform_qc_filename
                            
                            create_conform_qc(
                                conformed_file=funcf_tmean_conformed,
                                template_file=conform_template_f,
                                save_f=str(conform_qc_path),
                                modality="func",
                                logger=self.logger
                            )
                            self.logger.info("QC: functional conform overlay created")
                        except Exception as e:
                            self.logger.warning(f"QC: functional conform failed - {e}")
                else:
                    self.logger.warning(f"Step: {step_name} returned None - conform may have been skipped")
            else:
                self.logger.info("Step: conform skipped (disabled in configuration)")

            # Save boldref (use full-brain version)
            if funcf_tmean_w_skull:
                boldref_outputf = self.output_dir / f"{self.bids_prefix_wobold}_boldref.nii.gz"
                cmd_output = ["cp", str(funcf_tmean_w_skull), str(boldref_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(boldref_outputf))
                self.logger.info(f"Output: BOLD reference saved")

            # Initialize brain mask variable
            funcf_brain_mask = None

            # FUNC SKULL STRIPPING
            # ------------------------------------------------------------
            if self.config.get("func.skullstripping.enabled"):
                # Store the original (unskullstripped) image for QC
                funcf_tmean_original = funcf_tmean_w_skull
                
                step_name = self.pipeline.add_step(
                    name="func_skullstripping",
                    func=apply_skullstripping,
                    inputs={
                        "imagef": funcf_tmean_w_skull,
                        "modal": "func",
                        "output_name": "func_brain.nii.gz",
                    }
                )

                result = self.pipeline.run_step(
                    step_name,
                    config=self.config.to_dict()
                )
                # After skull stripping: wo_skull gets the skull-stripped version, w_skull remains unchanged
                funcf_tmean_wo_skull = result.output_files["imagef_skullstripped"]
                funcf_brain_mask = result.output_files["brain_mask"]
                self.logger.info(f"Step: {step_name} completed - {os.path.basename(funcf_tmean_wo_skull)}")
                self.logger.info(f"Output: functional brain mask generated - {os.path.basename(funcf_brain_mask)}")

                # Save brain mask 
                brainmask_outputf = self.output_dir / f"{self.bids_prefix_wobold}_desc-brain_mask.nii.gz"
                cmd_output = ["cp", str(funcf_brain_mask), str(brainmask_outputf)]
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
                # Validate target_file exists
                if self.target_file is None:
                    raise ValueError(f"Registration enabled but target_file is None (target_type: {self.target_type})")
                if not self.target_file.exists():
                    raise FileNotFoundError(f"Target file does not exist: {self.target_file}")
                
                # if target_type is template, then the moving image is the target file and the fixed image is the functional tmean
                # otherwise, the moving image is the functional tmean and the fixed image is the target file

                # resample the target to the functional resolution if requested (before registration)
                fixedf = str(self.target_file)

                # resample the target to the functional res, for initial rigid registration
                reff = self.working_dir / "target_res-func_for_registration.nii.gz"
                func_res = np.round(get_image_resolution(funcf_all, logger=self.logger), 1)
                cmd_resample = ['3dresample', 
                                '-input', str(self.target_file), '-prefix', str(reff), 
                                '-rmode', 'Cu',
                                '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])]
                run_command(cmd_resample)
                self.logger.info(f"Output: target resampled to func resolution for registration")

                # use the resampled target for registration if requested
                if self.config.get("registration.keep_original_func_resolution", True):
                    self.logger.info(f"Output: target resampled to func resolution for registration")
                    fixedf = str(reff)

                # Save original full-brain version before registration (needed for boldref if skull stripping was done)
                funcf_tmean_w_skull_original = funcf_tmean_w_skull
                
                # Use skull-stripped version for registration if available (better alignment), otherwise use full-brain
                funcf_tmean_for_registration = funcf_tmean_wo_skull if funcf_tmean_wo_skull is not None else funcf_tmean_w_skull
                
                step_name = self.pipeline.add_step(
                    name=f"func2{self.target_type}_registration",
                    func=ants_register,
                    inputs={
                        "movingf": funcf_tmean_for_registration,
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
                forward_transform = result.output_files["forward_transform"]
                inverse_transform = result.output_files["inverse_transform"]
                
                # Update the version that was registered
                if funcf_tmean_wo_skull is not None:
                    funcf_tmean_wo_skull = result.output_files["imagef_registered"]
                else:
                    funcf_tmean_w_skull = result.output_files["imagef_registered"]
                
                # Determine target_name for saving transforms
                if self.target_type == "anat":
                    target_name = "T1w"
                elif self.target_type == "template":
                    if self.template_name is None:
                        raise ValueError("target_type is 'template' but template_name is None")
                    target_name = self.template_name
                
                # Save forward transform
                forward_xfm_outputf = self.output_dir / f"{self.bids_prefix_wobold}_from-scanner_to-{target_name}_mode-image_xfm.h5"
                cmd_output = ["cp", str(forward_transform), str(forward_xfm_outputf)]
                run_command(cmd_output)
                self.generated_files.append(str(forward_xfm_outputf))
                self.logger.info(f"Output: forward transform saved")
                
                # Save inverse transform
                inverse_xfm_outputf = self.output_dir / f"{self.bids_prefix_wobold}_from-{target_name}_to-scanner_mode-image_xfm.h5"
                cmd_output = ["cp", str(inverse_transform), str(inverse_xfm_outputf)]
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
                        
                        # Use the version that was registered for QC
                        funcf_tmean_for_qc = funcf_tmean_wo_skull if funcf_tmean_wo_skull is not None else funcf_tmean_w_skull
                        create_registration_qc(
                            image_file=funcf_tmean_for_qc,
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

            # APPLY FUNC2TARGET REGISTRATION TRANSFORMS
            # ------------------------------------------------------------
            if self.config.get("registration.enabled", True):
                # forward_xfm_outputf should be defined from the registration step above
                # If registration was skipped or failed, this block wouldn't execute
                
                # Save original full-brain version before transforms (needed for boldref if skull stripping was done)
                funcf_tmean_w_skull_original = funcf_tmean_w_skull
                
                # Determine if we need sequential transforms (func2anat2template)
                if self.target2template and self.target_type == "anat":
                    # Sequential transforms: first to anat, then to template
                    # Step 1: Apply func2anat transform
                    anat_target_name = "T1w"
                    anat_fixedf = self.target_file
                    
                    # Prepare resampled anat for reference if needed
                    if self.config.get("registration.keep_original_func_resolution", True):
                        # Use the same resampled file from registration
                        anat_reff = self.working_dir / "target_res-func_for_registration.nii.gz"
                        self.logger.info(f"Output: using resampled anat from registration for apply transforms")
                    else:
                        anat_reff = anat_fixedf
                    
                    # Apply func2anat transform to boldref (tmean)
                    step_name_boldref_anat = self.pipeline.add_step(
                        name="func2anat_boldref_transform",
                        func=ants_apply_transforms,
                    )
                    
                    # Use original full-brain version for boldref if registration used wo_skull
                    boldref_moving = funcf_tmean_w_skull_original if funcf_tmean_wo_skull is not None else funcf_tmean_w_skull
                    
                    result_boldref_anat = self.pipeline.run_step(
                        step_name_boldref_anat,
                        movingf=boldref_moving,
                        moving_type=3,
                        interpolation=self.config.get("registration", {}).get("interpolation", "trilinear"),
                        outputf_name="func2anat_boldref.nii.gz",
                        fixedf=anat_fixedf,
                        transformf=[forward_xfm_outputf],
                        reff=anat_reff,
                        generate_tmean=False,
                    )
                    
                    funcf_tmean_w_skull_anat = result_boldref_anat.output_files["imagef_registered"]
                    
                    # Save anat space boldref
                    space_boldref_anat_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{anat_target_name}_boldref.nii.gz"
                    cmd_output = ["cp", str(funcf_tmean_w_skull_anat), str(space_boldref_anat_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(space_boldref_anat_outputf))
                    self.logger.info(f"Output: BOLD reference saved in anat space")
                    
                    # Save JSON file for anat boldref
                    ref_info_anat_outputf = f"{str(space_boldref_anat_outputf).split('.nii.gz')[0]}.json"
                    ref_info_anat = {
                        "target_file": str(self.target_file),
                    }
                    try:
                        with open(ref_info_anat_outputf, 'w') as f:
                            json.dump(ref_info_anat, f, indent=2)
                    except (IOError, PermissionError) as e:
                        self.logger.error(f"Output: failed to write reference info JSON - {e}")
                    
                    # Apply func2anat transform to funcf_all
                    step_name_func_anat = self.pipeline.add_step(
                        name="func2anat_apply_to_all",
                        func=ants_apply_transforms,
                    )
                    
                    result_func_anat = self.pipeline.run_step(
                        step_name_func_anat,
                        movingf=funcf_all,
                        moving_type=3,
                        interpolation=self.config.get("registration", {}).get("interpolation"),
                        outputf_name="func2anat.nii.gz",
                        fixedf=anat_fixedf,
                        transformf=[forward_xfm_outputf],
                        reff=anat_reff,
                        generate_tmean=True,
                    )
                    
                    funcf_all_anat = result_func_anat.output_files["imagef_registered"]
                    if result_func_anat.output_files.get("imagef_registered_tmean") is not None:
                        funcf_tmean_w_skull_anat = result_func_anat.output_files["imagef_registered_tmean"]
                    
                    # Save functional data in anat space
                    funcf_anat_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{anat_target_name}_desc-preproc_bold.nii.gz"
                    cmd_output = ["cp", str(funcf_all_anat), str(funcf_anat_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(funcf_anat_outputf))
                    self.logger.info(f"Output: functional data saved in anat space")
                    
                    # Apply func2anat transform to mask if provided
                    if funcf_brain_mask is not None:
                        result_mask_anat = self.pipeline.run_step(
                            step_name_func_anat,
                            movingf=funcf_brain_mask,
                            moving_type=0,
                            interpolation='NearestNeighbor',
                            outputf_name="func2anat_brainmask.nii.gz",
                            fixedf=anat_fixedf,
                            transformf=[forward_xfm_outputf],
                            reff=anat_reff,
                            generate_tmean=False,
                        )
                        
                        funcf_brain_mask_anat = result_mask_anat.output_files["imagef_registered"]
                        brainmask_anat_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{anat_target_name}_desc-brain_mask.nii.gz"
                        cmd_output = ["cp", str(funcf_brain_mask_anat), str(brainmask_anat_outputf)]
                        run_command(cmd_output)
                        self.generated_files.append(str(brainmask_anat_outputf))
                        self.logger.info(f"Output: brain mask saved in anat space")
                    
                    # Generate QC for anat space
                    if self.config.get("quality_control.enabled", True):
                        try:
                            filename_stem = get_filename_stem(self.func_file)
                            filename_stem = filename_stem.replace("_bold", "")
                            reg_anat_qc_filename = f"{filename_stem}_desc-func2anat_bold.png"
                            reg_anat_qc_path = self.qc_dir / reg_anat_qc_filename
                            
                            create_registration_qc(
                                image_file=str(funcf_tmean_w_skull_anat),
                                template_file=str(anat_reff),
                                save_f=str(reg_anat_qc_path),
                                modality="func2anat",
                                logger=self.logger
                            )
                            self.logger.info("QC: functional registration to anat overlay created")
                        except Exception as e:
                            self.logger.warning(f"QC: functional registration to anat failed - {e}")
                    
                    # Step 2: Apply anat2template transform
                    if self.template_file is None:
                        raise ValueError("target2template is True but template_file is None")
                    if self.template_name is None:
                        raise ValueError("target2template is True but template_name is None")
                    
                    template_fixedf = self.template_file
                    template_target_name = self.template_name
                    
                    # Resample template to func resolution if needed
                    if self.config.get("registration.keep_original_func_resolution", True):
                        template_reff = self.working_dir / "template_res-func_for_apply_transforms.nii.gz"
                        func_res = np.round(get_image_resolution(funcf_all_anat, logger=self.logger), 1)
                        cmd_resample = ['3dresample', 
                                        '-input', str(template_fixedf), '-prefix', str(template_reff), 
                                        '-rmode', 'Cu',
                                        '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])]
                        run_command(cmd_resample)
                        self.logger.info(f"Output: template resampled to func resolution")
                    else:
                        template_reff = template_fixedf
                    
                    # Apply anat2template transform to boldref
                    step_name_boldref_template = self.pipeline.add_step(
                        name="func2template_boldref_transform",
                        func=ants_apply_transforms,
                    )
                    
                    result_boldref_template = self.pipeline.run_step(
                        step_name_boldref_template,
                        movingf=funcf_tmean_w_skull_anat,
                        moving_type=3,
                        interpolation=self.config.get("registration", {}).get("interpolation", "trilinear"),
                        outputf_name="func2template_boldref.nii.gz",
                        fixedf=template_fixedf,
                        transformf=[self.target2template_transform],
                        reff=template_reff,
                        generate_tmean=False,
                    )
                    
                    funcf_tmean_w_skull_template = result_boldref_template.output_files["imagef_registered"]
                    
                    # Save template space boldref
                    space_boldref_template_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{template_target_name}_boldref.nii.gz"
                    cmd_output = ["cp", str(funcf_tmean_w_skull_template), str(space_boldref_template_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(space_boldref_template_outputf))
                    self.logger.info(f"Output: BOLD reference saved in template space")
                    
                    # Save JSON file for template boldref
                    ref_info_template_outputf = f"{str(space_boldref_template_outputf).split('.nii.gz')[0]}.json"
                    ref_info_template = {
                        "target_file": str(self.template_file),
                    }
                    try:
                        with open(ref_info_template_outputf, 'w') as f:
                            json.dump(ref_info_template, f, indent=2)
                    except (IOError, PermissionError) as e:
                        self.logger.error(f"Output: failed to write reference info JSON - {e}")
                    
                    # Apply anat2template transform to funcf_all
                    step_name_func_template = self.pipeline.add_step(
                        name="func2template_apply_to_all",
                        func=ants_apply_transforms,
                    )
                    
                    result_func_template = self.pipeline.run_step(
                        step_name_func_template,
                        movingf=funcf_all_anat,
                        moving_type=3,
                        interpolation=self.config.get("registration", {}).get("interpolation"),
                        outputf_name="func2template.nii.gz",
                        fixedf=template_fixedf,
                        transformf=[self.target2template_transform],
                        reff=template_reff,
                        generate_tmean=True,
                    )
                    
                    funcf_all_template = result_func_template.output_files["imagef_registered"]
                    if result_func_template.output_files.get("imagef_registered_tmean") is not None:
                        funcf_tmean_w_skull_template = result_func_template.output_files["imagef_registered_tmean"]
                    
                    # Save functional data in template space
                    funcf_template_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{template_target_name}_desc-preproc_bold.nii.gz"
                    cmd_output = ["cp", str(funcf_all_template), str(funcf_template_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(funcf_template_outputf))
                    self.logger.info(f"Output: functional data saved in template space")
                    
                    # Update funcf_all and funcf_tmean_w_skull for consistency
                    funcf_all = funcf_all_template
                    funcf_tmean_w_skull = funcf_tmean_w_skull_template
                    
                    # Apply anat2template transform to mask if provided
                    if funcf_brain_mask is not None:
                        result_mask_template = self.pipeline.run_step(
                            step_name_func_template,
                            movingf=funcf_brain_mask_anat,
                            moving_type=0,
                            interpolation='NearestNeighbor',
                            outputf_name="func2template_brainmask.nii.gz",
                            fixedf=template_fixedf,
                            transformf=[self.target2template_transform],
                            reff=template_reff,
                            generate_tmean=False,
                        )
                        
                        funcf_brain_mask_template = result_mask_template.output_files["imagef_registered"]
                        brainmask_template_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{template_target_name}_desc-brain_mask.nii.gz"
                        cmd_output = ["cp", str(funcf_brain_mask_template), str(brainmask_template_outputf)]
                        run_command(cmd_output)
                        self.generated_files.append(str(brainmask_template_outputf))
                        self.logger.info(f"Output: brain mask saved in template space")
                    
                    # Generate QC for template space
                    if self.config.get("quality_control.enabled", True):
                        try:
                            filename_stem = get_filename_stem(self.func_file)
                            filename_stem = filename_stem.replace("_bold", "")
                            reg_template_qc_filename = f"{filename_stem}_desc-func2template_bold.png"
                            reg_template_qc_path = self.qc_dir / reg_template_qc_filename
                            
                            create_registration_qc(
                                image_file=str(funcf_tmean_w_skull_template),
                                template_file=str(template_reff),
                                save_f=str(reg_template_qc_path),
                                modality="func2template",
                                logger=self.logger
                            )
                            self.logger.info("QC: functional registration to template overlay created")
                        except Exception as e:
                            self.logger.warning(f"QC: functional registration to template failed - {e}")
                
                else:
                    # Single transform: func2anat or func2template (not func2anat2template)
                    if self.target2template:
                        if self.template_file is None:
                            raise ValueError("target2template is True but template_file is None")
                        if self.template_name is None:
                            raise ValueError("target2template is True but template_name is None")
                        fixedf = self.template_file
                        transform_files = [forward_xfm_outputf, self.target2template_transform]
                        qc_modality = 'func2template'
                        target_name = self.template_name
                    else:
                        fixedf = self.target_file
                        transform_files = [forward_xfm_outputf]
                        qc_modality = f"func2{self.target_type}"
                        if self.target_type == "anat":
                            target_name = "T1w"
                        elif self.target_type == "template":
                            if self.template_name is None:
                                raise ValueError("target_type is 'template' but template_name is None")
                            target_name = self.template_name
                    
                    # Prepare resampled target for reference if needed
                    if self.config.get("registration.keep_original_func_resolution", True):
                        if not self.target2template:
                            # Use the same resampled file from registration
                            reff = self.working_dir / "target_res-func_for_registration.nii.gz"
                            self.logger.info(f"Output: using resampled target from registration for apply transforms")
                        else:
                            # For func2template, still need to resample the template
                            reff = self.working_dir / "target_res-func_for_apply_transforms.nii.gz"
                            func_res = np.round(get_image_resolution(funcf_all, logger=self.logger), 1)
                            cmd_resample = ['3dresample', 
                                            '-input', str(fixedf), '-prefix', str(reff), 
                                            '-rmode', 'Cu',
                                            '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])]
                            run_command(cmd_resample)
                            self.logger.info(f"Output: template resampled to func resolution")
                    else:
                        reff = fixedf
                    
                    # Apply transform to boldref (tmean)
                    step_name_boldref = self.pipeline.add_step(
                        name=f"func2{target_name}_boldref_transform",
                        func=ants_apply_transforms,
                    )
                    
                    # Use original full-brain version for boldref if registration used wo_skull
                    boldref_moving = funcf_tmean_w_skull_original if funcf_tmean_wo_skull is not None else funcf_tmean_w_skull
                    
                    result_boldref = self.pipeline.run_step(
                        step_name_boldref,
                        movingf=boldref_moving,
                        moving_type=3,
                        interpolation=self.config.get("registration", {}).get("interpolation", "trilinear"),
                        outputf_name=f"func2{target_name}_boldref.nii.gz",
                        fixedf=fixedf,
                        transformf=transform_files,
                        reff=reff,
                        generate_tmean=False,
                    )
                    
                    funcf_tmean_w_skull_registered = result_boldref.output_files["imagef_registered"]
                    
                    # Save space-{target} boldref
                    space_boldref_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{target_name}_boldref.nii.gz"
                    cmd_output = ["cp", str(funcf_tmean_w_skull_registered), str(space_boldref_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(space_boldref_outputf))
                    self.logger.info(f"Output: BOLD reference saved")
                    
                    # Save JSON file for boldref
                    ref_info_outputf = f"{str(space_boldref_outputf).split('.nii.gz')[0]}.json"
                    ref_info = {
                        "target_file": str(fixedf),
                    }
                    try:
                        with open(ref_info_outputf, 'w') as f:
                            json.dump(ref_info, f, indent=2)
                    except (IOError, PermissionError) as e:
                        self.logger.error(f"Output: failed to write reference info JSON - {e}")
                    
                    # Apply transform to funcf_all
                    step_name_func = self.pipeline.add_step(
                        name=f"func2{target_name}_apply_to_all",
                        func=ants_apply_transforms,
                    )
                    
                    result_func = self.pipeline.run_step(
                        step_name_func,
                        movingf=funcf_all,
                        moving_type=3,
                        interpolation=self.config.get("registration", {}).get("interpolation"),
                        outputf_name=f"func2{target_name}.nii.gz",
                        fixedf=fixedf,
                        transformf=transform_files,
                        reff=reff,
                        generate_tmean=True,
                    )
                    
                    funcf_all = result_func.output_files["imagef_registered"]
                    if result_func.output_files.get("imagef_registered_tmean") is not None:
                        funcf_tmean_w_skull = result_func.output_files["imagef_registered_tmean"]
                    
                    # Save functional data
                    funcf_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{target_name}_desc-preproc_bold.nii.gz"
                    cmd_output = ["cp", str(funcf_all), str(funcf_outputf)]
                    run_command(cmd_output)
                    self.generated_files.append(str(funcf_outputf))
                    self.logger.info(f"Output: functional data saved")
                    
                    # Apply transform to mask if provided
                    if funcf_brain_mask is not None:
                        result_mask = self.pipeline.run_step(
                            step_name_func,
                            movingf=funcf_brain_mask,
                            moving_type=0,
                            interpolation='NearestNeighbor',
                            outputf_name=f"func2{target_name}_brainmask.nii.gz",
                            fixedf=fixedf,
                            transformf=transform_files,
                            reff=reff,
                            generate_tmean=False,
                        )
                        
                        funcf_brain_mask_registered = result_mask.output_files["imagef_registered"]
                        brainmask_outputf = self.output_dir / f"{self.bids_prefix_wobold}_space-{target_name}_desc-brain_mask.nii.gz"
                        cmd_output = ["cp", str(funcf_brain_mask_registered), str(brainmask_outputf)]
                        run_command(cmd_output)
                        self.generated_files.append(str(brainmask_outputf))
                        self.logger.info(f"Output: brain mask saved")
                    
                    # Generate QC
                    if self.config.get("quality_control.enabled", True):
                        try:
                            filename_stem = get_filename_stem(self.func_file)
                            filename_stem = filename_stem.replace("_bold", "")
                            reg_qc_filename = f"{filename_stem}_desc-{qc_modality}_bold.png"
                            reg_qc_path = self.qc_dir / reg_qc_filename
                            
                            create_registration_qc(
                                image_file=str(funcf_tmean_w_skull),
                                template_file=str(reff),
                                save_f=str(reg_qc_path),
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
