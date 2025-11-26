"""
Configuration system for FastSurfer surface reconstruction.

Uses Pydantic for validation and YAML for configuration files.
"""

from pathlib import Path
from typing import Optional, Literal
import os

import yaml
import nibabel as nib
from pydantic import BaseModel, Field, field_validator, model_validator


class AtlasConfig(BaseModel):
    """Atlas configuration."""
    
    name: str = Field(default="ARM2", description="Atlas name (e.g., ARM2, DKT)")
    lut_dir: Optional[Path] = Field(
        default=None, 
        description="Custom LUT directory. If None, uses package default."
    )
    
    @field_validator("name")
    @classmethod
    def validate_atlas_name(cls, v: str) -> str:
        """Normalize atlas name to uppercase."""
        return v.upper()
    
    @property
    def colorlut_path(self) -> Optional[Path]:
        """Get path to ColorLUT file."""
        if self.lut_dir:
            lut_path = self.lut_dir / f"{self.name}_ColorLUT.tsv"
            if lut_path.exists():
                return lut_path
        
        # Try FastSurferRecon package default
        from pathlib import Path
        package_lut = Path(__file__).parent / "atlas" / "lut" / self.name / f"{self.name}_ColorLUT.tsv"
        if package_lut.exists():
            return package_lut
        
        # Try FastSurferCNN atlas directory (common when both packages are in same repo)
        # Check relative to FastSurferRecon: ../FastSurferCNN/atlas/atlas-{name}/{name}_ColorLUT.tsv
        fastsurfercnn_lut = Path(__file__).parent.parent.parent.parent / "FastSurferCNN" / "atlas" / f"atlas-{self.name}" / f"{self.name}_ColorLUT.tsv"
        if fastsurfercnn_lut.exists():
            return fastsurfercnn_lut
        
        # Try importing FastSurferCNN to find its location
        try:
            import FastSurferCNN
            fastsurfercnn_dir = Path(FastSurferCNN.__file__).parent
            fastsurfercnn_lut = fastsurfercnn_dir / "atlas" / f"atlas-{self.name}" / f"{self.name}_ColorLUT.tsv"
            if fastsurfercnn_lut.exists():
                return fastsurfercnn_lut
        except (ImportError, AttributeError):
            pass
        
        return None
    
    def get_hemi_lut(self, hemi: str) -> Path:
        """Get hemisphere-specific lookup table path."""
        if self.lut_dir:
            return self.lut_dir / f"{hemi}.lookup.txt"
        # Try package default
        from pathlib import Path
        package_lut = Path(__file__).parent / "atlas" / "lut" / self.name / f"{hemi}.lookup.txt"
        if not package_lut.exists():
            raise FileNotFoundError(f"Lookup table not found: {package_lut}")
        return package_lut
    
    def get_lut(self) -> Path:
        """Get main lookup table path."""
        if self.lut_dir:
            return self.lut_dir / "lookup.txt"
        # Try package default
        from pathlib import Path
        package_lut = Path(__file__).parent / "atlas" / "lut" / self.name / "lookup.txt"
        if not package_lut.exists():
            raise FileNotFoundError(f"Lookup table not found: {package_lut}")
        return package_lut


