"""
Modular processing components for macacaMRIprep workflows.

This module provides separate processors for anatomical and functional data
that can be combined in different ways to create flexible processing pipelines.
"""

from .anat2template import AnatomicalProcessor
from .func2target import FunctionalProcessor

from .bids_processor import BIDSDatasetProcessor

__all__ = [
    'AnatomicalProcessor',
    'FunctionalProcessor',
    'BIDSDatasetProcessor'
] 