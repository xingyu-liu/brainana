"""
Stage 19: Aseg Refinement

Creates aseg.mgz from aseg.presurf.hypos.mgz using surfaces and ribbon.
"""

from pathlib import Path
import logging

from .base import PipelineStage
from ..wrappers.recon_all import recon_all_hyporelabel, recon_all_apas2aseg

logger = logging.getLogger(__name__)


class AsegRefinement(PipelineStage):
    """Create aseg.mgz from aseg.presurf using surfaces."""
    
    name = "aseg_refinement"
    description = "Aseg refinement with surfaces"
    
    def _run(self) -> None:
        """Create aseg.mgz."""
        aseg = self.sd.mri("aseg.mgz")
        aseg_presurf_hypos = self.sd.mri("aseg.presurf.hypos.mgz")
        
        if aseg.exists():
            logger.info("aseg.mgz already exists, skipping")
            return
        
        # Create aseg.presurf.hypos.mgz if it doesn't exist
        if not aseg_presurf_hypos.exists():
            logger.info("Creating aseg.presurf.hypos.mgz...")
            recon_all_hyporelabel(
                subject=self.config.subject_id,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Create aseg.mgz from aseg.presurf.hypos using surfaces and ribbon
        logger.info("Creating aseg.mgz from aseg.presurf.hypos with surfaces...")
        recon_all_apas2aseg(
            subject=self.config.subject_id,
            hires=self.config.hires,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
    
    def should_skip(self) -> bool:
        """Skip if aseg.mgz exists."""
        return self.sd.mri("aseg.mgz").exists()

