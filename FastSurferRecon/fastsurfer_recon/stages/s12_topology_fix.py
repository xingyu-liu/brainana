"""
Stage 12: Topology Fix

Fixes topological defects in surface (optional for non-human).
"""

from pathlib import Path
import logging
import shutil

from .base import HemisphereStage
from ..wrappers.recon_all import recon_all_fix
from ..processing.surface_fix import fix_surface_orientation

logger = logging.getLogger(__name__)


class TopologyFix(HemisphereStage):
    """Fix topological defects."""
    
    name = "topology_fix"
    description = "Topology fix (fix)"
    
    def _run(self) -> None:
        """Fix topology."""
        if self.config.processing.nofix:
            logger.info(f"Skipping topology fix for {self.hemi} (--nofix flag set)")
            # Use orig.nofix directly as orig (aligns with recon-surf.sh)
            orig_nofix = self.hemi_path("orig.nofix")
            orig = self.hemi_path("orig")
            
            if not orig_nofix.exists():
                raise FileNotFoundError(
                    f"ERROR: {self.hemi}.orig.nofix not found! "
                    "Cannot proceed with --nofix without orig.nofix surface."
                )
            
            if not orig.exists():
                logger.info(f"Copying {self.hemi}.orig.nofix to {self.hemi}.orig")
                shutil.copy(orig_nofix, orig)
                if not orig.exists():
                    raise RuntimeError(
                        f"ERROR: Failed to copy {self.hemi}.orig.nofix to {self.hemi}.orig"
                    )
            return
        
        orig = self.hemi_path("orig")
        if orig.exists():
            logger.info(f"{self.hemi}.orig already exists, skipping")
            return
        
        # FreeSurfer's -fix step expects qsphere.nofix.
        # Spectral projection now creates qsphere.nofix directly, but this fallback
        # handles edge cases (e.g., if using FreeSurfer qsphere or legacy data).
        qsphere_nofix = self.hemi_path("qsphere.nofix")
        sphere = self.hemi_path("sphere")
        if not qsphere_nofix.exists() and sphere.exists():
            logger.info(f"Creating {self.hemi}.qsphere.nofix from {self.hemi}.sphere (fallback)")
            shutil.copy(sphere, qsphere_nofix)
        
        logger.info(f"Fixing topology for {self.hemi}...")
        recon_all_fix(
            subject=self.config.subject_id,
            hemi=self.hemi,
            hires=self.config.hires,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
        
        # Fix oriented surfaces if needed
        premesh = self.hemi_path("orig.premesh")
        if premesh.exists():
            fix_surface_orientation(
                surface_path=premesh,
                backup_path=self.hemi_path("orig.premesh.noorient"),
            )
        
        fix_surface_orientation(
            surface_path=orig,
            backup_path=self.hemi_path("orig.noorient"),
        )
    
    def should_skip(self) -> bool:
        """Skip if fix is disabled or orig exists."""
        if self.config.processing.nofix:
            return self.hemi_path("orig").exists()
        return self.hemi_path("orig").exists()

