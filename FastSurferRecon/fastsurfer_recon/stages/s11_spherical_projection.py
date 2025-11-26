"""
Stage 11: Spherical Projection

Projects surface to sphere (qsphere or spectral projection).
"""

from pathlib import Path
import logging
import shutil

from .base import HemisphereStage
from ..wrappers.recon_all import recon_all_qsphere
from ..processing.spherical import spherically_project_surface

logger = logging.getLogger(__name__)


class SphericalProjection(HemisphereStage):
    """Project surface to sphere."""
    
    name = "spherical_projection"
    description = "Spherical projection (qsphere)"
    
    def _run(self) -> None:
        """Project to sphere."""
        sphere = self.hemi_path("sphere")
        qsphere_nofix = self.hemi_path("qsphere.nofix")
        # Skip if either file exists (they should both exist after creation)
        if sphere.exists() or qsphere_nofix.exists():
            logger.info(f"{self.hemi} spherical projection already exists, skipping")
            return
        
        if self.config.processing.fsqsphere:
            # Use FreeSurfer qsphere
            logger.info(f"Using FreeSurfer qsphere for {self.hemi}")
            recon_all_qsphere(
                subject=self.config.subject_id,
                hemi=self.hemi,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        else:
            # Use spectral projection
            logger.info(f"Using spectral projection for {self.hemi}")
            # FastSurfer uses smoothwm.nofix as input for spherical projection
            # (not inflated.nofix, which is used for topology fix)
            smoothwm_nofix = self.hemi_path("smoothwm.nofix")
            if not smoothwm_nofix.exists():
                raise FileNotFoundError(
                    f"{smoothwm_nofix} not found. "
                    "Smoothing stage must run first."
                )
            
            # FastSurfer creates qsphere.nofix directly, so we do the same
            # Also create sphere for consistency with FreeSurfer naming
            qsphere_nofix = self.hemi_path("qsphere.nofix")
            spherically_project_surface(
                input_path=smoothwm_nofix,
                output_path=qsphere_nofix,
            )
            # Also create sphere as an alias (copy for compatibility)
            if not sphere.exists():
                shutil.copy(qsphere_nofix, sphere)
    
    def should_skip(self) -> bool:
        """Skip if sphere exists."""
        return self.hemi_path("sphere").exists()