class ProcessingConfig(BaseModel):
    """Processing options configuration."""
    
    # Threading
    threads: int = Field(default=1, ge=1, description="Number of threads")
    parallel_hemis: bool = Field(
        default=True, 
        description="Process hemispheres in parallel"
    )
    
    # Volume options
    hires_threshold: float = Field(
        default=0.999,
        description="Voxel size threshold below which hires mode is used"
    )
    hires: bool | Literal["auto"] = Field(
        default='auto',
        description="High-resolution mode. Use True/False to force, or 'auto' to detect from voxel size"
    )
    
    # Non-human options (default True for macaque)
    skip_cc: bool = Field(
        default=True,
        description="Skip corpus callosum segmentation (for non-human)"
    )
    skip_talairach: bool = Field(
        default=True,
        description="Skip Talairach registration (for non-human)"
    )
    skip_topology_fix: bool = Field(
        default=False,
        description="Skip topology fix (use orig.nofix directly)"
    )
    
    # Method choices
    use_fs_tessellation: bool = Field(
        default=False,
        description="Use FreeSurfer mri_tesselate instead of marching cubes"
    )
    use_fs_qsphere: bool = Field(
        default=False,
        description="Use FreeSurfer qsphere instead of spectral projection"
    )
    use_fs_aparc: bool = Field(
        default=False,
        description="Use FreeSurfer aparc instead of mapped parcellation"
    )
    do_surf_reg: bool = Field(
        default=False,
        description="Run surface registration to fsaverage"
    )
    
    # Additional options
    get_t1: bool = Field(
        default=False,
        description="Create T1.mgz (for compatibility with downstream tools)"
    )
    atlas_3t: bool = Field(
        default=False,
        description="Use 3T Talairach atlas instead of 1.5T"
    )
    
    # Bias correction
    n4_shrink_factor: int = Field(default=4, ge=1, description="N4 shrink factor")
    n4_num_iterations: int = Field(default=50, ge=1, description="N4 iterations per level")
    n4_levels: int = Field(default=4, ge=1, description="N4 fitting levels")
    
    # Aliases for backward compatibility with recon-surf.sh flags
    @property
    def no_cc(self) -> bool:
        """Alias for skip_cc."""
        return self.skip_cc
    
    @property
    def no_talairach(self) -> bool:
        """Alias for skip_talairach."""
        return self.skip_talairach
    
    @property
    def nofix(self) -> bool:
        """Alias for skip_topology_fix."""
        return self.skip_topology_fix
    
    @property
    def fstess(self) -> bool:
        """Alias for use_fs_tessellation."""
        return self.use_fs_tessellation
    
    @property
    def fsqsphere(self) -> bool:
        """Alias for use_fs_qsphere."""
        return self.use_fs_qsphere
    
    @property
    def fsaparc(self) -> bool:
        """Alias for use_fs_aparc."""
        return self.use_fs_aparc
    
    @property
    def fssurfreg(self) -> bool:
        """Alias for do_surf_reg."""
        return self.do_surf_reg


