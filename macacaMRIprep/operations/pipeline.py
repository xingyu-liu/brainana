"""
Pipeline state management for macacaMRIprep.

This module handles:
1. Pipeline execution and state tracking
2. Caching of intermediate results
3. Error recovery and cleanup
4. Progress tracking
"""

import os
import json
import time
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable
from dataclasses import dataclass
from enum import Enum, auto

from ..utils import setup_step_logging, log_step_start, log_step_end

class PipelineState(Enum):
    """Pipeline execution states."""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CACHED = auto()

@dataclass
class StepResult:
    """Result of a pipeline step."""
    state: PipelineState
    output_files: Dict[str, str]
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Get step duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

class Pipeline:
    """Base pipeline class for managing processing steps."""
    
    def __init__(
        self,
        name: str,
        output_dir: Union[str, Path],
        config: Any,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize pipeline.
        
        Args:
            name: Pipeline name
            output_dir: Output directory
            config: Pipeline configuration
            logger: Logger instance
            overwrite: Whether to overwrite existing outputs (default: True)
        """
        self.name = name
        self.output_dir = Path(output_dir)
        self.overwrite = config.get("general.overwrite")
        # Normalize verbose to integer (0, 1, or 2) for consistency
        from ..utils.logger import normalize_verbose
        self.verbose = normalize_verbose(config.get("general.verbose", 1))
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
        # Delete and recreate output directory if overwrite=True and it exists
        if self.overwrite and self.output_dir.exists():
            # Delete the directory completely (including workflow.log for fresh start)
            shutil.rmtree(self.output_dir)
            self.logger.info(f"System: deleted existing output directory - {self.output_dir}")
            
            # Recreate directory
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"System: starting fresh with new workflow.log")
        else:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize step counter and function storage
        self._step_counter = 0
        self._functions = {}
        
        # Set logs directory path and state file location, but don't create until needed
        self._logs_dir = self.output_dir / "logs"
        self.state_file = self._logs_dir / "pipeline_state.json"
        self.state = self._load_state()
        
        # Log pipeline initialization
        self.logger.info(f"System: pipeline initialized - {self.output_dir}")
    
    @property 
    def logs_dir(self) -> Path:
        """Get logs directory, creating it if it doesn't exist."""
        if not self._logs_dir.exists():
            self._logs_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"System: created logs directory - {self._logs_dir}")
        return self._logs_dir
    
    def _load_state(self) -> Dict[str, Any]:
        """Load pipeline state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"System: failed to load pipeline state - {e}")
        
        return {
            "steps": {},
            "current_step": None,
            "overall_state": PipelineState.PENDING.name,
            "start_time": None,
            "end_time": None
        }
    
    def _convert_paths_to_strings(self, obj):
        """Recursively convert Path objects to strings for JSON serialization."""
        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_paths_to_strings(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_paths_to_strings(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_paths_to_strings(item) for item in obj)
        else:
            return obj

    def _save_state(self) -> None:
        """Save pipeline state to file."""
        try:
            # Use the logs_dir property to ensure directory exists before saving
            logs_directory = self.logs_dir  # This will create the directory if needed
            
            # Convert any Path objects to strings before serialization
            serializable_state = self._convert_paths_to_strings(self.state)
            with open(self.state_file, 'w') as f:
                json.dump(serializable_state, f, indent=2)
        except Exception as e:
            self.logger.warning(f"System: failed to save pipeline state - {e}")
    
    def add_step(
        self,
        name: str,
        func: Callable,
        inputs: Optional[Dict[str, str]] = {},
        # dependencies: Optional[List[str]] = None,
        auto_number: bool = True
    ) -> str:
        """Add a step to the pipeline.
        
        Args:
            name: Step name (will be prefixed with number if auto_number=True)
            func: Step function
            inputs: Input file paths
            # dependencies: Step dependencies
            auto_number: Whether to automatically number the step
            
        Returns:
            The actual step name (with number prefix if auto_number=True)
        """
        # Auto-number the step if requested
        if auto_number:
            self._step_counter += 1
            numbered_name = f"{self._step_counter:02d}_{name}"
        else:
            numbered_name = name
        
        # Store the function reference
        self._functions[numbered_name] = func
        
        self.state["steps"][numbered_name] = {
            "func_name": func.__name__,
            "inputs": inputs,
            # "dependencies": dependencies or [],
            "result": None
        }
        self._save_state()
        
        # Log step addition
        self.logger.info(f"Workflow: added step - {numbered_name} (function: {func.__name__})")
        self.logger.debug(f"Data: step inputs - {inputs}")
        # if dependencies:
        #     self.logger.debug(f"Step dependencies: {dependencies}")
        
        return numbered_name
    
    def run_step(self, name: str, **kwargs) -> StepResult:
        """Run a pipeline step.
        
        Args:
            name: Step name
            **kwargs: Additional step arguments (will override inputs from add_step)
            
        Returns:
            Step result
        """
        if name not in self.state["steps"]:
            raise ValueError(f"Step not found: {name}")
        
        step = self.state["steps"][name]
        
        # # Check dependencies
        # for dep in step["dependencies"]:
        #     if dep not in self.state["steps"]:
        #         raise ValueError(f"Dependency not found: {dep}")
        #     dep_result = self.state["steps"][dep]["result"]
        #     if not dep_result or dep_result["state"] != PipelineState.COMPLETED.name:
        #         raise ValueError(f"Dependency not completed: {dep}")
        
        # # Check if step is already completed
        # if step["result"] and step["result"]["state"] == PipelineState.COMPLETED.name:
        #     self.logger.info(f"Step {name} already completed, using cached result")
        #     return StepResult(**step["result"])
        
        # Setup step-specific logging with configured log level
        # Get log level from config or use logger's level
        # Get log_level from config (will be derived from verbose if not explicitly set)
        config_log_level = self.config.get_log_level()
        if isinstance(config_log_level, str):
            config_log_level = getattr(logging, config_log_level.upper())
        else:
            config_log_level = self.logger.level if self.logger.level != logging.NOTSET else logging.INFO
            
        step_logger = setup_step_logging(self.logs_dir, name, level=config_log_level)
        
        # Prepare function arguments by merging inputs from add_step with run_step kwargs
        # Start with inputs from add_step, then override/add with kwargs
        func_args = dict(step["inputs"])  # Base arguments from add_step
        func_args.update(kwargs)  # Override/add with run_step arguments
        
        # Log step start
        log_step_start(step_logger, name, func_args)
        
        # Run step
        self.logger.info(f"Step: running step - {name}")
        step_logger.info(f"Step: starting step execution")
        
        self.state["current_step"] = name
        self.state["steps"][name]["result"] = {
            "state": PipelineState.RUNNING.name,
            "start_time": time.time()
        }
        self._save_state()
        
        try:
            # Create working directory for this step
            self.step_working_dir = os.path.join(self.output_dir, name)
            os.makedirs(self.step_working_dir, exist_ok=True)
            step_logger.info(f"System: working directory - {self.step_working_dir}")
            
            # Add working directory to func_args if not already present
            if 'working_dir' not in func_args:
                func_args['working_dir'] = str(self.step_working_dir)
            if 'logger' not in func_args:
                func_args['logger'] = step_logger  # Use step-specific logger
            
            # Execute step
            func = self._functions[name]
            step_logger.info(f"Step: executing function - {func.__name__}")
            step_logger.debug(f"Data: function arguments - {func_args}")
            
            result = func(**func_args)
            step_logger.info(f"Step: function execution completed")
            step_logger.debug(f"Data: function result - {result}")
            
            # Update state
            step["result"] = {
                "state": PipelineState.COMPLETED.name,
                "output_files": result,
                "start_time": self.state["steps"][name]["result"]["start_time"],
                "end_time": time.time()
            }
            self._save_state()
            
            # Log step completion
            duration = step["result"]["end_time"] - step["result"]["start_time"]
            log_step_end(step_logger, name, True, result, duration)
            
            return StepResult(**step["result"])
            
        except Exception as e:
            # Update state
            step["result"] = {
                "state": PipelineState.FAILED.name,
                "error": str(e),
                "start_time": self.state["steps"][name]["result"]["start_time"],
                "end_time": time.time()
            }
            self._save_state()
            
            # Log step failure
            duration = step["result"]["end_time"] - step["result"]["start_time"]
            log_step_end(step_logger, name, False, None, duration)
            step_logger.error(f"Step: step failed with error - {str(e)}")
            
            self.logger.error(f"Step: step {name} failed - {str(e)}")
            raise
    
    def run(self) -> Dict[str, StepResult]:
        """Run the pipeline.
        
        
        Returns:
            Dictionary of step results
        """
        self.logger.info("Workflow: starting pipeline execution")
        self.state["start_time"] = time.time()
        self.state["overall_state"] = PipelineState.RUNNING.name
        self._save_state()
        
        results = {}
        try:
            for name in self.state["steps"]:
                results[name] = self.run_step(name)
            
            self.state["overall_state"] = PipelineState.COMPLETED.name
            self.logger.info("Workflow: ✓ pipeline execution completed successfully")
            
        except Exception as e:
            self.state["overall_state"] = PipelineState.FAILED.name
            self.logger.error(f"Workflow: ✗ pipeline failed - {str(e)}")
            raise
        
        finally:
            self.state["end_time"] = time.time()
            self._save_state()
            
            # Log final pipeline status
            duration = self.state["end_time"] - self.state["start_time"]
            if self.state["overall_state"] == PipelineState.COMPLETED.name:
                self.logger.info(f"Workflow: ✓ pipeline completed successfully in {duration:.2f} seconds")
            else:
                self.logger.error(f"Workflow: ✗ pipeline failed after {duration:.2f} seconds")
        
        return results
    
    def cleanup(self) -> None:
        """Clean up pipeline state and temporary files."""
        self.logger.info("System: starting pipeline cleanup")
        
        # Track what was cleaned up
        cleaned_files = []
        cleaned_dirs = []
        errors = []
        
        try:
            # Clean up temporary files in each step directory
            for step_name in self.state["steps"].keys():
                step_dir = self.output_dir / step_name
                if step_dir.exists():
                    temp_patterns = [
                        "*.tmp", "*.temp", "*_temp.*", "*_tmp.*",
                        "*.mat.txt", "*.nii.gz.mat", 
                        "mcflirt_*", "*_mcf_*",
                        "*.par", "*.rms", "*.dat"
                    ]
                    
                    for pattern in temp_patterns:
                        temp_files = list(step_dir.glob(pattern))
                        for temp_file in temp_files:
                            try:
                                if temp_file.is_file():
                                    temp_file.unlink()
                                    cleaned_files.append(str(temp_file))
                                elif temp_file.is_dir():
                                    import shutil
                                    shutil.rmtree(temp_file)
                                    cleaned_dirs.append(str(temp_file))
                            except Exception as e:
                                errors.append(f"Failed to remove {temp_file}: {e}")
            
            # Clean up working directory temporary files
            working_dir = self.output_dir / "working"
            if working_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(working_dir)
                    cleaned_dirs.append(str(working_dir))
                except Exception as e:
                    errors.append(f"Failed to remove working directory: {e}")
            
            # Clean up cache files
            cache_files = list(self.output_dir.glob("*.cache"))
            for cache_file in cache_files:
                try:
                    cache_file.unlink()
                    cleaned_files.append(str(cache_file))
                except Exception as e:
                    errors.append(f"Failed to remove cache file {cache_file}: {e}")
            
            # For failed pipelines, optionally clean up incomplete outputs
            if self.state["overall_state"] == PipelineState.FAILED.name:
                self.logger.info("System: cleaning up failed pipeline outputs")
                
                # Find failed steps and clean their outputs
                for step_name, step_data in self.state["steps"].items():
                    if (step_data.get("result") and 
                        step_data["result"]["state"] == PipelineState.FAILED.name):
                        
                        step_dir = self.output_dir / step_name
                        if step_dir.exists():
                            try:
                                import shutil
                                shutil.rmtree(step_dir)
                                cleaned_dirs.append(str(step_dir))
                                self.logger.info(f"System: removed failed step directory - {step_dir}")
                            except Exception as e:
                                errors.append(f"Failed to remove failed step directory {step_dir}: {e}")
            
            # Log cleanup results
            if cleaned_files:
                self.logger.info(f"System: cleaned up {len(cleaned_files)} temporary files")
                self.logger.debug(f"Data: cleaned files - {cleaned_files}")
            
            if cleaned_dirs:
                self.logger.info(f"System: cleaned up {len(cleaned_dirs)} temporary directories")
                self.logger.debug(f"Data: cleaned directories - {cleaned_dirs}")
            
            if errors:
                self.logger.warning(f"System: encountered {len(errors)} errors during cleanup")
                for error in errors:
                    self.logger.warning(f"System:   {error}")
            
            if not cleaned_files and not cleaned_dirs:
                self.logger.info("System: no temporary files found to clean up")
            else:
                self.logger.info("System: pipeline cleanup completed successfully")
        
        except Exception as e:
            self.logger.error(f"System: pipeline cleanup failed - {e}")
            raise
    
    def get_progress(self) -> Dict[str, Any]:
        """Get pipeline progress.
        
        Returns:
            Dictionary containing progress information
        """
        total_steps = len(self.state["steps"])
        completed_steps = sum(
            1 for step in self.state["steps"].values()
            if step["result"] and step["result"]["state"] == PipelineState.COMPLETED.name
        )
        
        return {
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "progress_percentage": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
            "current_step": self.state["current_step"],
            "overall_state": self.state["overall_state"]
        }