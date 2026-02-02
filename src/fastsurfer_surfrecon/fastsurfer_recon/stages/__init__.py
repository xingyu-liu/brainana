"""
Pipeline stages for FastSurfer surface reconstruction.

Each stage represents a discrete step in the processing pipeline.
"""

from .base import PipelineStage, HemisphereStage

# Volume stages
from .s01_volume_prep import VolumePrep
from .s02_bias_correction import BiasCorrection
from .s03_mask_aseg import MaskAseg
from .s04_talairach import Talairach
from .s05_norm_t1 import NormT1
from .s06_cc_segmentation import CCSegmentation
from .s07_wm_filled import WMFilled

# Surface stages (hemisphere-specific)
from .s08_tessellation import Tessellation
from .s09_smoothing import Smoothing
from .s10_inflation import Inflation
from .s11_spherical_projection import SphericalProjection
from .s12_topology_fix import TopologyFix
from .s13_white_preaparc import WhitePreaparc
from .s14_parcellation import Parcellation
from .s15_surface_placement import SurfacePlacement
from .s16_compute_morphometry import ComputeMorphometry
from .s17_registration import Registration
from .s18_statistics import Statistics
from .s19_cortical_ribbon import CorticalRibbon
from .s20_aseg_refinement import AsegRefinement
from .s21_aparc_mapping import AparcMapping
from .s22_wmparc_mapping import WMParcMapping

__all__ = [
    # Base classes
    "PipelineStage",
    "HemisphereStage",
    # Volume stages
    "VolumePrep",
    "BiasCorrection",
    "MaskAseg",
    "Talairach",
    "NormT1",
    "CCSegmentation",
    "WMFilled",
    # Surface stages
    "Tessellation",
    "Smoothing",
    "Inflation",
    "SphericalProjection",
    "TopologyFix",
    "WhitePreaparc",
    "Parcellation",
    "SurfacePlacement",
    "ComputeMorphometry",
    "Registration",
    "Statistics",
    "CorticalRibbon",
    "AsegRefinement",
    "AparcMapping",
    "WMParcMapping",
]

