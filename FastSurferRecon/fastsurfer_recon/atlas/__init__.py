"""
Atlas definitions and lookup tables for FastSurfer surface reconstruction.

Provides atlas-specific configurations and label mappings.
"""

from pathlib import Path
from typing import Optional

# Package directory for LUT files
LUT_DIR = Path(__file__).parent / "lut"


def get_lut_path(atlas: str, hemi: Optional[str] = None) -> Path:
    """
    Get path to lookup table file.
    
    Parameters
    ----------
    atlas : str
        Atlas name (e.g., 'ARM2', 'DKT')
    hemi : str, optional
        Hemisphere ('lh' or 'rh'). If None, returns general LUT.
        
    Returns
    -------
    Path
        Path to LUT file
        
    Raises
    ------
    FileNotFoundError
        If LUT file doesn't exist
    """
    atlas_upper = atlas.upper()
    atlas_dir = LUT_DIR / atlas_upper
    
    if hemi:
        lut_file = atlas_dir / f"{hemi}.lookup.txt"
    else:
        lut_file = atlas_dir / "lookup.txt"
    
    if not lut_file.exists():
        raise FileNotFoundError(f"LUT file not found: {lut_file}")
    
    return lut_file


def list_atlases() -> list[str]:
    """
    List available atlases.
    
    Returns
    -------
    list[str]
        List of atlas names with LUT directories
    """
    if not LUT_DIR.exists():
        return []
    
    return [d.name for d in LUT_DIR.iterdir() if d.is_dir()]


__all__ = [
    "get_lut_path",
    "list_atlases",
    "LUT_DIR",
]

