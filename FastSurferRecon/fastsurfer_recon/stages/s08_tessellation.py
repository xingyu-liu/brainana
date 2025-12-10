"""
Stage 08: Surface Tessellation

Creates initial surface using marching cubes or FreeSurfer tessellation.
"""

from pathlib import Path
import logging
import re

from .base import HemisphereStage
from ..wrappers.mri import mri_pretess, mri_mc
from ..wrappers.mris import mris_info, mris_extract_main_component, mris_remesh
from ..wrappers.recon_all import recon_all_tessellate
from ..processing.surface_fix import fix_mc_surface_header

logger = logging.getLogger(__name__)


class Tessellation(HemisphereStage):
    """Create initial surface tessellation."""
    
    name = "tessellation"
    description = "Surface tessellation (orig.nofix)"
    
    def _run(self) -> None:
        """Create initial surface."""
        filled = self.sd.mri("filled.mgz")
        brain = self.sd.mri("brainmask.mgz")
        orig_nofix = self.hemi_path("orig.nofix")
        
        if orig_nofix.exists():
            logger.info(f"{self.hemi}.orig.nofix already exists, skipping")
            return
        
        if self.config.processing.fstess:
            # Use FreeSurfer tessellation
            logger.info(f"Using FreeSurfer tessellation for {self.hemi}")
            recon_all_tessellate(
                subject=self.config.subject_id,
                hemi=self.hemi,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        else:
            # Use marching cubes
            logger.info(f"Using marching cubes for {self.hemi}")
            
            # Pretessellate
            pretess = self.sd.mri(f"filled-pretess{self.hemi_value}.mgz")
            if not pretess.exists():
                mri_pretess(
                    input_vol=filled,
                    label=self.hemi_value,
                    norm=brain,
                    output_vol=pretess,
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
            
            # Marching cubes
            hires_suffix = ".predec" if self.config.hires else ""
            orig_nofix = self.hemi_path(f"orig.nofix{hires_suffix}")
            mri_mc(
                input_vol=pretess,
                label=self.hemi_value,
                output_surf=orig_nofix,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
            
            # Fix surface header (scannerRAS -> surfaceRAS)
            fix_mc_surface_header(
                surface_path=orig_nofix,
                pretess_path=pretess,
                output_path=orig_nofix,
            )
            
            # Verify surfaceRAS header
            info = mris_info(orig_nofix, log_file=self.config.log_file, subject_dir=self.sd.subject_dir)
            # Check for surfaceRAS with flexible whitespace (mris_info uses variable spacing)
            if not re.search(r"vertex\s+locs\s*:\s*surfaceRAS", info):
                logger.error(f"mris_info full output:\n{info}")
                raise RuntimeError(
                    f"Incorrect header in {orig_nofix}: "
                    "vertex locs is not set to surfaceRAS"
                )
            
            # Extract main component
            mris_extract_main_component(
                input_surf=orig_nofix,
                output_surf=orig_nofix,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
            
            # Re-fix header after extraction (mris_extract_main_component may reset it)
            fix_mc_surface_header(
                surface_path=orig_nofix,
                pretess_path=pretess,
                output_path=orig_nofix,
            )
            
            # Verify surfaceRAS header again after extraction
            info = mris_info(orig_nofix, log_file=self.config.log_file, subject_dir=self.sd.subject_dir)
            # Check for surfaceRAS with flexible whitespace (mris_info uses variable spacing)
            if not re.search(r"vertex\s+locs\s*:\s*surfaceRAS", info):
                logger.error(f"mris_info full output after extraction:\n{info}")
                raise RuntimeError(
                    f"Incorrect header in {orig_nofix} after extraction: "
                    "vertex locs is not set to surfaceRAS"
                )
            
            # Decimate for hires
            if self.config.hires:
                orig_nofix_final = self.hemi_path("orig.nofix")
                mris_remesh(
                    input_surf=orig_nofix,
                    output_surf=orig_nofix_final,
                    desired_face_area=0.5,
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
                orig_nofix = orig_nofix_final
    
    def should_skip(self) -> bool:
        """Skip if orig.nofix exists."""
        return self.hemi_path("orig.nofix").exists()

