"""
Command-line interface for preprocessing neuroimaging data.
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import json

from ..workflow.bids_processor import BIDSDatasetProcessor
from ..utils import get_logger, setup_logging, resolve_template, list_available_templates, validate_template_spec, print_available_templates
from ..config import load_config, validate_config
from ..config.config_validation import validate_paths
from ..environment import check_environment, check_dependencies
from ..quality_control import generate_qc_report

# Get logger for this module
logger = get_logger(__name__)

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Preprocess macaque neuroimaging data using BIDS datasets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process entire BIDS dataset (default: func2anat2template pipeline)
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1
  
  # Process specific subjects
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 --subjects 032100 032097
  
  # Anatomical processing only
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 --pipeline anat2template
  
  # Functional direct to template (no anatomical intermediary)
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 --pipeline func2template
  
  # Process with parallel processing
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 --n-procs 4
  
  # Process specific sessions and tasks
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 --sessions 001 --tasks resting
  
  # Custom configuration and working directory
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 -c config.json -w /tmp/work
  
  # Enable skullstripping and disable despiking
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 --skullstripping --no-despike
  
  # List available templates
  macacaMRIprep-preproc --list-templates
  
  # Generate QC report from existing outputs (no preprocessing)
  macacaMRIprep-preproc /path/to/bids /path/to/output --report-only
  
  # Force rerun all jobs, ignoring cache and previous outputs
  macacaMRIprep-preproc /path/to/bids /path/to/output --output-space NMT2Sym:res-1 --overwrite
        """
    )
    
    # Required positional arguments (except for utility commands)
    parser.add_argument(
        "dataset_dir",
        nargs="?",
        help="Path to BIDS dataset root directory (required unless using --list-templates)"
    )
    parser.add_argument(
        "output_dir", 
        nargs="?",
        help="Path to output derivatives directory (required unless using --list-templates)"
    )
    
    # Template specification
    parser.add_argument(
        "--output-space",
        help="Output template space specification (e.g., 'NMT2Sym:res-1' or 'NMT2Sym:res-1:brainWoCerebellumBrainstem'). "
             "Format: TEMPLATE_NAME:RESOLUTION[:DESCRIPTION]. Resolution is required. "
             "Use --list-templates to see available options. "
             "(required unless using --report-only or --list-templates)"
    )
    # Pipeline selection
    parser.add_argument(
        "--pipeline",
        choices=["func2anat2template", "anat2template", "func2template"],
        help="Processing pipeline to use: func2anat2template (default), anat2template, func2template. Overrides config func.registration_pipeline."
    )
    
    # BIDS entity filtering
    bids_group = parser.add_argument_group("BIDS entity filtering")
    bids_group.add_argument(
        "--subjects", "--participant-label",
        nargs="+",
        help="List of subject identifiers to process (e.g., 032100 032097)"
    )
    bids_group.add_argument(
        "--sessions",
        nargs="+", 
        help="List of session identifiers to process (e.g., 001 002)"
    )
    bids_group.add_argument(
        "--tasks",
        nargs="+",
        help="List of task names to process (e.g., resting auditory)"
    )
    bids_group.add_argument(
        "--runs",
        nargs="+",
        help="List of run numbers to process (e.g., 01 02)"
    )
    
    # Processing mode options
    proc_group = parser.add_argument_group("Processing mode")
    proc_group.add_argument(
        "--anat-only",
        action="store_true",
        help="Process anatomical data only"
    )
    proc_group.add_argument(
        "--func-only", 
        action="store_true",
        help="Process functional data only (requires anatomical dependencies)"
    )
    proc_group.add_argument(
        "--n-procs",
        type=int,
        default=1,
        help="Number of parallel processes to use (default: 1)"
    )
    
    # Configuration and working directory
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "--config", "-c",
        help="Configuration file (JSON format)"
    )
    config_group.add_argument(
        "--working-dir", "-w",
        help="Working directory for intermediate files (default: <output_dir>/working)"
    )
    
    # Processing options (config overrides)
    process_group = parser.add_argument_group("Processing options (override config)")
    process_group.add_argument(
        "--skullstripping",
        action="store_true",
        help="Enable skullstripping"
    )
    process_group.add_argument(
        "--no-despike",
        action="store_true",
        help="Disable despiking"
    )
    process_group.add_argument(
        "--no-bias-correction",
        action="store_true",
        help="Disable bias field correction"
    )
    process_group.add_argument(
        "--no-registration",
        action="store_true",
        help="Disable registration to template"
    )
    
    # Output options
    output_group = parser.add_argument_group("Output options")
    output_group.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output directory"
    )
    output_group.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Do not overwrite existing output directory"
    )
    
    # Logging options
    log_group = parser.add_argument_group("Logging")
    log_group.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level"
    )
    log_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    log_group.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output (except errors)"
    )
    
    # Development options
    dev_group = parser.add_argument_group("Development")
    dev_group.add_argument(
        "--check-only",
        action="store_true",
        help="Only check dependencies and configuration, don't run processing"
    )
    dev_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually running"
    )
    dev_group.add_argument(
        "--report-only",
        action="store_true",
        help="Generate QC report only from existing outputs (no preprocessing)"
    )
    dev_group.add_argument(
        "--list-templates",
        action="store_true",
        help="List available template spaces and exit"
    )
    
    # Caching and resumption options
    cache_group = parser.add_argument_group("Caching and resumption")
    cache_group.add_argument(
        "--no-check-outputs",
        action="store_true",
        help="Don't verify output files exist when checking completion (faster but less reliable)"
    )
    
    return parser.parse_args()

