"""
Stage 16: Compute Morphometry

Computes morphometry (curvature, area, thickness) from surfaces.
"""

import logging

from .base import HemisphereStage
from ..wrappers.mris import (
    mris_place_surface_curv_map,
    mris_place_surface_area_map,
    mris_place_surface_thickness,
)

logger = logging.getLogger(__name__)


class ComputeMorphometry(HemisphereStage):
    """Compute morphometry from white and pial surfaces."""
    
    name = "compute_morphometry"
    description = "Compute morphometry (curvature, area, thickness)"
    
    def _run(self) -> None:
        """Compute morphometry from surfaces.
        
        This stage computes morphometry(curvature, area, thickness)
        
        Morphometry files provide surface-based measurements used for analysis:
          - Curvature: local surface curvature (Gaussian and mean curvature)
          - Area: surface area per vertex
          - Thickness: cortical thickness (distance between white and pial surfaces)
        """
        white = self.hemi_path("white")
        pial = self.hemi_path("pial")
        
        if not white.exists():
            raise FileNotFoundError(f"white surface not found for {self.hemi}")
        if not pial.exists():
            raise FileNotFoundError(f"pial surface not found for {self.hemi}")
        
        logger.info(f"Computing morphometry for {self.hemi}...")
        
        # Curvature maps: measure local surface curvature
        # These are computed separately for white and pial surfaces
        curv_white = self.hemi_path("curv")
        mris_place_surface_curv_map(
            surface=white,
            output_curv=curv_white,
            n_smooth=2,  # Smoothing iterations for curvature computation
            n_iterations=10,  # Iterations for curvature estimation
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
        
        curv_pial = self.hemi_path("curv.pial")
        mris_place_surface_curv_map(
            surface=pial,
            output_curv=curv_pial,
            n_smooth=2,
            n_iterations=10,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
        
        # Area maps: surface area per vertex
        # These measure the local surface area around each vertex
        area_white = self.hemi_path("area")
        mris_place_surface_area_map(
            surface=white,
            output_area=area_white,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
        
        area_pial = self.hemi_path("area.pial")
        mris_place_surface_area_map(
            surface=pial,
            output_area=area_pial,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
    
        # Thickness: cortical thickness map
        # Measures the distance between white and pial surfaces at each vertex.
        # This is a key morphometric measure used in many neuroimaging analyses.
        thickness = self.hemi_path("thickness")
        mris_place_surface_thickness(
            white_surf=white,
            pial_surf=pial,
            output_thickness=thickness,
            n_smooth=20,  # Smoothing iterations for thickness map
            n_iterations=5,  # Iterations for thickness computation
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )

    def should_skip(self) -> bool:
        """Skip if """
        return (
            False
        )
