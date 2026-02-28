"""
Stage 02: Bias Field Correction

Performs N4 bias field correction and WM intensity normalization.
"""

from pathlib import Path
import logging

from .base import PipelineStage
from ..processing.bias_correction import bias_correct_and_normalize

logger = logging.getLogger(__name__)


class BiasCorrection(PipelineStage):
    """Bias field correction using N4 algorithm."""
    
    name = "bias_correction"
    description = "N4 bias field correction and WM normalization"
    
    def _run(self) -> None:
        """Run N4 bias correction."""
        logger.info("Running N4 bias field correction...")
        
        # Get mask if available
        mask_path = self.config.mask or self.sd.mask
        if not mask_path.exists():
            mask_path = None
            logger.warning("No mask available, running without mask")
        
        # Get aseg for WM normalization
        aseg_orig = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.orig.mgz")
        aseg_path = aseg_orig if aseg_orig.exists() else None
        
        bias_correct_and_normalize(
            input_path=self.sd.orig,
            output_path=self.sd.orig_nu,
            mask_path=mask_path,
            aseg_path=aseg_path,
            shrink_factor=self.config.processing.n4_shrink_factor,
            num_levels=self.config.processing.n4_levels,
            num_iterations=self.config.processing.n4_num_iterations,
            threads=self.config.processing.threads,
        )
    
    def should_skip(self) -> bool:
        """Skip if orig_nu.mgz exists."""
        return self.sd.orig_nu.exists()

