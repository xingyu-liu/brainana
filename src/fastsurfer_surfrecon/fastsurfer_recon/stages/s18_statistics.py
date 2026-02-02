"""
Stage 18: Statistics

Computes surface statistics and morphometry.
"""

import logging

from .base import HemisphereStage
from ..wrappers.base import run_recon_all
from ..wrappers.mris import mris_anatomical_stats

logger = logging.getLogger(__name__)


class Statistics(HemisphereStage):
    """Compute surface statistics."""
    
    name = "statistics"
    description = "Surface statistics and morphometry"
    
    def _run(self) -> None:
        """Compute statistics."""
        # Curvature statistics
        logger.info(f"Computing curvature statistics for {self.hemi}...")
        flags = []
        if self.config.hires:
            flags.append("-hires")
        run_recon_all(
            subject=self.config.subject_id,
            hemi=self.hemi,
            steps=["-curvstats"],
            flags=flags,
            threads=self.threads,
            log_file=self.config.log_file,
            subjects_dir=self.config.subjects_dir,
        )
        
        # Anatomical statistics for mapped parcellation
        aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
        if aparc_mapped.exists():
            # Use .mapped.stats filename to match original FastSurfer
            stats_file = self.sd.stats_dir / f"{self.hemi}.aparc.{self.config.atlas.name}atlas.mapped.stats"
            if not stats_file.exists():
                logger.info(f"Computing anatomical stats for {self.hemi}...")
                # Color table path (may not exist, but mris_anatomical_stats can work without it)
                ctab_path = self.sd.label_dir / "aparc.annot.mapped.ctab"
                mris_anatomical_stats(
                    subject=self.config.subject_id,
                    hemi=self.hemi,
                    surface=self.hemi_path("white"),
                    annotation=aparc_mapped,
                    output_stats=stats_file,
                    cortex_label=self.hemi_label("cortex.label"),
                    ctab=ctab_path if ctab_path.exists() else None,
                    noxfm=self.config.processing.no_talairach,
                    log_file=self.config.log_file,
                    subjects_dir=self.config.subjects_dir,
                )
        
        # FS aparc stats if available
        if self.config.processing.fsaparc:
            aparc_fs = self.hemi_label("aparc.annot")
            if aparc_fs.exists():
                stats_fs = self.sd.stats_dir / f"{self.hemi}.aparc.stats"
                if not stats_fs.exists():
                    logger.info(f"Computing FS aparc stats for {self.hemi}...")
                    mris_anatomical_stats(
                        subject=self.config.subject_id,
                        hemi=self.hemi,
                        surface=self.hemi_path("white"),
                        annotation=aparc_fs,
                        output_stats=stats_fs,
                        cortex_label=self.hemi_label("cortex.label"),
                        noxfm=self.config.processing.no_talairach,
                        log_file=self.config.log_file,
                    )
    
    def should_skip(self) -> bool:
        """Skip if stats already computed."""
        # Check for curvature stats
        curvstats = self.sd.stats_dir / f"{self.hemi}.curv.stats"
        if not curvstats.exists():
            return False
        
        # Check for parcellation stats
        aparc_mapped = self.hemi_label(f"aparc.{self.config.atlas.name}atlas.mapped.annot")
        if aparc_mapped.exists():
            stats = self.sd.stats_dir / f"{self.hemi}.aparc.{self.config.atlas.name}atlas.mapped.stats"
            if not stats.exists():
                return False
        
        return True

