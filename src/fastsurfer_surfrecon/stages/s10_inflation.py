"""
Stage 10: Surface Inflation

Inflates surface to sphere (inflate1).
This is the first inflation, performed before topology fix.
For high-resolution data, sufficient inflation (e.g., 100 iterations) is critical
for correct surface mapping onto sphere and subsequent defect labeling.
"""

from pathlib import Path
import logging

from .base import HemisphereStage
from ..wrappers.mris import mris_inflate

logger = logging.getLogger(__name__)


class Inflation(HemisphereStage):
    """Inflate surface to sphere (inflate1, before topology fix)."""
    
    name = "inflation"
    description = "Surface inflation (inflate1)"
    
    def _run(self) -> None:
        """Inflate surface (inflate1, before topology fix).
        
        Uses inflate_iterations parameter. For high-resolution data (0.75mm isotropic),
        use 20-50 or even 100 iterations to ensure sufficient inflation.
        """
        # Check for both inflated and inflated.nofix (depending on whether fix was run)
        # Also check if s11 (spherical projection) has run, which indicates s10 has completed
        # This handles the case where s12 deletes inflated.nofix after using it
        inflated = self.hemi_path("inflated")
        inflated_nofix = self.hemi_path("inflated.nofix")
        sphere = self.hemi_path("sphere")
        qsphere_nofix = self.hemi_path("qsphere.nofix")
        if inflated.exists() or inflated_nofix.exists() or sphere.exists() or qsphere_nofix.exists():
            logger.info(f"{self.hemi}.inflated already exists or spherical projection has run, skipping")
            return
        
        # Input is smoothwm.nofix (before topology fix)
        smoothwm_nofix = self.hemi_path("smoothwm.nofix")
        if not smoothwm_nofix.exists():
            raise FileNotFoundError(
                f"{self.hemi}.smoothwm.nofix not found. "
                "This should be created in stage 09 (smoothing)."
            )
        
        logger.info(f"Inflating {self.hemi} surface (inflate1, n={self.config.processing.inflate_iterations})...")
        mris_inflate(
            input_surf=smoothwm_nofix,
            output_surf=inflated_nofix,
            n_iterations=self.config.processing.inflate_iterations,
            no_save_sulc=self.config.processing.inflate_no_save_sulc,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
    
    def should_skip(self) -> bool:
        """Skip if inflated exists or if spherical projection has run (sphere/qsphere.nofix exists)."""
        # Check for both inflated and inflated.nofix
        # Also check if s11 (spherical projection) has run, which indicates s10 has completed
        # This handles the case where s12 deletes inflated.nofix after using it
        return (
            self.hemi_path("inflated").exists() 
            or self.hemi_path("inflated.nofix").exists()
            or self.hemi_path("sphere").exists()
            or self.hemi_path("qsphere.nofix").exists()
        )

