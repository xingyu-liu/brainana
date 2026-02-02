"""
Stage 07: WM Segmentation and Filled Volume

Creates wm.mgz and filled.mgz for surface tessellation.
"""

from pathlib import Path
import logging
import shutil

from .base import PipelineStage
from ..processing.segmentation import create_wm_from_file
from ..wrappers.mri import mri_normalize, mri_mask, mri_fill

logger = logging.getLogger(__name__)


class WMFilled(PipelineStage):
    """Create WM segmentation and filled volume."""
    
    name = "wm_filled"
    description = "WM segmentation and filled volume"
    
    def _run(self) -> None:
        """Create WM and filled volumes."""
        wm = self.sd.mri("wm.mgz")
        filled = self.sd.mri("filled.mgz")
        aseg_presurf = self.sd.mri("aseg.presurf.mgz")
        norm = self.sd.mri("norm.mgz")
        brainmask = self.sd.mri("brainmask.mgz")
        brain = self.sd.mri("brain.mgz")
        brain_finalsurfs = self.sd.mri("brain.finalsurfs.mgz")
        
        # Create WM segmentation
        if not wm.exists():
            logger.info("Creating wm.mgz from aseg...")
            aseg_auto = self.sd.mri("aseg.auto.mgz")
            
            # Get ColorLUT path from atlas config
            colorlut = self.config.atlas.colorlut_path
            if not colorlut or not Path(colorlut).exists():
                raise FileNotFoundError(
                    f"ColorLUT not found: {colorlut}. "
                    "WM segmentation requires a ColorLUT with wm_id column."
                )
            
            create_wm_from_file(
                input_path=aseg_auto,
                output_path=wm,
                lut_path=colorlut,
            )
        else:
            logger.info("wm.mgz already exists")
        
        # Copy aseg.auto to aseg.presurf
        if not aseg_presurf.exists():
            aseg_auto = self.sd.mri("aseg.auto.mgz")
            shutil.copy(aseg_auto, aseg_presurf)
        
        # Create filled volume using direct commands
        # This replaces recon-all's normalization2_maskbfs_fill step, which performs:
        #   1. Intensity normalization (creates brain.mgz)
        #   2. Masking with threshold (creates brain.finalsurfs.mgz)
        #   3. Filling white matter (creates filled.mgz)
        #
        # Note: brain.mgz and brain.finalsurfs.mgz are created here as part of the
        # filled.mgz creation process. They are only used within this stage and
        # for surface placement in later stages, so creating them here is appropriate.
        if not filled.exists():
            logger.info("Creating filled.mgz...")
            
            # Step 1: Intensity Normalization2
            # Normalize norm.mgz to create brain.mgz with intensity normalization.
            # This uses aseg.presurf.mgz and brainmask.mgz to guide normalization.
            # The -mprage flag indicates MPRAGE sequence, and -noconform preserves
            # the original voxel dimensions.
            if not brain.exists():
                logger.info("Creating brain.mgz (normalized norm.mgz)...")
                if not norm.exists():
                    raise FileNotFoundError(
                        f"norm.mgz not found at {norm}. "
                        "This should be created in stage 05 (norm_t1)."
                    )
                if not brainmask.exists():
                    raise FileNotFoundError(
                        f"brainmask.mgz not found at {brainmask}. "
                        "This should be created in stage 05 (norm_t1)."
                    )
                
                mri_normalize(
                    input_vol=norm,
                    output_vol=brain,
                    aseg=aseg_presurf,
                    mask=brainmask,
                    noconform=True,  # Preserve original voxel dimensions
                    seed=1234,  # Fixed seed for reproducibility
                    mprage=True,  # MPRAGE sequence
                    g=0,  # No gradient correction
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
            else:
                logger.info("brain.mgz already exists")
            
            # Step 2: Mask BFS (Brain Final Surfaces)
            # Apply brainmask to brain.mgz with threshold=5 to create brain.finalsurfs.mgz.
            # This volume is used for final surface placement (white and pial surfaces).
            # The threshold removes low-intensity voxels outside the brain mask.
            if not brain_finalsurfs.exists():
                logger.info("Creating brain.finalsurfs.mgz (masked brain.mgz)...")
                mri_mask(
                    input_vol=brain,
                    mask=brainmask,
                    output_vol=brain_finalsurfs,
                    threshold=5,  # Threshold for masking
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
            else:
                logger.info("brain.finalsurfs.mgz already exists")
            
            # Step 3: Fill white matter
            # Fill white matter segmentation to create a continuous volume for tessellation.
            # This fills holes and gaps in the white matter segmentation, creating a
            # filled volume that is used as input for surface tessellation (stage 08).
            # The cut_log file (ponscc.cut.log) contains information about corpus
            # callosum cuts, if available.
            logger.info("Creating filled.mgz from wm.mgz...")
            cut_log = self.sd.scripts_dir / "ponscc.cut.log"
            if not cut_log.exists():
                logger.warning(f"ponscc.cut.log not found at {cut_log} (may not be available for non-human data)")
            mri_fill(
                wm_vol=wm,
                output_vol=filled,
                aseg=aseg_presurf,
                cut_log=cut_log,  # Optional: corpus callosum cut information
                ctab=None,  # Use FreeSurfer default SubCorticalMassLUT.txt
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
            
            # Copy filled.mgz to filled.auto.mgz (as done by recon-all)
            # This maintains compatibility with FreeSurfer naming conventions.
            filled_auto = self.sd.mri("filled.auto.mgz")
            if not filled_auto.exists():
                logger.info("Copying filled.mgz to filled.auto.mgz")
                shutil.copy(filled, filled_auto)
        else:
            logger.info("filled.mgz already exists")
    
    def should_skip(self) -> bool:
        """Skip if wm, filled, and aseg.presurf exist."""
        return (
            self.sd.mri("wm.mgz").exists() and
            self.sd.mri("filled.mgz").exists() and
            self.sd.mri("aseg.presurf.mgz").exists()
        )

