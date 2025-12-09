"""
Stage 12: Topology Fix

Fixes topological defects in surface (optional for non-human).
"""

from pathlib import Path
import logging
import shutil

from .base import HemisphereStage
from ..wrappers.mris import mris_fix_topology, mris_remove_intersection
from ..wrappers.mris import mris_remesh
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
        
        # Required inputs for topology fix
        inflated_nofix = self.hemi_path("inflated.nofix")
        orig_nofix = self.hemi_path("orig.nofix")
        if not qsphere_nofix.exists():
            raise FileNotFoundError(
                f"{self.hemi}.qsphere.nofix not found. "
                "This should be created in stage 11 (spherical_projection)."
            )
        if not inflated_nofix.exists():
            raise FileNotFoundError(
                f"{self.hemi}.inflated.nofix not found. "
                "This should be created in stage 10 (inflation)."
            )
        if not orig_nofix.exists():
            raise FileNotFoundError(
                f"{self.hemi}.orig.nofix not found. "
                "This should be created in stage 08 (tessellation)."
            )
        
        logger.info(f"Fixing topology for {self.hemi}...")
        
        # Step 1: Fix topology - creates orig.premesh
        # mris_fix_topology -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 {subject} {hemi}
        premesh = self.hemi_path("orig.premesh")
        if not premesh.exists():
            logger.info(f"Running mris_fix_topology for {self.hemi}...")
            mris_fix_topology(
                subject=self.config.subject_id,
                hemi=self.hemi,
                sphere=qsphere_nofix,
                inflated=inflated_nofix,
                orig=orig_nofix,
                output_premesh=premesh,
                mgz=True,
                ga=True,
                seed=1234,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Step 2: Remesh (if needed)
        # mris_remesh --remesh --iters 3 --input orig.premesh --output orig
        if not orig.exists():
            logger.info(f"Remeshing {self.hemi}.orig.premesh to {self.hemi}.orig...")
            # Note: mris_remesh uses --desired-face-area, but recon-all uses --remesh --iters
            # The current implementation uses mris_remesh with desired-face-area=1.0, which
            # produces equivalent results to recon-all's remeshing step. The face area of 1.0
            # is a standard value that works well for most surfaces.
            mris_remesh(
                input_surf=premesh,
                output_surf=orig,
                desired_face_area=1.0,  # Default remesh area
                log_file=self.config.log_file,
            )
        
        # Step 3: Remove intersections
        # mris_remove_intersection ../surf/{hemi}.orig ../surf/{hemi}.orig
        logger.info(f"Removing intersections from {self.hemi}.orig...")
        mris_remove_intersection(
            input_surf=orig,
            output_surf=orig,
            log_file=self.config.log_file,
        )
        
        # Remove inflated.nofix (as done by recon-all after fix)
        inflated_nofix = self.hemi_path("inflated.nofix")
        if inflated_nofix.exists():
            logger.info(f"Removing {self.hemi}.inflated.nofix (no longer needed after fix)")
            inflated_nofix.unlink()
        
        # Fix oriented surfaces if needed
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

