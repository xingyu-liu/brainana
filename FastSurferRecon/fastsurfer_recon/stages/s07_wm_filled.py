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
        
        # Create filled volume using direct commands (replacing recon-all normalization2_maskbfs_fill)
        if not filled.exists():
            logger.info("Creating filled.mgz...")
            
            # Step 1: Intensity Normalization2
            # mri_normalize -seed 1234 -mprage -noconform -aseg aseg.presurf.mgz -mask brainmask.mgz norm.mgz brain.mgz
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
                
                # Pre-conversion: mri_normalize -seed 1234 -mprage -noconform -aseg aseg.presurf.mgz -mask brainmask.mgz norm.mgz brain.mgz
                # Note: Pre does NOT use -g flag
                mri_normalize(
                    input_vol=norm,
                    output_vol=brain,
                    aseg=aseg_presurf,
                    mask=brainmask,
                    noconform=True,
                    seed=1234,
                    mprage=True,
                    g=0,  # Explicitly disable -g flag to match pre-conversion (no -g flag)
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
            else:
                logger.info("brain.mgz already exists")
            
            # Step 2: Mask BFS
            # mri_mask -T 5 brain.mgz brainmask.mgz brain.finalsurfs.mgz
            if not brain_finalsurfs.exists():
                logger.info("Creating brain.finalsurfs.mgz (masked brain.mgz)...")
                # Pre-conversion: mri_mask -T 5 brain.mgz brainmask.mgz brain.finalsurfs.mgz
                mri_mask(
                    input_vol=brain,
                    mask=brainmask,
                    output_vol=brain_finalsurfs,
                    threshold=5,  # Pre uses 5, not 5.0
                    log_file=self.config.log_file,
                    subject_dir=self.sd.subject_dir,
                )
            else:
                logger.info("brain.finalsurfs.mgz already exists")
            
            # Step 3: Fill
            # Pre-conversion: mri_fill -a ../scripts/ponscc.cut.log -segmentation aseg.presurf.mgz -ctab ... wm.mgz filled.mgz
            logger.info("Creating filled.mgz from wm.mgz...")
            cut_log = self.sd.scripts_dir / "ponscc.cut.log"
            # Pre-conversion always includes -a flag, so we should always pass it
            if not cut_log.exists():
                logger.warning(f"ponscc.cut.log not found at {cut_log}, but pre-conversion always includes it")
            mri_fill(
                wm_vol=wm,
                output_vol=filled,
                aseg=aseg_presurf,
                cut_log=cut_log,  # Always pass cut_log to match pre-conversion (even if it doesn't exist)
                ctab=None,  # Use FreeSurfer default SubCorticalMassLUT.txt
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
            
            # Copy filled.mgz to filled.auto.mgz (as done by recon-all)
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

