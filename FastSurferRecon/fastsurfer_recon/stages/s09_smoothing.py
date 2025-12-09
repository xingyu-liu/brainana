"""
Stage 09: Surface Smoothing

Smooths the initial surface.
"""

from pathlib import Path
import logging

from .base import HemisphereStage
from ..wrappers.mris import mris_smooth

logger = logging.getLogger(__name__)


class Smoothing(HemisphereStage):
    """Smooth initial surface."""
    
    name = "smoothing"
    description = "Surface smoothing (smoothwm.nofix)"
    
    def _run(self) -> None:
        """Smooth surface."""
        orig_nofix = self.hemi_path("orig.nofix")
        smoothwm_nofix = self.hemi_path("smoothwm.nofix")
        
        if smoothwm_nofix.exists():
            logger.info(f"{self.hemi}.smoothwm.nofix already exists, skipping")
            return
        
        logger.info(f"Smoothing {self.hemi} surface...")
        mris_smooth(
            input_surf=orig_nofix,
            output_surf=smoothwm_nofix,
            n_iterations=self.config.processing.smooth_iterations,
            nw=True,
            seed=1234,
            log_file=self.config.log_file,
        )
    
    def should_skip(self) -> bool:
        """Skip if smoothwm.nofix exists."""
        return self.hemi_path("smoothwm.nofix").exists()

