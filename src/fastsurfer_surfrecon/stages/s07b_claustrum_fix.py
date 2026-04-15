"""
Stage 07b: Claustrum Fix

Patches brain.finalsurfs.mgz by filling claustrum voxels with the normalized
WM intensity value (110). This prevents the claustrum region from creating
spurious surface topology during tessellation.

Only runs when ``mri/aparc.ARM6atlas+aseg.orig.mgz`` is present in the subject
directory (written there by the fastsurfer_nn prep step when an ARM6 atlas is
provided). Skipped silently when the file is absent.
"""

import shutil
import logging

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

from .base import PipelineStage

logger = logging.getLogger(__name__)

# FreeSurfer's normalized WM control-point intensity (target of mri_normalize -mprage)
WM_NORMALIZED_INTENSITY = 110

# ARM6 atlas label IDs for left/right claustrum, mapped to side index {1=lh, 2=rh}
ARM6_CLAUSTRUM = {504: 1, 1504: 2}

# Primary-seg label IDs for left/right claustrum (ARM2 atlas; no-op for other atlases)
SEG_CLAUSTRUM = {502: 1, 1502: 2}


class ClaustrumFix(PipelineStage):
    """
    Fill claustrum voxels in brain.finalsurfs.mgz with normalized WM intensity.

    Uses the ARM6 atlas (``aparc.ARM6atlas+aseg.orig.mgz``) to locate the
    claustrum, intersects with the primary segmentation
    (``aparc+aseg.orig.mgz``) for a tighter mask, dilates by one voxel, then
    sets those voxels to the WM intensity in ``brain.finalsurfs.mgz``.

    The original ``brain.finalsurfs.mgz`` is preserved as
    ``brain.finalsurfs_orig.mgz`` before modification.
    """

    name = "claustrum_fix"
    description = "Claustrum fix (fill claustrum with WM intensity in brain.finalsurfs)"

    # ------------------------------------------------------------------
    # Skip / disable logic
    # ------------------------------------------------------------------

    def is_disabled(self) -> bool:
        """Skip entirely when ARM6 atlas was not prepared."""
        return not self.sd.mri("aparc.ARM6atlas+aseg.orig.mgz").exists()

    def should_skip(self) -> bool:
        """Skip if fix has already been applied (backup sentinel exists)."""
        return self.sd.mri("brain.finalsurfs_orig.mgz").exists()

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _run(self) -> None:
        arm6_f = self.sd.mri("aparc.ARM6atlas+aseg.orig.mgz")
        seg_f = self.sd.mri("aparc+aseg.orig.mgz")
        brain_f = self.sd.mri("brain.finalsurfs.mgz")

        for path, label in [
            (arm6_f, "ARM6 atlas"),
            (seg_f, "primary segmentation"),
            (brain_f, "brain.finalsurfs"),
        ]:
            if not path.exists():
                raise FileNotFoundError(f"{label} not found: {path}")

        claustrum_mask = self._build_claustrum_mask(arm6_f, seg_f)

        n_voxels = int(np.sum(claustrum_mask > 0))
        if n_voxels == 0:
            logger.warning(
                "Claustrum mask is empty — no claustrum labels found in the "
                "intersection of ARM6 atlas and primary segmentation. "
                "brain.finalsurfs.mgz will not be modified."
            )
            return

        logger.info(f"Claustrum mask: {n_voxels} voxels to fill")
        self._apply_fix(brain_f, claustrum_mask)

    def _build_claustrum_mask(
        self,
        arm6_f,
        seg_f,
    ) -> np.ndarray:
        """
        Build the claustrum mask as the intersection of ARM6 and primary seg,
        per hemisphere, with a 1-voxel dilation applied to the ARM6 mask first.

        Returns an int16 array with values 1 (lh) / 2 (rh) / 0 (background).
        """
        arm6_data = nib.load(arm6_f).get_fdata().astype(np.int16)
        seg_data = nib.load(seg_f).get_fdata().astype(np.int16)

        structure = ndi.generate_binary_structure(rank=3, connectivity=1)

        # Build ARM6 claustrum mask and dilate per side
        arm6_mask = np.zeros_like(arm6_data, dtype=np.int16)
        for label_id, side in ARM6_CLAUSTRUM.items():
            arm6_mask[arm6_data == label_id] = side

        arm6_mask_dilated = np.zeros_like(arm6_mask)
        for side in np.unique(arm6_mask):
            if side == 0:
                continue
            dilated = ndi.binary_dilation(arm6_mask == side, structure=structure, iterations=1)
            arm6_mask_dilated[dilated] = side
        arm6_mask = arm6_mask_dilated

        # Build primary-seg claustrum mask (no dilation needed)
        seg_mask = np.zeros_like(seg_data, dtype=np.int16)
        for label_id, side in SEG_CLAUSTRUM.items():
            seg_mask[seg_data == label_id] = side

        # Intersect per side
        sides = set(ARM6_CLAUSTRUM.values()) & set(SEG_CLAUSTRUM.values())
        final_mask = np.zeros_like(arm6_mask, dtype=np.int16)
        for side in sides:
            final_mask[(arm6_mask == side) & (seg_mask == side)] = side

        return final_mask

    def _apply_fix(self, brain_f, claustrum_mask: np.ndarray) -> None:
        """Back up brain.finalsurfs.mgz and fill claustrum voxels with WM intensity."""
        backup_f = self.sd.mri("brain.finalsurfs_orig.mgz")
        shutil.copy(brain_f, backup_f)
        logger.info(f"Backed up brain.finalsurfs.mgz → {backup_f.name}")

        brain_reader = nib.load(brain_f)
        brain_data = brain_reader.get_fdata().copy()

        for side in np.unique(claustrum_mask):
            if side == 0:
                continue
            n = int(np.sum(claustrum_mask == side))
            hemi = "lh" if side == 1 else "rh"
            logger.info(f"  Filling {hemi} claustrum: {n} voxels → {WM_NORMALIZED_INTENSITY}")
            brain_data[claustrum_mask == side] = WM_NORMALIZED_INTENSITY

        nib.save(
            nib.MGHImage(brain_data, brain_reader.affine, brain_reader.header),
            brain_f,
        )
        logger.info(f"Saved patched brain.finalsurfs.mgz")
