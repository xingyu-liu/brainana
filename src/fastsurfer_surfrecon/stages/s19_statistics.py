"""
Stage 18: Statistics

Computes surface statistics and morphometry.
"""

import logging
import re

import numpy as np

from pathlib import Path

from .base import HemisphereStage
from ..wrappers.base import run_recon_all
from ..wrappers.mris import mris_anatomical_stats

logger = logging.getLogger(__name__)


# First column width for StructName in stats output (match FreeSurfer fixed-width format)
_STATS_STRUCT_NAME_WIDTH = 40


def _fix_mapped_stats_struct_names(stats_file: Path, hemi_lut_path: Path) -> None:
    """
    Restore full structure names in a mapped.stats file.

    mris_anatomical_stats (FreeSurfer) writes only the part of the struct name
    after the last '/', so e.g. "SI/SII" becomes "SII". This breaks alignment with
    atlas lookup names. We reload names from the hemisphere LUT and replace any
    truncated StructName (first data column) with the full name, preserving
    FreeSurfer's fixed-width column format.
    """
    if not hemi_lut_path.exists():
        return
    # Load LUT names (column index 1 = struct name)
    names = np.loadtxt(hemi_lut_path, usecols=(1,), dtype=str)
    # Map suffix (part after '/') -> full name for names that contain '/'
    suffix_to_full = {}
    for n in names:
        n = n.strip()
        if "/" in n:
            suffix_to_full[n.split("/")[-1]] = n
    if not suffix_to_full:
        return
    # Rewrite stats file: preserve header lines; fix first column in data lines
    # while keeping fixed-width format (StructName left-aligned in _STATS_STRUCT_NAME_WIDTH chars)
    lines = stats_file.read_text().splitlines()
    out = []
    in_data = False
    for line in lines:
        if line.startswith("#"):
            out.append(line)
            if "ColHeaders" in line:
                in_data = True
            continue
        if not in_data:
            out.append(line)
            continue
        # Preserve original layout: first column (struct name) then rest of line unchanged
        m = re.match(r"(\S+)(\s+)(.*)", line)
        if not m:
            out.append(line)
            continue
        struct_name, _padding, rest = m.groups()
        if struct_name in suffix_to_full:
            struct_name = suffix_to_full[struct_name]
        out.append(struct_name.ljust(_STATS_STRUCT_NAME_WIDTH) + rest)
    stats_file.write_text("\n".join(out) + "\n")
    logger.debug(f"Fixed struct names in {stats_file.name}")


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
                # Restore full struct names (mris_anatomical_stats keeps only part after '/')
                hemi_lut = self.config.atlas.get_hemi_lut(self.hemi)
                _fix_mapped_stats_struct_names(stats_file, hemi_lut)
            elif stats_file.exists():
                # Fix struct names in existing file (e.g. from a previous run with truncated names)
                hemi_lut = self.config.atlas.get_hemi_lut(self.hemi)
                _fix_mapped_stats_struct_names(stats_file, hemi_lut)
        
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

