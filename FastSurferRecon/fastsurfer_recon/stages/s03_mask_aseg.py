"""
Stage 03: Mask and Aseg Processing

Creates aseg.presurf.mgz from aseg.auto_noCCseg.mgz.
This is the aseg file used for surface reconstruction.
"""

from pathlib import Path
import logging
import shutil

from .base import PipelineStage
from ..wrappers.mri import mri_mask

logger = logging.getLogger(__name__)


class MaskAseg(PipelineStage):
    """Create aseg.presurf.mgz from aseg.auto_noCCseg.mgz."""
    
    name = "mask_aseg"
    description = "Create aseg.presurf.mgz from aseg.auto_noCCseg.mgz"
    
    def _run(self) -> None:
        """Create aseg.presurf.mgz."""
        aseg_nocc = self.sd.mri("aseg.auto_noCCseg.mgz")
        aseg_presurf = self.sd.mri("aseg.presurf.mgz")
        
        if aseg_presurf.exists():
            logger.info("aseg.presurf.mgz already exists, skipping")
            return
        
        if not aseg_nocc.exists():
            raise FileNotFoundError(
                f"aseg.auto_noCCseg.mgz not found at {aseg_nocc}. "
                "This should be created by FastSurferCNN post-processing."
            )
        
        logger.info("Creating aseg.presurf.mgz from aseg.auto_noCCseg.mgz")
        
        # Apply mask to aseg if mask exists
        mask = self.config.mask or self.sd.mask
        if mask.exists():
            logger.info(f"Applying mask {mask} to aseg")
            mri_mask(
                input_vol=aseg_nocc,
                mask=mask,
                output_vol=aseg_presurf,
                log_file=self.config.log_file,
            )
        else:
            # Just copy if no mask
            logger.info("No mask available, copying aseg.auto_noCCseg.mgz to aseg.presurf.mgz")
            shutil.copy(aseg_nocc, aseg_presurf)
    
    def should_skip(self) -> bool:
        """Skip if aseg.presurf.mgz exists."""
        return self.sd.mri("aseg.presurf.mgz").exists()

