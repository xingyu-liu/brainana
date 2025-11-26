"""
Stage 16: Surface Registration

Registers surface to fsaverage (optional).
"""

from pathlib import Path
import logging
import shutil

from .base import HemisphereStage
from ..wrappers.recon_all import recon_all_sphere, recon_all_jacobian_white_avgcurv
from ..wrappers.mris import mris_register, mris_ca_label
from ..processing.spherical import compute_sphere_rotation
from ..wrappers.base import get_fs_home

logger = logging.getLogger(__name__)


class Registration(HemisphereStage):
    """Register surface to fsaverage."""
    
    name = "registration"
    description = "Surface registration to fsaverage"
    
    def _run(self) -> None:
        """Register surface."""
        if not (self.config.processing.fsaparc or self.config.processing.fssurfreg):
            logger.info(f"Skipping registration for {self.hemi} (not requested)")
            return
        
        sphere_reg = self.hemi_path("sphere.reg")
        if sphere_reg.exists():
            logger.info(f"{self.hemi}.sphere.reg already exists, skipping")
            return
        
        # Create sphere if needed
        sphere = self.hemi_path("sphere")
        if not sphere.exists():
            logger.info(f"Creating {self.hemi}.sphere...")
            recon_all_sphere(
                subject=self.config.subject_id,
                hemi=self.hemi,
                hires=self.config.hires,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )
        
        # Get fsaverage paths
        fs_home = get_fs_home()
        fsaverage_sphere = fs_home / "subjects" / "fsaverage" / "surf" / f"{self.hemi}.sphere"
        fsaverage_aparc = fs_home / "subjects" / "fsaverage" / "label" / f"{self.hemi}.aparc.annot"
        folding_atlas = fs_home / "average" / f"{self.hemi}.folding.atlas.acfb40.noaparc.i12.2016-08-02.tif"
        
        # Compute rotation angles
        angles_file = self.hemi_path("angles.txt")
        if not angles_file.exists():
            logger.info(f"Computing rotation angles for {self.hemi}...")
            aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
            compute_sphere_rotation(
                src_sphere_path=sphere,
                src_aparc_path=aparc_mapped,
                trg_sphere_path=fsaverage_sphere,
                trg_aparc_path=fsaverage_aparc,
                output_path=angles_file,
            )
        
        # Read rotation angles
        with open(angles_file) as f:
            angles = f.read().strip()
        
        # Register sphere
        logger.info(f"Registering {self.hemi} sphere to fsaverage...")
        mris_register(
            input_sphere=sphere,
            target_atlas=folding_atlas,
            output_sphere=sphere_reg,
            curv=True,
            norot=True,
            rotate=angles,
            threads=self.threads,
            log_file=self.config.log_file,
        )
        
        # Create FS aparc if requested
        if self.config.processing.fsaparc:
            aparc_fs = self.hemi_label("aparc.annot")
            if not aparc_fs.exists():
                logger.info(f"Creating FS aparc for {self.hemi}...")
                cp_atlas = fs_home / "average" / f"{self.hemi}.DKaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs"
                mris_ca_label(
                    subject=self.config.subject_id,
                    hemi=self.hemi,
                    sphere_reg=sphere_reg,
                    atlas=cp_atlas,
                    output_annot=aparc_fs,
                    cortex_label=self.hemi_label("cortex.label"),
                    aseg=self.sd.mri("aseg.presurf.mgz"),
                    seed=1234,
                    log_file=self.config.log_file,
                )
        
        # Compute jacobian and avgcurv
        logger.info(f"Computing jacobian and avgcurv for {self.hemi}...")
        recon_all_jacobian_white_avgcurv(
            subject=self.config.subject_id,
            hemi=self.hemi,
            hires=self.config.hires,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
    
    def is_disabled(self) -> bool:
        """Check if registration is disabled."""
        return not (self.config.processing.fsaparc or self.config.processing.fssurfreg)
    
    def should_skip(self) -> bool:
        """Skip if sphere.reg exists."""
        return self.hemi_path("sphere.reg").exists()

