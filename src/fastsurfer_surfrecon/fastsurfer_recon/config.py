"""
Configuration system for FastSurfer surface reconstruction.

Uses Pydantic for validation and YAML for configuration files.
"""

from pathlib import Path
from typing import Optional, Literal
import os

import yaml

# Brainana repo root (config.py -> fastsurfer_recon -> fastsurfer_surfrecon -> src -> brainana)
_BRAINANA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
import nibabel as nib
from pydantic import BaseModel, Field, field_validator, model_validator


class AtlasConfig(BaseModel):
    """Atlas configuration."""
    
    name: str = Field(description="Atlas name (e.g., ARM2, DKT)")
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
        
        # Try fastsurfer_surfrecon package default
        from pathlib import Path
        package_lut = Path(__file__).parent / "atlas" / "lut" / self.name / f"{self.name}_ColorLUT.tsv"
        if package_lut.exists():
            return package_lut
        
        # Try fastsurfer_nn atlas directory (common when both packages are in same repo)
        # src/fastsurfer_nn/atlas/atlas-{name}/{name}_ColorLUT.tsv
        fastsurfercnn_lut = _BRAINANA_ROOT / "src" / "fastsurfer_nn" / "atlas" / f"atlas-{self.name}" / f"{self.name}_ColorLUT.tsv"
        if fastsurfercnn_lut.exists():
            return fastsurfercnn_lut
        
        # Try importing fastsurfer_nn to find its location
        try:
            import fastsurfer_nn
            fastsurfercnn_dir = Path(fastsurfer_nn.__file__).parent
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
    threads: int = Field(ge=1, description="Number of threads")
    parallel_hemis: bool = Field(
        description="Process hemispheres in parallel"
    )
    
    # Volume options
    hires_threshold: float = Field(
        description="Voxel size threshold below which hires mode is used"
    )
    hires: bool | Literal["auto"] = Field(
        description="High-resolution mode. Use True/False to force, or 'auto' to detect from voxel size"
    )
    
    # Non-human options (default True for macaque)
    skip_cc: bool = Field(
        description="Skip corpus callosum segmentation (for non-human)"
    )
    skip_talairach: bool = Field(
        description="Skip Talairach registration (for non-human)"
    )
    
    # Method choices
    use_fs_tessellation: bool = Field(
        description="Use FreeSurfer mri_tesselate instead of marching cubes"
    # )
    # use_fs_qsphere: bool = Field(
    #     description="Use FreeSurfer qsphere instead of spectral projection"
    )
    use_fs_aparc: bool = Field(
        description="Use FreeSurfer aparc instead of mapped parcellation"
    )
    do_surf_reg: bool = Field(
        description="Run surface registration to fsaverage"
    )
    
    # Additional options
    get_t1: bool = Field(
        description="Create T1.mgz (for compatibility with downstream tools)"
    )
    atlas_3t: bool = Field(
        description="Use 3T Talairach atlas instead of 1.5T"
    )
    
    # Bias correction
    n4_shrink_factor: int = Field(ge=1, description="N4 shrink factor")
    n4_num_iterations: int = Field(ge=1, description="N4 iterations per level")
    n4_levels: int = Field(ge=1, description="N4 fitting levels")
    
    # Surface smoothing and inflation (for monkey/non-human data)
    smooth_iterations: int = Field(
        ge=1, 
        description="Surface smoothing iterations for smooth1 (Stage 09, before topology fix). Creates smoothwm.nofix from orig.nofix."
    )
    smooth2_iterations: int = Field(
        ge=1, 
        description="Surface smoothing iterations for smooth2 (Stage 14, after topology fix, for visualization). Re-smooths smoothwm from white.preaparc. Use 3 for monkey data."
    )
    inflate_iterations: Optional[int] = Field(
        ge=1, 
        description="Surface inflation iterations for inflate1 (Stage 10, before topology fix). None = use FreeSurfer default ~15-20. For high-resolution data (0.75mm isotropic), use 20-50 or even 100 to ensure sufficient inflation for correct surface mapping onto sphere."
    )
    inflate2_iterations: Optional[int] = Field(
        ge=1, 
        description="Surface inflation iterations for inflate2 (Stage 14, after topology fix, for visualization). None = use FreeSurfer default. Use 3 for monkey data (less inflation for visualization)."
    )
    inflate2_smooth_iterations: Optional[int] = Field(
        ge=0,
        description="Extra smoothing iterations applied only to the surface used as input to inflate2 (Stage 14). Output written to smoothwm.forinflate, not smoothwm. None or 0 = skip; inflate from smoothwm directly."
    )
    inflate_no_save_sulc: bool = Field(
        description="Skip saving sulc file during inflation"
    )
    
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
    def fstess(self) -> bool:
        """Alias for use_fs_tessellation."""
        return self.use_fs_tessellation
    
    # @property
    # def fsqsphere(self) -> bool:
    #     """Alias for use_fs_qsphere."""
    #     return self.use_fs_qsphere
    
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
    registration_template: Optional[Path] = Field(
        default=None,
        description="Path to registration template subject dir (e.g. sub-MEBRAIN). If set, use its surf/label/atlas; else use fsaverage from FREESURFER_HOME. When set, fsaparc (mris_ca_label) is skipped."
    )

    # Sub-configurations
    atlas: AtlasConfig = Field()
    processing: ProcessingConfig = Field()
    
    # Output control
    log_file: Optional[Path] = Field(default=None, description="Log file path")
    verbose: int = Field(ge=0, le=2, description="Verbosity level (0-2)")
    
    @property
    def cmd_log_file(self) -> Path:
        """Path to fastsurfer_recon.cmd file (logs all commands)."""
        return self.subjects_dir / self.subject_id / "scripts" / "fastsurfer_recon.cmd"
    
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

    @field_validator("registration_template", mode="before")
    @classmethod
    def resolve_registration_template(cls, v: Path | str | None) -> Path | None:
        """Resolve registration_template to absolute. Relative paths are resolved against brainana repo root."""
        if v is None:
            return None
        p = Path(v).expanduser()
        if not p.is_absolute():
            p = (_BRAINANA_ROOT / p).resolve()
        return p
    
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
    def find_default_config(cls) -> Optional[Path]:
        """
        Find the default configuration file.
        
        Looks for config/default.yaml relative to the package root.
        
        Returns
        -------
        Optional[Path]
            Path to default config file if found, None otherwise
        """
        # Try to find config/default.yaml relative to this file
        package_root = Path(__file__).parent.parent
        default_config = package_root / "config" / "default.yaml"
        if default_config.exists():
            return default_config
        return None
    
    @staticmethod
    def _convert_dot_notation_to_nested(overrides: dict) -> dict:
        """
        Convert dot notation keys to nested dict structure.
        
        Example: {"processing.threads": 4} -> {"processing": {"threads": 4}}
        
        Parameters
        ----------
        overrides : dict
            Dictionary with dot notation keys
            
        Returns
        -------
        dict
            Nested dictionary structure
        """
        nested = {}
        for key, value in overrides.items():
            if "." in key:
                parts = key.split(".")
                d = nested
                for part in parts[:-1]:
                    d = d.setdefault(part, {})
                d[parts[-1]] = value
            else:
                nested[key] = value
        return nested
    
    @classmethod
    def with_defaults(cls, **kwargs) -> "ReconSurfConfig":
        """
        Create configuration with defaults loaded from YAML if available.
        
        This method tries to load default.yaml first, then applies any
        provided kwargs as overrides. If default.yaml doesn't exist,
        falls back to code defaults.
        
        Parameters
        ----------
        **kwargs
            Configuration values to override (will override YAML defaults)
            
        Returns
        -------
        ReconSurfConfig
            Configuration with defaults loaded
        """
        default_config = cls.find_default_config()
        if default_config:
            # Load from YAML and apply overrides
            return cls.from_yaml(default_config, **kwargs)
        else:
            # No YAML found, use code defaults
            return cls(**kwargs)
    
    @classmethod
    def from_yaml(cls, config_path: Path, overrides: Optional[dict] = None, **kwargs) -> "ReconSurfConfig":
        """
        Load configuration from YAML file.
        
        Parameters
        ----------
        config_path : Path
            Path to YAML configuration file
        overrides : dict, optional
            Dictionary of override values (supports dot notation for nested keys)
        **kwargs
            Additional override values from command line (alternative to overrides dict)
            
        Returns
        -------
        ReconSurfConfig
            Validated configuration
        """
        with open(config_path) as f:
            config_dict = yaml.safe_load(f) or {}
        
        # Merge kwargs into overrides dict
        if overrides is None:
            overrides = {}
        overrides.update(kwargs)
        
        # Filter None values and convert dot notation to nested structure
        filtered_overrides = {k: v for k, v in overrides.items() if v is not None}
        nested_overrides = cls._convert_dot_notation_to_nested(filtered_overrides)
        
        # Merge nested overrides into config_dict (deep merge for nested dicts)
        for key, value in nested_overrides.items():
            if isinstance(value, dict) and key in config_dict and isinstance(config_dict[key], dict):
                # Deep merge nested dicts
                for subkey, subvalue in value.items():
                    config_dict[key][subkey] = subvalue
            else:
                config_dict[key] = value
        
        # Pydantic will automatically create nested BaseModel objects from dicts
        # So {"processing": {"inflate_iterations": 100}} will automatically
        # create ProcessingConfig from the nested dict
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

