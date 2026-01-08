"""
Stage 13: White Preaparc Surface

Creates white.preaparc surface for parcellation mapping.
"""

import logging

from .base import HemisphereStage
from ..wrappers.base import run_recon_all
from ..wrappers.mris import mris_place_surface

logger = logging.getLogger(__name__)


class WhitePreaparc(HemisphereStage):
    """Create white.preaparc surface."""
    
    name = "white_preaparc"
    description = "White preaparc surface"
    
    def _run(self) -> None:
        """Create white.preaparc.
        
        This stage performs two tasks:
        1. Auto-detect gray/white matter statistics (autodet.gw.stats.{hemi}.dat)
        2. Create white.preaparc surface from orig surface
        
        Note: autodet_stats is created FIRST, even if white.preaparc already exists,
        because it's required by later stages (s15 surface placement) regardless
        of whether white.preaparc needs to be recreated.
        """
        white_preaparc = self.hemi_path("white.preaparc")
        
        # Step 1: Auto-detect gray/white stats
        # This file is required by stage 15 (surface placement) for placing white
        # and pial surfaces. It must exist even if white.preaparc already exists.
        # Note: recon-all creates autodet.gw.stats.{hemi}.dat (not {hemi}.autodet.gw.stats.dat)
        autodet_stats = self.sdir / f"autodet.gw.stats.{self.hemi}.dat"
        if not autodet_stats.exists():
            logger.info(f"Auto-detecting GW stats for {self.hemi}...")
            flags = []
            if self.config.hires:
                flags.append("-hires")
            run_recon_all(
                subject=self.config.subject_id,
                hemi=self.hemi,
                steps=["-autodetgwstats"],
                flags=flags,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Step 2: Create white.preaparc if it doesn't exist
        # This is the pre-parcellation white surface used for parcellation mapping
        # in stage 14, and as input for final white surface placement in stage 15.
        if white_preaparc.exists():
            logger.info(f"{self.hemi}.white.preaparc already exists, skipping")
            return
        
        logger.info(f"Creating {self.hemi}.white.preaparc...")
        # Place white.preaparc surface using mris_place_surface
        # This creates a white matter surface from the fixed orig surface (after topology fix)
        # Parameters:
        #   - max_cbv_dist=5: Maximum distance for cortical boundary value search
        #   - nsmooth=3: Number of smoothing iterations during placement
        mris_place_surface(
            input_surf=self.hemi_path("orig"),
            output_surf=white_preaparc,
            hemi=self.hemi,
            wm=self.sd.mri("wm.mgz"),
            invol=self.sd.mri("brain.finalsurfs.mgz"),
            aseg=self.sd.mri("aseg.presurf.mgz"),
            adgws_in=autodet_stats,
            white=True,
            threads=self.threads,
            max_cbv_dist=5,
            nsmooth=3,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
            subjects_dir=self.config.subjects_dir,
        )

    
    def should_skip(self) -> bool:
        """Skip if white.preaparc and autodet.gw.stats.{hemi}.dat exist."""
        return (
            self.hemi_path("white.preaparc").exists() and
            (self.sdir / f"autodet.gw.stats.{self.hemi}.dat").exists()
        )

