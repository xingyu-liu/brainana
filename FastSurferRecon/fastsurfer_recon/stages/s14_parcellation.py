"""
Stage 14: Parcellation Mapping

Maps volume labels to surface parcellation.
"""

from pathlib import Path
import logging

from .base import HemisphereStage
from ..processing.parcellation import sample_parcellation, smooth_aparc_files
from ..wrappers.recon_all import recon_all_cortex_label, recon_all_smooth2_inflate2_curvHK
from ..wrappers.mris import mris_smooth, mris_inflate

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
        
        # Optional: Apply additional smoothing and inflation adjustments for monkey/non-human data
        # This allows fine-tuning after recon-all's default smooth2/inflate2
        # Only apply if inflate2_iterations is explicitly set (not None) - this is for visualization inflation
        if self.config.processing.inflate2_iterations is not None:
            logger.info(f"Applying post-processing adjustments for {self.hemi} (inflate2 visualization adjustment)...")
            
            smoothwm = self.hemi_path("smoothwm")
            inflated = self.hemi_path("inflated")
            white_preaparc = self.hemi_path("white.preaparc")
            
            if not smoothwm.exists() or not inflated.exists() or not white_preaparc.exists():
                logger.warning(
                    f"Cannot apply post-processing adjustments: missing surfaces. "
                    f"smoothwm exists: {smoothwm.exists()}, "
                    f"inflated exists: {inflated.exists()}, "
                    f"white.preaparc exists: {white_preaparc.exists()}"
                )
            else:
                # Re-smooth smoothwm with configured iterations (smooth2 for visualization)
                logger.info(f"Re-smoothing {self.hemi}.smoothwm with {self.config.processing.smooth2_iterations} iterations (smooth2 for visualization)...")
                # Create temporary smoothed version
                smoothwm_adjusted = self.hemi_path("smoothwm.adjusted")
                mris_smooth(
                    input_surf=white_preaparc,
                    output_surf=smoothwm_adjusted,
                    n_iterations=self.config.processing.smooth2_iterations,
                    nw=True,
                    seed=1234,
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
                # Replace original with adjusted version
                smoothwm_adjusted.replace(smoothwm)
                logger.info(f"Replaced {self.hemi}.smoothwm with adjusted version ({self.config.processing.smooth2_iterations} iterations)")
                # Update smoothwm path for inflation
                smoothwm = self.hemi_path("smoothwm")
                
                # Re-inflate inflated with configured iterations (inflate2 for visualization)
                logger.info(f"Re-inflating {self.hemi}.inflated with {self.config.processing.inflate2_iterations} iterations (inflate2 for visualization)...")
                # Create temporary inflated version
                inflated_adjusted = self.hemi_path("inflated.adjusted")
                mris_inflate(
                    input_surf=smoothwm,
                    output_surf=inflated_adjusted,
                    n_iterations=self.config.processing.inflate2_iterations,
                    no_save_sulc=False,  # For inflation2, we want to keep sulc
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
                # Replace original with adjusted version
                inflated_adjusted.replace(inflated)
                logger.info(f"Replaced {self.hemi}.inflated with adjusted version ({self.config.processing.inflate2_iterations} iterations)")
    
    def should_skip(self) -> bool:
        """Skip if mapped parcellation exists."""
        aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
        return aparc_mapped.exists()

