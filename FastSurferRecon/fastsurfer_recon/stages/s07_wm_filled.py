"""
Stage 07: WM Segmentation and Filled Volume

Creates wm.mgz and filled.mgz for surface tessellation.
"""

from pathlib import Path
import logging
import shutil

from .base import PipelineStage
from ..processing.segmentation import create_wm_from_file
from ..wrappers.recon_all import recon_all_normalization2_maskbfs_fill

logger = logging.getLogger(__name__)


class WMFilled(PipelineStage):
    """Create WM segmentation and filled volume."""
    
    name = "wm_filled"
    description = "WM segmentation and filled volume"
    
    def _run(self) -> None:
        """Create WM and filled volumes."""
        wm = self.sd.mri("wm.mgz")
        filled = self.sd.mri("filled.mgz")
        aseg_presurf = self.sd.mri("aseg.presurf.mgz")
        
        # Create WM segmentation
        if not wm.exists():
            logger.info("Creating wm.mgz from aseg...")
            aseg_auto = self.sd.mri("aseg.auto.mgz")
            
            # Get ColorLUT path from atlas config
            colorlut = self.config.atlas.colorlut_path
            if not colorlut or not Path(colorlut).exists():
                raise FileNotFoundError(
                    f"ColorLUT not found: {colorlut}. "
                    "WM segmentation requires a ColorLUT with wm_id column."
                )
            
            create_wm_from_file(
                input_path=aseg_auto,
                output_path=wm,
                lut_path=colorlut,
            )
        else:
            logger.info("wm.mgz already exists")
        
        # Copy aseg.auto to aseg.presurf
        if not aseg_presurf.exists():
            aseg_auto = self.sd.mri("aseg.auto.mgz")
            shutil.copy(aseg_auto, aseg_presurf)
        
        # Create filled volume
        if not filled.exists():
            logger.info("Creating filled.mgz...")
            recon_all_normalization2_maskbfs_fill(
                subject=self.config.subject_id,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        else:
            logger.info("filled.mgz already exists")
    
    def should_skip(self) -> bool:
        """Skip if wm, filled, and aseg.presurf exist."""
        return (
            self.sd.mri("wm.mgz").exists() and
            self.sd.mri("filled.mgz").exists() and
            self.sd.mri("aseg.presurf.mgz").exists()
        )

