"""
Stage 15: Surface Placement

Places white and pial surfaces.
"""

import logging
import shutil

from .base import HemisphereStage
from ..wrappers.mris import mris_place_surface

logger = logging.getLogger(__name__)


class SurfacePlacement(HemisphereStage):
    """Place white and pial surfaces."""
    
    name = "surface_placement"
    description = "White and pial surface placement"
    
    def _run(self) -> None:
        """Place white and pial surfaces.
        
        This stage performs the final surface placement:
        1. Place white surface from white.preaparc
        2. Place pial surface from white surface
        
        The white and pial surfaces are the final cortical boundaries used for
        statistics and analysis.
        """
        white = self.hemi_path("white")
        pial = self.hemi_path("pial")
        pial_t1 = self.hemi_path("pial.T1")
        
        # Determine which parcellation annotation to use for surface placement
        # This helps guide surface placement by providing cortical region information
        if self.config.processing.fsaparc:
            aparc = self.hemi_label("aparc.annot")  # FreeSurfer aparc
        else:
            aparc = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")  # Mapped atlas parcellation
        
        # Get cortex labels for surface placement
        # cortex.label: cortical ribbon (used for white surface)
        # cortex+hipamyg.label: cortical ribbon + hippocampus + amygdala (used for pial surface)
        cortex_label = self.hemi_label("cortex.label")
        cortex_hipamyg_label = self.hemi_label("cortex+hipamyg.label")
        
        # Step 1: Place white surface
        # The white surface is placed from white.preaparc, which was created in stage 13.
        # This is the final white matter surface boundary.
        if not white.exists():
            logger.info(f"Placing {self.hemi} white surface...")
            mris_place_surface(
                input_surf=self.hemi_path("white.preaparc"),
                output_surf=white,
                hemi=self.hemi,
                wm=self.sd.mri("wm.mgz"),
                invol=self.sd.mri("brain.finalsurfs.mgz"),
                aseg=self.sd.mri("aseg.presurf.mgz"),
                adgws_in=self.sdir / f"autodet.gw.stats.{self.hemi}.dat",
                white=True,
                threads=self.threads,
                rip_label=cortex_label,
                rip_bg=True,
                rip_surf=self.hemi_path("white.preaparc"),
                aparc=aparc if aparc.exists() else None,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Step 2: Place pial surface
        # The pial surface is placed from the white surface, extending outward to the
        # pial boundary. It uses cortex+hipamyg.label to include hippocampus and amygdala
        # regions. The pial surface is initially created as pial.T1, then copied to pial.
        if not pial_t1.exists():
            logger.info(f"Placing {self.hemi} pial surface...")
            mris_place_surface(
                input_surf=white,
                output_surf=pial_t1,
                hemi=self.hemi,
                wm=self.sd.mri("wm.mgz"),
                invol=self.sd.mri("brain.finalsurfs.mgz"),
                aseg=self.sd.mri("aseg.presurf.mgz"),
                adgws_in=self.sdir / f"autodet.gw.stats.{self.hemi}.dat",
                pial=True,
                threads=self.threads,
                rip_label=cortex_hipamyg_label if cortex_hipamyg_label.exists() else cortex_label,
                pin_medial_wall=cortex_label,  # Pin medial wall to prevent expansion
                repulse_surf=white,  # Repulse from white surface
                white_surf=white,  # Reference white surface
                aparc=aparc if aparc.exists() else None,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Copy pial.T1 to pial (standard naming convention)
        if not pial.exists():
            if pial_t1.exists():
                shutil.copy(pial_t1, pial)
            else:
                raise FileNotFoundError(f"pial.T1 not found for {self.hemi}")
    
    def should_skip(self) -> bool:
        """Skip if white and pial exist."""
        return (
            self.hemi_path("white").exists() and
            self.hemi_path("pial").exists()
        )

