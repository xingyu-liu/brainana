"""
Stage 10: Surface Inflation

Inflates surface to sphere (inflate1).
"""

from pathlib import Path
import logging

from .base import HemisphereStage
from ..wrappers.recon_all import recon_all_inflate1

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
        
        logger.info(f"Inflating {self.hemi} surface...")
        recon_all_inflate1(
            subject=self.config.subject_id,
            hemi=self.hemi,
            hires=self.config.hires,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
    
    def should_skip(self) -> bool:
        """Skip if inflated exists."""
        # Check for both inflated and inflated.nofix
        return self.hemi_path("inflated").exists() or self.hemi_path("inflated.nofix").exists()

