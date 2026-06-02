"""antspyx (ANTsPy) backends for the ANTs operations brainana normally shells out to.

These are drop-in replacements used **only when the ANTs command-line binaries are not
available on PATH** (auto-fallback in registration.py / preprocessing.py). They let the
lightweight "lite" notebook run on hosts without an ANTs install (e.g. a clean Colab
runtime), since antspyx is just a pip wheel.

Each function mirrors the exact return contract of the CLI op it replaces, so nothing
downstream changes. `import ants` is done lazily inside each function so importing this
module never requires antspyx to be installed.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .validation import (
    validate_input_file,
    ensure_working_directory,
    validate_output_file,
)
from ..utils import calculate_func_tmean


# Global ANTs backend selector. "auto" auto-detects per call (CLI if on PATH,
# else antspyx); "antspyx" forces the Python backend (skips CLI detection);
# "cli" forces the CLI. The "lite" notebook sets "antspyx" via set_ants_backend();
# the full pipeline never overrides it, so its CLI behavior is unchanged.
_ANTS_BACKEND = "auto"
_VALID_BACKENDS = ("auto", "antspyx", "cli")


def set_ants_backend(backend: str) -> None:
    """Override the ANTs backend globally for this process.

    Args:
        backend: "antspyx" forces the antspyx Python backend (no CLI detection),
            "cli" forces the ANTs command-line tools, "auto" (default) picks the
            CLI when present and otherwise falls back to antspyx.

    Raises:
        ValueError: If `backend` is not one of "auto", "antspyx", "cli".
    """
    global _ANTS_BACKEND
    if backend not in _VALID_BACKENDS:
        raise ValueError(
            f"Unknown ANTs backend {backend!r}; expected one of {_VALID_BACKENDS}."
        )
    _ANTS_BACKEND = backend


def get_ants_backend() -> str:
    """Return the current ANTs backend selector ("auto" | "antspyx" | "cli")."""
    return _ANTS_BACKEND


def cli_available(name: str) -> bool:
    """Return True if the ANTs CLI tool `name` should be used.

    Honors the global backend selector (see `set_ants_backend`): "antspyx" always
    returns False (so callers use the antspyx backend), "cli" always returns True,
    and "auto" checks whether `name` is on PATH.
    """
    if _ANTS_BACKEND == "antspyx":
        return False
    if _ANTS_BACKEND == "cli":
        return True
    return shutil.which(name) is not None


def antspyx_available() -> bool:
    """Return True if the antspyx (`ants`) Python package is importable."""
    import importlib.util

    return importlib.util.find_spec("ants") is not None


# antsApplyTransforms interpolation name -> antspyx interpolator name
_INTERP_MAP = {
    "linear": "linear",
    "nearestneighbor": "nearestNeighbor",
    "bspline": "bSpline",
    "genericlabel": "genericLabel",
    "cosinewindowedsinc": "cosineWindowedSinc",
    "welchwindowedsinc": "welchWindowedSinc",
    "hammingwindowedsinc": "hammingWindowedSinc",
    "lanczoswindowedsinc": "lanczosWindowedSinc",
    "gaussian": "gaussian",
}


def _map_interpolator(interpolation: str) -> str:
    """Map an antsApplyTransforms interpolation name to the antspyx spelling."""
    return _INTERP_MAP.get(str(interpolation).lower(), "linear")


def _parse_bracket_floats(value: str) -> List[float]:
    """'[0.1,3,0]' -> [0.1, 3.0, 0.0]; '[0.1]' -> [0.1]."""
    return [float(x) for x in str(value).strip("[]").split(",") if x.strip() != ""]


def _parse_iterations(convergence: str) -> tuple:
    """'[1000x500x250x100,1e-6,10]' -> (1000, 500, 250, 100)."""
    inner = str(convergence).strip("[]").split(",")[0]
    return tuple(int(float(x)) for x in inner.split("x"))


def _parse_x_vector(value: str) -> tuple:
    """'8x4x2x1' / '3x2x1x0vox' -> (8,4,2,1) / (3.0,2.0,1.0,0.0)."""
    cleaned = str(value).replace("vox", "").replace("mm", "")
    parts = [p for p in cleaned.split("x") if p != ""]
    nums = [float(p) for p in parts]
    if all(n.is_integer() for n in nums):
        return tuple(int(n) for n in nums)
    return tuple(nums)


def _registration_kwargs(xfm_type: str) -> Dict[str, Any]:
    """Map brainana's REGISTRATION_STEP_DEFAULTS to ants.registration() kwargs.

    Replicates the CLI parameters as closely as the high-level antspyx API allows
    (exact numerical equivalence is not guaranteed; both wrap the same ITK routines).
    """
    from .registration import REGISTRATION_STEP_DEFAULTS

    xfm = (xfm_type or "syn").lower()
    type_map = {
        "translation": "Translation",
        "rigid": "Rigid",
        "affine": "Affine",
        "syn": "SyN",
    }
    if xfm not in type_map:
        raise ValueError(f"Invalid xfm_type {xfm_type!r}; expected one of {list(type_map)}")

    # Linear-stage params come from the affine defaults (antspyx runs an internal
    # rigid+affine before SyN, controlled by the aff_* args).
    lin = REGISTRATION_STEP_DEFAULTS["affine" if xfm == "syn" else xfm]
    kwargs: Dict[str, Any] = {
        "type_of_transform": type_map[xfm],
        "aff_metric": "mattes",  # brainana uses MI ~= mattes for linear stages
        "aff_sampling": 32,
        "aff_random_sampling_rate": 0.25,
        "aff_iterations": _parse_iterations(lin["convergence"]),
        "aff_shrink_factors": _parse_x_vector(lin["shrink"]),
        "aff_smoothing_sigmas": _parse_x_vector(lin["smooth"]),
        "grad_step": _parse_bracket_floats(lin["gradient_step"])[0],
        "write_composite_transform": True,
    }

    if xfm == "syn":
        syn = REGISTRATION_STEP_DEFAULTS["syn"]
        grad = _parse_bracket_floats(syn["gradient_step"])  # [0.1, 3, 0]
        kwargs.update(
            {
                "grad_step": grad[0],
                "flow_sigma": grad[1] if len(grad) > 1 else 3,
                "total_sigma": grad[2] if len(grad) > 2 else 0,
                "reg_iterations": _parse_iterations(syn["convergence"]),
                "syn_metric": "CC",  # brainana's SyN stage emphasizes cross-correlation
                "syn_sampling": 4,
            }
        )
    return kwargs


def antspyx_register(
    fixedf: Union[str, Path],
    movingf: Union[str, Path],
    working_dir: Union[str, Path],
    output_prefix: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    xfm_type: Optional[str] = "syn",
    compute_inverse: Optional[bool] = True,
) -> Dict[str, str]:
    """antspyx replacement for ants_cpu_register (same return contract)."""
    import ants

    if logger is None:
        logger = logging.getLogger(__name__)
    from ..utils.bids import get_filename_stem

    if output_prefix is None:
        output_prefix = get_filename_stem(Path(movingf))

    fixed_path = validate_input_file(fixedf, logger)
    moving_path = validate_input_file(movingf, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    output_path_prefix = str(Path(work_dir) / output_prefix)

    num_threads = int(os.environ.get("OMP_NUM_THREADS", 8))
    logger.info(f"Data: output prefix - {output_prefix}")
    logger.info(
        f"Data: fixed image - {fixed_path.name}, moving image - {moving_path.name}"
    )
    logger.info(f"Step: executing antspyx registration ({xfm_type})")
    logger.info(
        f"System: using {num_threads} threads for ITK operations (capped at 32)"
    )
    reg_kwargs = _registration_kwargs(xfm_type)
    result = ants.registration(
        fixed=ants.image_read(str(fixed_path)),
        moving=ants.image_read(str(moving_path)),
        outprefix=f"{output_path_prefix}_",
        **reg_kwargs,
    )

    logger.info("Step: antspyx registration completed successfully")

    registered_image = f"{output_path_prefix}_registered.nii.gz"
    ants.image_write(result["warpedmovout"], registered_image)
    validate_output_file(registered_image, logger)
    logger.info(f"Output: registered image created - {registered_image}")

    def _single(t):
        return t[0] if isinstance(t, (list, tuple)) else t

    forward_transform = f"{output_path_prefix}_Composite.h5"
    fwd_src = _single(result["fwdtransforms"])
    if Path(fwd_src).resolve() != Path(forward_transform).resolve():
        shutil.copy(fwd_src, forward_transform)
    logger.info(f"Output: forward transform created - {forward_transform}")

    outputs: Dict[str, str] = {
        "output_path_prefix": output_path_prefix,
        "imagef_registered": registered_image,
        "forward_transform": forward_transform,
        "inverse_transform": None,
    }

    if compute_inverse:
        inverse_transform = f"{output_path_prefix}_InverseComposite.h5"
        inv_src = _single(result["invtransforms"])
        if Path(inv_src).resolve() != Path(inverse_transform).resolve():
            shutil.copy(inv_src, inverse_transform)
        outputs["inverse_transform"] = inverse_transform
        logger.info(f"Output: inverse transform created - {inverse_transform}")

    logger.info(
        f"Step: registration completed with {len(outputs)} output files - {list(outputs.keys())}"
    )
    return outputs


def antspyx_apply_transforms(
    movingf: Union[str, Path],
    moving_type: int,
    interpolation: str,
    outputf_name: Union[str, Path],
    fixedf: Union[str, Path],
    working_dir: Union[str, Path],
    transformf: Union[List[Union[str, Path]], Union[str, Path]],
    logger: Optional[logging.Logger] = None,
    reff: Optional[Union[str, Path]] = None,
    generate_tmean: Optional[bool] = True,
) -> Dict[str, str]:
    """antspyx replacement for ants_apply_transforms (same return contract).

    transformlist file paths are passed straight to antspyx, which uses the same ITK
    readers as the CLI — so .h5 (composite), .nii.gz (displacement field, incl. FireANTs
    output) and .mat (affine) are all supported, selected by extension.
    """
    import ants

    if logger is None:
        logger = logging.getLogger(__name__)

    movingf = validate_input_file(movingf, logger)
    fixedf = validate_input_file(fixedf, logger)
    if reff is not None:
        reff = validate_input_file(reff, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    outputf_name = work_dir / outputf_name

    if not isinstance(transformf, list):
        transformf = [transformf]
    # Match the CLI ordering: ANTs applies the last-listed transform first, and the CLI
    # body passes reversed(transformf); replicate so multi-transform composition matches.
    transformlist = [str(Path(t).resolve()) for t in reversed(transformf)]

    reference = reff if reff is not None else fixedf
    num_threads = int(os.environ.get("OMP_NUM_THREADS", 8))
    logger.info("Workflow: applying transforms using antspyx backend")
    logger.info(
        f"Data: moving image - {Path(movingf).name}, "
        f"reference - {Path(reference).name}, interpolation - {interpolation}"
    )
    logger.info(
        f"System: using {num_threads} threads for ITK operations (capped at 32)"
    )
    out_img = ants.apply_transforms(
        fixed=ants.image_read(str(reference)),
        moving=ants.image_read(str(movingf)),
        transformlist=transformlist,
        interpolator=_map_interpolator(interpolation),
        imagetype=int(moving_type),
    )
    ants.image_write(out_img, str(outputf_name))
    validate_output_file(outputf_name, logger)
    logger.info(
        f"Step: transform application completed successfully - {outputf_name}"
    )

    outputs = {"imagef_registered": str(outputf_name)}
    if generate_tmean:
        tmean_file = work_dir / (Path(outputf_name).name.split(".nii")[0] + "_tmean.nii.gz")
        calculate_func_tmean(str(outputf_name), str(tmean_file), logger)
        outputs["imagef_registered_tmean"] = str(tmean_file)
        logger.info(f"Output: tmean generated - {tmean_file}")
    return outputs


def antspyx_n4_bias(
    image_path: Union[str, Path],
    output_path: Union[str, Path],
    bias_field_path: Union[str, Path],
    shrink_factor: Union[int, str],
    bspline_fitting: Union[int, str],
    mask_path: Optional[Union[str, Path]] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, str]:
    """antspyx replacement for the N4BiasFieldCorrection CLI branch (same return keys)."""
    import ants

    if logger is None:
        logger = logging.getLogger(__name__)

    img = ants.image_read(str(image_path))
    mask = ants.image_read(str(mask_path)) if mask_path else None
    # brainana passes -b "[150]"; antspyx spline_param takes the mesh-resolution value.
    spline_param = _parse_iterations(bspline_fitting)
    spline_param = spline_param[0] if len(spline_param) == 1 else list(spline_param)

    logger.info("Workflow: N4 bias correction using antspyx backend")
    common = dict(image=img, mask=mask, shrink_factor=int(shrink_factor), spline_param=spline_param)
    corrected = ants.n4_bias_field_correction(**common)
    bias_field = ants.n4_bias_field_correction(**common, return_bias_field=True)

    ants.image_write(corrected, str(output_path))
    ants.image_write(bias_field, str(bias_field_path))
    return {"imagef_bias_corrected": str(output_path), "bias_field": str(bias_field_path)}
