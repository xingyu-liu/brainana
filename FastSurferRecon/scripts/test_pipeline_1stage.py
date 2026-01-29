#!/usr/bin/env python3
"""
Test script for FastSurfer surface reconstruction pipeline with step control.

Runs a single stage only (no preceding stages). Edit RUN_STEP below to choose
which stage to run.
"""

import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastsurfer_recon.config import ReconSurfConfig
from fastsurfer_recon.io.subjects_dir import SubjectsDir
from fastsurfer_recon.utils.logging import setup_logging
from fastsurfer_recon.stages import (
    # Volume stages
    VolumePrep,
    BiasCorrection,
    MaskAseg,
    Talairach,
    NormT1,
    CCSegmentation,
    WMFilled,
    # Surface stages
    Tessellation,
    Smoothing,
    Inflation,
    SphericalProjection,
    TopologyFix,
    WhitePreaparc,
    Parcellation,
    SurfacePlacement,
    ComputeMorphometry,
    Registration,
    Statistics,
    CorticalRibbon,
    AsegRefinement,
    AparcMapping,
    WMParcMapping,
)

# ============================================================================
# Configuration - Edit these variables as needed
# ============================================================================
# RUN_STEPS = [f's{i:02d}' for i in range(1, 8)]
# RUN_STEPS = ['s11']
# RUN_STEPS = ['s14']
RUN_STEPS = [f's{i:02d}' for i in range(16, 23)]

# Test subject
subject_root = Path("/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon")
subject_dir = subject_root / "sub-NMT2Sym"
subjects_dir = subject_dir.parent
subject_id = subject_dir.name

n_threads = 8
parallel_hemis = False

# ============================================================================


# Valid step names
VALID_STEPS = {
    "s01", "s02", "s03", "s04", "s05", "s06", "s07",
    "s08", "s09", "s10", "s11", "s12", "s13", "s14", "s15", "s16", "s17", "s18",
    "s19", "s20", "s21", "s22",
}


def get_stage_number(step: str) -> int:
    """Get numeric stage number from step string (e.g., 's07' -> 7)."""
    if not step.startswith("s"):
        raise ValueError(f"Step must start with 's', got: {step}")
    try:
        return int(step[1:])
    except ValueError:
        raise ValueError(f"Invalid step format: {step}")


