"""
Stage 15: Surface Placement

Places white and pial surfaces.
"""

from pathlib import Path
import logging
import shutil

from .base import HemisphereStage
from ..wrappers.mris import (
    mris_place_surface,
    mris_place_surface_curv_map,
    mris_place_surface_area_map,
    mris_place_surface_thickness,
)

logger = logging.getLogger(__name__)


class SurfacePlacement(HemisphereStage):
    """Place white and pial surfaces."""
    
    name = "surface_placement"
    description = "White and pial surface placement"
    
    def _run(self) -> None:
        """Place white and pial surfaces."""
        white = self.hemi_path("white")
        pial = self.hemi_path("pial")
        pial_t1 = self.hemi_path("pial.T1")
        
        if white.exists() and pial.exists():
            logger.info(f"{self.hemi} white and pial already exist, skipping")
            return
        
        # Determine which parcellation to use
        if self.config.processing.fsaparc:
            aparc = self.hemi_label("aparc.annot")
        else:
            aparc = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
        
        cortex_label = self.hemi_label("cortex.label")
        cortex_hipamyg_label = self.hemi_label("cortex+hipamyg.label")
        
        # Place white surface
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
            )
        
        # Place pial surface
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
                pin_medial_wall=cortex_label,
                repulse_surf=white,
                white_surf=white,
                aparc=aparc if aparc.exists() else None,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
        
        # Link pial.T1 to pial
        if not pial.exists():
            if pial_t1.exists():
                shutil.copy(pial_t1, pial)
            else:
                raise FileNotFoundError(f"pial.T1 not found for {self.hemi}")
        
        # Compute morphometry
        logger.info(f"Computing morphometry for {self.hemi}...")
        
        # Curvature maps
        curv_white = self.hemi_path("curv")
        if not curv_white.exists():
            mris_place_surface_curv_map(
                surface=white,
                output_curv=curv_white,
                n_smooth=2,
                n_iterations=10,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
        
        curv_pial = self.hemi_path("curv.pial")
        if not curv_pial.exists():
            mris_place_surface_curv_map(
                surface=pial,
                output_curv=curv_pial,
                n_smooth=2,
                n_iterations=10,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
        
        # Area maps
        area_white = self.hemi_path("area")
        if not area_white.exists():
            mris_place_surface_area_map(
                surface=white,
                output_area=area_white,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
        
        area_pial = self.hemi_path("area.pial")
        if not area_pial.exists():
            mris_place_surface_area_map(
                surface=pial,
                output_area=area_pial,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
        
        # Thickness
        thickness = self.hemi_path("thickness")
        if not thickness.exists():
            mris_place_surface_thickness(
                white_surf=white,
                pial_surf=pial,
                output_thickness=thickness,
                n_smooth=20,
                n_iterations=5,
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
    
    def should_skip(self) -> bool:
        """Skip if white, pial, and morphometry exist."""
        return (
            self.hemi_path("white").exists() and
            self.hemi_path("pial").exists() and
            self.hemi_path("thickness").exists()
        )

