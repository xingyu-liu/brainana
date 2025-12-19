"""
BIDS Dataset Processor for macacaMRIprep.

This module provides functionality to process entire BIDS datasets,
coordinating anatomical and functional preprocessing workflows across
subjects, sessions, and runs.
"""

import os
import shutil
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import time
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
import nibabel as nib
import numpy as np
# Add hashlib for cache key generation
import hashlib
import copy
import re

from .anat2template import AnatomicalProcessor
from .func2target import FunctionalProcessor
from ..utils import get_logger, setup_logging
from ..utils.templates import resolve_template
from ..utils.bids import parse_bids_entities, get_filename_stem, find_bids_metadata
from ..operations.registration import ants_register
from ..config import get_config, update_config_from_bids_metadata, load_config, get_output_space
from ..config.config_io import save_config
from ..quality_control import generate_qc_report
from ..quality_control.snapshots import create_registration_qc

# FastSurferCNN imports for PyTorch thread configuration
try:
    from FastSurferCNN.utils.threads import setup_pytorch_threads, get_num_threads
    import torch
except ImportError:
    # FastSurferCNN may not be available in all environments
    setup_pytorch_threads = None
    get_num_threads = None
    torch = None

from bids import BIDSLayout

# %%
# Helper functions for config handling
def _ensure_config_dict(config: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    """
    Ensure config is returned as a dictionary.
    
    Args:
        config: Configuration object or dictionary
        
    Returns:
        Configuration as dictionary
    """
    if isinstance(config, dict):
        return config.copy()
    elif hasattr(config, 'to_dict'):
        return config.to_dict()
    else:
        raise TypeError(f"Config must be a dictionary or have to_dict() method, got {type(config)}: {config}")


def _create_job_result(job: 'BaseJob', status: str, start_time: float, 
                      end_time: float, outputs: Optional[Dict[str, Any]] = None, 
                      error: Optional[str] = None) -> Dict[str, Any]:
    """
    Create standardized job result dictionary.
    
    Args:
        job: Processing job
        status: Job status ('completed' or 'failed')
        start_time: Job start time
        end_time: Job end time
        outputs: Job outputs (for successful jobs)
        error: Error message (for failed jobs)
        
    Returns:
        Standardized job result dictionary
    """
    result = {
        "job_id": job.job_id,
        "sub": job.sub,
        "ses": job.ses,
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "duration": end_time - start_time
    }
    
    if outputs is not None:
        result["outputs"] = outputs
    if error is not None:
        result["error"] = error
        
    return result


def _analyze_anatomical_session(anat_files: List['BIDSFile']) -> Dict[str, Any]:
    """
    Analyze anatomical files in a session to determine processing strategy.
    
    Args:
        anat_files: List of BIDSFile objects for anatomical images
        
    Returns:
        Dictionary with processing strategy and file groupings
    """
    t1w_files = [f for f in anat_files if f.suffix == "T1w"]
    t2w_files = [f for f in anat_files if f.suffix == "T2w"]
    
    if t1w_files and t2w_files:
        strategy = "combined"  # Process T1w first, then T2w→T1w
        priority_order = t1w_files + t2w_files
    elif t1w_files:
        strategy = "t1w_only"
        priority_order = t1w_files
    elif t2w_files:
        strategy = "t2w_only"  # Same as T1w pipeline
        priority_order = t2w_files
    else:
        strategy = "no_anat"
        priority_order = []
    
    return {
        "strategy": strategy,
        "t1w_files": t1w_files,
        "t2w_files": t2w_files,
        "processing_order": priority_order
    }

# %%
@dataclass
class BIDSFile:
    """Represents a BIDS file with metadata."""
    path: str
    sub: str
    ses: Optional[str] = None
    run: Optional[str] = None
    task: Optional[str] = None
    acq: Optional[str] = None
    modality: Optional[str] = None
    suffix: Optional[str] = None
    extension: Optional[str] = None
    entities: Optional[Dict[str, str]] = None


@dataclass
class BaseJob:
    """Base class for processing jobs."""
    job_id: str
    sub: str
    ses: Optional[str]
    output_dir: str
    working_dir: str
    config: Dict[str, Any]
    output_root: str  # Base output directory for systematic BIDS path construction
    dataset_dir: str  # Input BIDS dataset directory for structure preservation
    template_spec: Optional[str] = None
    priority: int = 0  # For dependency ordering
    # Dataset context for better structured individual reports
    dataset_context: Optional[Dict[str, Any]] = None  # Full dataset summary for context
    bids_entities: Optional[Dict[str, Any]] = None  # Expected BIDS entities for this subject
    # Caching-related fields
    cache_key: Optional[str] = None  # Unique cache key for this job
    is_completed: bool = False  # Simple completion flag
    # Track actual output files generated during processing
    generated_files: List[str] = field(default_factory=list)  # Track actual output files
    
    def add_generated_file(self, file_path: str) -> None:
        """Add a generated file to the tracking list.
        
        Args:
            file_path: Path to the generated file
        """
        self.generated_files.append(str(file_path))
    
    def get_generated_files(self) -> List[str]:
        """Get list of generated files.
        
        Returns:
            List of generated file paths
        """
        return self.generated_files.copy()


@dataclass
class AnatomicalJob(BaseJob):
    """Represents an anatomical processing job for a subject/session."""
    anat_files: List[BIDSFile] = field(default_factory=list)
    
    def __post_init__(self):
        """Set job type and priority after initialization."""
        if not self.job_id.endswith('_anat'):
            self.job_id += '_anat'
        self.priority = 1  # Higher priority (process first)


@dataclass
class FunctionalJob(BaseJob):
    """Represents a functional processing job for a subject/session."""
    func_files: List[BIDSFile] = field(default_factory=list)
    dependency_job_ids: List[str] = field(default_factory=list)  # Anatomical jobs this depends on
    
    def __post_init__(self):
        """Set job type and priority after initialization."""
        if not self.job_id.endswith('_func'):
            self.job_id += '_func'
        self.priority = 2  # Lower priority (process after anatomical)
    
    def add_dependency(self, job_id: str) -> None:
        """Add an anatomical job dependency.
        
        Args:
            job_id: ID of the anatomical job this functional job depends on
        """
        if job_id not in self.dependency_job_ids:
            self.dependency_job_ids.append(job_id)


#%%
def _generate_job_cache_key(job: BaseJob) -> str:
    """
    Generate a unique cache key for a processing job based on job identity only.
    
    This creates a hash of the job's characteristics to uniquely identify it:
    - job_id (subject/session/type)
    - input files (anatomical or functional)
    - template specification
    
    NOTE: This deliberately EXCLUDES config_hash so that jobs with identical
    inputs but different processing parameters can still be recognized.
    The config_hash is used separately to validate parameter changes.
    
    Args:
        job: Processing job (AnatomicalJob or FunctionalJob)
        
    Returns:
        Unique cache key string (MD5 hash)
    """
    # Create cache key from job identity only (exclude config_hash)
    cache_data = {
        "job_id": job.job_id,
        "template_spec": job.template_spec,
        "job_type": job.__class__.__name__
    }
    
    # Add input files based on job type
    if isinstance(job, AnatomicalJob):
        cache_data["anat_files"] = [f.path for f in job.anat_files]
    elif isinstance(job, FunctionalJob):
        cache_data["func_files"] = [f.path for f in job.func_files]
        cache_data["dependency_job_ids"] = sorted(job.dependency_job_ids)
    
    cache_str = json.dumps(cache_data, sort_keys=True)
    return hashlib.md5(cache_str.encode()).hexdigest()

def _check_job_completion(
    job: BaseJob, 
    logger: Optional[logging.Logger] = None
) -> bool:
    """
    Check if a processing job is completed by verifying actual generated files exist.
    
    This function checks the actual files recorded during processing and verifies
    they still exist on disk.
    
    Args:
        job: Processing job to check (AnatomicalJob or FunctionalJob)
        logger: Logger instance
        
    Returns:
        Boolean indicating if job is completed
    """
    if logger is None:
        logger = get_logger("completion_checker")
    
    # If job is marked as completed, verify files still exist
    if job.is_completed:
        generated_files = job.get_generated_files()
        
        if generated_files:
            # Check if all generated files still exist
            missing_files = []
            present_files = []
            
            for file_path in generated_files:
                if Path(file_path).exists():
                    present_files.append(file_path)
                else:
                    missing_files.append(file_path)
            
            if missing_files:
                logger.warning(f"Output: missing files for {job.job_id} - {len(missing_files)} files")
                return False
            else:
                logger.debug(f"Output: all files present for {job.job_id} - {len(present_files)} files")
                return True
        else:
            # No generated files recorded - this could be a legacy job or not yet processed
            logger.debug(f"Output: no generated files recorded for {job.job_id}")
            return False
    else:
        # Job not marked as completed
        return False

#%%
def _process_single_job(
    job: BaseJob, 
    logger: Optional[logging.Logger] = None,
    worker_log_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core processing logic for a single job.
    
    Args:
        job: Processing job information (AnatomicalJob or FunctionalJob)
        logger: Logger instance to use (if None, creates worker logger)
        worker_log_file: Optional log file path for worker process logging
        
    Returns:
        Dictionary with processing outputs
    """
    # Setup logging for worker process if no logger provided
    if logger is None:
        setup_logging(log_file=worker_log_file, level=logging.INFO)
        logger = get_logger(f"worker_{job.job_id}")
    
    # Setup CPU threads for this worker process (default to 8 for systems with >8 cores)
    # This prevents resource cap issues when multiple processes run in parallel
    if setup_pytorch_threads is not None and get_num_threads is not None:
        num_threads = get_num_threads()
        setup_pytorch_threads(num_threads)
        if torch is not None:
            logger.info(f"System: PyTorch threads configured to {torch.get_num_threads()} in worker process")
    else:
        logger.warning("System: FastSurferCNN not available, skipping PyTorch thread configuration")
    
    # Create subject-level QC directory using PyBIDS-style systematic approach
    output_root = Path(job.output_root)
    sub_output_dir = output_root / f"sub-{job.sub}"
    sub_qc_dir = sub_output_dir / "figures"
    sub_qc_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"System: base output directory - {os.path.basename(output_root)}")
    logger.info(f"System: subject directory - {os.path.basename(sub_output_dir)}")
    logger.info(f"System: QC directory created at subject level")

    outputs = {}
    
    # Process job based on type
    if isinstance(job, AnatomicalJob):
        outputs = _process_anatomical_job(job, sub_qc_dir, logger)
    elif isinstance(job, FunctionalJob):
        outputs = _process_functional_job(job, sub_qc_dir, logger)
    else:
        raise ValueError(f"Unknown job type: {type(job)}")
    
    # Return outputs along with generated files for caching
    return {
        "outputs": outputs,
        "generated_files": job.generated_files  # Pass generated files back to main thread
    }


def _process_anatomical_job(job: AnatomicalJob, sub_qc_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    """Process anatomical data for a single job with T1w and T2w support."""
    
    # Analyze session to determine processing strategy
    session_analysis = _analyze_anatomical_session(job.anat_files)
    strategy = session_analysis["strategy"]
    processing_order = session_analysis["processing_order"]
    
    logger.info(f"Workflow: starting anatomical processing for {job.job_id}")
    logger.info(f"Data: found {len(session_analysis['t1w_files'])} T1w and {len(session_analysis['t2w_files'])} T2w files")
    logger.info(f"Strategy: {strategy}")
    
    if strategy == "no_anat":
        logger.warning(f"Data: no anatomical files found for {job.job_id}")
        return {"anatomical": []}
    
    anat_results = []
    t1w_ref_for_t2w = {}  # Store preprocessed T1w file (in native space) for potential T2w use
    
    # Handle T1w synthesis if needed (only for T1w files)
    t1w_files = session_analysis["t1w_files"]
    if len(t1w_files) > 1:
        logger.info(f"Data: multiple T1w files detected for {job.job_id}, synthesizing...")
        
        synthesized_t1w = _synthesize_multiple_anatomical(
            t1w_files,
            job.output_root,
            job.dataset_dir,
            job.working_dir,
            logger
        )
        
        if synthesized_t1w:
            primary_anat = t1w_files[0]
            synth_entities = primary_anat.entities.copy() if primary_anat.entities else {}
            synth_entities.pop('run', None)
            
            synthesized_bids_file = BIDSFile(
                path=synthesized_t1w,
                sub=primary_anat.sub,
                ses=primary_anat.ses,
                modality="anat",
                suffix="T1w",
                entities=synth_entities,
                acq=primary_anat.acq,
                run=None
            )
            
            # Replace all T1w files with synthesized version in processing order
            non_t1w_files = [f for f in processing_order if f.suffix != "T1w"]
            processing_order = non_t1w_files + [synthesized_bids_file]
            
            logger.info(f"Output: using synthesized T1w for processing")
            t1w_files = [primary_anat]
        else:
            logger.warning("Synthesis: T1w synthesis failed, processing all original T1w files")
    
    # Handle T2w synthesis if needed (only for T2w files)
    t2w_files = session_analysis["t2w_files"]
    if len(t2w_files) > 1:
        logger.info(f"Multiple T2w files detected for {job.job_id}, synthesizing...")
        
        synthesized_t2w = _synthesize_multiple_anatomical(
            t2w_files,
            job.output_root,
            job.dataset_dir,
            job.working_dir,
            logger
        )
        
        if synthesized_t2w:
            primary_anat = t2w_files[0]
            synth_entities = primary_anat.entities.copy() if primary_anat.entities else {}
            synth_entities.pop('run', None)
            
            synthesized_bids_file = BIDSFile(
                path=synthesized_t2w,
                sub=primary_anat.sub,
                ses=primary_anat.ses,
                modality="anat",
                suffix="T2w",
                entities=synth_entities,
                acq=primary_anat.acq,
                run=None
            )
            
            # Replace all T2w files with synthesized version in processing order
            non_t2w_files = [f for f in processing_order if f.suffix != "T2w"]
            processing_order = non_t2w_files + [synthesized_bids_file]
            
            logger.info(f"Using synthesized T2w for processing: {synthesized_t2w}")
        else:
            logger.warning("Synthesis: T2w synthesis failed, processing all original T2w files")
    
    # Ensure correct processing order: T1w first, then T2w
    # This handles any order issues from synthesis steps and guarantees T1w < T2w
    modality_priority = {"T1w": 1, "T2w": 2}
    processing_order.sort(key=lambda f: modality_priority.get(f.suffix, 99))
    
    # Process files in priority order: T1w first, then T2w
    for i, anat_file in enumerate(processing_order):
        modality = anat_file.suffix
        logger.info(f"Step: processing {modality} file {i+1}/{len(processing_order)} - {os.path.basename(anat_file.path)}")
        
        # Load BIDS metadata for anatomical file
        anat_metadata = find_bids_metadata(anat_file.path, job.dataset_dir)
        current_config = _ensure_config_dict(job.config)
        
        if anat_metadata:
            logger.info(f"Data: found metadata - {len(anat_metadata)} keys")
        else:
            logger.info(f"Data: no metadata found")
        
        # Determine processing parameters based on modality and strategy
        processor_kwargs = {
            "modality": modality
        }
        
        if modality == "T2w" and strategy == "combined" and t1w_ref_for_t2w:
            # Scenario B: T2w with T1w in same session - use dedicated coregistration
            logger.info("Strategy: T2w with T1w - processing T2w with bias correction only, then coregistering to T1w")
            logger.info(f"Data: T2w file to be processed - {os.path.basename(anat_file.path)}")
            logger.info(f"Data: available T1w reference - {os.path.basename(t1w_ref_for_t2w.get('with_skull', 'None'))}")
            
            t2w_config = copy.deepcopy(current_config)
            t2w_config["anat"]["skullstripping"]["enabled"] = False  # Disable skull stripping
            t2w_config["registration"]["enabled"] = False  # Disable template registration
            current_config = t2w_config
            
        elif modality == "T2w":
            logger.info("Strategy: T2w-only - using standard template")
        
        # Preserve exact input directory structure by mirroring to output
        anat_input_path = Path(anat_file.path)
        
        # Determine output directory
        if str(anat_input_path).startswith(str(job.output_root)):
            try:
                relative_path = anat_input_path.parent.relative_to(job.output_root)
                anat_output_dir = Path(job.output_root) / relative_path
            except ValueError:
                logger.error(f"System: failed to construct output directory for {os.path.basename(anat_file.path)}")
                continue
        elif str(anat_input_path).startswith(str(job.dataset_dir)):
            try:
                relative_path = anat_input_path.parent.relative_to(job.dataset_dir)
                anat_output_dir = Path(job.output_root) / relative_path
            except ValueError:
                logger.error(f"System: failed to construct output directory for {os.path.basename(anat_file.path)}")
                continue
        else:
            logger.error(f"System: input path not in base output directory or dataset directory")
            continue
        
        anat_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up working directory for anatomical processing
        anat_stem = get_filename_stem(anat_file.path)
        
        # Normalize the stem to use proper BIDS formatting (run-X instead of run_X)
        # This handles datasets with non-standard formatting
        normalized_stem = re.sub(r'_run_([a-zA-Z0-9]+)', r'_run-\1', anat_stem)
        
        # Remove run identifier but ensure modality suffix (T1w/T2w) is preserved
        # Use the modality information from the BIDSFile to ensure correct suffix
        working_dir_stem = re.sub(r'_run-[a-zA-Z0-9_]+', '', normalized_stem)
        
        # Ensure the working directory includes the correct modality suffix
        if not working_dir_stem.endswith(f'_{modality}'):
            working_dir_stem = f"{working_dir_stem}_{modality}"
        
        sub_working_dir = Path(job.working_dir) / f"sub-{job.sub}"
        if anat_file.ses:
            sub_working_dir = sub_working_dir / f"ses-{anat_file.ses}"
        sub_working_dir = sub_working_dir / "anat" / working_dir_stem
        
        # Create anatomical processor
        anat_workflow = AnatomicalProcessor(
            anat_file=anat_file.path,
            output_dir=str(anat_output_dir),
            working_dir=str(sub_working_dir),
            template_spec=job.template_spec,
            config=current_config,
            logger=logger,
            qc_dir=str(sub_qc_dir),
            output_root=str(job.output_root),  # Pass dataset-level output root for fastsurfer
            **processor_kwargs
        )
        
        anat_result = anat_workflow.run()
        anat_results.append(anat_result)
        
        # Store T1w outputs for potential T2w use
        if modality == "T1w":
            # Extract bias-corrected file path for T2w reference
            if "generated_files" in anat_result:
                for file_path in anat_result["generated_files"]:
                    # Extract bias-corrected file path for T2w reference, in native space
                    if file_path.endswith("_desc-preproc_T1w.nii.gz") and 'space-' not in file_path:
                        t1w_ref_for_t2w['with_skull'] = file_path
                        file_path_without_skull = file_path.replace('_desc-preproc_T1w.nii.gz', '_desc-preproc_T1w_brain.nii.gz')
                        if file_path_without_skull in anat_result["generated_files"]:
                            t1w_ref_for_t2w['without_skull'] = file_path_without_skull
        
        # Perform T2w→T1w coregistration for Scenario B
        if modality == "T2w" and strategy == "combined" and t1w_ref_for_t2w:
            logger.info("Performing T2w→T1w coregistration using dedicated function")
            
            # Find bias-corrected T2w file for coregistration
            t2w_bias_corrected = None
            if "generated_files" in anat_result:
                for file_path in anat_result["generated_files"]:
                    if "_desc-preproc_T2w.nii.gz" in file_path and "_brain" not in file_path:
                        t2w_bias_corrected = file_path
                        break
            
            if t2w_bias_corrected and t1w_ref_for_t2w:
                # Perform coregistration using dedicated function
                coregistered_t2w = _coregister_t2w_to_t1w(
                    t2w_file=t2w_bias_corrected,
                    t1w_reference=t1w_ref_for_t2w,
                    working_dir=str(sub_working_dir),
                    output_dir=str(anat_output_dir),
                    logger=logger,
                    qc_dir=str(sub_qc_dir),
                    config=current_config
                )
                
                if coregistered_t2w:
                    # Add coregistered T2w to job outputs
                    job.add_generated_file(coregistered_t2w)
                    logger.info(f"Step: T2w coregistration completed - {os.path.basename(coregistered_t2w)}")
                else:
                    logger.error("Step: T2w coregistration failed")
            else:
                logger.error("System: missing required files for T2w coregistration")
        
        # Track generated files for caching
        if "generated_files" in anat_result:
            generated_files = anat_result["generated_files"]
            logger.info(f"Output: workflow returned {len(generated_files)} generated files")
            for file_path in generated_files:
                job.add_generated_file(file_path)
                logger.info(f"Output: added to job - {os.path.basename(file_path)}")
        else:
            logger.warning(f"Output: no 'generated_files' key in anat_result for {job.job_id}")
        
        logger.info(f"Step: anatomical processing completed for {modality} file {i+1}/{len(processing_order)}")
    
    logger.info(f"Workflow: all anatomical processing completed for {job.job_id}")
    return {"anatomical": anat_results}


def _process_functional_job(job: FunctionalJob, sub_qc_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    """Process functional data for a single job."""
    logger.info(f"Workflow: starting functional processing for {job.job_id}")
    
    # Determine functional processing pipeline from config or use default
    registration_pipeline = job.config.get("func.registration_pipeline", "func2anat2template")
    if not registration_pipeline:
        # Fallback: try accessing via nested dict (for dict configs)
        func_dict = job.config.get("func", {})
        if isinstance(func_dict, dict):
            registration_pipeline = func_dict.get("registration_pipeline", "func2anat2template")
    
    # Check if output_space is native - if so, disable template registration
    output_space = get_output_space(job.config)
    is_native_space = (output_space and output_space.lower() == "native")
    
    if registration_pipeline == "func2anat":
        target_type = "anat"
        target2template = False
    elif registration_pipeline == "func2anat2template":
        target_type = "anat"
        target2template = not is_native_space  # Simple: False if native, True otherwise
    elif registration_pipeline == "func2template":
        if is_native_space:
            # Native space: switch to func2anat
            logger.info("Pipeline: func2template requested but output_space is native - switching to func2anat")
            target_type = "anat"
            target2template = False
        else:
            target_type = "template"
            target2template = False
    else:
        # Default to func2anat2template if not specified
        logger.warning(f"Pipeline: unknown registration_pipeline '{registration_pipeline}', defaulting to func2anat2template")
        target_type = "anat"
        target2template = not is_native_space

    output_root = Path(job.output_root)
    func_results = []
    
    for func_file in job.func_files:
        logger.info(f"Step: processing functional file - {os.path.basename(func_file.path)}")
        
        # Load BIDS metadata for functional file and update config
        func_metadata = find_bids_metadata(func_file.path, job.dataset_dir)
        current_config = _ensure_config_dict(job.config)
        
        if func_metadata:
            logger.info(f"Data: found metadata - {len(func_metadata)} keys")
            current_config = update_config_from_bids_metadata(current_config, func_metadata, logger)
            logger.info(f"Config: updated slice timing configuration from metadata")
        else:
            logger.info(f"Data: no metadata found")
        logger.debug(f"Config: current configuration loaded")
        
        # Find the matching preprocessed anatomical file for the functional file
        if target_type == "anat":
            target_file = None
            skullstripping_enabled = current_config.get('anat', {}).get('skullstripping', {}).get('enabled')
            
            # Define file type and pattern to search for
            if skullstripping_enabled:
                file_type = "brain-extracted"
                search_pattern = '*desc-preproc_T1w_brain.nii.gz'
            else:
                file_type = "full"
                search_pattern = '*desc-preproc_T1w.nii.gz'
            pattern_suffix = search_pattern.replace('*', '')
            
            # Modify the search pattern to exclude template-space files
            native_space_search_pattern = search_pattern.replace('*.nii.gz', '*[^_space-].nii.gz')
            
            # Strategy 1: Look for anatomical files in the same session first
            if func_file.ses:
                same_ses_pattern = output_root / f"sub-{func_file.sub}" / f"ses-{func_file.ses}" / "anat" / native_space_search_pattern
            else:
                same_ses_pattern = output_root / f"sub-{func_file.sub}" / "anat" / native_space_search_pattern
            
            same_ses_files = list(same_ses_pattern.parent.glob(native_space_search_pattern)) if same_ses_pattern.parent.exists() else []
            
            # Filter to ensure they match the subject and session
            same_ses_anats = []
            
            for f in same_ses_files:
                entities = parse_bids_entities(f.name)
                if (entities.get('sub') == func_file.sub and 
                    entities.get('ses') == func_file.ses):
                    if pattern_suffix in f.name and "_space-" not in f.name:
                        same_ses_anats.append(f)
            
            if same_ses_anats:
                target_file = str(same_ses_anats[0])  # Use first match
                logger.info(f"Found {file_type} anatomical file in same session {func_file.ses}: {target_file}")
            
            # Strategy 2: If no anatomical file in same session, search across all sessions for this subject
            if target_file is None:
                logger.info(f"No preprocessed anatomical file found in session {func_file.ses}, searching across all sessions for subject {func_file.sub}")
                
                # Search all sessions for this subject
                all_ses_files = list(output_root.glob(f"sub-{func_file.sub}/**/anat/{native_space_search_pattern}"))
                
                # Filter and sort by session
                across_ses_anats = []
                for f in all_ses_files:
                    entities = parse_bids_entities(f.name)
                    if entities.get('sub') == func_file.sub:
                        if pattern_suffix in f.name and "_space-" not in f.name:
                            across_ses_anats.append(f)
                
                if across_ses_anats:
                    # Sort by session to prefer earlier sessions
                    across_ses_anats.sort(key=lambda x: parse_bids_entities(x.name).get('ses', ''))
                    target_file = str(across_ses_anats[0])
                    logger.info(f"Data: found {file_type} anatomical file in different session - {os.path.basename(target_file)}")
                else:
                    logger.error(f"Data: no {file_type} preprocessed anatomical file found for subject {func_file.sub}")
                    continue
            
            # Find target2template transform file
            target2template_transform = None
            if target2template:
                if not job.template_spec or job.template_spec.lower() == "native":
                    logger.error("target2template is True but template_spec is None or 'native'")
                    continue
                    
                try:
                    target_dir = Path(target_file).parent
                    template_name = job.template_spec.split(':')[0]
                    
                    if not template_name:
                        logger.error(f"System: failed to extract template name from template_spec: {job.template_spec}")
                        continue
                    
                    # Look for transform files with various naming patterns
                    transform_patterns = [
                        f"*from-T1w_to-{template_name}_mode-image_xfm.h5"
                    ]
                    
                    for pattern in transform_patterns:
                        transform_files = list(target_dir.glob(pattern))
                        if transform_files:
                            target2template_transform = str(transform_files[0])
                            logger.info(f"Data: found transform file - {os.path.basename(target2template_transform)}")
                            break
                    
                    if target2template_transform is None:
                        logger.error(f"Data: no target2template_transform file found for template {template_name}")
                        logger.debug(f"System: searched patterns - {transform_patterns}")
                        continue
                
                except (IndexError, AttributeError) as e:
                    logger.error(f"System: error finding target2template_transform file - {e}")
                    continue
                
        elif target_type == "template":
            if not job.template_spec or job.template_spec.lower() == "native":
                logger.error(f"target_type is 'template' but template_spec is None or 'native'")
                continue
            try:
                target_file = resolve_template(job.template_spec)
                target2template_transform = None
            except Exception as e:
                logger.error(f"System: failed to resolve template {job.template_spec} - {e}")
                continue

        # if none or path not exists, raise an error
        if target_file is None or not Path(target_file).exists():
            raise ValueError(f"The pipeline {registration_pipeline} failed to find a target file ({target_type}) for {func_file.path}")
        if target2template:
            if target2template_transform is None or not Path(target2template_transform).exists():
                raise ValueError(f"The pipeline {registration_pipeline} failed to find a target({target_type})2template_transform file for {func_file.path}")
        
        # Log the registration strategy
        if is_native_space:
            logger.info(f"Strategy: output space is native - template registration skipped")
        elif target2template:
            logger.info(f"Strategy: target2template registration enabled")
        else:
            logger.info(f"Strategy: target2template registration disabled")
        
        # Preserve exact input directory structure by mirroring to output
        func_input_path = Path(func_file.path)
        func_output_dir = Path(job.output_root) / func_input_path.parent.relative_to(job.dataset_dir)
        
        # Set up working directory for functional processing  
        # Use original filename stem to preserve exact input structure
        func_stem = get_filename_stem(func_file.path)
        
        func_working_dir = Path(job.working_dir) / f"sub-{job.sub}"
        if func_file.ses:
            func_working_dir = func_working_dir / f"ses-{func_file.ses}"
        func_working_dir = func_working_dir / "func" / func_stem
        
        func_workflow = FunctionalProcessor(
            func_file=func_file.path,
            target_file=str(target_file),
            output_dir=str(func_output_dir),
            working_dir=str(func_working_dir),
            config=current_config,
            logger=logger,
            target_type=target_type,
            target2template=target2template,
            target2template_transform=str(target2template_transform) if target2template_transform else None,
            template_spec=job.template_spec,
            qc_dir=str(sub_qc_dir)
        )
        
        func_result = func_workflow.run()
        func_results.append(func_result)
        
        # Track generated files for caching
        if "generated_files" in func_result:
            generated_files = func_result["generated_files"]
            logger.info(f"Output: workflow returned {len(generated_files)} generated files")
            for file_path in generated_files:
                job.add_generated_file(file_path)
                logger.info(f"Output: added to job - {os.path.basename(file_path)}")
        else:
            logger.warning(f"Output: no 'generated_files' key in func_result for {job.job_id}")
    
    logger.info(f"Workflow: functional processing completed for {job.job_id}")
    return {"functional": func_results}


def _handle_job_completion(
    job: BaseJob, 
    is_completed: bool, 
    processor: Optional['BIDSDatasetProcessor'] = None,
    logger: Optional[logging.Logger] = None
) -> None:
    """
    Handle job completion stamping and caching.
    
    Args:
        job: Processing job to stamp
        is_completed: Whether job completed successfully
        processor: BIDSDatasetProcessor instance for caching
        logger: Logger instance for logging
    """
    # Mark job completion status
    job.is_completed = is_completed
    
    # Stamp completion immediately if processor is available
    if processor:
        processor._stamp_job_completion(job, is_completed=is_completed)
        processor._save_cache()
        status = "completion" if is_completed else "failure"
        if logger:
            logger.info(f"Stamped and cached {status} for: {job.job_id}")


def _process_multiple_jobs(jobs_with_data: List[BaseJob], n_procs: int, 
                          job_type: str, logger: logging.Logger, output_dir: Path,
                          processor: 'BIDSDatasetProcessor' = None) -> List[Dict[str, Any]]:
    """
    Process multiple jobs either sequentially or in parallel.
    
    Args:
        jobs_with_data: List of jobs to process (AnatomicalJob or FunctionalJob)
        n_procs: Number of processes to use
        job_type: Type of job for logging ('anat' or 'func')
        logger: Logger instance
        output_dir: Output directory for logs
        
    Returns:
        List of job results
    """
    if not jobs_with_data:
        logger.info(f"Data: no {job_type} data found to process")
        return []
    
    logger.info(f"Workflow: processing {len(jobs_with_data)} jobs with {job_type} data")
    
    if n_procs == 1:
        # Sequential processing
        results = []
        for job in jobs_with_data:
            start_time = time.time()
            try:
                job_result = _process_single_job(job, logger, None)
                outputs = job_result["outputs"]
                generated_files = job_result["generated_files"]
                
                # Update job object with generated files (no need for this in serial processing since
                # we're using the same job object, but keeping for consistency)
                job.generated_files = generated_files
                
                # Handle job completion
                _handle_job_completion(job, is_completed=True, processor=processor, logger=logger)
                
                result = _create_job_result(job, "completed", start_time, time.time(), outputs=outputs)
                results.append(result)
                logger.info(f"Workflow: {job_type.capitalize()} processing completed for {job.job_id}")
            except Exception as e:
                # Handle job failure
                _handle_job_completion(job, is_completed=False, processor=processor, logger=logger)
                result = _create_job_result(job, "failed", start_time, time.time(), error=str(e))
                results.append(result)
                logger.error(f"Workflow: {job_type.capitalize()} job {job.job_id} failed - {e}")
                logger.error(f"System: traceback - {traceback.format_exc()}")
        return results
    else:
        # Parallel processing
        results = []
        
        if n_procs > 4:
            logger.warning(f"System: using {n_procs} processes - ensure sufficient RAM (8GB+ per process)")
        
        # Create logs directory for worker processes
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        with ProcessPoolExecutor(max_workers=n_procs) as executor:
            # Submit jobs with timing
            job_futures = {}
            for job in jobs_with_data:
                start_time = time.time()
                worker_log_file = str(logs_dir / f"worker_{job.job_id}_{job_type}.log")
                future = executor.submit(_process_single_job, job, None, worker_log_file)
                job_futures[future] = (job, start_time)
            
            completed_count = 0
            total_jobs = len(jobs_with_data)
            
            for future in as_completed(job_futures):
                job, start_time = job_futures[future]
                completed_count += 1
                end_time = time.time()
                
                try:
                    job_result = future.result()
                    outputs = job_result["outputs"]
                    generated_files = job_result["generated_files"]
                    
                    # Update job object with generated files from worker process
                    job.generated_files = generated_files
                    
                    # Handle job completion
                    _handle_job_completion(job, is_completed=True, processor=processor, logger=logger)
                    
                    result = _create_job_result(job, "completed", start_time, end_time, outputs=outputs)
                    results.append(result)
                    logger.info(f"Workflow: {job_type.capitalize()} processing completed for {job.job_id} ({completed_count}/{total_jobs})")
                except Exception as e:
                    # Handle job failure
                    _handle_job_completion(job, is_completed=False, processor=processor, logger=logger)
                    result = _create_job_result(job, "failed", start_time, end_time, error=str(e))
                    results.append(result)
                    logger.error(f"Workflow: {job_type.capitalize()} job {job.job_id} failed ({completed_count}/{total_jobs}) - {e}")
                    logger.error(f"System: traceback - {traceback.format_exc()}")
        
        return results


def _synthesize_multiple_anatomical(
    anat_files: List[BIDSFile],
    base_output_dir: str,
    dataset_dir: str,
    working_dir: str,
    logger: logging.Logger
) -> Optional[str]:
    """
    Synthesize multiple anatomical images (T1w or T2w) for a session by coregistering and averaging them.
    
    Args:
        anat_files: List of BIDSFile objects for anatomical images (all same modality)
        base_output_dir: Base output directory
        dataset_dir: BIDS dataset directory
        working_dir: Working directory
        logger: Logger instance
        
    Returns:
        Path to synthesized anatomical image, or None if synthesis failed
    """
    if len(anat_files) <= 1:
        return None
    
    # Determine modality from the first file
    modality = anat_files[0].suffix  # T1w or T2w
    logger.info(f"Synthesizing {len(anat_files)} {modality} images")
    logger.info(f"Source runs: {[f.run or 'None' for f in anat_files]}")
    logger.info(f"Reference image (run-{anat_files[0].run or '01'}): {anat_files[0].path}")
    
    try:
        # Use the first image as reference
        reference_file = anat_files[0]
        reference_path = Path(reference_file.path)
        
        # Create working directory for synthesis
        synthesis_work_dir = Path(working_dir) / f"sub-{reference_file.sub}"
        if reference_file.ses:
            synthesis_work_dir = synthesis_work_dir / f"ses-{reference_file.ses}"
        synthesis_work_dir = synthesis_work_dir / f"anat_{modality.lower()}_synthesis"
        synthesis_work_dir.mkdir(parents=True, exist_ok=True)
        
        # Create output directory that mirrors input structure
        anat_input_path = Path(reference_file.path)
        anat_output_dir = Path(base_output_dir) / anat_input_path.parent.relative_to(dataset_dir)
        anat_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load reference image
        logger.info(f"Data: using reference {modality} - {os.path.basename(reference_path)}")
        reference_img = nib.load(str(reference_path))
        
        # Storage for coregistered images
        coregistered_images = [reference_img]
        
        # Coregister all other images to the reference
        for i, anat_file in enumerate(anat_files[1:], 1):
            logger.info(f"Step: coregistering {modality} {i+1}/{len(anat_files)} - {os.path.basename(anat_file.path)}")
            
            moving_path = Path(anat_file.path)
            
            # Use real run values for meaningful output naming
            reference_run = anat_files[0].run or "01"  # Fallback to "01" if no run
            moving_run = anat_file.run or f"{i+1:02d}"  # Fallback to sequence number
            
            # Output prefix using real run values: run-02_to_run-01_T1w_coreg
            output_prefix = f"run-{moving_run}_to_run-{reference_run}_{modality}_coreg"
            
            try:
                # Use the existing ants_register function for coregistration
                # This performs rigid + affine registration (linear only, no nonlinear)
                registration_result = ants_register(
                    fixedf=str(reference_path),
                    movingf=str(moving_path),
                    working_dir=str(synthesis_work_dir),
                    output_prefix=output_prefix,
                    config=get_config().to_dict(),  # Use default macacaMRIprep config
                    logger=logger,
                    xfm_type='rigid'  # Use only linear registration (affine)
                )
                
                # Check if registration was successful
                if "imagef_registered" in registration_result:
                    coregistered_path = registration_result["imagef_registered"]
                    logger.info(f"Step: successfully coregistered - {os.path.basename(coregistered_path)}")
                    
                    # Load and store the coregistered image
                    coregistered_img = nib.load(coregistered_path)
                    coregistered_images.append(coregistered_img)
                else:
                    logger.warning(f"Step: registration did not produce expected output for {os.path.basename(anat_file.path)}")
                    
            except Exception as e:
                logger.error(f"Step: coregistration failed for {os.path.basename(anat_file.path)} - {e}")
                continue
        
        # Average all coregistered images
        if len(coregistered_images) < len(anat_files):
            logger.warning(f"Data: only {len(coregistered_images)}/{len(anat_files)} images successfully coregistered")
        
        if len(coregistered_images) > 1:
            logger.info(f"Step: averaging {len(coregistered_images)} coregistered images")
            
            # Stack all image data
            image_data = []
            for img in coregistered_images:
                image_data.append(img.get_fdata())
            
            # Calculate mean across images
            mean_data = np.mean(image_data, axis=0)
            
            # Create synthesized image using reference header
            synthesized_img = nib.Nifti1Image(
                mean_data.astype(np.float32),
                affine=reference_img.affine,
                header=reference_img.header
            )
            
            # Generate output filename based on reference file
            reference_stem = get_filename_stem(reference_file.path)
            logger.debug(f"Data: original reference stem - {reference_stem}")
            
            # Remove run identifier from synthesized filename using regex to handle various formats
            # This pattern matches both _run-X and _run_X formats (hyphen or underscore)
            run_pattern = r'_run[-_][a-zA-Z0-9]+'
            synthesized_filename = re.sub(run_pattern, '', reference_stem) + ".nii.gz"
            logger.debug(f"Data: synthesized filename after run removal - {synthesized_filename}")
            synthesized_path = anat_output_dir / synthesized_filename
            
            # Save synthesized image
            nib.save(synthesized_img, str(synthesized_path))
            logger.info(f"Output: synthesized {modality} saved")
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
                "OutputFilename": synthesized_filename,
                "Modality": modality
            }
            
            metadata_path = synthesized_path.parent / Path(get_filename_stem(synthesized_path) + '.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Synthesis metadata saved: {metadata_path}")
            
            return str(synthesized_path)
        else:
            logger.error("No successfully coregistered images to average")
            return None
            
    except Exception as e:
        logger.error(f"{modality} synthesis failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def _coregister_t2w_to_t1w(
    t2w_file: str,
    t1w_reference: Dict[str, str],
    working_dir: str,
    output_dir: str,
    logger: logging.Logger,
    qc_dir: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Coregister T2w to T1w using the same approach as T1w synthesis.
    
    Args:
        t2w_file: Path to T2w image
        t1w_reference: Dictionary with T1w reference paths (with/without skull)
        working_dir: Working directory for temporary files
        output_dir: Output directory for final result
        logger: Logger instance
        qc_dir: Optional QC directory for snapshot generation
        config: Optional configuration dictionary for QC settings
        
    Returns:
        Path to coregistered T2w image, or None if coregistration failed
    """
    try:
        logger.info(f"Step: coregistering T2w to T1w reference")
        logger.info(f"Data: moving T2w - {os.path.basename(t2w_file)}")
        logger.info(f"Data: fixed T1w - {os.path.basename(t1w_reference['with_skull'])}")
        
        # Create working directory for T2w coregistration
        t2w_work_dir = Path(working_dir) / "t2w_to_t1w_coregistration"
        t2w_work_dir.mkdir(parents=True, exist_ok=True)
        
        # Output prefix for coregistration
        output_prefix = "t2w_to_t1w_coreg"
        
        # Use the same ants_register approach as T1w synthesis
        # Use provided config or fall back to default
        reg_config = config if config is not None else get_config().to_dict()
        registration_result = ants_register(
            fixedf=str(t1w_reference['with_skull']),
            movingf=str(t2w_file),
            working_dir=str(t2w_work_dir),
            output_prefix=output_prefix,
            config=reg_config,
            logger=logger,
            xfm_type='rigid'
        )
        
        # Check if registration was successful
        if "imagef_registered" in registration_result:
            coregistered_path = registration_result["imagef_registered"]
            logger.info(f"Step: T2w coregistration successful - {os.path.basename(coregistered_path)}")
            
            # Generate final output filename using consistent variable naming
            filename_stem = get_filename_stem(t2w_file)
            # Remove T2w suffix and any existing desc-preproc to avoid duplication
            filename_base = filename_stem.replace("_T2w", "").replace("_desc-preproc", "")
            final_output_filename = f"{filename_base}_space-T1w_desc-preproc_T2w.nii.gz"
            final_output_path = Path(output_dir) / final_output_filename
            
            # Copy coregistered image to final location
            shutil.copy2(coregistered_path, str(final_output_path))
            logger.info(f"Output: T2w coregistered to T1w space")
            
            # Save the T2w to T1w transformation matrix
            if "forward_transform" in registration_result and registration_result["forward_transform"]:
                xfm_output_filename = f"{filename_base}_from-T2w_to-T1w_mode-image_xfm.h5"
                xfm_output_path = Path(output_dir) / xfm_output_filename
                shutil.copy2(registration_result["forward_transform"], str(xfm_output_path))
                logger.info(f"Output: T2w to T1w transform saved - {xfm_output_filename}")
            else:
                logger.warning("Output: T2w to T1w transform not available in registration result")
            
            # Save the inverse transform
            if "inverse_transform" in registration_result and registration_result["inverse_transform"]:
                xfm_output_filename = f"{filename_base}_from-T1w_to-T2w_mode-image_xfm.h5"
                xfm_output_path = Path(output_dir) / xfm_output_filename
                shutil.copy2(registration_result["inverse_transform"], str(xfm_output_path))
                logger.info(f"Output: T1w to T2w transform saved - {xfm_output_filename}")
            else:
                logger.warning("Output: T1w to T2w transform not available in registration result")
            
            # Generate QC snapshot for T2w coregistration if QC is enabled and directory is provided
            if qc_dir and config and config.get("quality_control", {}).get("enabled", True):
                try:
                    # Generate BIDS-compliant filename for T2w coregistration QC (following standard pattern)
                    qc_filename = f"{filename_base}_desc-T2w2T1w_T2w.png"
                    qc_path = Path(qc_dir) / qc_filename
                    
                    # Create T2w to T1w coregistration QC snapshot
                    if t1w_reference['without_skull'] is not None:
                        qc_template = t1w_reference['without_skull']
                    else:
                        qc_template = t1w_reference['with_skull']
                    t2w_qc_outputs = create_registration_qc(
                        image_file=str(final_output_path),  # Coregistered T2w
                        template_file=str(qc_template),   # Reference T1w
                        save_f=str(qc_path),
                        modality="T2w2T1w",
                        logger=logger
                    )
                    
                    if t2w_qc_outputs:
                        logger.info(f"QC: T2w coregistration overlay created")
                    else:
                        logger.warning("QC: failed to create T2w coregistration overlay")
                        
                except Exception as e:
                    logger.warning(f"QC: could not generate T2w coregistration overlay - {e}")
            
            return str(final_output_path)
        else:
            logger.error("Step: T2w coregistration did not produce expected output")
            return None
            
    except Exception as e:
        logger.error(f"Step: T2w to T1w coregistration failed - {e}")
        logger.error(f"System: traceback - {traceback.format_exc()}")
        return None


class BIDSDatasetProcessor:
    """
    Process entire BIDS datasets using macacaMRIprep workflows.
    
    This class coordinates anatomical and functional preprocessing across
    subjects, sessions, and runs in a BIDS dataset.
    
    Important Notes on Cross-Session Dependencies:
    ============================================
    
    Functional data often requires processed anatomical data as a registration target,
    but the anatomical data may be in a different session than the functional data.
    
    Example problematic scenario:
    - Subject-01/ses-01: Contains T1w anatomical data
    - Subject-01/ses-02: Contains BOLD functional data (no T1w)
    - Subject-01/ses-03: Contains BOLD functional data (no T1w)
    
    If jobs are processed per session in parallel, the functional data in ses-02 and ses-03
    may start processing before the T1w in ses-01 is finished, causing failures when trying
    to find the required preprocessed anatomical targets and transform files.
    
    Two-Phase Processing Solution:
    =============================
    
    When processing both anatomical and functional data in parallel (n_procs > 1),
    this processor automatically uses a two-phase approach:
    1. Phase 1: Process ALL anatomical data across ALL subjects/sessions first
    2. Phase 2: Process ALL functional data across ALL subjects/sessions second
    
    This ensures all anatomical dependencies are available before functional processing begins.
    
    Caching and Resumption:
    ======================
    
    The processor supports caching to enable resuming interrupted processing:
    - Completion status is checked by verifying expected output files exist
    - Job completion status is persistently stored in processing_cache.json
    - Cache is automatically updated during processing to enable resumption
    - Use overwrite=False to skip already completed jobs (default caching behavior)  
    - Use overwrite=True to reprocess all jobs regardless of cache
    - Use check_outputs=True to validate output files before skipping
    """
    
    def __init__(
        self,
        dataset_dir: Union[str, Path],
        output_dir: Union[str, Path],
        working_dir: Optional[Union[str, Path]] = None,
        config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ):
        """
        Initialize BIDS dataset processor.
        
        Args:
            dataset_dir: Path to BIDS dataset root directory
            output_dir: Path to output derivatives directory
            config: Configuration file path or dictionary
            logger: Optional logger instance
            **kwargs: Additional arguments passed to workflows
        """

        self.dataset_dir = Path(dataset_dir).absolute()
        self.output_dir = Path(output_dir).absolute()
        
        # Process config and override template settings with template_spec
        if config is None:
            # Load default config
            self.config = get_config()
        elif isinstance(config, (str, Path)):
            # Load config from file
            self.config = load_config(config)
        else:
            # Use provided config dict
            self.config = config
        
        # Update config with dataset_dir and output_dir
        config_dict = _ensure_config_dict(self.config)
        if 'paths' not in config_dict:
            config_dict['paths'] = {}
        config_dict['paths']['dataset_dir'] = str(self.dataset_dir)
        config_dict['paths']['output_dir'] = str(self.output_dir)
        
        # Update the config object
        if hasattr(self.config, 'update'):
            self.config.update(config_dict)
        else:
            self.config = config_dict

        self.template_spec = get_output_space(self.config)
        self.kwargs = kwargs
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if working_dir is not None:
            self.working_dir = Path(working_dir).absolute()
        else:
            self.working_dir = self.output_dir / "working"
            
        # Setup logging
        if logger is not None:
            self.logger = logger
        else:
            setup_logging(level=logging.INFO)
            self.logger = get_logger(self.__class__.__name__)
        
        # Log the template override
        self.logger.info(f"Config: template specification - {self.template_spec} (overrides config)")
        
        # Setup global dataset log file
        self._setup_dataset_logging()
        
        # Initialize BIDS layout with optional filtering
        bids_filtering = self.config.get("bids_filtering", {})
        ignore_patterns = self._build_ignore_patterns(bids_filtering)
        
        if ignore_patterns:
            self.logger.info(f"System: initializing BIDS layout with filtering")
            self.logger.info(f"Data: including subjects - {bids_filtering.get('subjects', 'all')}")
            self.logger.info(f"Data: including sessions - {bids_filtering.get('sessions', 'all')}")
        else:
            self.logger.info(f"System: initializing BIDS layout")
        
        try:
            self.layout = BIDSLayout(
                str(self.dataset_dir),
                validate=False,  # Skip validation for speed
                derivatives=False,
                ignore=ignore_patterns if ignore_patterns else None
            )
        except Exception as e:
            self.logger.error(f"System: failed to initialize BIDS layout - {e}")
            raise
        
        self.logger.info(f"System: BIDS dataset loaded successfully")
        self.logger.info(f"Data: found {len(self.layout.get_subjects())} subjects")
        
        # Setup BIDS derivatives structure
        self._setup_bids_derivatives()
        
        # Processing state tracking
        self.processing_jobs: List[BaseJob] = []
        self.completed_jobs: List[str] = []
        self.failed_jobs: List[str] = []
        
        # Cache management
        self.cache_file = self.output_dir / "processing_cache.json"
        self.job_cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()
        
    def _build_ignore_patterns(self, bids_filtering: Dict[str, Any]) -> List[Any]:
        """
        Build regex patterns to ignore subjects/sessions not in the filter.
        
        This optimizes BIDS layout initialization by excluding unwanted directories
        during indexing rather than filtering after indexing.
        
        Args:
            bids_filtering: Dictionary containing subjects, sessions, tasks, runs filters
            
        Returns:
            List of regex patterns to pass to BIDSLayout ignore parameter
        """
        ignore_patterns = []
        
        # Filter by subjects if specified
        subjects = bids_filtering.get('subjects')
        if subjects:
            # Normalize subjects by removing 'sub-' prefix if present
            normalized_subjects = [s[4:] if s.startswith('sub-') else s for s in subjects]
            included_subjects = set(str(s) for s in normalized_subjects)
            
            # Create pattern to exclude subjects not in the list
            # Pattern matches "sub-<ID>/" where ID is not in included subjects
            excluded_pattern = r"sub-(?!" + "|".join(re.escape(s) for s in included_subjects) + r")\w*/"
            ignore_patterns.append(re.compile(excluded_pattern))
            
        # Filter by sessions if specified  
        sessions = bids_filtering.get('sessions')
        if sessions:
            # Convert to set for faster lookup and normalize to strings
            included_sessions = set(str(s) for s in sessions)
            
            # Create pattern to exclude sessions not in the list
            # Pattern matches "ses-<ID>/" where ID is not in included sessions
            excluded_pattern = r"ses-(?!" + "|".join(re.escape(s) for s in included_sessions) + r")\w*/"
            ignore_patterns.append(re.compile(excluded_pattern))
            
        return ignore_patterns
    
    def _load_cache(self) -> None:
        """Load processing cache from disk."""
        # Load from processing_cache.json if it exists
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    self.job_cache = json.load(f)
                self.logger.info(f"System: loaded processing cache - {len(self.job_cache)} entries")
                return
            except Exception as e:
                self.logger.warning(f"System: failed to load cache file - {e}")
        
        # If no cache file exists, start with empty cache
        self.job_cache = {}
        self.logger.info("System: no processing cache found - starting fresh")
            
    def _save_cache(self) -> None:
        """Save processing cache to disk."""
        try:
            # Ensure directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_file, 'w') as f:
                json.dump(self.job_cache, f, indent=2, default=str)
            self.logger.info(f"System: saved processing cache - {len(self.job_cache)} entries")
            self.logger.debug(f"System: cache file path - {self.cache_file}")
            # Debug: Log cache contents
            for cache_key, entry in self.job_cache.items():
                self.logger.debug(f"Cache entry: {entry.get('job_id', 'unknown')} -> is_completed={entry.get('is_completed', False)}")
        except Exception as e:
            self.logger.warning(f"System: failed to save cache file - {e}")
    
    def check_job_completion(
        self, 
        job: BaseJob, 
        use_cache: bool = True,
        verify_outputs: bool = False
    ) -> bool:
        """
        Check if a job is completed. Uses stamped completion as primary method,
        with optional file verification for resumption scenarios.
        
        Args:
            job: Processing job to check (AnatomicalJob or FunctionalJob)
            use_cache: Whether to use cached completion status
            verify_outputs: Whether to verify output files exist (for resumption only)
            
        Returns:
            Boolean indicating if job is completed
        """
        cache_key = job.cache_key or _generate_job_cache_key(job)
        job.cache_key = cache_key
        
        # Check cache first if enabled
        if use_cache and cache_key in self.job_cache:
            cached_entry = self.job_cache[cache_key]
            
            # Use cached completion status directly
            cached_completed = cached_entry.get("is_completed", False)
            
            # Restore generated files from cache
            if "generated_files" in cached_entry:
                job.generated_files = cached_entry["generated_files"]
            
            # Restore completion status
            job.is_completed = cached_completed
            
            # Use cached completion status
            self.logger.debug(f"Using cached completion status for {job.job_id}: {cached_completed}")
            
            # Optional: verify files still exist if requested (for resumption)
            if verify_outputs and cached_completed:
                self.logger.debug(f"Verifying output files exist for cached completion: {job.job_id}")
                
                file_check_status = _check_job_completion(job, self.logger)
                
                # Warn if files are missing but keep cached completion status
                if not file_check_status:
                    self.logger.warning(f"Job {job.job_id} marked complete but some output files are missing")
            
            return cached_completed
        
        # No cache entry - use file checking (for legacy compatibility)
        completion_status = _check_job_completion(job, self.logger)
        
        # Update cache using stamp method
        self._stamp_job_completion(job, is_completed=completion_status)
        
        return completion_status
    
    def clear_cache(self, job_ids: Optional[List[str]] = None) -> None:
        """
        Clear processing cache.
        
        Args:
            job_ids: Specific job IDs to clear from cache. If None, clears all.
        """
        if job_ids is None:
            self.job_cache.clear()
            self.logger.info("System: cleared entire processing cache")
        else:
            cleared_count = 0
            for cache_key in list(self.job_cache.keys()):
                if self.job_cache[cache_key].get("job_id") in job_ids:
                    del self.job_cache[cache_key]
                    cleared_count += 1
            self.logger.info(f"System: cleared cache for {cleared_count} jobs")
        
        self._save_cache()
    
    def _setup_dataset_logging(self) -> None:
        """Set up global dataset processing log file."""
        try:

            # Set up dataset log file
            dataset_log_file = self.output_dir / "logs" / "processing.log"
            
            # Ensure logs directory exists
            dataset_log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Create file handler for dataset-level logging
            log_level = self.logger.level if self.logger.level != logging.NOTSET else logging.INFO
            
            dataset_file_handler = logging.FileHandler(dataset_log_file, mode='w')
            dataset_file_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            dataset_file_handler.setLevel(log_level)  # Use configured log level instead of forcing DEBUG
            
            # Ensure main logger level allows messages to reach the file handler
            if self.logger.level == logging.NOTSET or self.logger.level > log_level:
                self.logger.setLevel(log_level)
                
            self.logger.addHandler(dataset_file_handler)
            self.logger.info(f"System: dataset processing log initialized - {dataset_log_file}")
            self.logger.info(f"System: worker process logs directory - {self.output_dir / 'logs'}")
            
        except Exception as e:
            self.logger.warning(f"System: failed to set up dataset logging - {e}")
    
    def _setup_bids_derivatives(self) -> None:
        """
        Set up BIDS derivatives directory structure and metadata files.
        """
        self.logger.info("System: setting up BIDS derivatives structure")
        
        # Create dataset_description.json for derivatives
        dataset_desc = {
            "Name": f"macacaMRIprep derivatives of {self.dataset_dir.name}",
            "BIDSVersion": "1.8.0",
            "DatasetType": "derivative",
            "GeneratedBy": [
                {
                    "Name": "macacaMRIprep",
                    "Version": "1.0.0",  # Should be dynamically set
                    "CodeURL": "https://github.com/your-org/macacaMRIprep"
                }
            ],
            "SourceDatasets": [
                {
                    "URL": str(self.dataset_dir),
                    "Version": "unknown"
                }
            ],
            "HowToAcknowledge": "Please cite macacaMRIprep in your publications",
            "DatasetDOI": ""
        }
        
        dataset_desc_file = self.output_dir / "dataset_description.json"
        if not dataset_desc_file.exists():
            with open(dataset_desc_file, 'w') as f:
                json.dump(dataset_desc, f, indent=2)
            self.logger.info(f"System: created derivatives dataset_description.json - {dataset_desc_file}")
        
        # Create .bidsignore file for derivatives
        bidsignore_content = [
            "# macacaMRIprep generated files",
            "working/",
            "*.log",
            "*.tmp",
            "**/tmp*",
            "**/working*"
        ]
        
        bidsignore_file = self.output_dir / ".bidsignore"
        if not bidsignore_file.exists():
            with open(bidsignore_file, 'w') as f:
                f.write('\n'.join(bidsignore_content))
            self.logger.info(f"System: created .bidsignore file - {bidsignore_file}")
            
        # Save processing configuration for reproducibility
        if self.config:
            config_file = self.output_dir / "processing_config.yaml"
            config_dict = _ensure_config_dict(self.config)
            save_config(config_dict, config_file)
            self.logger.info(f"System: saved processing configuration - {config_file}")
        
        self.logger.info("System: BIDS derivatives structure setup completed")
    
    def get_dataset_summary(self) -> Dict[str, Any]:
        """Get summary of the BIDS dataset."""
        subs = self.layout.get_subjects()
        sess = self.layout.get_sessions()
        
        summary = {
            "dataset_root": str(self.dataset_dir),
            "output_dir": str(self.output_dir),
            "total_subs": len(subs),
            "subs": subs,
            "total_sess": len(sess) if sess else 0,
            "sess": sess or [],
            "modalities": {},
            "tasks": self.layout.get_tasks() or []
        }
        
        # Count files by modality
        for modality in ['anat', 'func']:
            files = self.layout.get(datatype=modality, extension=['.nii.gz', '.nii'], return_type='filename')
            summary["modalities"][modality] = len(files)
        
        return summary
    
    def discover_processing_jobs(
        self,
        subs: Optional[List[str]] = None,
        sess: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        runs: Optional[List[str]] = None
    ) -> List[BaseJob]:
        """
        Discover all processing jobs in the dataset.
        
        Args:
            subs: List of subject IDs to process (default: all)
            sess: List of session IDs to process (default: all)
            tasks: List of task names to process (default: all)
            runs: List of run numbers to process (default: all)
        
        Returns:
            List of BaseJob objects (AnatomicalJob and FunctionalJob)
        """
        self.logger.info("Workflow: discovering processing jobs")
        
        # Get subjects to process
        all_subjects = self.layout.get_subjects()
        if subs is None:
            target_subjects = all_subjects
        else:
            # Normalize input subjects by removing 'sub-' prefix if present
            normalized_subs = [s[4:] if s.startswith('sub-') else s for s in subs]
            target_subjects = [s for s in normalized_subs if s in all_subjects]
            if len(target_subjects) != len(normalized_subs):
                missing = set(normalized_subs) - set(target_subjects)
                self.logger.warning(f"Some requested subjects not found: {missing}")
        
        jobs = []
        
        for sub in target_subjects:
            # Get sessions for this subject
            sub_sess = self.layout.get_sessions(subject=sub)
            self.logger.info(f"Data: subject {sub} sessions - {sub_sess}")
            
            if not sub_sess:
                sub_sess = [None]  # No sessions in dataset
                self.logger.info(f"Data: no sessions found for subject {sub} - using None")
            
            if sess is not None:
                sub_sess = [s for s in sub_sess if s in sess]
                self.logger.info(f"Data: sessions after filtering for subject {sub} - {sub_sess}")
            
            for ses in sub_sess:
                job_id = f"sub-{sub}"
                if ses:
                    job_id += f"_ses-{ses}"
                
                # Find anatomical files using PyBIDS query system
                anat_filters = {
                    "subject": sub, 
                    "datatype": "anat", 
                    "suffix": ["T1w", "T2w"], 
                    "extension": [".nii.gz", ".nii"]
                }
                if ses:
                    anat_filters["session"] = ses
                
                anat_files = []
                anat_files_found = list(self.layout.get(**anat_filters))
                self.logger.info(f"Data: found {len(anat_files_found)} anatomical files for {job_id}")
                
                for anat_file in anat_files_found:
                    # Use existing BIDS utilities to parse entities consistently
                    bids_entities = anat_file.get_entities()
                    # Also use our parse_bids_entities to ensure consistency with codebase patterns
                    parsed_entities = parse_bids_entities(anat_file.path)
                    # Merge both approaches for robustness
                    final_entities = {**bids_entities, **parsed_entities}
                    
                    suffix = final_entities.get('suffix', 'T1w')
                    anat_files.append(BIDSFile(
                        path=anat_file.path,
                        sub=sub,
                        ses=ses,
                        modality="anat",
                        suffix=suffix,  # Capture actual suffix (T1w or T2w)
                        entities=final_entities,
                        acq=final_entities.get('acq'),  # Use standard BIDS 'acq' not 'acquisition'
                        run=final_entities.get('run')
                    ))
                    self.logger.debug(f"Data: queued {suffix} anatomical file - {Path(anat_file.path).name}")
                
                # Find functional files using PyBIDS query system  
                func_filters = {
                    "subject": sub, 
                    "datatype": "func", 
                    "suffix": "bold", 
                    "extension": [".nii.gz", ".nii"]
                }
                if ses:
                    func_filters["session"] = ses
                if tasks:
                    func_filters["task"] = tasks
                if runs:
                    func_filters["run"] = runs
                
                func_files = []
                func_files_found = list(self.layout.get(**func_filters))
                self.logger.info(f"Data: found {len(func_files_found)} functional files for {job_id}")
                
                for func_file in func_files_found:
                    # Use existing BIDS utilities to parse entities consistently
                    bids_entities = func_file.get_entities()
                    # Also use our parse_bids_entities to ensure consistency with codebase patterns
                    parsed_entities = parse_bids_entities(func_file.path)
                    # Merge both approaches for robustness
                    final_entities = {**bids_entities, **parsed_entities}
                    
                    func_files.append(BIDSFile(
                        path=func_file.path,
                        sub=sub,
                        ses=ses,
                        task=final_entities.get('task'),
                        run=final_entities.get('run'),
                        modality="func",
                        suffix="bold",
                        entities=final_entities,
                        acq=final_entities.get('acq')  # Use standard BIDS 'acq' not 'acquisition'
                    ))
                
                # Create separate jobs for anatomical and functional data
                session_jobs_created = []
                
                # Create anatomical job if we have anatomical data
                if anat_files:
                    # Use PyBIDS to construct BIDS-compliant output paths
                    sub_output_dir = self.output_dir / f"sub-{sub}"
                    if ses:
                        sub_output_dir = sub_output_dir / f"ses-{ses}"
                    
                    # Create dataset context for this job
                    dataset_context = self.get_dataset_summary()
                    
                    # Enhanced BIDS entities context using PyBIDS
                    sub_sess = self.layout.get_sessions(subject=sub) or [None]
                    sub_tasks = self.layout.get_tasks(subject=sub) or []
                    sub_runs = []
                    for datatype in ['anat', 'func']:
                        datatype_runs = self.layout.get_runs(subject=sub, datatype=datatype) or []
                        sub_runs.extend(datatype_runs)
                    sub_runs = list(set(sub_runs))  # Remove duplicates
                    
                    # Use PyBIDS to get all available entity values for this subject
                    bids_entities = {
                        "sub": sub,
                        "sess": sub_sess,
                        "tasks": sub_tasks,
                        "runs": sub_runs,
                        "acq": self.layout.get_acquisitions(subject=sub) or [],
                        "modalities": ["anat"],
                        # Additional PyBIDS metadata
                        "space": self.layout.get_spaces(subject=sub) or []
                    }
                    
                    anat_job = AnatomicalJob(
                        job_id=job_id,  # Will be modified to add _anat suffix in __post_init__
                        sub=sub,
                        ses=ses,
                        anat_files=anat_files,
                        output_dir=str(sub_output_dir),
                        working_dir=str(self.working_dir),
                        config=self.config,
                        template_spec=self.template_spec,
                        output_root=str(self.output_dir),  # Pass base output dir for BIDS-compliant paths
                        dataset_dir=str(self.dataset_dir),  # Pass dataset directory for structure preservation
                        dataset_context=dataset_context,  # Full dataset context
                        bids_entities=bids_entities  # Enhanced BIDS entities using PyBIDS
                    )
                    
                    # Generate cache key for job
                    anat_job.cache_key = _generate_job_cache_key(anat_job)
                    
                    jobs.append(anat_job)
                    session_jobs_created.append(f"anatomical ({len(anat_files)} files)")
                    self.logger.info(f"Workflow: created anatomical job - {anat_job.job_id} ({len(anat_files)} files)")
                
                # Create functional job if we have functional data
                if func_files:
                    # Use PyBIDS to construct BIDS-compliant output paths
                    sub_output_dir = self.output_dir / f"sub-{sub}"
                    if ses:
                        sub_output_dir = sub_output_dir / f"ses-{ses}"
                    
                    # Create dataset context for this job (reuse if already created)
                    if 'dataset_context' not in locals():
                        dataset_context = self.get_dataset_summary()
                    
                    # Enhanced BIDS entities context using PyBIDS (reuse if already created)
                    if 'bids_entities' not in locals():
                        sub_sess = self.layout.get_sessions(subject=sub) or [None]
                        sub_tasks = self.layout.get_tasks(subject=sub) or []
                        sub_runs = []
                        for datatype in ['anat', 'func']:
                            datatype_runs = self.layout.get_runs(subject=sub, datatype=datatype) or []
                            sub_runs.extend(datatype_runs)
                        sub_runs = list(set(sub_runs))  # Remove duplicates
                        
                        # Use PyBIDS to get all available entity values for this subject
                        bids_entities = {
                            "sub": sub,
                            "sess": sub_sess,
                            "tasks": sub_tasks,
                            "runs": sub_runs,
                            "acq": self.layout.get_acquisitions(subject=sub) or [],
                            "modalities": ["func"],
                            # Additional PyBIDS metadata
                            "space": self.layout.get_spaces(subject=sub) or []
                        }
                    else:
                        # Update modalities for functional job
                        bids_entities = bids_entities.copy()
                        bids_entities["modalities"] = ["func"]
                    
                    func_job = FunctionalJob(
                        job_id=job_id,  # Will be modified to add _func suffix in __post_init__
                        sub=sub,
                        ses=ses,
                        func_files=func_files,
                        output_dir=str(sub_output_dir),
                        working_dir=str(self.working_dir),
                        config=self.config,
                        template_spec=self.template_spec,
                        output_root=str(self.output_dir),  # Pass base output dir for BIDS-compliant paths
                        dataset_dir=str(self.dataset_dir),  # Pass dataset directory for structure preservation
                        dataset_context=dataset_context,  # Full dataset context
                        bids_entities=bids_entities  # Enhanced BIDS entities using PyBIDS
                    )
                    
                    # Add anatomical dependency if there's an anatomical job for this session
                    # BUT only if the pipeline requires anatomical dependencies
                    registration_pipeline = self.config.get("func", {}).get("registration_pipeline", "")
                    
                    # Only add anatomical dependency if pipeline is NOT func2template
                    # func2template pipeline registers directly to template, no anatomical dependency needed
                    if anat_files and registration_pipeline != "func2template":
                        # The anatomical job was just created, so we know its ID
                        anat_job_id = f"sub-{sub}"
                        if ses:
                            anat_job_id += f"_ses-{ses}"
                        anat_job_id += "_anat"
                        func_job.add_dependency(anat_job_id)
                        self.logger.info(f"Workflow: added anatomical dependency {anat_job_id} for functional job {func_job.job_id} (pipeline: {registration_pipeline})")
                    elif registration_pipeline == "func2template":
                        self.logger.info(f"Workflow: no anatomical dependency for functional job {func_job.job_id} (func2template pipeline)")
                    
                    # Generate cache key for job
                    func_job.cache_key = _generate_job_cache_key(func_job)
                    
                    jobs.append(func_job)
                    session_jobs_created.append(f"functional ({len(func_files)} files)")
                    self.logger.info(f"Workflow: created functional job - {func_job.job_id} ({len(func_files)} BOLD files)")
                
                if session_jobs_created:
                    self.logger.info(f"Workflow: created jobs for {job_id} - {', '.join(session_jobs_created)}")
                else:
                    self.logger.warning(f"Data: no data found for {job_id} - skipping job creation")
        
        self.processing_jobs = jobs
        self.logger.info(f"Workflow: discovered {len(jobs)} processing jobs")
        
        # Log summary by type
        anat_jobs = sum(1 for job in jobs if isinstance(job, AnatomicalJob))
        func_jobs = sum(1 for job in jobs if isinstance(job, FunctionalJob))
        self.logger.info(f"Data: anatomical jobs - {anat_jobs}")
        self.logger.info(f"Data: functional jobs - {func_jobs}")
        
        return jobs
    
    def run_dataset(
        self,
        subs: Optional[List[str]] = None,
        sess: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        runs: Optional[List[str]] = None,
        run_anat: bool = True,
        run_func: bool = True,
        n_procs: int = 1,
        overwrite: Optional[bool] = None,
        check_outputs: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Process the entire BIDS dataset.
        
        To handle cross-session dependencies, this processor always processes anatomical 
        data first (if requested), then functional data (if requested). This ensures 
        anatomical dependencies are available for functional processing.
        
        Args:
            subs: List of subject IDs to process
            sess: List of session IDs to process
            tasks: List of task names to process
            runs: List of run numbers to process
            run_anat: Whether to run anatomical processing
            run_func: Whether to run functional processing
            n_procs: Number of parallel processes
            overwrite: Overwrite existing outputs and force reprocessing (disables caching).
                      If None, reads from config['general']['overwrite'] (default: False)
            check_outputs: Verify output files exist when checking completion.
                          If None, reads from config['caching']['check_outputs'] (default: True)
        
        Returns:
            Dictionary with processing results
        """
        start_time = time.time()
        self.logger.info("Workflow: starting BIDS dataset processing")
        
        # Read config-based parameters if not provided as arguments
        config_dict = _ensure_config_dict(self.config)
        
        # Get overwrite setting from config if not provided
        if overwrite is None:
            overwrite = config_dict.get('general', {}).get('overwrite', False)
            if overwrite:
                self.logger.info(f"System: overwrite mode enabled from config - {overwrite}")
        
        # Get verify_outputs setting from config if not provided
        if check_outputs is None:
            verify_outputs = config_dict.get('caching', {}).get('check_outputs', True)
            if not verify_outputs:
                self.logger.info(f"System: output verification disabled from config - {verify_outputs}")
        else:
            verify_outputs = check_outputs
        
        # ========================================================================
        # PHASE 0: Handle overwrite mode and check completion status for all jobs
        # ========================================================================
        # Handle overwrite mode - delete output directory if it exists
        if overwrite:
            self.logger.info("System: overwrite enabled - reprocessing all jobs regardless of completion status")
            if self.output_dir.exists():
                self.logger.info(f"System: deleting existing output directory - {self.output_dir}")
                shutil.rmtree(self.output_dir)
                self.logger.info("System: output directory deleted successfully")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._setup_bids_derivatives()
            self._setup_dataset_logging()
            
            # Clear cache since we're starting fresh - force clear in-memory cache and recreate empty file
            self.job_cache.clear()
            self.logger.info("Cleared entire processing cache")
            self._save_cache()  # Save empty cache to disk
        else:
            self.logger.info("System: caching enabled - checking completion status")
        
        # Use existing jobs if already discovered, otherwise discover them
        if hasattr(self, 'processing_jobs') and self.processing_jobs:
            jobs = self.processing_jobs
            self.logger.info(f"System: using previously discovered {len(jobs)} processing jobs")
        else:
            # Discover processing jobs
            jobs = self.discover_processing_jobs(subs, sess, tasks, runs)
        
        if not jobs:
            # detemine whether the dataset is already completed or just not discovered
            if self.completed_jobs:
                self.logger.info("Workflow: all jobs are already completed")
                duration = time.time() - start_time
                return {
                    "status": "completed",  # Changed from 'all_completed' to 'completed'
                    "total_jobs": len(self.completed_jobs),
                    "completed_jobs": len(self.completed_jobs),
                    "failed_jobs": 0,
                    "duration_seconds": duration,
                    "duration_formatted": f"{duration/60:.1f} minutes",
                    "processing_approach": "cached"
                }
            else:
                self.logger.info("Data: no jobs discovered - dataset may not be BIDS compliant")
            
        # Check completion status for all jobs if caching is enabled (not overwrite)
        if not overwrite:
            self.logger.info("System: checking completion status for all jobs")
            
            completed_jobs = []
            pending_jobs = []
            
            for job in jobs:
                # Check if job should be processed based on type and requested processing
                should_process = True
                if isinstance(job, AnatomicalJob) and not run_anat:
                    should_process = False
                elif isinstance(job, FunctionalJob) and not run_func:
                    should_process = False
                
                if not should_process:
                    # Skip this job type
                    continue
                
                is_completed = self.check_job_completion(
                    job, use_cache=True, verify_outputs=verify_outputs
                )
                
                if is_completed:
                    completed_jobs.append(job)
                    self.logger.info(f"Workflow: ✓ job {job.job_id} already completed - skipping")
                else:
                    pending_jobs.append(job)
                    self.logger.info(f"Workflow: ○ job {job.job_id} pending")
            
            self.logger.info(f"Workflow: completion check - {len(completed_jobs)} completed, {len(pending_jobs)} pending")
            
            # Update jobs list to only include pending jobs
            jobs = pending_jobs
            
            # Update tracking lists with completed jobs
            for job in completed_jobs:
                self.completed_jobs.append(job.job_id)
        
        # Save cache after completion check
        self._save_cache()
        
        # Clear working directories for pending jobs to avoid conflicts
        if jobs and not overwrite:
            self.logger.info("System: clearing working directories for pending jobs to avoid conflicts")
            for job in jobs:
                # Clear working directory for this job
                job_working_dir = Path(job.working_dir) / f"sub-{job.sub}"
                if job.ses:
                    job_working_dir = job_working_dir / f"ses-{job.ses}"
                
                if job_working_dir.exists():
                    try:
                        shutil.rmtree(job_working_dir)
                        self.logger.debug(f"System: cleared working directory - {job_working_dir}")
                    except Exception as e:
                        self.logger.warning(f"System: failed to clear working directory {job_working_dir} - {e}")
        
        if not jobs:
            self.logger.info("Workflow: all jobs are already completed")
            duration = time.time() - start_time
            return {
                "status": "completed",  # Changed from 'all_completed' to 'completed'
                "total_jobs": len(self.completed_jobs),
                "completed_jobs": len(self.completed_jobs),
                "failed_jobs": 0,
                "duration_seconds": duration,
                "duration_formatted": f"{duration/60:.1f} minutes",
                "processing_approach": "cached"
            }
        
        # Check if we have anything to process
        if not run_anat and not run_func:
            self.logger.warning("System: neither anatomical nor functional processing requested")
            return {"status": "no_processing_requested", "duration": 0}
        
        # Sort jobs by priority (secondary mechanism - primary is two-phase processing)
        # This ensures anatomical jobs (priority=1) come before functional jobs (priority=2)
        # in the job list, though the two-phase approach is the main dependency mechanism
        jobs.sort(key=lambda x: x.priority)
        
        # Log the priority ordering for debugging
        anat_job_count = sum(1 for job in jobs if isinstance(job, AnatomicalJob))
        func_job_count = sum(1 for job in jobs if isinstance(job, FunctionalJob))
        self.logger.info(f"System: job priority ordering - {anat_job_count} anatomical (priority=1), {func_job_count} functional (priority=2)")
        
        # Log the actual job order after sorting for verification
        if self.logger.level <= logging.DEBUG:
            self.logger.debug("System: job processing order after priority sorting")
            for i, job in enumerate(jobs):
                job_type = "anatomical" if isinstance(job, AnatomicalJob) else "functional"
                self.logger.debug(f"System:   {i+1}. {job.job_id} ({job_type}, priority={job.priority})")
        
        all_results = []
        
        # ========================================================================
        # PHASE 1: Process ALL anatomical data (if requested)
        # This ensures all anatomical dependencies are available before functional processing
        # ========================================================================
        if run_anat:
            self.logger.info("=" * 60)
            self.logger.info("Workflow: PHASE 1 - processing ALL anatomical data")
            self.logger.info("=" * 60)
            
            anat_jobs = [job for job in jobs if isinstance(job, AnatomicalJob)]
            anat_results = _process_multiple_jobs(
                anat_jobs, n_procs, "anat", self.logger, self.output_dir, self
            )
            all_results.extend(anat_results)
            
            # Check if anatomical processing succeeded
            anat_success_count = sum(1 for r in anat_results if r["status"] == "completed")
            anat_fail_count = len(anat_results) - anat_success_count
            
            if anat_results:  # Only log if there were anatomical jobs
                self.logger.info(f"Workflow: phase 1 completed - {anat_success_count} anatomical succeeded, {anat_fail_count} failed")
                
                if anat_fail_count > 0 and run_func:
                    self.logger.warning("Workflow: anatomical failures detected - functional processing may fail for dependent data")
            
            # Save cache after anatomical processing
            if anat_results:
                self._save_cache()
                self.logger.info(f"System: saved cache after anatomical processing - {len(self.job_cache)} entries")
            
        # ========================================================================
        # PHASE 2: Process ALL functional data (if requested)
        # All anatomical dependencies are now available from Phase 1
        # ========================================================================
        if run_func:
            self.logger.info("=" * 60)
            self.logger.info("Workflow: PHASE 2 - processing ALL functional data")
            self.logger.info("=" * 60)
            
            if not run_anat:
                self.logger.info("Workflow: anatomical processing not requested - assuming dependencies satisfied")
            
            func_jobs = [job for job in jobs if isinstance(job, FunctionalJob)]
            
            # Add dependency checking for functional jobs
            # Use the complete list of all jobs (both original and newly processed) to find dependencies
            all_jobs_for_deps = self.processing_jobs if hasattr(self, 'processing_jobs') else jobs
            # Also include any jobs that were just processed in Phase 1
            if run_anat and anat_results:
                # Add the anatomical jobs that were just processed to the dependency search
                processed_anat_jobs = [job for job in anat_jobs if job.job_id in [r["job_id"] for r in anat_results]]
                all_jobs_for_deps = list(all_jobs_for_deps) + processed_anat_jobs
            
            ready_func_jobs = []
            for job in func_jobs:
                if isinstance(job, FunctionalJob) and job.dependency_job_ids:
                    # Check if all dependencies are completed
                    all_deps_completed = True
                    for dep_job_id in job.dependency_job_ids:
                        # Look for dependency in all available jobs
                        dep_job = next((j for j in all_jobs_for_deps if j.job_id == dep_job_id), None)
                        if dep_job is None or not dep_job.is_completed:
                            all_deps_completed = False
                            self.logger.debug(f"Dependency {dep_job_id} for {job.job_id} not completed (found: {dep_job is not None}, completed: {dep_job.is_completed if dep_job else False})")
                            break
                    
                    if all_deps_completed:
                        ready_func_jobs.append(job)
                        self.logger.info(f"Workflow: functional job {job.job_id} dependencies satisfied - ready for processing")
                    else:
                        self.logger.warning(f"Workflow: functional job {job.job_id} dependencies not met - skipping")
                else:
                    # No dependencies or not a functional job
                    ready_func_jobs.append(job)
                    self.logger.info(f"Workflow: functional job {job.job_id} has no dependencies - ready for processing")
            
            func_results = _process_multiple_jobs(
                ready_func_jobs, n_procs, "func", self.logger, self.output_dir, self
            )
            all_results.extend(func_results)
            
            # Check functional processing results
            func_success_count = sum(1 for r in func_results if r["status"] == "completed")
            func_fail_count = len(func_results) - func_success_count
            
            if func_results:  # Only log if there were functional jobs
                self.logger.info(f"Workflow: phase 2 completed - {func_success_count} functional succeeded, {func_fail_count} failed")
            
            # Save cache after functional processing
            if func_results:
                self._save_cache()
                self.logger.info(f"System: saved cache after functional processing - {len(self.job_cache)} entries")
            
        # Save cache after processing
        self._save_cache()
        
        # Update tracking lists
        for result in all_results:
            if result["status"] == "completed":
                self.completed_jobs.append(result["job_id"])
            else:
                self.failed_jobs.append(result["job_id"])
        
        # ========================================================================
        # PHASE 3: Generate subject-level QC reports (consolidate all sessions)
        # ========================================================================
        self.logger.info("=" * 60)
        self.logger.info("Workflow: PHASE 3 - generating subject-level QC reports")
        self.logger.info("=" * 60)
        
        # Include all original jobs (both processed and skipped) for report generation
        all_original_jobs = self.processing_jobs if hasattr(self, 'processing_jobs') else jobs
        self._generate_subject_reports(all_original_jobs)
        
        # Calculate summary
        duration = time.time() - start_time
        total_jobs = len(all_original_jobs)  # Use original job count
        completed = len(self.completed_jobs)
        failed = len(self.failed_jobs)
        
        processing_approach = "dependency_safe"
        if not overwrite:
            processing_approach += "_with_caching"
        if run_anat and run_func:
            processing_approach = "two_phase_" + processing_approach
        elif run_anat:
            processing_approach = "anatomical_only_" + processing_approach
        elif run_func:
            processing_approach = "functional_only_" + processing_approach
        
        # Determine overall status based on results
        if failed == 0:
            overall_status = "completed"
        elif completed == 0:
            overall_status = "failed"
        else:
            overall_status = "completed_with_failures"
        
        # Include skipped jobs in results for consistency
        complete_results = all_results.copy()
        if not overwrite:
            # Find jobs that were skipped (in all_original_jobs but not in jobs)
            processed_job_ids = {job.job_id for job in jobs}
            skipped_jobs = [job for job in all_original_jobs if job.job_id not in processed_job_ids]
            
            # Add skipped job results
            for skipped_job in skipped_jobs:
                skipped_result = _create_job_result(
                    job=skipped_job,
                    status="skipped",
                    start_time=start_time,
                    end_time=start_time,  # No processing time for skipped jobs
                    outputs=None,
                    error=None
                )
                complete_results.append(skipped_result)
        
        summary = {
            "status": overall_status,
            "total_jobs": total_jobs,
            "completed_jobs": completed,
            "failed_jobs": failed,
            "skipped_jobs": total_jobs - len(jobs) if not overwrite else 0,
            "processed_jobs": len(jobs),
            "duration_seconds": duration,
            "duration_formatted": f"{duration/60:.1f} minutes",
            "processing_approach": processing_approach,
            "caching_enabled": not overwrite
        }
        
        # Log final status
        if overall_status == "completed":
            self.logger.info(f"Workflow: dataset processing completed successfully in {duration/60:.1f} minutes")
        elif overall_status == "failed":
            self.logger.error(f"Workflow: dataset processing failed completely in {duration/60:.1f} minutes")
        else:
            self.logger.warning(f"Workflow: dataset processing completed with some failures in {duration/60:.1f} minutes")
        
        self.logger.info(f"Workflow: jobs completed - {completed}/{total_jobs}")
        if summary["skipped_jobs"] > 0:
            self.logger.info(f"Workflow: jobs skipped (already completed) - {summary['skipped_jobs']}")
        if failed > 0:
            self.logger.warning(f"Workflow: jobs failed - {failed}")
        
        # Save final processing summary (for reporting/inspection, not for caching)
        summary_file = self.output_dir / "processing_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        self.logger.info(f"Output: processing summary saved - {summary_file}")
        
        # Clear cache if processing completed successfully
        if overall_status == "completed":
            self.logger.info("System: processing completed successfully - clearing cache to free disk space")
            self.clear_cache()
            self.logger.info("System: cache cleared successfully")
        else:
            self.logger.info("System: processing completed with failures - keeping cache for potential re-runs")
        
        return summary
    

    
    def _generate_subject_reports(self, jobs: List[BaseJob]) -> None:
        """
        Generate QC reports at the subject level, consolidating all sessions.
        
        Args:
            jobs: List of all processing jobs
        """
        # Group jobs by subject
        subs_jobs = {}
        for job in jobs:
            if job.sub not in subs_jobs:
                subs_jobs[job.sub] = []
            subs_jobs[job.sub].append(job)
        
        self.logger.info(f"QC: generating QC reports for {len(subs_jobs)} subjects")
        
        for sub, sub_jobs in subs_jobs.items():
            try:
                self._generate_single_subject_report(sub, sub_jobs)
                self.logger.info(f"QC: ✓ report generated for subject {sub}")
            except Exception as e:
                self.logger.error(f"QC: ✗ report generation failed for subject {sub} - {e}")
                self.logger.error(f"System: traceback - {traceback.format_exc()}")
    
    def _generate_single_subject_report(self, sub: str, sub_jobs: List[BaseJob]) -> None:
        """
        Generate a single QC report for a subject, including all sessions.
        
        Args:
            sub: Subject ID
            sub_jobs: List of jobs for this subject (one per session)
        """
        
        # Use the first job as representative for shared info
        representative_job = sub_jobs[0]
        
        base_output_dir = Path(self.output_dir)
        sub_qc_dir = base_output_dir / f"sub-{sub}" / "figures"
        
        # Generate comprehensive QC report
        if sub_qc_dir.exists():
            # Log available files for debugging
            png_files = list(sub_qc_dir.glob("*.png"))
            self.logger.info(f"QC: found {len(png_files)} PNG files in {sub_qc_dir} for subject {sub}")
            for png_file in png_files:
                self.logger.debug(f"QC: PNG file - {png_file.name}")
            
            # Convert Config object to dictionary if needed
            config_dict = _ensure_config_dict(representative_job.config)
            
            # Calculate subject-wide file counts by querying BIDS layout
            try:
                layout = BIDSLayout(self.dataset_dir, validate=False)
                
                # Count all T1w files for this subject across all sessions
                sub_t1w_files = layout.get(
                    subject=sub,
                    datatype="anat",
                    suffix="T1w",
                    extension=[".nii.gz", ".nii"]
                )
                
                # Count all T2w files for this subject across all sessions
                sub_t2w_files = layout.get(
                    subject=sub,
                    datatype="anat",
                    suffix="T2w",
                    extension=[".nii.gz", ".nii"]
                )
                
                # Count all BOLD files for this subject across all sessions  
                sub_func_files = layout.get(
                    subject=sub,
                    datatype="func",
                    suffix="bold",
                    extension=[".nii.gz", ".nii"]
                )
                
                sub_t1w_count = len(sub_t1w_files)
                sub_t2w_count = len(sub_t2w_files)
                sub_anat_count = sub_t1w_count + sub_t2w_count
                sub_func_count = len(sub_func_files)
                
                self.logger.debug(f"Subject {sub} has {sub_t1w_count} T1w, {sub_t2w_count} T2w, and {sub_func_count} BOLD files across all sessions")
                
            except Exception as e:
                self.logger.warning(f"QC: could not calculate subject-wide file counts - {e}")
                # Fallback to aggregating counts from all jobs for this subject
                sub_t1w_count = 0
                sub_t2w_count = 0
                for job in sub_jobs:
                    if isinstance(job, AnatomicalJob):
                        for anat_file in job.anat_files:
                            if anat_file.suffix == "T1w":
                                sub_t1w_count += 1
                            elif anat_file.suffix == "T2w":
                                sub_t2w_count += 1
                sub_anat_count = sub_t1w_count + sub_t2w_count
                sub_func_count = sum(len(job.func_files) for job in sub_jobs if isinstance(job, FunctionalJob))
            
            # Aggregate job counts across all sessions for this subject
            total_anat_count = sum(len(job.anat_files) for job in sub_jobs if isinstance(job, AnatomicalJob))
            total_func_count = sum(len(job.func_files) for job in sub_jobs if isinstance(job, FunctionalJob))
            
            # Create dataset context with subject-wide aggregated information
            sub_context = {
                **representative_job.dataset_context,  # Include global dataset info
                "job_file_counts": {
                    "anatomical": total_anat_count,
                    "functional": total_func_count,
                    "total": total_anat_count + total_func_count
                },
                "subject_file_counts": {
                    "anatomical": sub_anat_count,
                    "t1w": sub_t1w_count,
                    "t2w": sub_t2w_count,
                    "functional": sub_func_count,
                    "total": sub_anat_count + sub_func_count
                },
                "sessions_processed": [job.ses for job in sub_jobs if job.ses],
                "total_sessions": len(sub_jobs)
            }
            
            # Generate report path for subject (no session in filename)
            report_filename = f"sub-{sub}.html"
            report_path = base_output_dir / report_filename
            
            report_outputs = generate_qc_report(
                snapshot_dir=str(sub_qc_dir),
                report_path=str(report_path),
                config=config_dict,
                logger=self.logger,
                snapshot_paths=None,  # Auto-discover snapshots
                dataset_context=sub_context,  # Subject-wide aggregated context
            )
            
            self.logger.info(f"QC: report generated for subject {sub} - {report_outputs}")
            
            # Verify report was created successfully
            if "html_report" in report_outputs:
                report_path = Path(report_outputs["html_report"])
                if report_path.exists():
                    self.logger.info(f"QC: report created successfully - {report_path}")
                else:
                    self.logger.warning(f"QC: report file not found - {report_path}")
            else:
                self.logger.warning("QC: no HTML report generated")
        else:
            self.logger.warning(f"QC: no QC directory found for subject {sub}")

    def _stamp_job_completion(
        self, 
        job: BaseJob, 
        is_completed: bool = True
    ) -> None:
        """
        Stamp job completion status immediately when job finishes successfully.
        This is the primary method for marking jobs as complete.
        
        Args:
            job: Processing job to stamp (AnatomicalJob or FunctionalJob)
            is_completed: True if job completed successfully
        """
        cache_key = job.cache_key or _generate_job_cache_key(job)
        
        # Update job completion status
        job.is_completed = is_completed
        
        if is_completed:
            # Debug: Check generated files
            generated_files = job.get_generated_files()
            if generated_files:
                job_type = "anatomical" if isinstance(job, AnatomicalJob) else "functional"
                self.logger.info(f"Output: generated {len(generated_files)} {job_type} files")
                for file_path in generated_files[:3]:  # Show first 3
                    self.logger.info(f"Output:   - {Path(file_path).name}")
            else:
                self.logger.warning(f"Output: no files tracked for {job.job_id}")
        
        # Update cache with stamped completion
        cache_entry = {
            "job_id": job.job_id,
            "is_completed": is_completed,
            "last_checked": time.time(),
            "generated_files": job.generated_files
        }
        
        self.job_cache[cache_key] = cache_entry
        
        # Debug logging
        self.logger.info(f"Workflow: stamped job completion - {job.job_id} (is_completed={is_completed}, generated_files={len(job.generated_files)})")
        self.logger.debug(f"Cache key: {cache_key}")
        self.logger.debug(f"Cache entry: {cache_entry}")