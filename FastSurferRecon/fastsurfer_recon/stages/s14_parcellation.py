"""
Stage 14: Parcellation Mapping

Maps volume labels to surface parcellation.
"""

import logging

import nibabel.freesurfer.io as fs

from .base import HemisphereStage
from ..processing.parcellation import sample_parcellation, smooth_aparc_files
from ..wrappers.base import run_recon_all
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
            flags = []
            if self.config.hires:
                flags.append("-hires")
            run_recon_all(
                subject=self.config.subject_id,
                hemi=self.hemi,
                steps=["-cortex-label"],
                flags=flags,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Create inflated and curvHK surfaces
        inflated = self.hemi_path("inflated")
        curv = self.hemi_path("curv")
        if not inflated.exists() or not curv.exists():
            logger.info(f"Creating inflated and curvHK for {self.hemi}...")
            flags = []
            if self.config.hires:
                flags.append("-hires")
            run_recon_all(
                subject=self.config.subject_id,
                hemi=self.hemi,
                steps=["-curvHK"],
                flags=flags,
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
        
        # Load surface once for reuse
        white_preaparc_path = self.hemi_path("white.preaparc")
        logger.info(f"Loading surface: {white_preaparc_path}")
        surface_data = fs.read_geometry(white_preaparc_path, read_metadata=True)
        surface = (surface_data[0], surface_data[1])
        
        # Sample parcellation
        aparc_prefix = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.prefix.annot")
        aseg_orig = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.orig.mgz")
        
        sample_parcellation(
            surface_path=white_preaparc_path,
            segmentation_path=aseg_orig,
            cortex_path=cortex_label,
            output_path=aparc_prefix,
            volume_lut=seg_lut,
            surface_lut=surf_lut,
            proj_mm=0.6,
            search_radius=2.0,
            surface=surface,
        )
        
        # Smooth parcellation (reuse the same surface)
        smooth_aparc_files(
            insurf=white_preaparc_path,
            inaparc=aparc_prefix,
            incort=cortex_label,
            outaparc=aparc_mapped,
            surface=surface,
        )
        
        # Optional: Apply additional smoothing and inflation adjustments for visualization
        # 
        # This section allows fine-tuning of smoothwm and inflated surfaces for non-human
        # data (e.g., monkey data) where different smoothing/inflation parameters may be
        # needed for optimal visualization. This is applied AFTER the initial smooth2/inflate2
        # steps in stage 12 (topology fix).
        #
        # IMPORTANT: These files are replaced in-place. This is safe because:
        #   - smoothwm and inflated are created in stage 12 (topology fix)
        #   - This stage (14) runs after stage 12
        #   - Stage 15 (surface placement) uses white.preaparc, not smoothwm/inflated
        #   - These are visualization surfaces, not used for surface placement
        #
        # Only apply if inflate2_iterations is explicitly set (not None), indicating
        # that custom visualization parameters are desired.
        if self.config.processing.inflate2_iterations is not None:
            logger.info(f"Applying post-processing adjustments for {self.hemi} (visualization smoothing/inflation)...")
            
            smoothwm = self.hemi_path("smoothwm")
            inflated = self.hemi_path("inflated")
            white_preaparc = self.hemi_path("white.preaparc")
            
            # Verify all required surfaces exist before proceeding
            if not smoothwm.exists() or not inflated.exists() or not white_preaparc.exists():
                logger.warning(
                    f"Cannot apply post-processing adjustments: missing surfaces. "
                    f"smoothwm exists: {smoothwm.exists()}, "
                    f"inflated exists: {inflated.exists()}, "
                    f"white.preaparc exists: {white_preaparc.exists()}"
                )
            else:
                # Re-smooth smoothwm with configured iterations (smooth2 for visualization)
                # This creates a visualization-optimized smoothwm surface with custom
                # smoothing iterations (typically 3 for monkey data vs default ~10)
                logger.info(f"Re-smoothing {self.hemi}.smoothwm with {self.config.processing.smooth2_iterations} iterations (visualization smoothing)...")
                
                # Create temporary smoothed version to avoid corrupting original if process fails
                smoothwm_adjusted = self.hemi_path("smoothwm.adjusted")
                mris_smooth(
                    input_surf=white_preaparc,  # Start from white.preaparc for consistent smoothing
                    output_surf=smoothwm_adjusted,
                    n_iterations=self.config.processing.smooth2_iterations,
                    nw=True,
                    seed=1234,
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
                
                # Atomically replace original with adjusted version
                # Using replace() ensures atomic operation (rename on Unix, copy+delete on Windows)
                smoothwm_adjusted.replace(smoothwm)
                logger.info(f"Replaced {self.hemi}.smoothwm with adjusted version ({self.config.processing.smooth2_iterations} iterations)")
                
                # Update smoothwm path reference for inflation step
                smoothwm = self.hemi_path("smoothwm")
                
                # Re-inflate inflated with configured iterations (inflate2 for visualization)
                # This creates a visualization-optimized inflated surface with custom
                # inflation iterations (typically 3 for monkey data vs default ~15-20)
                logger.info(f"Re-inflating {self.hemi}.inflated with {self.config.processing.inflate2_iterations} iterations (visualization inflation)...")
                
                # Create temporary inflated version to avoid corrupting original if process fails
                inflated_adjusted = self.hemi_path("inflated.adjusted")
                mris_inflate(
                    input_surf=smoothwm,  # Use the newly adjusted smoothwm
                    output_surf=inflated_adjusted,
                    n_iterations=self.config.processing.inflate2_iterations,
                    no_save_sulc=False,  # For visualization, we want to keep sulc file
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
                
                # Atomically replace original with adjusted version
                inflated_adjusted.replace(inflated)
                logger.info(f"Replaced {self.hemi}.inflated with adjusted version ({self.config.processing.inflate2_iterations} iterations)")
    
    def should_skip(self) -> bool:
        """Skip if mapped parcellation exists."""
        aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
        return aparc_mapped.exists()

