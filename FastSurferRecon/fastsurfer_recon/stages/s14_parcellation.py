"""
Stage 14: Parcellation Mapping

Maps volume labels to surface parcellation.
"""

from pathlib import Path
import logging

from .base import HemisphereStage
from ..processing.parcellation import sample_parcellation, smooth_aparc_files
from ..wrappers.recon_all import recon_all_cortex_label, recon_all_smooth2_inflate2_curvHK

logger = logging.getLogger(__name__)


class Parcellation(HemisphereStage):
    """Map volume labels to surface."""
    
    name = "parcellation"
    description = "Surface parcellation mapping"
    
    def _run(self) -> None:
        """Map parcellation to surface."""
        # Create cortex label
        cortex_label = self.hemi_label("cortex.label")
        if not cortex_label.exists():
            logger.info(f"Creating {self.hemi}.cortex.label...")
            recon_all_cortex_label(
                subject=self.config.subject_id,
                hemi=self.hemi,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Create inflated and curvHK surfaces
        inflated = self.hemi_path("inflated")
        curv = self.hemi_path("curv")
        if not inflated.exists() or not curv.exists():
            logger.info(f"Creating inflated and curvHK for {self.hemi}...")
            recon_all_smooth2_inflate2_curvHK(
                subject=self.config.subject_id,
                hemi=self.hemi,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Map parcellation
        aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
        if aparc_mapped.exists():
            logger.info(f"{self.hemi}.aparc.{self.config.atlas.name}atlas.mapped.annot already exists, skipping")
            return
        
        logger.info(f"Mapping parcellation to {self.hemi} surface...")
        
        # Get lookup tables
        seg_lut = self.config.atlas.get_hemi_lut(self.hemi)
        surf_lut = self.config.atlas.get_lut()
        
        # Sample parcellation
        aparc_prefix = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.prefix.annot")
        aseg_orig = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.orig.mgz")
        
        sample_parcellation(
            surface_path=self.hemi_path("white.preaparc"),
            segmentation_path=aseg_orig,
            cortex_path=cortex_label,
            output_path=aparc_prefix,
            volume_lut=seg_lut,
            surface_lut=surf_lut,
            proj_mm=0.6,
            search_radius=2.0,
        )
        
        # Smooth parcellation
        smooth_aparc_files(
            insurf=self.hemi_path("white.preaparc"),
            inaparc=aparc_prefix,
            incort=cortex_label,
            outaparc=aparc_mapped,
        )
    
    def should_skip(self) -> bool:
        """Skip if mapped parcellation exists."""
        aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
        return aparc_mapped.exists()

