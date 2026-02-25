"""
Stage 22: WM Parcellation Mapping

Maps surface parcellation to white matter volume to create wmparc.mapped.mgz.
"""

from pathlib import Path
import logging

from .base import PipelineStage
from ..wrappers.mri import mri_surf2volseg

logger = logging.getLogger(__name__)


class WMParcMapping(PipelineStage):
    """Map surface parcellation to white matter volume."""
    
    name = "wmparc_mapping"
    description = "Map surface parcellation to white matter"
    
    def _run(self) -> None:
        """Map aparc to white matter volume."""
        ribbon = self.sd.mri("ribbon.mgz")
        if not ribbon.exists():
            raise FileNotFoundError(
                "ribbon.mgz not found. Run cortical_ribbon stage first."
            )
        
        aparc_mapped = self.sd.mri(f"aparc.{self.config.atlas.name}atlas+aseg.mapped.mgz")
        if not aparc_mapped.exists():
            raise FileNotFoundError(
                "aparc+aseg.mapped.mgz not found. Run aparc_mapping stage first."
            )
        
        wmparc_mapped = self.sd.mri(f"wmparc.{self.config.atlas.name}atlas.mapped.mgz")
        logger.info("Mapping surface parcellation to white matter volume...")
        mri_surf2volseg(
            output_vol=wmparc_mapped,
            input_aseg=aparc_mapped,
            lh_annot=self.sd.label_dir / f"lh.aparc.{self.config.atlas.name}atlas.mapped.annot",
            rh_annot=self.sd.label_dir / f"rh.aparc.{self.config.atlas.name}atlas.mapped.annot",
            lh_cortex_mask=self.sd.label_dir / "lh.cortex.label",
            rh_cortex_mask=self.sd.label_dir / "rh.cortex.label",
            lh_white=self.sd.surf_dir / "lh.white",
            rh_white=self.sd.surf_dir / "rh.white",
            lh_pial=self.sd.surf_dir / "lh.pial",
            rh_pial=self.sd.surf_dir / "rh.pial",
            label_wm=True,
            lh_annot_offset=3000,  # WM parcellation uses 3000/4000 offsets
            rh_annot_offset=4000,
            threads=self.threads,
            log_file=self.config.log_file,
            subject_dir=self.sd.subject_dir,
        )
        
        # Create or refresh symlink for compatibility (redo: ensure it points to new .mapped.mgz)
        wmparc_generic = self.sd.mri("wmparc.mgz")
        if wmparc_generic.exists():
            wmparc_generic.unlink()
        wmparc_generic.symlink_to(wmparc_mapped.name)
        logger.info("Symlink wmparc.mgz -> %s", wmparc_mapped.name)
    
    # def should_skip(self) -> bool:
    #     """Skip if wmparc.mapped.mgz exists."""
    #     return self.sd.mri(f"wmparc.{self.config.atlas.name}atlas.mapped.mgz").exists()

    def should_skip(self) -> bool:
        """Skip if """
        return (
            False
        )