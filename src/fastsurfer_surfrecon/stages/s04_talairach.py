"""
Stage 04: Talairach Registration

Computes Talairach transform (optional for non-human data).
"""

from pathlib import Path
import logging
import shutil

from .base import PipelineStage
from ..wrappers.registration import talairach_avi, lta_convert
from ..wrappers.mri import mri_add_xform_to_header

logger = logging.getLogger(__name__)


class Talairach(PipelineStage):
    """Compute Talairach registration."""
    
    name = "talairach"
    description = "Talairach registration"
    
    def _run(self) -> None:
        """Run Talairach registration."""
        if self.config.processing.no_talairach:
            logger.info("Skipping Talairach registration (--no-talairach flag set)")
            logger.info("NOTE: eTIV (estimated total intracranial volume) will not be calculated.")
            logger.info("      This does not affect surface reconstruction or morphometry.")
            
            # Just copy orig_nu.mgz to nu.mgz (without Talairach header)
            nu = self.sd.mri("nu.mgz")
            if not nu.exists():
                logger.info("Copying orig_nu.mgz to nu.mgz (no Talairach transform)")
                shutil.copy(self.sd.orig_nu, nu)
            
            # Create dummy identity transform for tools that require it (e.g., mris_anatomical_stats)
            # Some FreeSurfer tools don't support -noxfm, so we create an identity transform
            talairach_xfm = self.sd.transform("talairach.xfm")
            if not talairach_xfm.exists():
                logger.info("Creating dummy identity talairach.xfm for compatibility")
                talairach_xfm.parent.mkdir(parents=True, exist_ok=True)
                # Create identity transform (no transformation)
                with open(talairach_xfm, "w") as f:
                    f.write("MNI Transform File\n")
                    f.write("% identity transform (no Talairach registration)\n\n")
                    f.write("Transform_Type = Linear;\n")
                    f.write("Linear_Transform = \n")
                    f.write("1.0 0.0 0.0 0.0\n")
                    f.write("0.0 1.0 0.0 0.0\n")
                    f.write("0.0 0.0 1.0 0.0;\n")
            return
        
        talairach_lta = self.sd.transform("talairach.lta")
        talairach_xfm = self.sd.transform("talairach.auto.xfm")
        
        logger.info("Computing Talairach transform...")
        
        # Determine atlas (3T vs 1.5T)
        atlas = "3T18yoSchwartzReactN32_as_orig" if self.config.processing.atlas_3t else "1.5T18yoSchwartzReactN32_as_orig"
        
        # Run talairach_avi
        talairach_avi(
            input_vol=self.sd.orig_nu,
            output_xfm=talairach_xfm,
            atlas=atlas,
            log_file=self.config.log_file,
        )
        
        # Convert xfm to lta
        lta_convert(
            src_vol=self.sd.orig,
            trg_vol=self.sd.orig,
            input_xfm=talairach_xfm,
            output_lta=talairach_lta,
            subject=self.config.subject_id,
            log_file=self.config.log_file,
        )
        
        # Add transform to nu.mgz header
        if not self.sd.mri("nu.mgz").exists():
            mri_add_xform_to_header(
                xform=talairach_xfm,
                input_vol=self.sd.orig_nu,
                output_vol=self.sd.mri("nu.mgz"),
                log_file=self.config.log_file,
                subject_dir=self.sd.subject_dir,
            )
    
    def is_disabled(self) -> bool:
        """
        Check if Talairach registration is disabled.
        
        Note: Even when disabled, we still need to run to create nu.mgz
        and the dummy talairach.xfm transform. So this returns False.
        """
        return False
    
    def should_skip(self) -> bool:
        """Skip if transforms exist (or nu.mgz and talairach.xfm if disabled)."""
        if self.config.processing.no_talairach:
            # When disabled, we need both nu.mgz and the dummy talairach.xfm
            # If either doesn't exist, we need to run to create them
            nu_exists = self.sd.mri("nu.mgz").exists()
            xfm_exists = self.sd.transform("talairach.xfm").exists()
            return nu_exists and xfm_exists
        talairach_lta = self.sd.transform("talairach.lta")
        return talairach_lta.exists()
