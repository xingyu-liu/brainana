"""
Stage 12: Topology Fix

Fixes topological defects in surface.
"""

from pathlib import Path
import logging
import shutil

from .base import HemisphereStage
from ..wrappers.mris import mris_fix_topology, mris_remove_intersection
from ..wrappers.mris import mris_smooth, mris_inflate
from ..processing.surface_fix import fix_surface_orientation
from ..processing.spherical import spherically_project_surface
from ..processing.topology_fix import get_euler_number, repair_surface_pymeshfix

logger = logging.getLogger(__name__)


class TopologyFix(HemisphereStage):
    """Fix topological defects."""
    
    name = "topology_fix"
    description = "Topology fix (fix)"
    
    def _run(self) -> None:
        """Fix topological defects in surface.
        
        This stage performs a multi-step topology correction process:
        1. Fix topology using mris_fix_topology (creates orig.premesh)
        2. Copy premesh to orig (if needed)
        3. Remove surface intersections
        4. Clean up temporary files (inflated.nofix)
        5. Fix surface orientation
        6. Recreate smoothwm from fixed orig 
        7. Recreate inflated from smoothwm 
        8. Recreate sphere from smoothwm
        
        The topology fix is critical for ensuring the surface has correct topology
        (genus 0, no handles) required for spherical mapping and parcellation.
        """
        orig = self.hemi_path("orig")
        # Prepare inputs for topology fix
        # FreeSurfer's mris_fix_topology expects qsphere.nofix as input.
        # Our spectral projection (stage 11) creates qsphere.nofix directly, but this
        # fallback handles edge cases (e.g., if using FreeSurfer qsphere or legacy data
        # where only sphere exists).
        qsphere_nofix = self.hemi_path("qsphere.nofix")
        sphere = self.hemi_path("sphere")
        if not qsphere_nofix.exists() and sphere.exists():
            logger.info(f"Creating {self.hemi}.qsphere.nofix from {self.hemi}.sphere (fallback for FreeSurfer qsphere)")
            shutil.copy(sphere, qsphere_nofix)
        
        # Verify all required inputs exist before proceeding
        # These files should have been created in previous stages:
        #   - qsphere.nofix: stage 11 (spherical projection)
        #   - inflated.nofix: stage 10 (inflation)
        #   - orig.nofix: stage 08 (tessellation)
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
        
        # Step 1: Fix topology using mris_fix_topology
        # This command identifies and fixes topological defects (handles, holes) in the surface.
        # It uses the spherical representation (qsphere.nofix) and inflated surface to guide
        # the topology correction. The -ga flag enables automatic genus adjustment.
        # Output: orig.premesh (preliminary mesh with fixed topology)
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
                mgz=True,  # Use mgz format for volumes
                ga=True,   # Enable automatic genus adjustment
                seed=1234, # Fixed seed for reproducibility
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # If premesh has Euler != 2, run pymeshfix iteratively (max 5) to close boundary
        # edges and fix orientation; stop when Euler == 2.
        premesh_for_orig = premesh
        euler = get_euler_number(premesh)
        if euler is not None and euler != 2:
            premesh_pymeshfix = self.hemi_path("orig.premesh.pymeshfix")
            max_iterations = 5
            logger.info(f"Premesh Euler number {euler} (target 2). Running pymeshfix up to {max_iterations} iterations...")
            current_input = premesh
            for iteration in range(max_iterations):
                # Use temp output when input and output would be the same path
                if current_input.resolve() == premesh_pymeshfix.resolve():
                    output_path = premesh_pymeshfix.parent / (premesh_pymeshfix.name + ".tmp")
                else:
                    output_path = premesh_pymeshfix
                if not repair_surface_pymeshfix(current_input, output_path):
                    logger.warning(f"pymeshfix failed at iteration {iteration + 1}, using current mesh")
                    break
                if output_path.suffix == ".tmp":
                    shutil.move(output_path, premesh_pymeshfix)
                euler_after = get_euler_number(premesh_pymeshfix)
                logger.info(f"  Iteration {iteration + 1}: Euler = {euler_after}")
                if euler_after is not None and euler_after == 2:
                    logger.info(f"  Topology corrected (Euler=2) after {iteration + 1} iteration(s)")
                    premesh_for_orig = premesh_pymeshfix
                    break
                current_input = premesh_pymeshfix
            else:
                premesh_for_orig = premesh_pymeshfix
                logger.warning(f"Euler still != 2 after {max_iterations} iterations; using pymeshfix result")
        elif euler is not None and euler == 2:
            logger.info(f"Premesh already has correct topology (Euler=2), skipping pymeshfix")

        # Step 2: Copy premesh to orig (final fixed surface)
        # The premesh (or pymeshfix result) is the topology-fixed version that becomes the final orig surface.
        if not orig.exists():
            logger.info(f"Copying {self.hemi}.orig.premesh to {self.hemi}.orig...")
            shutil.copy(premesh_for_orig, orig)
        
        # Step 3: Remove surface intersections
        # Even after topology fix, the surface may have self-intersections.
        # This step removes any remaining intersections to ensure a clean surface.
        logger.info(f"Removing intersections from {self.hemi}.orig...")
        mris_remove_intersection(
            input_surf=orig,
            output_surf=orig,  # In-place operation
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
        
        # Step 4: Clean up temporary files
        # inflated.nofix is no longer needed after topology fix (it was only needed as input).
        # This matches recon-all behavior and frees up disk space.
        inflated_nofix = self.hemi_path("inflated.nofix")
        if inflated_nofix.exists():
            logger.info(f"Removing {self.hemi}.inflated.nofix (no longer needed after fix)")
            inflated_nofix.unlink()
        
        # Step 5: Fix surface orientation
        # Ensure the surface has correct vertex ordering (consistent normal direction).
        # This creates a backup (orig.noorient) before fixing if needed.
        fix_surface_orientation(
            surface_path=orig,
            backup_path=self.hemi_path("orig.noorient"),
        )
        
        # Step 6: re-create smoothwm from fixed orig after topology fix
        smoothwm = self.hemi_path("smoothwm")
        if not smoothwm.exists():
            logger.info(f"Creating {self.hemi}.smoothwm from fixed {self.hemi}.orig (smooth, {self.config.processing.smooth_iterations} iterations)...")
            mris_smooth(
                input_surf=orig,
                output_surf=smoothwm,
                n_iterations=self.config.processing.smooth_iterations,
                nw=True,
                seed=1234,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
        
        # Step 7: re-create inflated from smoothwm after topology fix
        inflated = self.hemi_path("inflated")
        if not inflated.exists():
            logger.info(f"Creating {self.hemi}.inflated from {self.hemi}.smoothwm (inflate2, {self.config.processing.inflate2_iterations or 'default'} iterations)...")
            mris_inflate(
                input_surf=smoothwm,
                output_surf=inflated,
                n_iterations=self.config.processing.inflate_iterations,
                no_save_sulc=False,  # Save sulc file for visualization
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
        
        # Step 8: Re-create sphere from smoothwm after topology fix
        # So sphere has the same vertex count as orig/smoothwm/white/pial (post-fix mesh).
        smoothwm = self.hemi_path("smoothwm")
        sphere = self.hemi_path("sphere")
        qsphere = self.hemi_path("qsphere")

        logger.info(f"Re-creating {self.hemi}.sphere from {self.hemi}.smoothwm (post-topology-fix)...")
        spherically_project_surface(
            input_path=smoothwm,
            output_path=sphere,
            threads=self.threads,
        )
        shutil.copy(sphere, qsphere)

    def should_skip(self) -> bool:
        """Skip if orig exists."""
        return self.hemi_path("orig").exists()

