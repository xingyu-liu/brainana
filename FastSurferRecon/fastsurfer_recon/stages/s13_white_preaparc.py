"""
Stage 13: White Preaparc Surface

Creates white.preaparc surface for parcellation mapping.
"""

from pathlib import Path
import logging

from .base import HemisphereStage
from ..wrappers.recon_all import recon_all_autodetgwstats, recon_all_white_preaparc
from ..wrappers.mris import mris_place_surface

logger = logging.getLogger(__name__)


class WhitePreaparc(HemisphereStage):
    """Create white.preaparc surface."""
    
    name = "white_preaparc"
    description = "White preaparc surface"
    
    def _run(self) -> None:
        """Create white.preaparc."""
        white_preaparc = self.hemi_path("white.preaparc")
        
        # Auto-detect gray/white stats (needed even if white.preaparc exists)
        # Note: recon-all creates autodet.gw.stats.{hemi}.dat (not {hemi}.autodet.gw.stats.dat)
        autodet_stats = self.sdir / f"autodet.gw.stats.{self.hemi}.dat"
        if not autodet_stats.exists():
            logger.info(f"Auto-detecting GW stats for {self.hemi}...")
            no_remesh = self.config.processing.nofix
            recon_all_autodetgwstats(
                subject=self.config.subject_id,
                hemi=self.hemi,
                no_remesh=no_remesh,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Create white.preaparc if it doesn't exist
        if white_preaparc.exists():
            logger.info(f"{self.hemi}.white.preaparc already exists, skipping")
            return
        
        if self.config.processing.nofix:
            # Direct placement without remesh
            logger.info(f"Creating {self.hemi}.white.preaparc (no-fix mode)...")
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
                max_cbv_dist=3.5,
                log_file=self.config.log_file,
            )
        else:
            # Use recon-all
            logger.info(f"Creating {self.hemi}.white.preaparc...")
            recon_all_white_preaparc(
                subject=self.config.subject_id,
                hemi=self.hemi,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
    
    def should_skip(self) -> bool:
        """Skip if white.preaparc and autodet.gw.stats.{hemi}.dat exist."""
        return (
            self.hemi_path("white.preaparc").exists() and
            (self.sdir / f"autodet.gw.stats.{self.hemi}.dat").exists()
        )

