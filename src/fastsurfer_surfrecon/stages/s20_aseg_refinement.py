"""
Stage 20: Aseg Refinement

Creates aseg.mgz from aseg.presurf.hypos.mgz using surfaces and ribbon.
"""

import logging

from .base import PipelineStage
from ..wrappers.base import run_recon_all

logger = logging.getLogger(__name__)


class AsegRefinement(PipelineStage):
    """Create aseg.mgz from aseg.presurf using surfaces."""
    
    name = "aseg_refinement"
    description = "Aseg refinement with surfaces"
    
    def _run(self) -> None:
        """Create aseg.mgz."""
        
        # Create aseg.presurf.hypos.mgz (hyporelabel); always run so reruns overwrite
        logger.info("Creating aseg.presurf.hypos.mgz...")
        flags = []
        if self.config.hires:
            flags.append("-hires")
        run_recon_all(
            subject=self.config.subject_id,
            steps=["-hyporelabel"],
            flags=flags,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
        
        # Create aseg.mgz from aseg.presurf.hypos using surfaces and ribbon
        logger.info("Creating aseg.mgz from aseg.presurf.hypos with surfaces...")
        flags = []
        if self.config.hires:
            flags.append("-hires")
        run_recon_all(
            subject=self.config.subject_id,
            steps=["-apas2aseg"],
            flags=flags,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
    
    # def should_skip(self) -> bool:
    #     """Skip if aseg.mgz exists."""
    #     return self.sd.mri("aseg.mgz").exists()

    def should_skip(self) -> bool:
        """Skip if """
        return (
            False
        )