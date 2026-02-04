"""
Stage 01: Volume Preparation

Verifies that required input files exist (orig.mgz, aparc+aseg.orig.mgz, 
mask.mgz, and aseg.auto_noCCseg.mgz).
These should be prepared by fastsurfer_nn post-processing.
"""

from pathlib import Path
import logging

from .base import PipelineStage

logger = logging.getLogger(__name__)


class VolumePrep(PipelineStage):
    """Verify input volumes are ready (orig.mgz, aparc+aseg.orig.mgz, mask.mgz, aseg.auto_noCCseg.mgz)."""
    
    name = "volume_prep"
    description = "Verify input files exist (prepared by fastsurfer_nn)"
    
    def _run(self) -> None:
        """Verify required input files exist."""
        # Check orig.mgz (should be created by fastsurfer_nn)
        if not self.sd.orig.exists():
            raise FileNotFoundError(
                f"orig.mgz not found at {self.sd.orig}. "
                "This should be created by fastsurfer_nn post-processing."
            )
        logger.info(f"Found orig.mgz: {self.sd.orig}")
        
        # Check aparc+aseg.orig.mgz (should be created by fastsurfer_nn)
        aseg_orig = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.orig.mgz")
        if not aseg_orig.exists():
            raise FileNotFoundError(
                f"aparc+aseg.orig.mgz not found at {aseg_orig}. "
                "This should be created by fastsurfer_nn post-processing "
                "(copy of aparc.{atlas}atlas+aseg.orig.mgz)."
            )
        logger.info(f"Found aparc+aseg.orig.mgz: {aseg_orig}")
        
        # Check mask.mgz (should be created by fastsurfer_nn)
        mask = self.config.mask or self.sd.mask
        if not mask.exists():
            raise FileNotFoundError(
                f"mask.mgz not found at {mask}. "
                "This should be created by fastsurfer_nn post-processing."
            )
        logger.info(f"Found mask.mgz: {mask}")
        
        # Check aseg.auto_noCCseg.mgz (should be created by fastsurfer_nn)
        aseg_nocc = self.sd.mri("aseg.auto_noCCseg.mgz")
        if not aseg_nocc.exists():
            raise FileNotFoundError(
                f"aseg.auto_noCCseg.mgz not found at {aseg_nocc}. "
                "This should be created by fastsurfer_nn post-processing."
            )
        logger.info(f"Found aseg.auto_noCCseg.mgz: {aseg_nocc}")
        
        # Link orig.mgz to rawavg.mgz (needed by pctsurfcon)
        rawavg = self.sd.mri("rawavg.mgz")
        if not rawavg.exists():
            logger.info("Linking orig.mgz to rawavg.mgz")
            rawavg.symlink_to("orig.mgz")
    
    def should_skip(self) -> bool:
        """Skip if all required files exist."""
        aseg_orig = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.orig.mgz")
        mask = self.config.mask or self.sd.mask
        aseg_nocc = self.sd.mri("aseg.auto_noCCseg.mgz")
        return (
            self.sd.orig.exists() and 
            aseg_orig.exists() and 
            mask.exists() and 
            aseg_nocc.exists()
        )

