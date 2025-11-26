"""
Stage 05: Normalization and T1 Creation

Creates norm.mgz and T1.mgz from nu.mgz.
"""

from pathlib import Path
import logging
import shutil

from .base import PipelineStage
from ..wrappers.mri import mri_mask, mri_normalize

logger = logging.getLogger(__name__)


class NormT1(PipelineStage):
    """Create norm.mgz and T1.mgz."""
    
    name = "norm_t1"
    description = "Create norm.mgz and T1.mgz"
    
    def _run(self) -> None:
        """Create normalized volumes."""
        mask = self.config.mask or self.sd.mask
        nu = self.sd.mri("nu.mgz")
        norm = self.sd.mri("norm.mgz")
        t1 = self.sd.mri("T1.mgz")
        brainmask = self.sd.mri("brainmask.mgz")
        
        # Create norm.mgz (masked nu)
        if not norm.exists():
            logger.info("Creating norm.mgz (masked nu.mgz)")
            mri_mask(
                input_vol=nu,
                mask=mask,
                output_vol=norm,
                log_file=self.config.log_file,
            )
        else:
            logger.info("norm.mgz already exists")
        
        # Create T1.mgz if requested
        if self.config.processing.get_t1:
            if not t1.exists():
                logger.info("Creating T1.mgz (normalized nu.mgz)")
                aseg_orig = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.orig.mgz")
                mri_normalize(
                    input_vol=nu,
                    output_vol=t1,
                    aseg=aseg_orig if aseg_orig.exists() else None,
                    log_file=self.config.log_file,
                )
            else:
                logger.info("T1.mgz already exists")
            
            # Create brainmask.mgz (masked T1)
            if not brainmask.exists():
                logger.info("Creating brainmask.mgz (masked T1.mgz)")
                mri_mask(
                    input_vol=t1,
                    mask=mask,
                    output_vol=brainmask,
                    log_file=self.config.log_file,
                )
        else:
            # Link brainmask to norm
            if not brainmask.exists():
                logger.info("Linking brainmask.mgz to norm.mgz")
                brainmask.symlink_to("norm.mgz")
    
    def should_skip(self) -> bool:
        """Skip if norm and brainmask exist."""
        norm = self.sd.mri("norm.mgz")
        brainmask = self.sd.mri("brainmask.mgz")
        if not norm.exists() or not brainmask.exists():
            return False
        if self.config.processing.get_t1:
            t1 = self.sd.mri("T1.mgz")
            return t1.exists()
        return True

