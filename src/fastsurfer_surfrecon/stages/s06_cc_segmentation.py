"""
Stage 06: Corpus Callosum Segmentation

Adds corpus callosum segmentation to aseg (optional for non-human).
"""

from pathlib import Path
import logging
import shutil

from .base import PipelineStage
from ..wrappers.mri import mri_cc
from ..processing.segmentation import paint_cc_from_pred

logger = logging.getLogger(__name__)


class CCSegmentation(PipelineStage):
    """Add corpus callosum segmentation."""
    
    name = "cc_segmentation"
    description = "Corpus callosum segmentation"
    
    def _run(self) -> None:
        """Add CC to aseg."""
        if self.config.processing.no_cc:
            logger.info("Skipping CC segmentation (--no-cc flag set)")
            # Just copy aseg.auto_noCCseg to aseg.auto (no CC labels added)
            # This aligns with recon-surf.sh line 690-691
            aseg_nocc = self.sd.mri("aseg.auto_noCCseg.mgz")
            aseg_auto = self.sd.mri("aseg.auto.mgz")
            
            if not aseg_nocc.exists():
                raise FileNotFoundError(
                    f"ERROR: aseg.auto_noCCseg.mgz not found! "
                    "Cannot create aseg.auto.mgz without aseg.auto_noCCseg.mgz."
                )
            
            if not aseg_auto.exists():
                logger.info("Copying aseg.auto_noCCseg.mgz to aseg.auto.mgz (no CC)")
                shutil.copy(aseg_nocc, aseg_auto)
            return
        
        aseg_auto = self.sd.mri("aseg.auto.mgz")
        cc_lta = self.sd.transform("cc_up.lta")
        
        logger.info("Creating CC segmentation...")
        
        aseg_nocc = self.sd.mri("aseg.auto_noCCseg.mgz")
        mri_cc(
            aseg_no_cc=aseg_nocc,
            output_aseg=aseg_auto,
            output_lta=cc_lta,
            subject=self.config.subject_id,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
        
        # Add CC to deep segmentation if it exists
        aseg_orig = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.orig.mgz")
        aseg_deep = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.deep.withCC.mgz")
        if aseg_orig.exists() and not aseg_deep.exists():
            logger.info("Adding CC to deep segmentation...")
            paint_cc_from_pred(
                target_path=aseg_orig,
                source_path=aseg_auto,
                output_path=aseg_deep,
            )
    
    def is_disabled(self) -> bool:
        """
        Check if CC segmentation is disabled.
        
        Note: Even when disabled, we still need to run to create aseg.auto.mgz
        by copying aseg.auto_noCCseg.mgz. So this returns False.
        """
        return False
    
    def should_skip(self) -> bool:
        """Skip if aseg.auto exists."""
        aseg_auto = self.sd.mri("aseg.auto.mgz")
        return aseg_auto.exists()