def run_single_stage(config: ReconSurfConfig, run_step: str):
    """Run only the specified single stage (no preceding stages)."""
    sd = SubjectsDir(config.subjects_dir, config.subject_id)
    
    # Setup directories
    sd.setup()

    # set hemis
    hemis = ["lh", "rh"]

    # Setup logging
    if config.log_file:
        log_path = config.log_file
    else:
        log_path = sd.log_file
    
    logger = logging.getLogger("fastsurfer_recon")
    file_handler = logging.FileHandler(log_path, mode="a")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
    )
    logger.addHandler(file_handler)
    
    # Write header
    from datetime import datetime
    with open(log_path, "a") as f:
        start_time = datetime.now()
        f.write(f"\n{'='*80}\n")
        f.write(f"FastSurfer Recon Pipeline Log (Single Stage Test)\n")
        f.write(f"Subject: {config.subject_id}\n")
        f.write(f"Run Step: {run_step}\n")
        f.write(f"Start: {start_time}\n")
        f.write(f"{'='*80}\n\n")
    
    # Initialize cmd log file (fastsurfer_recon.cmd)
    cmd_log_path = config.cmd_log_file
    cmd_log_path.parent.mkdir(parents=True, exist_ok=True)
    from fastsurfer_recon.wrappers.base import set_cmd_log_file
    with open(cmd_log_path, "a") as f:
        timestamp = datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y")
        f.write(f"\n\n#---------------------------------\n")
        f.write(f"# New invocation of fastsurfer-recon (single stage) {timestamp} \n")
        f.write(f"# Run Step: {run_step}\n")
        f.write(f"#--------------------------------------------\n")
    # Set global cmd log file so all commands are logged
    set_cmd_log_file(cmd_log_path)
    
    run_num = get_stage_number(run_step)
    
    print("=" * 80)
    print(f"Running single stage: {run_step}")
    print("=" * 80)
    print()
    
    # Phase 1: Volume Processing (s01-s07)
    if 1 <= run_num <= 7:
        volume_stages = [
            ("s01", VolumePrep),
            ("s02", BiasCorrection),
            ("s03", MaskAseg),
            ("s04", Talairach),
            ("s05", NormT1),
            ("s06", CCSegmentation),
            ("s07", WMFilled),
        ]
        
        for step_name, stage_class in volume_stages:
            if get_stage_number(step_name) != run_num:
                continue
            print("=" * 60)
            print(f"Phase 1: Volume — {step_name}: {stage_class.__name__}")
            print("=" * 60)
            stage = stage_class(config, sd)
            stage.run()
            print(f"\nCompleted {step_name}.")
            return
    
    # Phase 2: Surface Creation (s08-s18)
    if 8 <= run_num <= 18:
        surface_stages = [
            ("s08", Tessellation),
            ("s09", Smoothing),
            ("s10", Inflation),
            ("s11", SphericalProjection),
            ("s12", TopologyFix),
            ("s13", WhitePreaparc),
            ("s14", Parcellation),
            ("s15", SurfacePlacement),
            ("s16", ComputeMorphometry),
            ("s17", Registration),
            ("s18", Statistics),
        ]
        
        for step_name, stage_class in surface_stages:
            if get_stage_number(step_name) != run_num:
                continue
            print("=" * 60)
            print(f"Phase 2: Surface — {step_name}: {stage_class.__name__}")
            print("=" * 60)
            
            if step_name == "s18":
                print("Computing statistics for both hemispheres (sequential)")
                for hemi in hemis:
                    print(f"  Processing {hemi}...")
                    stage = stage_class(config, sd, hemi)
                    stage.run()
            else:
                if config.processing.parallel_hemis:
                    print(f"Running for both hemispheres in parallel...")
                    log = logging.getLogger(__name__)
                    
                    def process_hemi(hemi: str):
                        stage = stage_class(config, sd, hemi)
                        stage.run()
                    
                    with ThreadPoolExecutor(max_workers=len(hemis)) as executor:
                        futures = {executor.submit(process_hemi, hemi): hemi for hemi in hemis}
                        for future in as_completed(futures):
                            hemi = futures[future]
                            try:
                                future.result()
                            except Exception as e:
                                log.error(f"Error processing {hemi}: {e}")
                                raise
                else:
                    print(f"Running for both hemispheres sequentially...")
                    for hemi in hemis:
                        print(f"  Processing {hemi}...")
                        stage = stage_class(config, sd, hemi)
                        stage.run()
            print(f"\nCompleted {step_name}.")
            return
    
    # Phase 3: Post-Surface (s19-s22)
    if 19 <= run_num <= 22:
        post_surface_stages = [
            ("s19", CorticalRibbon),
            ("s20", AsegRefinement),
            ("s21", AparcMapping),
            ("s22", WMParcMapping),
        ]
        
        for step_name, stage_class in post_surface_stages:
            if get_stage_number(step_name) != run_num:
                continue
            print("=" * 60)
            print(f"Phase 3: Post-Surface — {step_name}: {stage_class.__name__}")
            print("=" * 60)
            stage = stage_class(config, sd)
            stage.run()
            print(f"\nCompleted {step_name}.")
            return
    
    print(f"\nNo stage matched {run_step} (internal error).")


def main():
    """Main entry point."""
    # Validate run step
    for run_step in RUN_STEPS:
        if run_step not in VALID_STEPS:
            print(f"Error: Invalid step '{run_step}'")
            print(f"Valid steps are: {', '.join(sorted(VALID_STEPS))}")
            sys.exit(1)
    
    # Setup logging
    setup_logging()
    
    # Create configuration - load defaults from default.yaml, then override specific values
    config = ReconSurfConfig.with_defaults(
        subject_id=subject_id,
        subjects_dir=subjects_dir,
        atlas={"name": "ARM2"},
        processing={
            "threads": n_threads,
            "parallel_hemis": parallel_hemis,
            "skip_cc": True,  # Non-human
            "skip_talairach": True,  # Non-human
            "hires": "auto",  # Auto-detect from voxel size
        },
        verbose=2,  # DEBUG
    )
    
    # Run single stage only
    for run_step in RUN_STEPS:
        try:
            run_single_stage(config, run_step)
            print()
            print("=" * 80)
            print(f"Single-stage test completed ({run_step})")
            print("=" * 80)
        except Exception as e:
            print()
            print("=" * 80)
            print(f"Single-stage test failed: {e}")
            print("=" * 80)
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    main()