def load_and_merge_config(args: argparse.Namespace) -> Dict[str, Any]:
    """Load configuration from file and merge with command line arguments."""
    # Load base configuration
    if args.config:
        config = load_config(args.config)
        logger.info(f"Config: loaded configuration from - {args.config}")
    else:
        from ..config import get_config
        config = get_config().to_dict()
        logger.info("Config: using default configuration")
    
    # Override with command line arguments
    config_overrides = {}
    
    # General settings
    if args.working_dir:
        config_overrides.setdefault("general", {})["working_dir"] = args.working_dir
    
    # Handle verbose flag - normalize to integer (0, 1, or 2)
    from ..utils.logger import normalize_verbose
    
    if args.verbose:
        config_overrides.setdefault("general", {})["verbose"] = 1  # --verbose sets to 1
        # log_level will be automatically derived from verbose
    
    if args.quiet:
        config_overrides.setdefault("general", {})["verbose"] = 0  # --quiet sets to 0
        # log_level will be automatically derived from verbose
    
    if args.n_procs:
        config_overrides.setdefault("general", {})["n_procs"] = args.n_procs
    
    # Pipeline selection
    if args.pipeline:
        config_overrides.setdefault("func", {})["registration_pipeline"] = args.pipeline
    
    # Processing mode - determine based on pipeline first, then apply overrides
    registration_pipeline = args.pipeline or config.get("func", {}).get("registration_pipeline", "func2anat2template")
    
    # Set defaults based on pipeline
    config_overrides.setdefault("general", {})["anat_only"] = False
    config_overrides.setdefault("general", {})["func_only"] = False
    
    if registration_pipeline == "func2template":
        # func2template: functional only (direct to template, no anatomical processing needed)
        config_overrides.setdefault("general", {})["run_anat"] = False
        config_overrides.setdefault("general", {})["run_func"] = True
    elif registration_pipeline == "anat2template":
        # anat2template: anatomical only
        config_overrides.setdefault("general", {})["run_anat"] = True
        config_overrides.setdefault("general", {})["run_func"] = False
    elif registration_pipeline == "func2anat2template":
        # func2anat2template: both anatomical and functional
        config_overrides.setdefault("general", {})["run_anat"] = True
        config_overrides.setdefault("general", {})["run_func"] = True
    
    # Apply overrides after pipeline logic
    if args.anat_only:
        # Override: anatomical only regardless of pipeline
        config_overrides.setdefault("general", {})["anat_only"] = True
        config_overrides.setdefault("general", {})["func_only"] = False
        config_overrides.setdefault("general", {})["run_anat"] = True
        config_overrides.setdefault("general", {})["run_func"] = False
    elif args.func_only:
        # Override: functional only regardless of pipeline
        config_overrides.setdefault("general", {})["anat_only"] = False
        config_overrides.setdefault("general", {})["func_only"] = True
        config_overrides.setdefault("general", {})["run_anat"] = False
        config_overrides.setdefault("general", {})["run_func"] = True
    
    # BIDS entity filtering
    if args.subjects:
        config_overrides.setdefault("bids_filtering", {})["subjects"] = args.subjects
    
    if args.sessions:
        config_overrides.setdefault("bids_filtering", {})["sessions"] = args.sessions
    
    if args.tasks:
        config_overrides.setdefault("bids_filtering", {})["tasks"] = args.tasks
    
    if args.runs:
        config_overrides.setdefault("bids_filtering", {})["runs"] = args.runs
    
    # Template space
    if args.output_space:
        config_overrides.setdefault("template", {})["output_space"] = args.output_space
    
    # Processing options
    if args.skullstripping:
        config_overrides.setdefault("func", {}).setdefault("skullstripping", {})["enabled"] = True
        config_overrides.setdefault("anat", {}).setdefault("skullstripping", {})["enabled"] = True
    
    if args.no_despike:
        config_overrides.setdefault("func", {}).setdefault("despike", {})["enabled"] = False
    
    if args.no_bias_correction:
        config_overrides.setdefault("func", {}).setdefault("bias_correction", {})["enabled"] = False
        config_overrides.setdefault("anat", {}).setdefault("bias_correction", {})["enabled"] = False
    
    if args.no_registration:
        config_overrides.setdefault("registration", {})["enabled"] = False
    
    # Output options
    if args.overwrite:
        config_overrides.setdefault("general", {})["overwrite"] = True
    elif args.no_overwrite:
        config_overrides.setdefault("general", {})["overwrite"] = False
    
    # Caching and resumption options
    if args.no_check_outputs:
        config_overrides.setdefault("caching", {})["check_outputs"] = False
    
    # Merge overrides into config
    def deep_merge(base_dict, override_dict):
        for key, value in override_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                deep_merge(base_dict[key], value)
            else:
                base_dict[key] = value
    
    deep_merge(config, config_overrides)
    
    return config

