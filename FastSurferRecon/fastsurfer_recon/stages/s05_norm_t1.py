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
                subject_dir=self.sd.subject_dir,
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
                    subject_dir=self.sd.subject_dir,
                )
            else:
                logger.info("T1.mgz already exists")
            
            # Create brainmask.mgz (masked T1)
            # If brainmask exists as a symlink (from previous run with get_t1=False),
            # we need to remove it and create a real file from T1.mgz
            if brainmask.exists() and brainmask.is_symlink():
                logger.info("Removing symlink brainmask.mgz (will recreate from T1.mgz)")
                brainmask.unlink()
            
            if not brainmask.exists():
                logger.info("Creating brainmask.mgz (masked T1.mgz)")
                mri_mask(
                    input_vol=t1,
                    mask=mask,
                    output_vol=brainmask,
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
            else:
                logger.info("brainmask.mgz already exists")
        else:
            # Create T1.mgz as symlink to nu.mgz (for downstream tools that need T1.mgz)
            # T1.mgz should have skull (like nu.mgz), not just brain (like norm.mgz)
            # If T1.mgz exists as a regular file (from previous run with get_t1=True),
            # we need to remove it and create a symlink
            if t1.exists() and not t1.is_symlink():
                logger.info("Removing existing T1.mgz (will create symlink to nu.mgz)")
                t1.unlink()
            
            if not t1.exists():
                logger.info("Linking T1.mgz to nu.mgz (skipping normalization, keeping skull)")
                t1.symlink_to("nu.mgz")
            elif t1.is_symlink():
                logger.info("T1.mgz already exists as symlink")
            
            # Link brainmask to norm
            # If brainmask exists as a regular file (from previous run with get_t1=True),
            # we need to remove it and create a symlink
            if brainmask.exists() and not brainmask.is_symlink():
                logger.info("Removing existing brainmask.mgz (will create symlink to norm.mgz)")
                brainmask.unlink()
            
            if not brainmask.exists():
                logger.info("Linking brainmask.mgz to norm.mgz")
                brainmask.symlink_to("norm.mgz")
    
    def should_skip(self) -> bool:
        """
        Skip if norm and brainmask exist, and if get_t1=True, also check T1.mgz exists.
        
        Also check if brainmask needs to be recreated (e.g., if it's a symlink
        but get_t1=True, or if it's a regular file but get_t1=False).
        """
        norm = self.sd.mri("norm.mgz")
        brainmask = self.sd.mri("brainmask.mgz")
        
        # Must have norm.mgz
        if not norm.exists():
            return False
        
        # Must have brainmask.mgz
        if not brainmask.exists():
            return False
        
        # If get_t1 is True, we need T1.mgz and brainmask should be a regular file (not symlink)
        if self.config.processing.get_t1:
            t1 = self.sd.mri("T1.mgz")
            if not t1.exists():
                return False
            # If brainmask is a symlink, we need to recreate it from T1.mgz
            if brainmask.is_symlink():
                return False
            return True
        else:
            # If get_t1 is False, T1.mgz should be a symlink to nu.mgz (with skull)
            t1 = self.sd.mri("T1.mgz")
            if not t1.exists():
                return False
            if not t1.is_symlink():
                return False
            
            # brainmask should also be a symlink to norm.mgz
            # If it's a regular file, we need to recreate it as a symlink
            if not brainmask.is_symlink():
                return False
            return True

