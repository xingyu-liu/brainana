"""
Stage 10: Surface Inflation

Inflates surface to sphere (inflate1).
"""

from pathlib import Path
import logging

from .base import HemisphereStage
from ..wrappers.mris import mris_inflate

logger = logging.getLogger(__name__)


class Inflation(HemisphereStage):
    """Inflate surface to sphere."""
    
    name = "inflation"
    description = "Surface inflation (inflate1)"
    
    def _run(self) -> None:
        """Inflate surface."""
        # Check for both inflated and inflated.nofix (depending on whether fix was run)
        inflated = self.hemi_path("inflated")
        inflated_nofix = self.hemi_path("inflated.nofix")
        if inflated.exists() or inflated_nofix.exists():
            logger.info(f"{self.hemi}.inflated already exists, skipping")
            return
        
        # Input is smoothwm.nofix (before topology fix)
        smoothwm_nofix = self.hemi_path("smoothwm.nofix")
        if not smoothwm_nofix.exists():
            raise FileNotFoundError(
                f"{self.hemi}.smoothwm.nofix not found. "
                "This should be created in stage 09 (smoothing)."
            )
        
        logger.info(f"Inflating {self.hemi} surface...")
        mris_inflate(
            input_surf=smoothwm_nofix,
            output_surf=inflated_nofix,
            n_iterations=self.config.processing.inflate_iterations,
            no_save_sulc=self.config.processing.inflate_no_save_sulc,
            log_file=self.config.log_file,
        )
    
    def should_skip(self) -> bool:
        """Skip if inflated exists."""
        # Check for both inflated and inflated.nofix
        return self.hemi_path("inflated").exists() or self.hemi_path("inflated.nofix").exists()

