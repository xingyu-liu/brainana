"""
Base workflow class for macacaMRIprep preprocessing pipelines.

This module provides the foundation for all preprocessing workflows,
including configuration management, logging setup, and pipeline orchestration.
"""

import os
import time
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Union
from abc import ABC, abstractmethod

from ..config import Config, load_config, validate_config
from ..config.config_validation import validate_paths
from ..operations.pipeline import Pipeline
from ..utils import setup_logging, setup_workflow_logging, ensure_workflow_log_exists, get_logger
from ..environment import check_dependencies, check_environment

class BasePreprocessingWorkflow(ABC):
    """Base class for all preprocessing workflows.
    
    This class provides common functionality for all workflows including:
    - Configuration loading and validation
    - Logging setup and management
    - Pipeline initialization
    - Environment checking
    - Resource monitoring
    """
    
    def __init__(
        self,
        output_dir: Union[str, Path],
        working_dir: Optional[Union[str, Path]] = None,
        config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize base workflow.
        
        Args:
            output_dir: Output directory for results
            config: Configuration file path or dictionary
            verbose: Verbosity level (0=quiet, 1=normal, 2=verbose)
            logger: Optional logger instance
            overwrite: Whether to overwrite existing output directory
            
        Raises:
            ValueError: If configuration is invalid
            FileNotFoundError: If config file doesn't exist
            PermissionError: If output directory cannot be created
        """
        # Setup paths
        self.output_dir = Path(output_dir).absolute()
        self.output_dir.mkdir(parents=True, exist_ok=True)
            
        if working_dir is not None:
            self.working_dir = Path(working_dir).absolute()
        else:
            self.working_dir = Path(output_dir).absolute() / 'working_dir'
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup basic logger first (needed for config loading)
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger(self.__class__.__name__)
        
        # Load and validate configuration
        self.config = self._load_and_validate_config(config)
        
        # Extract verbose and overwrite from validated config
        # Normalize verbose to integer (0, 1, or 2) for consistency
        from ..utils.logger import normalize_verbose
        self.verbose = normalize_verbose(self.config.get("general.verbose", 1))
        self.overwrite = self.config.get("general.overwrite")

        # Setup proper logging with configured level
        self._setup_logging(self.config.get_log_level(), self.logger)
        
        # Initialize pipeline
        self.pipeline = Pipeline(
            name=self.__class__.__name__,
            output_dir=self.working_dir,
            config=self.config,
            logger=self.logger,
        )
        
        # Setup workflow logging - create workflow.log file
        # Use configured log level from config
        log_level = self.config.get_log_level()
        self.workflow_logger = setup_workflow_logging(
            workflow_dir=self.working_dir,
            workflow_name=self.__class__.__name__,
            level=log_level
        )
        
        # Also add workflow.log handler to main logger so all messages go there
        workflow_log_file = os.path.join(self.working_dir, "workflow.log")
        try:
            workflow_file_handler = logging.FileHandler(workflow_log_file)
            workflow_file_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            workflow_file_handler.setLevel(log_level)
            
            # Ensure main logger level allows the messages to reach the file handler
            # NOTSET (0) means inherit from parent, but we need explicit level for file logging
            if self.logger.level == logging.NOTSET or self.logger.level > log_level:
                self.logger.setLevel(log_level)
                
            self.logger.addHandler(workflow_file_handler)
        except Exception as e:
            self.logger.warning(f"System: failed to add workflow.log handler - {e}")
        
        # Initialize state
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._resource_monitor = ResourceMonitor()
        
        # Log workflow initialization
        self.logger.info(f"Workflow: {self.__class__.__name__} initialized")
        self.logger.info(f"System: output directory - {os.path.basename(self.working_dir)}")
        self.logger.info(f"System: overwrite mode - {self.overwrite}")
        
    def _setup_logging(self, log_level: Union[str, int], logger: Optional[logging.Logger]) -> None:
        """Setup logging for the workflow.
        
        Args:
            log_level: Logging level (string like 'INFO', 'DEBUG', or logging constant)
            logger: Optional existing logger
        """
        if logger is not None:
            self.logger = logger
        else:
            # Convert string level to int if needed
            if isinstance(log_level, str):
                level = getattr(logging, log_level.upper())
            else:
                level = log_level
            
            # Setup logging
            setup_logging(level=level)
            self.logger = get_logger(self.__class__.__name__)
        
        # Note: self.verbose is already set and normalized in __init__, don't overwrite it here
        
    def _load_and_validate_config(
        self, 
        config: Optional[Union[str, Path, Dict[str, Any], Config]]
    ) -> Config:
        """Load and validate configuration.
        
        Args:
            config: Configuration source (file path, dictionary, or Config object)
            
        Returns:
            Validated Config object
            
        Raises:
            ValueError: If configuration is invalid
        """
        from ..config import Config
        
        try:
            if config is None:
                # Use default configuration
                config_obj = Config()
            elif isinstance(config, Config):
                # Already a Config object, just use it
                config_obj = config
                self.logger.info("Config: using provided Config object")
            elif isinstance(config, (str, Path)):
                # Load from file
                config_obj = Config(config)
                self.logger.info(f"Config: loaded from {os.path.basename(config)}")
            elif isinstance(config, dict):
                # Use provided dictionary
                config_obj = Config(config)
            else:
                raise ValueError(f"Invalid config type: {type(config)}")
            
            self.logger.info("Config: validation completed")
            if config_obj.get("general.verbose") >= 2:
                self.logger.debug(f"Config: {len(config_obj.to_dict())} parameters loaded")
            
            return config_obj
            
        except Exception as e:
            self.logger.error(f"Config: loading failed - {e}")
            raise
    
    def check_dependencies(self) -> None:
        """Check system dependencies and environment."""
        self.logger.info("Checking dependencies and environment...")
        
        try:
            # Check Python dependencies
            check_dependencies()
            
            # Check external tools and environment variables
            # Check if skull stripping is enabled for any modality
            skullstripping_enabled = (
                        self.config.get("func.skullstripping.enabled", False) or
        self.config.get("anat.skullstripping.enabled", False)
            )
            check_environment()
            
            self.logger.info("✓ Dependencies and environment check completed")
            
        except Exception as e:
            self.logger.error(f"Dependency/environment check failed: {e}")
            raise
    
    def validate_inputs(self, **kwargs) -> None:
        """Validate input files and parameters.
        
        This method should be overridden by subclasses to validate
        their specific input requirements.
        
        Args:
            **kwargs: Input parameters to validate
            
        Raises:
            ValueError: If inputs are invalid
            FileNotFoundError: If required files don't exist
        """
        # Base implementation - subclasses should override
        pass
    
    def pre_run_checks(self) -> None:
        """Perform pre-run validation and setup.
        
        This includes dependency checking, input validation,
        and any other setup required before running the pipeline.
        """
        self.logger.info("Performing pre-run checks...")
        
        # Check dependencies
        self.check_dependencies()
        
        # Validate inputs (implemented by subclasses)
        self.validate_inputs()
        
        # Check available disk space
        self._check_disk_space()
        
        # Start resource monitoring
        self._resource_monitor.start()
        
        self.logger.info("✓ Pre-run checks completed")
    
    def _check_disk_space(self, min_gb: float = 5.0) -> None:
        """Check available disk space in output directory.
        
        Args:
            min_gb: Minimum required disk space in GB
            
        Raises:
            RuntimeError: If insufficient disk space
        """
        try:
            total, used, free = shutil.disk_usage(self.working_dir.parent)
            free_gb = free / (1024**3)
            
            if free_gb < min_gb:
                raise RuntimeError(
                    f"Insufficient disk space: {free_gb:.1f} GB available, "
                    f"{min_gb:.1f} GB required"
                )
            
            self.logger.info(f"Disk space available: {free_gb:.1f} GB")
            
        except Exception as e:
            self.logger.warning(f"Could not check disk space: {e}")
    
    @abstractmethod
    def run(self) -> Dict[str, Any]:
        """Run the preprocessing workflow.
        
        This method must be implemented by subclasses to define
        their specific preprocessing steps.
        
        Returns:
            Dictionary containing workflow results
        """
        pass
    
    def cleanup(self, remove_intermediates: bool = False) -> None:
        """Clean up temporary files and resources.
        
        Args:
            remove_intermediates: Whether to remove intermediate files
        """
        self.logger.info("Starting workflow cleanup...")
        
        try:
            # Clean up pipeline
            self.pipeline.cleanup()
            
            # Stop resource monitoring
            self._resource_monitor.stop()
            
            # Remove intermediate files if requested
            if remove_intermediates:
                self._remove_intermediate_files()
            
            self.logger.info("✓ Workflow cleanup completed")
            
        except Exception as e:
            self.logger.warning(f"Cleanup failed: {e}")
    
    def _remove_intermediate_files(self) -> None:
        """Remove intermediate processing files to save space."""
        self.logger.info("Removing intermediate files...")
        
        # Define patterns for intermediate files to remove
        patterns_to_remove = [
            "**/func_mc_ref.nii.gz",
            "**/func_tmean.nii.gz", 
            "**/*_temp.nii.gz",
            "**/*.mat",
            "**/*.par",
            "**/*.rms"
        ]
        
        removed_count = 0
        for pattern in patterns_to_remove:
            for file_path in self.working_dir.glob(pattern):
                try:
                    file_path.unlink()
                    removed_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not remove {file_path}: {e}")
        
        self.logger.info(f"Removed {removed_count} intermediate files")
    
    def get_progress(self) -> Dict[str, Any]:
        """Get workflow progress information.
        
        Returns:
            Dictionary with progress information
        """
        pipeline_progress = self.pipeline.get_progress()
        
        # Add workflow-specific information
        progress = {
            "workflow_name": self.__class__.__name__,
            "output_dir": str(self.working_dir),
            "start_time": self._start_time,
            "current_time": time.time(),
            "elapsed_time": time.time() - self._start_time if self._start_time else None,
            **pipeline_progress
        }
        
        # Add resource usage if available
        if self._resource_monitor.is_running():
            progress["resource_usage"] = self._resource_monitor.get_current_usage()
        
        return progress
    
    def get_summary(self) -> Dict[str, Any]:
        """Get workflow execution summary.
        
        Returns:
            Dictionary with execution summary
        """
        progress = self.get_progress()
        
        summary = {
            "workflow": self.__class__.__name__,
            "status": progress["overall_state"],
            "steps_completed": f"{progress['completed_steps']}/{progress['total_steps']}",
            "output_directory": str(self.working_dir),
            "configuration": self.config.to_dict(),
        }
        
        if self._start_time and self._end_time:
            summary["total_duration"] = self._end_time - self._start_time
        elif self._start_time:
            summary["elapsed_time"] = time.time() - self._start_time
        
        return summary
    
    def __enter__(self):
        """Context manager entry."""
        self._start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self._end_time = time.time()
        
        # Cleanup resources
        try:
            self.cleanup()
        except Exception as e:
            self.logger.warning(f"Cleanup during exit failed: {e}")
        
        # Log final status
        if exc_type is None:
            duration = self._end_time - self._start_time
            self.logger.info(f"Workflow completed successfully in {duration:.2f} seconds")
        else:
            self.logger.error(f"Workflow failed with {exc_type.__name__}: {exc_val}")


class ResourceMonitor:
    """Monitor system resource usage during workflow execution."""
    
    def __init__(self):
        """Initialize resource monitor."""
        self.running = False
        self.start_time: Optional[float] = None
        self.peak_memory: float = 0.0
        self.peak_cpu: float = 0.0
        
    def start(self) -> None:
        """Start monitoring resources."""
        self.running = True
        self.start_time = time.time()
        
        # Try to get initial resource usage
        try:
            import psutil
            process = psutil.Process()
            self.initial_memory = process.memory_info().rss / (1024**2)  # MB
            self.peak_memory = self.initial_memory
        except ImportError:
            # psutil not available, disable monitoring
            self.running = False
    
    def stop(self) -> None:
        """Stop monitoring resources."""
        self.running = False
    
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self.running
    
    def get_current_usage(self) -> Dict[str, Any]:
        """Get current resource usage.
        
        Returns:
            Dictionary with current resource usage
        """
        if not self.running:
            return {"status": "monitoring_disabled"}
        
        try:
            import psutil
            process = psutil.Process()
            
            # Memory usage
            memory_mb = process.memory_info().rss / (1024**2)
            self.peak_memory = max(self.peak_memory, memory_mb)
            
            # CPU usage
            cpu_percent = process.cpu_percent()
            self.peak_cpu = max(self.peak_cpu, cpu_percent)
            
            # Disk usage
            disk_usage = psutil.disk_usage('/')
            
            return {
                "current_memory_mb": memory_mb,
                "peak_memory_mb": self.peak_memory,
                "current_cpu_percent": cpu_percent,
                "peak_cpu_percent": self.peak_cpu,
                "disk_free_gb": disk_usage.free / (1024**3),
                "monitoring_duration": time.time() - self.start_time if self.start_time else 0
            }
            
        except Exception as e:
            return {"status": "monitoring_error", "error": str(e)}