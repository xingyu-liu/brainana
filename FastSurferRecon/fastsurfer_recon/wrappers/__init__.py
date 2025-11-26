"""
FreeSurfer binary wrappers.

Provides Python interfaces to FreeSurfer command-line tools.
"""

from .base import run_fs_command, run_recon_all, FreeSurferError, get_fs_home

# Import all wrappers
from .mri import (
    mri_convert,
    mri_pretess,
    mri_mc,
    mri_mask,
    mri_normalize,
    mri_cc,
    mri_surf2volseg,
    mri_add_xform_to_header,
)

from .mris import (
    mris_info,
    mris_extract_main_component,
    mris_remesh,
    mris_smooth,
    mris_place_surface,
    mris_place_surface_curv_map,
    mris_place_surface_area_map,
    mris_place_surface_thickness,
    mris_register,
    mris_ca_label,
    mris_anatomical_stats,
)

from .recon_all import (
    recon_all_tessellate,
    recon_all_inflate1,
    recon_all_qsphere,
    recon_all_fix,
    recon_all_autodetgwstats,
    recon_all_white_preaparc,
    recon_all_cortex_label,
    recon_all_smooth2_inflate2_curvHK,
    recon_all_sphere,
    recon_all_jacobian_white_avgcurv,
    recon_all_curvstats,
    recon_all_cortribbon,
    recon_all_pctsurfcon,
    recon_all_hyporelabel,
    recon_all_apas2aseg,
    recon_all_aparc2aseg,
    recon_all_wmparc,
    recon_all_parcstats,
    recon_all_normalization2_maskbfs_fill,
)

from .registration import (
    talairach_avi,
    lta_convert,
    pctsurfcon as pctsurfcon_wrapper,
)

__all__ = [
    # Base utilities
    "run_fs_command",
    "run_recon_all",
    "FreeSurferError",
    "get_fs_home",
    # mri_* commands
    "mri_convert",
    "mri_pretess",
    "mri_mc",
    "mri_mask",
    "mri_normalize",
    "mri_cc",
    "mri_surf2volseg",
    "mri_add_xform_to_header",
    # mris_* commands
    "mris_info",
    "mris_extract_main_component",
    "mris_remesh",
    "mris_smooth",
    "mris_place_surface",
    "mris_place_surface_curv_map",
    "mris_place_surface_area_map",
    "mris_place_surface_thickness",
    "mris_register",
    "mris_ca_label",
    "mris_anatomical_stats",
    # recon-all stages
    "recon_all_tessellate",
    "recon_all_inflate1",
    "recon_all_qsphere",
    "recon_all_fix",
    "recon_all_autodetgwstats",
    "recon_all_white_preaparc",
    "recon_all_cortex_label",
    "recon_all_smooth2_inflate2_curvHK",
    "recon_all_sphere",
    "recon_all_jacobian_white_avgcurv",
    "recon_all_curvstats",
    "recon_all_cortribbon",
    "recon_all_pctsurfcon",
    "recon_all_hyporelabel",
    "recon_all_apas2aseg",
    "recon_all_aparc2aseg",
    "recon_all_wmparc",
    "recon_all_parcstats",
    "recon_all_normalization2_maskbfs_fill",
    # Registration
    "talairach_avi",
    "lta_convert",
    "pctsurfcon_wrapper",
]

