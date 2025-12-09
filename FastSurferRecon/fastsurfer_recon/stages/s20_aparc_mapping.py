"""
Stage 20: Aparc Volume Mapping

Maps surface parcellation to volume to create aparc+aseg.mapped.mgz.
"""

from pathlib import Path
import logging

from .base import PipelineStage
from ..wrappers.mri import mri_surf2volseg

logger = logging.getLogger(__name__)


class AparcMapping(PipelineStage):
    """Map surface parcellation to volume."""
    
    name = "aparc_mapping"
    description = "Map surface parcellation to volume"
    
    def _run(self) -> None:
        """Map aparc to volume."""
        aseg = self.sd.mri("aseg.mgz")
        if not aseg.exists():
            raise FileNotFoundError(
                "aseg.mgz not found. Run aseg_refinement stage first."
            )
        
        aparc_mapped = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.mapped.mgz")
        if aparc_mapped.exists():
            logger.info("aparc+aseg.mapped.mgz already exists, skipping")
            return
        
        logger.info("Mapping surface parcellation to volume...")
        mri_surf2volseg(
            output_vol=aparc_mapped,
            input_aseg=aseg,
            subject=self.config.subject_id,
            lh_annot=self.sd.label_dir / f"lh.aparc.{self.config.atlas.name}atlas.mapped.annot",
            rh_annot=self.sd.label_dir / f"rh.aparc.{self.config.atlas.name}atlas.mapped.annot",
            lh_cortex_mask=self.sd.label_dir / "lh.cortex.label",
            rh_cortex_mask=self.sd.label_dir / "rh.cortex.label",
            lh_white=self.sd.surf_dir / "lh.white",
            rh_white=self.sd.surf_dir / "rh.white",
            lh_pial=self.sd.surf_dir / "lh.pial",
            rh_pial=self.sd.surf_dir / "rh.pial",
            label_cortex=True,
            threads=self.threads,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
        
        # Create symlinks for compatibility
        aparc_atlas = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.mgz")
        aparc_generic = self.sd.mri("aparc+aseg.mgz")
        
        if not aparc_atlas.exists():
            logger.info(f"Creating symlink: aparc.{self.config.atlas.name}atlas+aseg.mgz")
            aparc_atlas.symlink_to(aparc_mapped.name)
        
        if not aparc_generic.exists():
            logger.info("Creating symlink: aparc+aseg.mgz")
            aparc_generic.symlink_to(aparc_mapped.name)
    
    def should_skip(self) -> bool:
        """Skip if aparc+aseg.mapped.mgz exists."""
        return self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.mapped.mgz").exists()

