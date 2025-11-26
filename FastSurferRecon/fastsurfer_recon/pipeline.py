"""
Main pipeline orchestrator for FastSurfer surface reconstruction.

Coordinates the execution of all pipeline stages.
"""

from pathlib import Path
from typing import Optional, Callable
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import ReconSurfConfig
from .io.subjects_dir import SubjectsDir
from .stages import (
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
    Registration,
    Statistics,
    CorticalRibbon,
    AsegRefinement,
    AparcMapping,
    WMParcMapping,
)

logger = logging.getLogger(__name__)


class ReconSurfPipeline:
    """
    Main surface reconstruction pipeline.
    
    Orchestrates the execution of all pipeline stages, handling
    parallelization, logging, and error recovery.
    
    Parameters
    ----------
    config : ReconSurfConfig
        Pipeline configuration
        
    Examples
    --------
    >>> config = ReconSurfConfig(
    ...     subject_id="sub-001",
    ...     subjects_dir=Path("/data/subjects"),
    ...     t1_input=Path("/data/input/T1.mgz"),
    ...     segmentation=Path("/data/input/aparc+aseg.mgz"),
    ... )
    >>> pipeline = ReconSurfPipeline(config)
    >>> pipeline.run()
    """
    
    def __init__(self, config: ReconSurfConfig):
        self.config = config
        self.sd = SubjectsDir(config.subjects_dir, config.subject_id)
        
        # Timing
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def run(self) -> None:
        """
        Run the complete surface reconstruction pipeline.
        
        Executes all phases:
        1. Volume preprocessing
        2. Surface creation (per hemisphere)
        3. Statistics and finalization
        """
        self.start_time = datetime.now()
        logger.info(f"Starting recon-surf for {self.config.subject_id}")
        logger.info(f"Start time: {self.start_time}")
        
        # Setup directories
        self.sd.setup()
        self._setup_logging()
        
        try:
            # Phase 1: Volume Processing
            self._run_volume_phase()
            
            # Phase 2: Surface Creation (per hemisphere)
            self._run_surface_phase()
            
            # Phase 3: Statistics and Finalization
            self._run_stats_phase()
            
            # Write done file
            self._write_done_file()
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise
        
        self.end_time = datetime.now()
        elapsed = self.end_time - self.start_time
        logger.info(f"Completed recon-surf for {self.config.subject_id}")
        logger.info(f"Total time: {elapsed}")
    
    def _setup_logging(self) -> None:
        """Set up file logging."""
        if self.config.log_file:
            log_path = self.config.log_file
        else:
            log_path = self.sd.log_file
        
        # Add file handler
        file_handler = logging.FileHandler(log_path, mode="a")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logging.getLogger("fastsurfer_recon").addHandler(file_handler)
        
        # Write header
        with open(log_path, "a") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"FastSurfer Recon Pipeline Log\n")
            f.write(f"Subject: {self.config.subject_id}\n")
            f.write(f"Start: {self.start_time}\n")
            f.write(f"{'='*80}\n\n")
    
    def _run_volume_phase(self) -> None:
        """
        Volume preprocessing phase.
        
        Stages:
        - s01: Volume preparation (orig, conformance check)
        - s02: Bias correction (N4)
        - s03: Mask and aseg processing
        - s04: Talairach registration (optional)
        - s05: Normalization and T1 creation
        - s06: CC segmentation (optional)
        - s07: WM segmentation and filled creation
        """
        logger.info("=" * 60)
        logger.info("Phase 1: Volume Processing")
        logger.info("=" * 60)
        
        # Volume stages (sequential)
        stages = [
            VolumePrep(self.config, self.sd),
            BiasCorrection(self.config, self.sd),
            MaskAseg(self.config, self.sd),
            Talairach(self.config, self.sd),
            NormT1(self.config, self.sd),
            CCSegmentation(self.config, self.sd),
            WMFilled(self.config, self.sd),
        ]
        
        for stage in stages:
            stage.run()
    
    def _run_surface_phase(self) -> None:
        """
        Surface creation phase (per hemisphere).
        
        Stages:
        - s08: Tessellation
        - s09: Smoothing
        - s10: Inflation
        - s11: Spherical projection
        - s12: Topology fix (optional)
        - s13: White preaparc
        - s14: Parcellation mapping
        - s15: Surface placement
        - s16: Registration (optional)
        - s17: Statistics
        """
        logger.info("=" * 60)
        logger.info("Phase 2: Surface Creation")
        logger.info("=" * 60)
        
        def process_hemisphere(hemi: str) -> None:
            """Process a single hemisphere."""
            logger.info(f"Processing hemisphere: {hemi}")
            
            # Surface stages (sequential per hemisphere)
            stages = [
                Tessellation(self.config, self.sd, hemi),
                Smoothing(self.config, self.sd, hemi),
                Inflation(self.config, self.sd, hemi),
                SphericalProjection(self.config, self.sd, hemi),
                TopologyFix(self.config, self.sd, hemi),
                WhitePreaparc(self.config, self.sd, hemi),
                Parcellation(self.config, self.sd, hemi),
                SurfacePlacement(self.config, self.sd, hemi),
                Registration(self.config, self.sd, hemi),
                Statistics(self.config, self.sd, hemi),
            ]
            
            for stage in stages:
                stage.run()
        
        # Run hemispheres
        if self.config.processing.parallel_hemis and self.config.processing.threads >= 2:
            logger.info("Running hemispheres in parallel")
            self._run_parallel(process_hemisphere, ["lh", "rh"])
        else:
            logger.info("Running hemispheres sequentially")
            for hemi in ["lh", "rh"]:
                process_hemisphere(hemi)
        
        # Post-surface volume stages (need both hemispheres' surfaces)
        post_surface_stages = [
            CorticalRibbon(self.config, self.sd),
            AsegRefinement(self.config, self.sd),
            AparcMapping(self.config, self.sd),
            WMParcMapping(self.config, self.sd),
        ]
        
        for stage in post_surface_stages:
            stage.run()
    
    def _run_stats_phase(self) -> None:
        """
        Statistics and finalization phase.
        
        Note: Statistics are computed per-hemisphere in the surface phase.
        This phase handles any final cross-hemisphere operations.
        """
        logger.info("=" * 60)
        logger.info("Phase 3: Finalization")
        logger.info("=" * 60)
        
        # Statistics are already computed per-hemisphere in surface phase
        # This phase can be used for cross-hemisphere operations if needed
        logger.info("Statistics computed per hemisphere in surface phase")
    
    def _run_parallel(
        self, 
        func: Callable[[str], None], 
        items: list[str],
    ) -> None:
        """
        Run a function on multiple items in parallel.
        
        Parameters
        ----------
        func : callable
            Function to call for each item
        items : list
            Items to process
        """
        with ThreadPoolExecutor(max_workers=len(items)) as executor:
            futures = {executor.submit(func, item): item for item in items}
            
            for future in as_completed(futures):
                item = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error processing {item}: {e}")
                    raise
    
    def _write_done_file(self) -> None:
        """Write the done file with run information."""
        import os
        import platform
        
        done_path = self.sd.done_file
        
        # Get username safely
        try:
            username = os.getlogin()
        except OSError:
            username = os.environ.get("USER", str(os.getuid()))
        
        elapsed = self.end_time - self.start_time if self.end_time else None
        elapsed_hours = elapsed.total_seconds() / 3600 if elapsed else 0
        
        content = f"""------------------------------
SUBJECT {self.config.subject_id}
START_TIME {self.start_time}
END_TIME {self.end_time}
RUNTIME_HOURS {elapsed_hours:.3f}
USER {username}
HOST {platform.node()}
PROCESSOR {platform.machine()}
OS {platform.system()}
UNAME {platform.platform()}
VERSION fastsurfer-recon
CMDPATH fastsurfer-recon
"""
        
        done_path.write_text(content)
        logger.info(f"Wrote done file: {done_path}")