def validate_arguments(args: argparse.Namespace, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
    """Validate command line arguments and resolve template path."""
    
    # Skip validation for utility commands
    if args.list_templates:
        return None, None
    
    # Log received arguments for debugging
        logger.debug(f"Data: received arguments - dataset_dir '{args.dataset_dir}', output_dir '{args.output_dir}'")
    
    # Check required arguments with better error messages
    if not args.dataset_dir:
        raise ValueError("dataset_dir is required (unless using --list-templates). "
                        "Make sure the first positional argument is a valid BIDS dataset directory path.")
    
    if not args.output_dir:
        raise ValueError("output_dir is required (unless using --list-templates). "
                        "Make sure the second positional argument is a valid output directory path. "
                        "Check that all variables in your command are properly defined (e.g., ${dataset_dir}, ${output_dir}).")
    
    # Validate paths
    dataset_dir = Path(args.dataset_dir).absolute()
    output_dir = Path(args.output_dir).absolute()
    
    if not dataset_dir.exists():
        raise ValueError(f"Dataset directory does not exist: {dataset_dir}. "
                        f"Check that the path is correct and that the ${dataset_dir} variable is properly set.")
    
    if not dataset_dir.is_dir():
        raise ValueError(f"Dataset path is not a directory: {dataset_dir}")
    
    # Check for BIDS dataset structure
    if not args.report_only and not args.check_only and not args.dry_run:
        dataset_description = dataset_dir / "dataset_description.json"
        if not dataset_description.exists():
            logger.warning(f"Data: no dataset_description.json found in {dataset_dir} - assuming BIDS dataset")
    
    # Create output directory if needed
    if not args.dry_run and not args.check_only:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Resolve template unless in report-only mode
    template_path = None
    if not args.report_only and not args.check_only:
        output_space = args.output_space or (config.get("template", {}).get("output_space") if config else None)
        
        if not output_space:
            raise ValueError("output-space is required (unless using --report-only, --check-only, or --list-templates)")
        
        # Handle native space - skip template resolution
        if output_space.lower() == "native":
            template_path = None
        else:
            # Validate and resolve template
            if not validate_template_spec(output_space):
                available_templates = list_available_templates()
                raise ValueError(f"Invalid template specification: {output_space}. "
                               f"Available templates: {available_templates}")
            
            template_path = resolve_template(output_space)
            if not template_path or not Path(template_path).exists():
                raise ValueError(f"Template file not found for: {output_space}")
    
    return template_path, str(output_dir)



def print_configuration(config: Dict[str, Any], args: argparse.Namespace) -> None:
    """Print processing configuration summary."""
    
    print("=" * 60)
    print("macacaMRIprep Configuration Summary")
    print("=" * 60)
    
    # Dataset information
    print(f"Dataset directory: {args.dataset_dir}")
    print(f"Output directory: {args.output_dir}")
    working_dir = config.get("general", {}).get("working_dir")
    if working_dir:
        print(f"Working directory: {working_dir}")
    
    # Template information
    output_space = config.get("template", {}).get("output_space")
    if output_space:
        print(f"Template space: {output_space}")
    registration_pipeline = config.get("func", {}).get("registration_pipeline", "func2anat2template")
    print(f"Pipeline: {registration_pipeline}")
    
    # Processing mode
    general_config = config.get("general", {})
    run_anat = general_config.get("run_anat", True)
    run_func = general_config.get("run_func", True)
    
    if run_anat and run_func:
        print("Processing mode: Full pipeline (anatomical + functional)")
    elif run_anat and not run_func:
        print("Processing mode: Anatomical only")
    elif not run_anat and run_func:
        print("Processing mode: Functional only")
    else:
        print("Processing mode: No processing specified")
    
    # Parallel processing
    n_procs = general_config.get("n_procs", 1)
    if n_procs > 1:
        print(f"Parallel processes: {n_procs}")
        print("Note: Two-phase processing will be used (anatomical first, then functional)")
    
    # BIDS entity filtering
    bids_filtering = config.get("bids_filtering", {})
    if bids_filtering.get("subjects"):
        print(f"Subjects: {', '.join(bids_filtering['subjects'])}")
    if bids_filtering.get("sessions"):
        print(f"Sessions: {', '.join(bids_filtering['sessions'])}")
    if bids_filtering.get("tasks"):
        print(f"Tasks: {', '.join(bids_filtering['tasks'])}")
    if bids_filtering.get("runs"):
        print(f"Runs: {', '.join(bids_filtering['runs'])}")
    
    # Key processing options
    print("\nKey processing options:")
    
    anat_config = config.get("anat", {})
    func_config = config.get("func", {})
    reg_config = config.get("registration", {})
    
    # Anatomical
    if anat_config.get("skullstripping", {}).get("enabled"):
        print("  ✓ Anatomical skull stripping enabled")
    if anat_config.get("bias_correction", {}).get("enabled"):
        print("  ✓ Anatomical bias correction enabled")
    
    # Functional
    if func_config.get("slice_timing_correction", {}).get("enabled"):
        print("  ✓ Slice timing correction enabled")
    if func_config.get("motion_correction", {}).get("enabled"):
        print("  ✓ Motion correction enabled")
    if func_config.get("despike", {}).get("enabled"):
        print("  ✓ Despiking enabled")
    if func_config.get("skullstripping", {}).get("enabled"):
        print("  ✓ Functional skull stripping enabled")
    if func_config.get("bias_correction", {}).get("enabled"):
        print("  ✓ Functional bias correction enabled")
    
    # Registration
    if reg_config.get("enabled"):
        print("  ✓ Registration to template enabled")
        func2template_xfm_type = reg_config.get("func2template_xfm_type", "syn")
        anat2template_xfm_type = reg_config.get("anat2template_xfm_type", "syn")
        func2anat_xfm_type = reg_config.get("func2anat_xfm_type", "syn")
        print(f"    - Functional registration type: {func2template_xfm_type}")
        print(f"    - Anatomical registration type: {anat2template_xfm_type}")
        print(f"    - Functional to anatomical registration type: {func2anat_xfm_type}")
    
    print("=" * 60)

def main() -> None:
    """Main entry point."""
    try:
        # Parse arguments
        args = parse_args()
        
        # Handle --list-templates before setting up logging
        if args.list_templates:
            print_available_templates()
            return
        
        # Setup initial logging
        # Derive log_level from verbose/quiet flags or use explicit --log-level
        if args.verbose:
            log_level = "DEBUG"
        elif args.quiet:
            log_level = "ERROR"
        else:
            log_level = args.log_level
        setup_logging(level=getattr(logging, log_level))
        
        logger.info("Workflow: starting macacaMRIprep BIDS dataset processing")
        
        # Load and merge configuration first
        config = load_and_merge_config(args)
        
        # Validate arguments and resolve template
        template_path, output_dir = validate_arguments(args, config)
        
        # Get processing mode from config
        run_anat = config.get("general", {}).get("run_anat", True)
        run_func = config.get("general", {}).get("run_func", True)
        
        if args.dataset_dir:
            logger.info(f"Data: dataset directory - {args.dataset_dir}")
        if output_dir:
            logger.info(f"Data: output directory - {output_dir}")
        if template_path:
            output_space = args.output_space or config.get("template", {}).get("output_space")
            logger.info(f"Config: template - {output_space} -> {template_path}")
        
        # Handle report-only mode
        if args.report_only:
            logger.info("Workflow: report-only mode - generating QC reports from existing outputs")
            
            if not Path(output_dir).exists():
                raise ValueError(f"Output directory does not exist: {output_dir}")
            
            try:
                # Create processor for report generation
                processor = BIDSDatasetProcessor(
                    dataset_dir=args.dataset_dir,
                    output_dir=output_dir,
                    working_dir=args.working_dir,
                    config=config,
                    logger=logger
                )
                
                # Discover jobs for report generation
                bids_filtering = config.get("bids_filtering", {})
                jobs = processor.discover_processing_jobs(
                    subs=bids_filtering.get("subjects"),
                    sess=bids_filtering.get("sessions"),
                    tasks=bids_filtering.get("tasks"),
                    runs=bids_filtering.get("runs")
                )
                
                if not jobs:
                    logger.warning("Data: no processing jobs found for report generation")
                    return
                
                # Generate reports
                processor._generate_subject_reports(jobs)
                
                logger.info("QC: ✓ reports generated successfully")
                return
                
            except Exception as e:
                logger.error(f"QC: failed to generate reports - {str(e)}")
                raise
        
        # Validate configuration
        config = validate_config(config)
        
        # Check dependencies
        logger.info("System: checking dependencies")
        check_dependencies()
        
        # Check environment
        check_environment()
        
        if args.check_only:
            logger.info("System: ✓ dependencies and configuration check completed successfully")
            return
        
        # Print configuration
        print_configuration(config, args)
        
        if args.dry_run:
            logger.info("Workflow: dry run completed - would proceed with BIDS dataset processing using above configuration")
            return
        
        # Initialize and run BIDS dataset processor
        logger.info("System: initializing BIDS dataset processor")
        
        processor = BIDSDatasetProcessor(
            dataset_dir=args.dataset_dir,
            output_dir=output_dir,
            working_dir=args.working_dir,
            config=config,
            logger=logger
        )
        
        # If overwrite is enabled, clear the cache (since we're reprocessing everything)
        if config.get("general", {}).get("overwrite", False):
            logger.info("System: clearing processing cache (overwrite enabled)")
            processor.clear_cache()
            logger.info("System: cache cleared")
        
        logger.info("Workflow: running BIDS dataset processing")
        bids_filtering = config.get("bids_filtering", {})
        results = processor.run_dataset(
            subs=bids_filtering.get("subjects"),
            sess=bids_filtering.get("sessions"),
            tasks=bids_filtering.get("tasks"),
            runs=bids_filtering.get("runs"),
            run_anat=run_anat,
            run_func=run_func,
            n_procs=config.get("general", {}).get("n_procs", 1),
            overwrite=config.get("general", {}).get("overwrite", False),
            check_outputs=config.get("caching", {}).get("check_outputs", True)
        )
        
        # Print results summary
        print("\n" + "=" * 60)
        print("Processing Results Summary")
        print("=" * 60)
        print(f"Status: {results['status']}")
        print(f"Total jobs: {results['total_jobs']}")
        print(f"Completed: {results['completed_jobs']}")
        print(f"Failed: {results['failed_jobs']}")
        if 'skipped_jobs' in results and results['skipped_jobs'] > 0:
            print(f"Skipped (already completed): {results['skipped_jobs']}")
        if 'processed_jobs' in results:
            print(f"Processed this run: {results['processed_jobs']}")
        print(f"Duration: {results['duration_formatted']}")
        print(f"Processing approach: {results['processing_approach']}")
        if results.get('caching_enabled', False):
            print(f"Caching: Enabled")
        
        if results['failed_jobs'] > 0:
            logger.warning(f"Workflow: {results['failed_jobs']} jobs failed")
        else:
            logger.info("Workflow: ✓ all jobs completed successfully")
        
        # Log output locations
        print(f"\nOutputs saved to: {output_dir}")
        print(f"Processing logs: {Path(output_dir) / 'logs'}")
        print(f"Quality control reports: {output_dir}/*.html")
        
    except KeyboardInterrupt:
        logger.error("Workflow: processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Workflow: error during processing - {str(e)}")
        if args.verbose if 'args' in locals() else False:
            import traceback
            logger.error(f"System: traceback - {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main() 