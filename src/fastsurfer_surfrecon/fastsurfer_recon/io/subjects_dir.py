"""
FreeSurfer subjects directory structure management.

Provides a convenient interface for accessing and managing
the FreeSurfer directory structure.
"""

from pathlib import Path
from typing import Optional, Literal


HemiType = Literal["lh", "rh"]


class SubjectsDir:
    """
    Manager for FreeSurfer subjects directory structure.
    
    Provides convenient access to standard FreeSurfer paths
    and handles directory creation.
    
    Parameters
    ----------
    subjects_dir : Path
        Root subjects directory (SUBJECTS_DIR)
    subject_id : str
        Subject identifier
        
    Examples
    --------
    >>> sd = SubjectsDir(Path("/data/subjects"), "sub-001")
    >>> sd.mri_dir
    PosixPath('/data/subjects/sub-001/mri')
    >>> sd.surf("lh.white")
    PosixPath('/data/subjects/sub-001/surf/lh.white')
    """
    
    def __init__(self, subjects_dir: Path, subject_id: str):
        self.subjects_dir = Path(subjects_dir)
        self.subject_id = subject_id
    
    @property
    def subject_dir(self) -> Path:
        """Subject's root directory."""
        return self.subjects_dir / self.subject_id
    
    @property
    def mri_dir(self) -> Path:
        """Subject's mri directory."""
        return self.subject_dir / "mri"
    
    @property
    def surf_dir(self) -> Path:
        """Subject's surf directory."""
        return self.subject_dir / "surf"
    
    @property
    def label_dir(self) -> Path:
        """Subject's label directory."""
        return self.subject_dir / "label"
    
    @property
    def stats_dir(self) -> Path:
        """Subject's stats directory."""
        return self.subject_dir / "stats"
    
    @property
    def scripts_dir(self) -> Path:
        """Subject's scripts directory."""
        return self.subject_dir / "scripts"
    
    @property
    def transforms_dir(self) -> Path:
        """Subject's transforms directory."""
        return self.mri_dir / "transforms"
    
    @property
    def tmp_dir(self) -> Path:
        """Subject's tmp directory."""
        return self.mri_dir / "tmp"
    
    # File accessors
    
    def mri(self, filename: str) -> Path:
        """Get path to file in mri directory."""
        return self.mri_dir / filename
    
    def surf(self, filename: str) -> Path:
        """Get path to file in surf directory."""
        return self.surf_dir / filename
    
    def label(self, filename: str) -> Path:
        """Get path to file in label directory."""
        return self.label_dir / filename
    
    def stats(self, filename: str) -> Path:
        """Get path to file in stats directory."""
        return self.stats_dir / filename
    
    def transform(self, filename: str) -> Path:
        """Get path to file in transforms directory."""
        return self.transforms_dir / filename
    
    # Hemisphere-specific accessors
    
    def hemi_surf(self, hemi: HemiType, filename: str) -> Path:
        """
        Get hemisphere-prefixed surface path.
        
        Parameters
        ----------
        hemi : str
            Hemisphere ('lh' or 'rh')
        filename : str
            Filename without hemisphere prefix
            
        Returns
        -------
        Path
            Full path: surf/{hemi}.{filename}
        """
        return self.surf_dir / f"{hemi}.{filename}"
    
    def hemi_label(self, hemi: HemiType, filename: str) -> Path:
        """
        Get hemisphere-prefixed label path.
        
        Parameters
        ----------
        hemi : str
            Hemisphere ('lh' or 'rh')
        filename : str
            Filename without hemisphere prefix
            
        Returns
        -------
        Path
            Full path: label/{hemi}.{filename}
        """
        return self.label_dir / f"{hemi}.{filename}"
    
    # Common file shortcuts
    
    @property
    def orig(self) -> Path:
        """Path to mri/orig.mgz."""
        return self.mri("orig.mgz")
    
    @property
    def orig_nu(self) -> Path:
        """Path to mri/orig_nu.mgz."""
        return self.mri("orig_nu.mgz")
    
    @property
    def nu(self) -> Path:
        """Path to mri/nu.mgz."""
        return self.mri("nu.mgz")
    
    @property
    def norm(self) -> Path:
        """Path to mri/norm.mgz."""
        return self.mri("norm.mgz")
    
    @property
    def brain(self) -> Path:
        """Path to mri/brain.mgz."""
        return self.mri("brain.mgz")
    
    @property
    def brainmask(self) -> Path:
        """Path to mri/brainmask.mgz."""
        return self.mri("brainmask.mgz")
    
    @property
    def mask(self) -> Path:
        """Path to mri/mask.mgz."""
        return self.mri("mask.mgz")
    
    @property
    def aseg(self) -> Path:
        """Path to mri/aseg.mgz."""
        return self.mri("aseg.mgz")
    
    @property
    def wm(self) -> Path:
        """Path to mri/wm.mgz."""
        return self.mri("wm.mgz")
    
    @property
    def filled(self) -> Path:
        """Path to mri/filled.mgz."""
        return self.mri("filled.mgz")
    
    @property
    def brain_finalsurfs(self) -> Path:
        """Path to mri/brain.finalsurfs.mgz."""
        return self.mri("brain.finalsurfs.mgz")
    
    @property
    def aseg_presurf(self) -> Path:
        """Path to mri/aseg.presurf.mgz."""
        return self.mri("aseg.presurf.mgz")
    
    @property
    def ribbon(self) -> Path:
        """Path to mri/ribbon.mgz."""
        return self.mri("ribbon.mgz")
    
    @property
    def log_file(self) -> Path:
        """Path to recon-surf log file."""
        return self.scripts_dir / "recon-surf.log"
    
    @property
    def done_file(self) -> Path:
        """Path to recon-surf done file."""
        return self.scripts_dir / "recon-surf.done"
    
    # Atlas-specific paths
    
    def aparc_aseg(self, atlas: str = "DKT") -> Path:
        """
        Get path to aparc+aseg file for atlas.
        
        Parameters
        ----------
        atlas : str
            Atlas name (e.g., 'DKT', 'ARM2')
            
        Returns
        -------
        Path
            Path to mri/aparc.{atlas}atlas+aseg.*.mgz
        """
        return self.mri(f"aparc.{atlas}atlas+aseg.orig.mgz")
    
    def aparc_aseg_mapped(self, atlas: str = "DKT") -> Path:
        """Get path to mapped aparc+aseg file."""
        return self.mri(f"aparc.{atlas}atlas+aseg.mapped.mgz")
    
    def wmparc_mapped(self, atlas: str = "DKT") -> Path:
        """Get path to mapped wmparc file."""
        return self.mri(f"wmparc.{atlas}atlas.mapped.mgz")
    
    def hemi_aparc(self, hemi: HemiType, atlas: str = "DKT") -> Path:
        """Get path to hemisphere aparc annotation."""
        return self.label(f"{hemi}.aparc.{atlas}atlas.mapped.annot")
    
    # Directory management
    
    def setup(self) -> None:
        """Create the standard FreeSurfer directory structure."""
        dirs = [
            self.mri_dir,
            self.transforms_dir,
            self.tmp_dir,
            self.surf_dir,
            self.label_dir,
            self.stats_dir,
            self.scripts_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
    
    def exists(self) -> bool:
        """Check if subject directory exists."""
        return self.subject_dir.exists()
    
    def is_complete(self) -> bool:
        """Check if recon-surf has completed (done file exists)."""
        return self.done_file.exists()
    
    def __repr__(self) -> str:
        return f"SubjectsDir({self.subjects_dir!r}, {self.subject_id!r})"