class ReconSurfConfig(BaseModel):
    """Main configuration for surface reconstruction pipeline."""
    
    # Required inputs
    subject_id: str = Field(..., description="Subject ID")
    subjects_dir: Path = Field(..., description="FreeSurfer subjects directory")
    # Note: t1_input and segmentation are optional - if not provided, 
    # we assume orig.mgz and aparc+aseg.orig.mgz already exist in mri/
    t1_input: Optional[Path] = Field(
        default=None, 
        description="T1-weighted input image (conformed). If None, assumes orig.mgz exists."
    )
    segmentation: Optional[Path] = Field(
        default=None,
        description="Segmentation file (aparc+aseg). If None, assumes aparc+aseg.orig.mgz exists."
    )
    
    # Optional inputs
    mask: Optional[Path] = Field(default=None, description="Brain mask file")
    
    # Sub-configurations
    atlas: AtlasConfig = Field(default_factory=AtlasConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    
    # Output control
    log_file: Optional[Path] = Field(default=None, description="Log file path")
    verbose: int = Field(default=1, ge=0, le=2, description="Verbosity level (0-2)")
    
    # Environment
    freesurfer_home: Optional[Path] = Field(
        default=None,
        description="FREESURFER_HOME path. If None, uses environment variable."
    )
    
    @field_validator("subjects_dir", "t1_input", "segmentation", mode="before")
    @classmethod
    def resolve_path(cls, v: Path | str) -> Path:
        """Resolve paths to absolute."""
        if v is None:
            return v
        return Path(v).expanduser().resolve()
    
    @field_validator("mask", "log_file", "freesurfer_home", mode="before")
    @classmethod
    def resolve_optional_path(cls, v: Path | str | None) -> Path | None:
        """Resolve optional paths to absolute."""
        if v is None:
            return None
        return Path(v).expanduser().resolve()
    
    @model_validator(mode="after")
    def validate_inputs(self) -> "ReconSurfConfig":
        """Validate that input files exist."""
        # If t1_input is provided, check it exists
        if self.t1_input is not None and not self.t1_input.exists():
            raise ValueError(f"T1 input file not found: {self.t1_input}")
        # If segmentation is provided, check it exists
        if self.segmentation is not None and not self.segmentation.exists():
            raise ValueError(f"Segmentation file not found: {self.segmentation}")
        # Check mask if provided
        if self.mask is not None and not self.mask.exists():
            raise ValueError(f"Mask file not found: {self.mask}")
        return self
    
    @model_validator(mode="after")
    def validate_freesurfer(self) -> "ReconSurfConfig":
        """Validate FreeSurfer environment."""
        if self.freesurfer_home is None:
            fs_home = os.environ.get("FREESURFER_HOME")
            if fs_home:
                self.freesurfer_home = Path(fs_home)
        
        if self.freesurfer_home is None:
            raise ValueError(
                "FREESURFER_HOME not set. Either set the environment variable "
                "or provide freesurfer_home in config."
            )
        
        if not self.freesurfer_home.exists():
            raise ValueError(f"FREESURFER_HOME does not exist: {self.freesurfer_home}")
        
        return self
    
    @property
    def subject_dir(self) -> Path:
        """Get the subject's directory."""
        return self.subjects_dir / self.subject_id
    
    @property
    def mri_dir(self) -> Path:
        """Get the subject's mri directory."""
        return self.subject_dir / "mri"
    
    @property
    def surf_dir(self) -> Path:
        """Get the subject's surf directory."""
        return self.subject_dir / "surf"
    
    @property
    def label_dir(self) -> Path:
        """Get the subject's label directory."""
        return self.subject_dir / "label"
    
    @property
    def stats_dir(self) -> Path:
        """Get the subject's stats directory."""
        return self.subject_dir / "stats"
    
    @property
    def scripts_dir(self) -> Path:
        """Get the subject's scripts directory."""
        return self.subject_dir / "scripts"
    
    @property
    def hires(self) -> bool:
        """
        Get resolved hires value.
        
        If processing.hires is "auto", detects from voxel size of orig.mgz.
        Otherwise returns the boolean value directly.
        """
        if self.processing.hires == "auto":
            orig_path = self.mri_dir / "orig.mgz"
            if not orig_path.exists():
                # If orig.mgz doesn't exist yet, default to False
                return False
            try:
                img = nib.load(orig_path)
                vox_size = img.header.get_zooms()[0]
                return vox_size < self.processing.hires_threshold
            except Exception:
                # If we can't read the voxel size, default to False
                return False
        return bool(self.processing.hires)
    
    @classmethod
    def from_yaml(cls, config_path: Path, **overrides) -> "ReconSurfConfig":
        """
        Load configuration from YAML file.
        
        Parameters
        ----------
        config_path : Path
            Path to YAML configuration file
        **overrides
            Override values from command line
            
        Returns
        -------
        ReconSurfConfig
            Validated configuration
        """
        with open(config_path) as f:
            config_dict = yaml.safe_load(f) or {}
        
        # Apply overrides
        for key, value in overrides.items():
            if value is not None:
                if "." in key:
                    # Handle nested keys like "processing.threads"
                    parts = key.split(".")
                    d = config_dict
                    for part in parts[:-1]:
                        d = d.setdefault(part, {})
                    d[parts[-1]] = value
                else:
                    config_dict[key] = value
        
        return cls(**config_dict)
    
    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        # Convert to dict, handling Path objects
        def path_representer(dumper, data):
            return dumper.represent_scalar("tag:yaml.org,2002:str", str(data))
        
        yaml.add_representer(Path, path_representer)
        
        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
    
    def setup_directories(self) -> None:
        """Create the FreeSurfer subject directory structure."""
        for dir_path in [
            self.mri_dir,
            self.mri_dir / "transforms",
            self.mri_dir / "tmp",
            self.surf_dir,
            self.label_dir,
            self.stats_dir,
            self.scripts_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

