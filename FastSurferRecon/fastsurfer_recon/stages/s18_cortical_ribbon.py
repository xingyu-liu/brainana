"""
Stage 18: Cortical Ribbon

Creates cortical ribbon volume from white and pial surfaces.
"""

from pathlib import Path
import logging

from .base import PipelineStage
from ..wrappers.recon_all import recon_all_cortribbon

logger = logging.getLogger(__name__)


class CorticalRibbon(PipelineStage):
    """Create cortical ribbon volume."""
    
    name = "cortical_ribbon"
    description = "Cortical ribbon creation"
    
    def _run(self) -> None:
        """Create cortical ribbon."""
        ribbon = self.sd.mri("ribbon.mgz")
        lh_ribbon = self.sd.mri("lh.ribbon.mgz")
        rh_ribbon = self.sd.mri("rh.ribbon.mgz")
        
        if ribbon.exists() and lh_ribbon.exists() and rh_ribbon.exists():
            logger.info("Cortical ribbon already exists, skipping")
            return
        
        logger.info("Creating cortical ribbon...")
        recon_all_cortribbon(
            subject=self.config.subject_id,
            hires=self.config.hires,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
    
    def should_skip(self) -> bool:
        """Skip if ribbon files exist."""
        return (
            self.sd.mri("ribbon.mgz").exists() and
            self.sd.mri("lh.ribbon.mgz").exists() and
            self.sd.mri("rh.ribbon.mgz").exists()
        )

