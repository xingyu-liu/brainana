"""
Type definitions for standalone processing steps.

This module provides standardized input/output types for processing steps,
enabling clean integration with Nextflow workflows.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List, Union


@dataclass
class StepInput:
    """Standardized input for processing steps.
    
    Attributes:
        input_file: Primary input file path
        working_dir: Working directory for intermediate files
        config: Full configuration dictionary
        output_name: Optional output filename (if None, auto-generated)
        metadata: Additional metadata (subject_id, session_id, etc.)
    """
    input_file: Path
    working_dir: Path
    config: Dict[str, Any]
    output_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Convert string paths to Path objects."""
        if isinstance(self.input_file, str):
            self.input_file = Path(self.input_file)
        if isinstance(self.working_dir, str):
            self.working_dir = Path(self.working_dir)


@dataclass
class StepOutput:
    """Standardized output from processing steps.
    
    Attributes:
        output_file: Primary output file path
        metadata: Step-specific metadata
        additional_files: Additional output files (masks, transforms, etc.) as dict with semantic keys
        qc_files: QC visualization files (if generated during step)
    """
    output_file: Path
    metadata: Dict[str, Any] = field(default_factory=dict)
    additional_files: Dict[str, Path] = field(default_factory=dict)
    qc_files: List[Path] = field(default_factory=list)
    
    def __post_init__(self):
        """Convert string paths to Path objects."""
        if isinstance(self.output_file, str):
            self.output_file = Path(self.output_file)
        # Convert additional_files dict values to Path objects
        if isinstance(self.additional_files, dict):
            self.additional_files = {
                k: Path(v) if isinstance(v, str) else v
                for k, v in self.additional_files.items()
            }
        self.qc_files = [
            Path(f) if isinstance(f, str) else f 
            for f in self.qc_files
        ]


@dataclass
class AnatomicalState:
    """Tracks anatomical file states through processing.
    
    This class maintains the state of anatomical processing, tracking
    different versions of the file (with/without skull, registered, etc.)
    """
    subject_id: str
    session_id: Optional[str]
    original: Path
    reoriented: Optional[Path] = None
    conformed: Optional[Path] = None
    bias_corrected: Optional[Path] = None
    skullstripped: Optional[Path] = None
    brain_mask: Optional[Path] = None
    segmentation: Optional[Path] = None
    registered: Optional[Path] = None
    forward_transform: Optional[Path] = None
    inverse_transform: Optional[Path] = None
    
    def __post_init__(self):
        """Convert string paths to Path objects."""
        if isinstance(self.original, str):
            self.original = Path(self.original)
        for attr in ['reoriented', 'conformed', 'bias_corrected', 
                     'skullstripped', 'brain_mask', 'segmentation',
                     'registered', 'forward_transform', 'inverse_transform']:
            val = getattr(self, attr)
            if val is not None and isinstance(val, str):
                setattr(self, attr, Path(val))
    
    @property
    def current(self) -> Path:
        """Get current processing state (most advanced version)."""
        return (self.registered or 
                self.skullstripped or 
                self.bias_corrected or 
                self.conformed or 
                self.reoriented or 
                self.original)


@dataclass
class FunctionalState:
    """Tracks functional file states through processing.
    
    This class maintains the state of functional processing, tracking
    both the 4D BOLD file and the temporal mean (tmean) at each step.
    """
    subject_id: str
    session_id: Optional[str]
    task: str
    run: Optional[str]
    original: Path
    # 4D BOLD file states
    reoriented: Optional[Path] = None
    slice_timed: Optional[Path] = None
    motion_corrected: Optional[Path] = None
    despiked: Optional[Path] = None
    conformed: Optional[Path] = None
    registered: Optional[Path] = None
    # Temporal mean (tmean) states
    tmean_reoriented: Optional[Path] = None
    tmean_slice_timed: Optional[Path] = None
    tmean_motion_corrected: Optional[Path] = None
    tmean_despiked: Optional[Path] = None
    tmean_bias_corrected: Optional[Path] = None
    tmean_conformed: Optional[Path] = None
    tmean_skullstripped: Optional[Path] = None
    tmean_registered: Optional[Path] = None
    # Additional files
    brain_mask: Optional[Path] = None
    motion_params: Optional[Path] = None
    forward_transform: Optional[Path] = None
    inverse_transform: Optional[Path] = None
    
    def __post_init__(self):
        """Convert string paths to Path objects."""
        if isinstance(self.original, str):
            self.original = Path(self.original)
        for attr in ['reoriented', 'slice_timed', 'motion_corrected', 
                     'despiked', 'conformed', 'registered',
                     'tmean_reoriented', 'tmean_slice_timed', 'tmean_motion_corrected',
                     'tmean_despiked', 'tmean_bias_corrected', 'tmean_conformed',
                     'tmean_skullstripped', 'tmean_registered',
                     'brain_mask', 'motion_params', 'forward_transform', 'inverse_transform']:
            val = getattr(self, attr)
            if val is not None and isinstance(val, str):
                setattr(self, attr, Path(val))
    
    @property
    def current_4d(self) -> Path:
        """Get current 4D BOLD file state."""
        return (self.registered or 
                self.conformed or 
                self.despiked or 
                self.motion_corrected or 
                self.slice_timed or 
                self.reoriented or 
                self.original)
    
    @property
    def current_tmean(self) -> Optional[Path]:
        """Get current temporal mean state."""
        return (self.tmean_registered or 
                self.tmean_skullstripped or 
                self.tmean_conformed or 
                self.tmean_bias_corrected or 
                self.tmean_despiked or 
                self.tmean_motion_corrected or 
                self.tmean_slice_timed or 
                self.tmean_reoriented)

