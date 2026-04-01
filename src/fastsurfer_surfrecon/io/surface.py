"""
Surface I/O utilities for FastSurfer surface reconstruction.
"""

from pathlib import Path
import subprocess

import nibabel as nib


def convert_fs_surface_to_gifti(
    input_surf: str | Path,
    output_gii: str | Path,
    *,
    apply_cras: bool = True,
) -> Path:
    """
    Convert a FreeSurfer surface to GIFTI format.

    Parameters
    ----------
    input_surf : str or Path
        Input FreeSurfer surface (e.g., lh.white)
    output_gii : str or Path
        Output GIFTI surface path (e.g., lh.white.surf.gii)
    apply_cras : bool, default=True
        If True, apply CRAS translation from FreeSurfer surface metadata
        directly to vertex coordinates in the output GIFTI.

    Returns
    -------
    Path
        Output GIFTI path
    """
    input_surf = Path(input_surf)
    output_gii = Path(output_gii)
    output_gii.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["mris_convert", str(input_surf), str(output_gii)],
        check=True,
        capture_output=True,
        text=True,
    )

    if apply_cras:
        gifti_img = nib.load(str(output_gii))
        vertices = gifti_img.darrays[0].data

        _, _, header_info = nib.freesurfer.read_geometry(str(input_surf), read_metadata=True)
        c_ras = header_info.get("cras")
        if c_ras is None:
            raise RuntimeError(f"Missing CRAS metadata in surface header: {input_surf}")

        vertices += c_ras
        gifti_img.darrays[0].data = vertices
        gifti_img.to_filename(str(output_gii))

    return output_gii


__all__ = ["convert_fs_surface_to_gifti"]
