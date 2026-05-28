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

# Add src/ to path for fastsurfer_surfrecon package (scripts/ -> fastsurfer_surfrecon -> src)
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fastsurfer_surfrecon.config import ReconSurfConfig
from fastsurfer_surfrecon.io.subjects_dir import SubjectsDir
from fastsurfer_surfrecon.utils.logging import setup_logging
from fastsurfer_surfrecon.stages import (
    # Volume stages
    VolumePrep,
    BiasCorrection,
    MaskAseg,
    Talairach,
    NormT1,
    CCSegmentation,
    WMFilled,
    ClaustrumFix,
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
from fastsurfer_surfrecon.scripts.stage_utils import (
    VOLUME_STEPS,
    SURFACE_STEPS,
    POST_SURFACE_STEPS,
    stage_order_value,
    validate_step,
)

# ============================================================================
# Configuration - Edit these variables as needed
# ============================================================================
RUN_STEPS = ["s07b"]
# RUN_STEPS = [f's{i:02d}' for i in range(1, 8)] + ['s07b']
# RUN_STEPS = ['s11']
# RUN_STEPS = ['s14'] + [f's{i:02d}' for i in range(16, 23)]

# Test subject
subject_dir = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/surf_recon/sub-032109"
)
subjects_dir = subject_dir.parent
subject_id = subject_dir.name

n_threads = 8
parallel_hemis = True

# ============================================================================


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

    logger = logging.getLogger("fastsurfer_surfrecon")
    file_handler = logging.FileHandler(log_path, mode="a")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    # Write header
    from datetime import datetime

    with open(log_path, "a") as f:
        start_time = datetime.now()
        f.write(f"\n{'='*80}\n")
        f.write("FastSurfer Recon Pipeline Log (Single Stage Test)\n")
        f.write(f"Subject: {config.subject_id}\n")
        f.write(f"Run Step: {run_step}\n")
        f.write(f"Start: {start_time}\n")
        f.write(f"{'='*80}\n\n")

    # Initialize cmd log file (fastsurfer_recon.cmd)
    cmd_log_path = config.cmd_log_file
    cmd_log_path.parent.mkdir(parents=True, exist_ok=True)
    from fastsurfer_surfrecon.wrappers.base import set_cmd_log_file

    with open(cmd_log_path, "a") as f:
        timestamp = datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y")
        f.write("\n\n#---------------------------------\n")
        f.write(f"# New invocation of fastsurfer-recon (single stage) {timestamp} \n")
        f.write(f"# Run Step: {run_step}\n")
        f.write("#--------------------------------------------\n")
    # Set global cmd log file so all commands are logged
    set_cmd_log_file(cmd_log_path)

    run_num = stage_order_value(run_step)

    print("=" * 80)
    print(f"Running single stage: {run_step}")
    print("=" * 80)
    print()

    # Phase 1: Volume Processing (s01-s07b)
    if run_step in VOLUME_STEPS:
        volume_stages = [
            ("s01", VolumePrep),
            ("s02", BiasCorrection),
            ("s03", MaskAseg),
            ("s04", Talairach),
            ("s05", NormT1),
            ("s06", CCSegmentation),
            ("s07", WMFilled),
            ("s07b", ClaustrumFix),
        ]

        for step_name, stage_class in volume_stages:
            if stage_order_value(step_name) != run_num:
                continue
            print("=" * 60)
            print(f"Phase 1: Volume — {step_name}: {stage_class.__name__}")
            print("=" * 60)
            stage = stage_class(config, sd)
            stage.run()
            print(f"\nCompleted {step_name}.")
            return

    # Phase 2: Surface Creation (s08-s17)
    if run_step in SURFACE_STEPS:
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
        ]

        for step_name, stage_class in surface_stages:
            if stage_order_value(step_name) != run_num:
                continue
            print("=" * 60)
            print(f"Phase 2: Surface — {step_name}: {stage_class.__name__}")
            print("=" * 60)

            if config.processing.parallel_hemis:
                print("Running for both hemispheres in parallel...")
                log = logging.getLogger(__name__)

                def process_hemi(hemi: str):
                    stage = stage_class(config, sd, hemi)
                    stage.run()

                with ThreadPoolExecutor(max_workers=len(hemis)) as executor:
                    futures = {
                        executor.submit(process_hemi, hemi): hemi for hemi in hemis
                    }
                    for future in as_completed(futures):
                        hemi = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            log.error(f"Error processing {hemi}: {e}")
                            raise
            else:
                print("Running for both hemispheres sequentially...")
                for hemi in hemis:
                    print(f"  Processing {hemi}...")
                    stage = stage_class(config, sd, hemi)
                    stage.run()
            print(f"\nCompleted {step_name}.")
            return

    # Phase 3: Post-Surface (s18-s22)
    # s18: CorticalRibbon - creates ribbon.mgz (needs both hemispheres' surfaces)
    # s19: Statistics - computes brainvol.stats (needs ribbon.mgz for cortical volume)
    if run_step in POST_SURFACE_STEPS:
        # s18: CorticalRibbon (runs once for both hemispheres)
        if run_step == "s18":
            print("=" * 60)
            print("Phase 3: Post-Surface — s18: CorticalRibbon")
            print("=" * 60)
            CorticalRibbon(config, sd).run()
            print("\nCompleted s18.")
            return

        # s19: Statistics (runs per hemisphere, needs ribbon.mgz)
        if run_step == "s19":
            print("=" * 60)
            print("Phase 3: Post-Surface — s19: Statistics")
            print("=" * 60)
            print("Computing statistics for both hemispheres (sequential)")
            for hemi in hemis:
                print(f"  Processing {hemi}...")
                Statistics(config, sd, hemi).run()
            print("\nCompleted s19.")
            return

        # s20-s22: Other post-surface stages
        post_surface_stages = [
            ("s20", AsegRefinement),
            ("s21", AparcMapping),
            ("s22", WMParcMapping),
        ]

        for step_name, stage_class in post_surface_stages:
            if stage_order_value(step_name) != run_num:
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
        try:
            validate_step(run_step)
        except ValueError as e:
            print(f"Error: {e}")
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
