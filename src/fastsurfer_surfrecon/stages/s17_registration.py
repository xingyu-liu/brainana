"""
Stage 17: Surface Registration

Registers surface to fsaverage (human) or a custom template (e.g. sub-MEBRAIN for macaque).
"""

import logging

from .base import HemisphereStage
from ..wrappers.base import run_recon_all, get_fs_home
from ..wrappers.mris import mris_register, mris_ca_label
from ..processing.spherical import compute_sphere_rotation

logger = logging.getLogger(__name__)


def _template_paths(config, hemi: str):
    """Resolve template sphere, annot, and folding atlas paths.

    Choice A (single path): config.registration_template is path to template subject dir.
    Choice A (convention): fsaverage uses aparc.annot; custom template uses aparc.{atlas.name}atlas.mapped.annot.
    """
    template_dir = getattr(config, "registration_template", None) and config.registration_template
    if template_dir:
        sphere = template_dir / "surf" / f"{hemi}.sphere"
        annot = template_dir / "label" / f"{hemi}.aparc.{config.atlas.name}atlas.mapped.annot"
        folding_atlas = template_dir / "atlas" / f"{hemi}.folding.atlas.tif"
        return sphere, annot, folding_atlas, True  # use_custom_template
    
    fs_home = get_fs_home()
    sphere = None # fs_home / "subjects" / "fsaverage" / "surf" / f"{hemi}.sphere"
    annot = None # fs_home / "subjects" / "fsaverage" / "label" / f"{hemi}.aparc.annot"
    folding_atlas = None # fs_home / "average" / f"{hemi}.folding.atlas.acfb40.noaparc.i12.2016-08-02.tif"
    
    return sphere, annot, folding_atlas, False


class Registration(HemisphereStage):
    """Register surface to fsaverage or custom template (e.g. sub-MEBRAIN)."""

    name = "registration"
    description = "Surface registration to template"

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
            flags = []
            if self.config.hires:
                flags.append("-hires")
            run_recon_all(
                subject=self.config.subject_id,
                hemi=self.hemi,
                steps=["-sphere"],
                flags=flags,
                threads=self.threads,
                log_file=self.config.log_file,
                subjects_dir=self.config.subjects_dir,
            )

        template_sphere, template_aparc, folding_atlas, use_custom_template = _template_paths(
            self.config, self.hemi
        )
        if use_custom_template:
            logger.info(f"Using registration template: {self.config.registration_template}")

        # Compute rotation angles
        angles_file = self.hemi_path("angles.txt")
        if not angles_file.exists():
            logger.info(f"Computing rotation angles for {self.hemi}...")
            aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
            compute_sphere_rotation(
                src_sphere_path=sphere,
                src_aparc_path=aparc_mapped,
                trg_sphere_path=template_sphere,
                trg_aparc_path=template_aparc,
                output_path=angles_file,
            )

        # Read rotation angles
        with open(angles_file) as f:
            angles = f.read().strip()

        # Register sphere
        logger.info(f"Registering {self.hemi} sphere to template...")
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

        # Create FS aparc only for fsaverage (human); skip when using custom template (no GCS atlas)
        if self.config.processing.fsaparc and not use_custom_template:
            fs_home = get_fs_home()
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
        flags = []
        if self.config.hires:
            flags.append("-hires")
        run_recon_all(
            subject=self.config.subject_id,
            hemi=self.hemi,
            steps=["-jacobian_white", "-avgcurv"],
            flags=flags,
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

