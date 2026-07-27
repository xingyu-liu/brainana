"""Sweep FLIRT ``-coarsesearch`` / ``-finesearch`` for func conform.

Why this exists
---------------
``func_conform`` fails on heavily distorted EPI (Newcastle): FLIRT converges to a wrong
global minimum. Production func conform is hardcoded in
``operations/registration.py::FLIRT_CONFORM_CONFIG_FUNC`` as ``coarsesearch=30,
finesearch=10``; this script sweeps finer angular steps and ranks them.

What the two parameters actually do (FSL source, ``flirt.cc::set_rot_samplings`` and
``flirt.cc::search_cost``) -- this is *not* "fine refinement around coarse minima":

* coarse stage -- full grid over the search range on all 3 rotation axes at
  ``coarsedelta``. At every node a *translation-only optimisation* runs. Expensive.
* fine stage -- a **second, independent full-range grid** at ``finedelta``. At each fine
  node the translations are **trilinearly interpolated from the coarse grid** and the
  cost is evaluated exactly once, with no optimisation. Cheap per node.
* ``find_cost_minima`` then runs on that fine cost volume; the surviving minima seed the
  registration schedule.

    nodes/axis for +/-180 deg     total nodes           measured cost
    coarse 30/20/15/10  13/19/25/37   2.2k/6.9k/15.6k/50.7k   21.1 ms/node
    fine   10/6/4/2     37/61/91/181  51k/227k/754k/5.93M      1.1 ms/node

So ``finesearch`` only resolves a surface whose translations are accurate to
``coarsesearch`` spacing: ``fine << coarse`` samples interpolation error, ``fine ~ coarse``
adds nothing. Hence the ratio filter in the PARAMS block.

Two consequences worth knowing before editing the axes:

* A step must divide 180 or its grid straddles 0 deg rather than sampling it, so the
  identity rotation is never tested. 8, 24 and 40 all fail this; ``build_grid`` warns.
* ``fine=2`` costs ~107 min/session by itself at +/-180 and sits far below the
  interpolation floor, so it is not in the default grid.

Inputs are already skull-stripped; the fixed image is a native-grid T1w brain, so this
script reproduces steps 2 and 4 of ``conform_to_template`` (pad + downsample to the
moving grid) and skips skullstripping entirely.

Runs natively against host FSL. Edit the PARAMS block at the bottom and run:

    python scripts/dev/nhp_mriprep/test_func_conform.py
"""

# %% Imports
from __future__ import annotations

import csv
import html
import itertools
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

_src_dir = (
    Path(__file__).resolve().parents[3] / "src"
)  # scripts/dev/ -> scripts/ -> repo root
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import nibabel as nib
from sklearn.metrics import normalized_mutual_info_score

from nhp_mri_prep.operations.preprocessing import (
    DEFAULT_CONFORM_PADDING_PERCENTAGE,
    DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD,
    MACAQUE_HEAD_RADIUS_MM,
)
from nhp_mri_prep.operations.registration import (
    flirt_apply_transforms,
    flirt_register,
)
from nhp_mri_prep.operations.validation import (
    ensure_working_directory,
    validate_input_file,
    validate_output_file,
)
from nhp_mri_prep.quality_control.snapshots import create_conform_qc
from nhp_mri_prep.utils.mri import ensure_3d, pad_image
from nhp_mri_prep.utils.system import run_command, set_numerical_threads

logger = logging.getLogger("test_func_conform")

MOVING_PREFIX = "moving_"
MOVING_GLOBS = ("moving_*.nii.gz", "moving_*.nii")
FIXED_NAME = "fixed.nii.gz"

XFM_PREFIX = "xfm"
CONFORMED_NAME = "conformed.nii.gz"


# %% Data model
@dataclass
class Combo:
    """One (coarsesearch, finesearch) cell of the sweep."""

    coarse: int
    fine: int

    @property
    def label(self) -> str:
        return f"cs{self.coarse}_fs{self.fine}"

    def nodes(self, span_deg: float) -> tuple[int, int]:
        """(coarse, fine) grid nodes per rotation axis, matching set_rot_samplings()."""
        return (
            int(round(span_deg / self.coarse)) + 1,
            int(round(span_deg / self.fine)) + 1,
        )


@dataclass
class Prep:
    """Template prepared for one target voxel size (shared by all sessions on it)."""

    target_vox: float
    template_for_reg: Path
    template_for_xfm: Path


@dataclass
class RunSpec:
    """Everything a worker process needs; must stay picklable (plain types only)."""

    stem: str
    moving: Path
    template_for_reg: Path
    template_for_xfm: Path
    coarse: int
    fine: int
    base_flirt: dict[str, Any]
    run_dir: Path
    qc_path: Path
    num_slices: int
    resume: bool

    @property
    def label(self) -> str:
        return f"cs{self.coarse}_fs{self.fine}"


@dataclass
class Row:
    """One CSV record = one (session, combo). Field order defines CSV column order."""

    image: str = ""
    param_set: str = ""
    coarsesearch: int = 0
    finesearch: int = 0
    status: str = "ok"
    nmi: float = float("nan")
    ncc: float = float("nan")
    flirt_cost: float = float("nan")
    rms_to_gold_mm: float = float("nan")
    success: str = ""  # "1" / "0" / "" when no consensus was available
    rot_x_deg: float = float("nan")
    rot_y_deg: float = float("nan")
    rot_z_deg: float = float("nan")
    trans_x_mm: float = float("nan")
    trans_y_mm: float = float("nan")
    trans_z_mm: float = float("nan")
    reg_time_s: float = float("nan")
    total_time_s: float = float("nan")
    mat_path: str = ""
    qc_path: str = ""
    error: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.image, self.param_set)


# %% Grid construction
# Per-node cost fitted on this dataset (ses-01, 1 mm grid, 91x109x72 reference) from a
# 2x2 calibration over (30,20) x (10,6): predicted vs measured within 3%. A coarse node
# costs ~20x a fine node because it runs a translation optimisation rather than a single
# cost evaluation. Used only to warn about runtime before a long sweep.
COARSE_NODE_SECONDS = 0.0211
FINE_NODE_SECONDS = 0.00108


def samples_zero(step_deg: int, span_deg: float) -> bool:
    """True when the rotation grid actually includes 0 deg.

    ``set_rot_sampling`` lays ``round(span/step)+1`` nodes evenly across the search
    range, so 0 deg is a node only when ``round(span/step)`` is even -- i.e. for a
    +/-180 range, only when the step divides 180. Steps like 8, 24 and 40 straddle zero
    instead of sampling it, which skips the identity rotation: the single most likely
    answer for a scanner-aligned acquisition.
    """
    return round(span_deg / step_deg) % 2 == 0


def build_grid(
    coarse_values: Sequence[int],
    fine_values: Sequence[int],
    ratio_min: float,
    ratio_max: float,
    span_deg: float = 360.0,
) -> tuple[list[Combo], list[Combo]]:
    """Return (kept, skipped) combos, coarsest-first so cheap rows report early.

    A cell is kept when ``ratio_min <= fine/coarse <= ratio_max``. Below ratio_min the
    fine grid resolves the error in translations interpolated across coarse cells rather
    than signal; above ratio_max it adds nothing over the coarse grid. Skipped cells are
    returned too, so the report can show them as deliberate gaps rather than silently
    omitting them.
    """
    for step in {*coarse_values, *fine_values}:
        if not samples_zero(int(step), span_deg):
            logger.warning(
                "GRID: step %s does not divide %.0f/2 -- its rotation grid never samples "
                "0 deg, so the identity rotation is never tested",
                step,
                span_deg,
            )
    kept: list[Combo] = []
    skipped: list[Combo] = []
    for coarse, fine in itertools.product(
        sorted(coarse_values, reverse=True), sorted(fine_values, reverse=True)
    ):
        combo = Combo(int(coarse), int(fine))
        ratio = fine / coarse
        (kept if ratio_min - 1e-9 <= ratio <= ratio_max + 1e-9 else skipped).append(
            combo
        )
    return kept, skipped


def estimated_seconds(combo: Combo, span_deg: float) -> float:
    """Rough wall-clock for one registration, from the fitted per-node costs."""
    coarse_nodes, fine_nodes = combo.nodes(span_deg)
    return COARSE_NODE_SECONDS * coarse_nodes**3 + FINE_NODE_SECONDS * fine_nodes**3


# %% Input discovery
def _strip_nii(name: str) -> str:
    for ext in (".nii.gz", ".nii"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def discover_moving(
    input_dir: Path, sessions: Sequence[str] | None
) -> list[tuple[str, Path]]:
    """Find moving_*.nii(.gz); return [(stem, path)] filtered/ordered by `sessions`."""
    found: dict[str, Path] = {}
    for pattern in MOVING_GLOBS:
        for path in sorted(input_dir.glob(pattern)):
            if not path.is_file():
                continue
            stem = _strip_nii(path.name)[len(MOVING_PREFIX) :]
            found.setdefault(stem, path)
    if not found:
        raise FileNotFoundError(f"No {MOVING_PREFIX}* images in {input_dir}")
    if sessions is None:
        return sorted(found.items())
    missing = [s for s in sessions if s not in found]
    if missing:
        raise FileNotFoundError(
            f"Requested sessions not found in {input_dir}: {missing}"
        )
    return [(s, found[s]) for s in sessions]


def _voxel_sizes(imagef: Path) -> np.ndarray:
    affine = nib.load(str(imagef)).affine
    return np.sqrt(np.sum(affine[:3, :3] ** 2, axis=0))


def target_voxel_size(movingf: Path) -> float:
    """Target isotropic voxel size for a moving image, exactly as conform_to_template."""
    size = float(np.round(np.min(_voxel_sizes(movingf)), 2))
    if size <= 0:
        raise ValueError(f"Invalid target voxel size {size} mm for {movingf}")
    return size


# %% Template preparation (steps 2 + 4 of conform_to_template, no skullstripping)
def _resample(inputf: Path, outputf: Path, voxel: float) -> None:
    if outputf.exists():
        outputf.unlink()
    cmd = [
        "3dresample",
        "-dxyz", f"{voxel}", f"{voxel}", f"{voxel}",
        "-input", str(inputf),
        "-prefix", str(outputf),
        "-rmode", "Cu",
    ]  # fmt: skip
    returncode, _, stderr = run_command(cmd, step_logger=logger)
    if returncode != 0:
        raise RuntimeError(f"3dresample failed (exit {returncode}): {stderr}")
    validate_output_file(outputf, logger)


def prepare_template(
    fixed_f: Path, target_vox: float, work_dir: Path, resume: bool
) -> Prep:
    """Pad the fixed image and resample it onto the moving grid.

    Mirrors ``conform_to_template`` step 2 (pad by DEFAULT_CONFORM_PADDING_PERCENTAGE,
    then downsample when the template is finer than the moving image) and step 4 (a
    second resample to the moving voxel size, used as the apply/metrics reference).
    """
    work_dir = ensure_working_directory(work_dir, logger)
    template_for_reg = work_dir / "template_padded.nii.gz"
    downsampled = work_dir / "template_padded_downsampled.nii.gz"
    template_for_xfm = work_dir / "template_for_xfm.nii.gz"

    if (
        resume
        and template_for_xfm.is_file()
        and (downsampled.is_file() or template_for_reg.is_file())
    ):
        reg = downsampled if downsampled.is_file() else template_for_reg
        logger.info(
            "PREP %.2f mm: reusing cached template prep in %s", target_vox, work_dir
        )
        return Prep(target_vox, reg, template_for_xfm)

    source = ensure_3d(fixed_f, work_dir / "_fixed_3d.nii.gz", logger=logger)[0]

    img = nib.load(str(source))
    original_shape = np.array(img.shape[:3])
    pad_amounts = (original_shape * DEFAULT_CONFORM_PADDING_PERCENTAGE).astype(int)
    pad_image(str(source), str(template_for_reg), pad_amounts, logger=logger)

    padded = nib.load(str(template_for_reg))
    padded.header.set_xyzt_units("mm", "sec")
    nib.save(padded, str(template_for_reg))
    validate_output_file(template_for_reg, logger)

    # Downsample only when the template is finer than the moving grid, capped at the
    # 0.5 mm floor -- same conditions as production.
    template_vox = _voxel_sizes(template_for_reg)
    target = np.full((3,), target_vox)
    reg_f = template_for_reg
    if np.any(template_vox < target - 0.01):
        downsample_to = target_vox
        if target_vox < DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD - 0.01:
            downsample_to = DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD
            logger.info(
                "PREP %.2f mm: target finer than %.2f mm floor; capping downsample",
                target_vox,
                DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD,
            )
        _resample(template_for_reg, downsampled, downsample_to)
        reg_f = downsampled

    _resample(reg_f, template_for_xfm, target_vox)
    logger.info(
        "PREP %.2f mm: reg=%s %s | xfm=%s %s",
        target_vox,
        reg_f.name,
        nib.load(str(reg_f)).shape,
        template_for_xfm.name,
        nib.load(str(template_for_xfm)).shape,
    )
    return Prep(target_vox, reg_f, template_for_xfm)


# %% Metrics
def _overlap_mask(
    fixed: np.ndarray, moving: np.ndarray, percentile: float = 10.0
) -> np.ndarray:
    """Voxels above the given percentile of positive intensities in *both* images."""
    pos_fixed = fixed[fixed > 0]
    pos_moving = moving[moving > 0]
    if pos_fixed.size == 0 or pos_moving.size == 0:
        return np.zeros(fixed.shape, dtype=bool)
    return (fixed > np.percentile(pos_fixed, percentile)) & (
        moving > np.percentile(pos_moving, percentile)
    )


def _discretize(values: np.ndarray, n_bins: int) -> np.ndarray:
    vmin, vmax = float(values.min()), float(values.max())
    if vmax <= vmin:
        return np.zeros_like(values, dtype=np.int32)
    return np.digitize(values, np.linspace(vmin, vmax, n_bins + 1)[1:-1]).astype(
        np.int32
    )


def compute_similarity(
    conformed_f: Path, template_f: Path, n_bins: int = 64
) -> dict[str, float]:
    """NMI and NCC between the conformed image and the template, on the same grid."""
    fixed = np.ascontiguousarray(
        nib.load(str(template_f)).get_fdata(), dtype=np.float64
    )
    moving = np.ascontiguousarray(
        nib.load(str(conformed_f)).get_fdata(), dtype=np.float64
    )
    if moving.ndim == 4:
        moving = moving.mean(axis=-1)
    if fixed.shape != moving.shape:
        raise ValueError(
            f"Shape mismatch for metrics: template {fixed.shape} vs conformed {moving.shape}"
        )
    mask = _overlap_mask(fixed, moving)
    if not np.any(mask):
        return {"nmi": float("nan"), "ncc": float("nan")}
    fixed_vals, moving_vals = fixed[mask], moving[mask]
    return {
        "nmi": float(
            normalized_mutual_info_score(
                _discretize(fixed_vals, n_bins), _discretize(moving_vals, n_bins)
            )
        ),
        "ncc": float(np.corrcoef(fixed_vals, moving_vals)[0, 1]),
    }


def measure_flirt_cost(
    movingf: Path, reff: Path, matf: Path, cost: str, run_dir: Path
) -> float:
    """FLIRT's own cost at the final transform, via the measurecost1 schedule.

    Comparable across combos because the cost function is held fixed. Returns NaN rather
    than raising -- a missing cost must not invalidate an otherwise good run.
    """
    schedule = (
        Path(os.environ.get("FSLDIR", "")) / "etc" / "flirtsch" / "measurecost1.sch"
    )
    if not schedule.is_file():
        logger.warning("COST: schedule not found at %s", schedule)
        return float("nan")
    cmd = [
        "flirt",
        "-in", str(movingf),
        "-ref", str(reff),
        "-init", str(matf),
        "-schedule", str(schedule),
        "-cost", cost,
    ]  # fmt: skip
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(run_dir), timeout=600
        )
        for line in proc.stdout.splitlines():
            token = line.strip().split()
            if token:
                try:
                    return float(token[0])
                except ValueError:
                    continue
        logger.warning("COST: unparseable measurecost output for %s", matf)
    except Exception as exc:  # noqa: BLE001 - metric is advisory
        logger.warning("COST: measurecost failed for %s - %s", matf, exc)
    return float("nan")


_AVSCALE_ROT = re.compile(r"Rotation Angles \(x,y,z\) \[rads\]\s*=\s*(.+)")
_AVSCALE_TRANS = re.compile(r"Translations \(x,y,z\) \[mm\]\s*=\s*(.+)")


def decompose_transform(matf: Path, reff: Path) -> dict[str, float]:
    """Rotations (deg) and translations (mm) via ``avscale``; NaN on any failure."""
    nan6 = {
        f"{p}_{a}{u}": float("nan")
        for p, u in (("rot", "_deg"), ("trans", "_mm"))
        for a in "xyz"
    }
    try:
        proc = subprocess.run(
            ["avscale", "--allparams", str(matf), str(reff)],
            capture_output=True, text=True, timeout=120,
        )  # fmt: skip
        rot = _AVSCALE_ROT.search(proc.stdout)
        trans = _AVSCALE_TRANS.search(proc.stdout)
        if rot:
            for axis, value in zip("xyz", rot.group(1).split()):
                nan6[f"rot_{axis}_deg"] = float(np.rad2deg(float(value)))
        if trans:
            for axis, value in zip("xyz", trans.group(1).split()):
                nan6[f"trans_{axis}_mm"] = float(value)
    except Exception as exc:  # noqa: BLE001 - metric is advisory
        logger.warning("AVSCALE: failed for %s - %s", matf, exc)
    return nan6


# %% Transform comparison (FSL rmsdiff formula)
def read_mat(matf: Path) -> np.ndarray:
    mat = np.loadtxt(str(matf))
    if mat.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 FSL matrix in {matf}, got {mat.shape}")
    return mat


def rms_deviation(
    a: np.ndarray, b: np.ndarray, radius: float = MACAQUE_HEAD_RADIUS_MM
) -> float:
    """RMS displacement (mm) between two transforms over a sphere of `radius`.

    Jenkinson's rmsdiff measure: for the difference transform ``M = A @ inv(B)`` with
    rotation part ``R = M[:3,:3] - I`` and translation ``t = M[:3,3]``,
    ``rms = sqrt(radius^2 * trace(R.T @ R) / 5 + t.T @ t)``. Only meaningful for two
    transforms sharing the same moving and reference spaces, i.e. within one session.
    """
    diff = a @ np.linalg.inv(b)
    rot = diff[:3, :3] - np.eye(3)
    trans = diff[:3, 3]
    return float(np.sqrt(radius**2 * np.trace(rot.T @ rot) / 5.0 + trans @ trans))


def consensus_gold(
    mats: dict[str, np.ndarray], costs: dict[str, float], threshold: float
) -> tuple[str | None, dict[str, float]]:
    """Pick a session's de-facto gold transform as the medoid of the largest cluster.

    Every session is the same subject on the same scanner, so the correct transform is
    reproducible: combos that succeed agree with each other, while combos that fail
    scatter. The biggest mutually-agreeing group is therefore the answer. This measures
    *reproducibility*, not ground truth -- if every combo fails identically the consensus
    is wrong too, which is why the QC grid and GOLD_OVERRIDE exist.

    Returns (gold param_set, {param_set: rms_to_gold_mm}).
    """
    labels = sorted(mats)
    if not labels:
        return None, {}
    if len(labels) == 1:
        return labels[0], {labels[0]: 0.0}

    pair = {
        (a, b): rms_deviation(mats[a], mats[b])
        for i, a in enumerate(labels)
        for b in labels[i:]
    }

    def rms(a: str, b: str) -> float:
        return pair[(a, b)] if (a, b) in pair else pair[(b, a)]

    clusters = {a: [b for b in labels if rms(a, b) <= threshold] for a in labels}
    best_size = max(len(c) for c in clusters.values())
    candidates = [a for a in labels if len(clusters[a]) == best_size]
    # Tie-break on FLIRT's own cost: among equally reproducible clusters, prefer the one
    # whose seed actually fits the data best.
    seed = min(
        candidates,
        key=lambda a: (
            float("inf") if math.isnan(costs.get(a, float("nan"))) else costs[a],
            a,
        ),
    )
    members = clusters[seed]
    gold = min(members, key=lambda a: (sum(rms(a, b) for b in members), a))
    return gold, {a: rms(a, gold) for a in labels}


# %% Per-run worker
def _worker_init(verbose: bool) -> None:
    """Runs once per pool process: pin threads and keep matplotlib headless."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    set_numerical_threads(1)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(process)d] %(levelname)s %(name)s: %(message)s",
    )


def _flirt_config(base: dict[str, Any], coarse: int, fine: int) -> dict[str, Any]:
    flirt = dict(base)
    flirt["coarsesearch"] = coarse
    flirt["finesearch"] = fine
    return {"registration": {"flirt": flirt}}


def run_one(spec: RunSpec) -> Row:
    """Register, apply, QC and score one (session, combo). Never raises."""
    row = Row(
        image=spec.stem,
        param_set=spec.label,
        coarsesearch=spec.coarse,
        finesearch=spec.fine,
    )
    matf = spec.run_dir / f"{XFM_PREFIX}.mat"
    conformed_f = spec.run_dir / CONFORMED_NAME
    row.mat_path = str(matf)

    try:
        spec.run_dir.mkdir(parents=True, exist_ok=True)
        cached = spec.resume and matf.is_file() and _loadable(conformed_f)
        t_start = time.perf_counter()

        if cached:
            logger.info("RUN %s/%s: reusing cached transform", spec.stem, spec.label)
            reg_time = float("nan")
        else:
            t_reg = time.perf_counter()
            flirt_register(
                fixedf=str(spec.template_for_reg),
                movingf=str(spec.moving),
                working_dir=str(spec.run_dir),
                output_prefix=XFM_PREFIX,
                config=_flirt_config(spec.base_flirt, spec.coarse, spec.fine),
                logger=logger,
                dof=6,
            )
            reg_time = time.perf_counter() - t_reg
            flirt_apply_transforms(
                movingf=str(spec.moving),
                outputf_name=CONFORMED_NAME,
                reff=str(spec.template_for_xfm),
                working_dir=str(spec.run_dir),
                transformf=str(matf),
                logger=logger,
                interpolation="trilinear",
                generate_tmean=False,
            )

        row.reg_time_s = reg_time
        row.total_time_s = time.perf_counter() - t_start

        similarity = compute_similarity(conformed_f, spec.template_for_xfm)
        row.nmi, row.ncc = similarity["nmi"], similarity["ncc"]
        row.flirt_cost = measure_flirt_cost(
            spec.moving,
            spec.template_for_reg,
            matf,
            str(spec.base_flirt.get("cost", "mutualinfo")),
            spec.run_dir,
        )
        for key, value in decompose_transform(matf, spec.template_for_reg).items():
            setattr(row, key, value)

        if not (spec.resume and spec.qc_path.is_file()):
            create_conform_qc(
                conformed_file=str(conformed_f),
                template_file=str(spec.template_for_xfm),
                save_f=str(spec.qc_path),
                modality="func",
                num_slices=spec.num_slices,
                logger=logger,
            )
        row.qc_path = str(spec.qc_path) if spec.qc_path.is_file() else ""

    except Exception as exc:  # noqa: BLE001 - one bad combo must not kill the sweep
        logger.exception("RUN %s/%s failed", spec.stem, spec.label)
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"[:400]
    return row


def _loadable(path: Path) -> bool:
    try:
        return (
            path.is_file()
            and path.stat().st_size > 0
            and nib.load(str(path)).shape is not None
        )
    except Exception:  # noqa: BLE001
        return False


# %% CSV store
_ROW_FIELDS = [f.name for f in fields(Row)]


def write_rows(csv_path: Path, rows: Iterable[Row]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_ROW_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    tmp.replace(
        csv_path
    )  # atomic, so a mid-sweep reader never sees a half-written file


def read_rows(csv_path: Path) -> dict[tuple[str, str], Row]:
    if not csv_path.is_file():
        return {}
    store: dict[tuple[str, str], Row] = {}
    float_fields = {f.name for f in fields(Row) if f.type == "float"}
    int_fields = {f.name for f in fields(Row) if f.type == "int"}
    with csv_path.open(newline="") as handle:
        for record in csv.DictReader(handle):
            row = Row()
            for name in _ROW_FIELDS:
                raw = record.get(name, "")
                if name in float_fields:
                    try:
                        setattr(row, name, float(raw))
                    except (TypeError, ValueError):
                        setattr(row, name, float("nan"))
                elif name in int_fields:
                    try:
                        setattr(row, name, int(float(raw)))
                    except (TypeError, ValueError):
                        setattr(row, name, 0)
                else:
                    setattr(row, name, raw or "")
            store[row.key] = row
    return store


# %% Scoring across the sweep
def apply_consensus(
    rows: dict[tuple[str, str], Row],
    threshold: float,
    gold_override: dict[str, str],
) -> dict[str, str]:
    """Fill rms_to_gold_mm / success on every row. Returns {image: gold param_set}."""
    by_image: dict[str, list[Row]] = {}
    for row in rows.values():
        by_image.setdefault(row.image, []).append(row)

    golds: dict[str, str] = {}
    for image, image_rows in by_image.items():
        mats: dict[str, np.ndarray] = {}
        costs: dict[str, float] = {}
        for row in image_rows:
            row.rms_to_gold_mm = float("nan")
            row.success = ""
            if row.status != "ok" or not row.mat_path:
                continue
            try:
                mats[row.param_set] = read_mat(Path(row.mat_path))
                costs[row.param_set] = row.flirt_cost
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "CONSENSUS: unreadable matrix for %s/%s - %s",
                    image,
                    row.param_set,
                    exc,
                )

        if len(mats) < 2:
            # Nothing to agree with -- leave success blank rather than claiming one.
            logger.warning(
                "CONSENSUS: %s has %d usable transform(s); no consensus",
                image,
                len(mats),
            )
            continue

        override = gold_override.get(image)
        if override and override in mats:
            gold = override
            distances = {a: rms_deviation(mats[a], mats[gold]) for a in mats}
        else:
            if override:
                logger.warning(
                    "CONSENSUS: GOLD_OVERRIDE %s/%s has no transform; using cluster",
                    image,
                    override,
                )
            gold, distances = consensus_gold(mats, costs, threshold)
        if gold is None:
            continue
        golds[image] = gold
        for row in image_rows:
            if row.param_set in distances:
                row.rms_to_gold_mm = distances[row.param_set]
                row.success = "1" if distances[row.param_set] <= threshold else "0"
    return golds


@dataclass
class Summary:
    param_set: str
    coarse: int
    fine: int
    n: int = 0
    n_scored: int = 0
    n_success: int = 0
    nmi: tuple[float, float] = (float("nan"), float("nan"))
    ncc: tuple[float, float] = (float("nan"), float("nan"))
    cost: float = float("nan")
    reg_time_s: float = float("nan")
    errors: int = 0

    @property
    def success_rate(self) -> float:
        return self.n_success / self.n_scored if self.n_scored else float("nan")


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return (float("nan"), float("nan"))
    return (float(np.nanmean(arr)), float(np.nanstd(arr)))


def summarize(rows: Iterable[Row]) -> dict[str, Summary]:
    grouped: dict[str, list[Row]] = {}
    for row in rows:
        grouped.setdefault(row.param_set, []).append(row)
    summaries: dict[str, Summary] = {}
    for param_set, group in grouped.items():
        head = group[0]
        summary = Summary(param_set, head.coarsesearch, head.finesearch, n=len(group))
        summary.errors = sum(1 for r in group if r.status != "ok")
        scored = [r for r in group if r.success in ("0", "1")]
        summary.n_scored = len(scored)
        summary.n_success = sum(1 for r in scored if r.success == "1")
        summary.nmi = _mean_std([r.nmi for r in group])
        summary.ncc = _mean_std([r.ncc for r in group])
        summary.cost = _mean_std([r.flirt_cost for r in group])[0]
        summary.reg_time_s = _mean_std([r.reg_time_s for r in group])[0]
        summaries[param_set] = summary
    return summaries


# %% HTML report
_REPORT_CSS = """
:root { color-scheme: dark; }
body { background:#12141a; color:#dfe3ea; font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
       margin:0; padding:28px 32px 64px; }
h1 { font-size:20px; margin:0 0 4px; } h2 { font-size:16px; margin:32px 0 10px; color:#9fb4d4; }
.sub { color:#8a93a6; font-size:12px; margin-bottom:18px; }
.note { background:#1a1d26; border-left:3px solid #d98c3f; padding:10px 14px; margin:14px 0;
        color:#bcc4d4; font-size:12.5px; border-radius:0 4px 4px 0; }
table { border-collapse:collapse; margin:8px 0 4px; font-variant-numeric:tabular-nums; }
th,td { padding:5px 10px; border-bottom:1px solid #262b36; text-align:right; white-space:nowrap; }
th { background:#1a1d26; color:#9fb4d4; font-weight:600; text-align:right; position:sticky; top:0; }
th.sortable { cursor:pointer; user-select:none; } th.sortable:hover { color:#cfe0ff; }
td.l, th.l { text-align:left; }
tbody tr:hover { background:#191d26; }
tr.best td { background:#16301f; }
tr.vis-failed td { opacity:.42; text-decoration:line-through; }
.matrix td { text-align:center; min-width:74px; font-weight:600; color:#0d1014; }
.matrix td.skip { background:#1a1d26; color:#5d6577; font-weight:400; font-style:italic; }
.matrix td.none { background:#22262f; color:#6b7385; font-weight:400; }
.matrix th { text-align:center; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:14px; margin-top:10px; }
.card { background:#1a1d26; border:1px solid #262b36; border-radius:6px; padding:10px; }
.card img { width:100%; border-radius:4px; background:#000; display:block; }
.card .cap { font-size:12px; color:#9fb4d4; margin:0 0 6px; display:flex; justify-content:space-between; gap:8px; }
.card.fail { border-color:#7a3030; } .card.gold { border-color:#3f7a52; }
.card.marked { border-color:#b04a4a; box-shadow:inset 0 0 0 1px #b04a4a; }
.badge { font-size:10.5px; padding:1px 6px; border-radius:9px; background:#2a3040; color:#9fb4d4; }
.badge.ok { background:#1e3a28; color:#7fd39b; } .badge.bad { background:#3a1e1e; color:#e08a8a; }
.badge.gold { background:#3a3418; color:#e0cf7f; }
.controls { margin:10px 0; font-size:12.5px; color:#9fb4d4; }
.controls label { margin-right:16px; cursor:pointer; }
code { background:#1a1d26; padding:1px 5px; border-radius:3px; color:#c8d4e8; }
"""

_REPORT_JS = """
(function() {
  function lsGet(k){try{return localStorage.getItem(k);}catch(e){return null;}}
  function lsSet(k,v){try{localStorage.setItem(k,v);}catch(e){}}
  function lsDel(k){try{localStorage.removeItem(k);}catch(e){}}
  var PREFIX = 'func_conform_fail::' + (document.body.dataset.reportId||'') + '::';

  // Sortable tables: numeric columns come from data-* attrs, text from cell content.
  document.querySelectorAll('table.sortable').forEach(function(table) {
    var tbody = table.querySelector('tbody'); if (!tbody) return;
    var key = table.dataset.defaultSort || '', asc = table.dataset.defaultAsc === 'true';
    function value(row, k) {
      if (row.dataset[k] !== undefined) {
        var n = parseFloat(row.dataset[k]);
        return isNaN(n) ? -Infinity : n;
      }
      var th = table.querySelector('th[data-sort="'+k+'"]');
      return th ? row.cells[th.cellIndex].textContent.trim() : '';
    }
    function sort() {
      Array.from(tbody.rows)
        .sort(function(a,b){ var x=value(a,key), y=value(b,key);
                             return x<y ? (asc?-1:1) : x>y ? (asc?1:-1) : 0; })
        .forEach(function(r){ tbody.appendChild(r); });
    }
    table.querySelectorAll('th.sortable').forEach(function(th) {
      th.addEventListener('click', function() {
        if (key === th.dataset.sort) { asc = !asc; } else { key = th.dataset.sort; asc = false; }
        sort();
      });
    });
    if (key) sort();
  });

  // Per-run "looks wrong" marks, persisted locally so they survive a report rebuild.
  document.querySelectorAll('.qc-fail-cb').forEach(function(cb) {
    var card = cb.closest('.card');
    if (lsGet(PREFIX + cb.dataset.k) === '1') { cb.checked = true; card.classList.add('marked'); }
    cb.addEventListener('change', function() {
      if (cb.checked) { lsSet(PREFIX + cb.dataset.k, '1'); card.classList.add('marked'); }
      else { lsDel(PREFIX + cb.dataset.k); card.classList.remove('marked'); }
      applyFilter();
    });
  });

  var only = document.getElementById('only-fail');
  function applyFilter() {
    var on = only && only.checked;
    document.querySelectorAll('.grid .card').forEach(function(card) {
      var bad = card.classList.contains('fail') || card.classList.contains('marked');
      card.style.display = (!on || bad) ? '' : 'none';
    });
  }
  if (only) only.addEventListener('change', applyFilter);
  applyFilter();
})();
"""


def _fmt(value: float, decimals: int = 4) -> str:
    return (
        "-"
        if value is None or (isinstance(value, float) and math.isnan(value))
        else f"{value:.{decimals}f}"
    )


def _fmt_ms(pair: tuple[float, float], decimals: int = 4) -> str:
    mean, std = pair
    return "-" if math.isnan(mean) else f"{mean:.{decimals}f} ± {std:.{decimals}f}"


def _attr(value: float) -> str:
    return (
        ""
        if value is None or (isinstance(value, float) and math.isnan(value))
        else f"{value:.6f}"
    )


def _rate_color(rate: float) -> str:
    """Red (0) through amber to green (1); grey when unscored."""
    if math.isnan(rate):
        return "#22262f"
    return f"hsl({120 * max(0.0, min(1.0, rate)):.0f}, 62%, {38 + 22 * rate:.0f}%)"


def _rel(path: str, report: Path) -> str:
    if not path:
        return ""
    try:
        return os.path.relpath(path, report.parent)
    except ValueError:
        return path


def _heat_matrix(
    summaries: dict[str, Summary],
    kept: Sequence[Combo],
    skipped: Sequence[Combo],
    span_deg: float,
) -> str:
    coarse_values = sorted({c.coarse for c in list(kept) + list(skipped)}, reverse=True)
    fine_values = sorted({c.fine for c in list(kept) + list(skipped)}, reverse=True)
    skipped_labels = {c.label for c in skipped}

    head = "".join(f"<th>fine {f}</th>" for f in fine_values)
    body = []
    for coarse in coarse_values:
        cells = [f'<th class="l">coarse {coarse}</th>']
        for fine in fine_values:
            label = Combo(coarse, fine).label
            if label in skipped_labels:
                cells.append(
                    '<td class="skip" title="outside the fine/coarse ratio window">skipped</td>'
                )
            elif label not in summaries:
                cells.append('<td class="none">-</td>')
            else:
                summary = summaries[label]
                rate = summary.success_rate
                text = "-" if math.isnan(rate) else f"{100 * rate:.0f}%"
                title = (
                    f"{label}: {summary.n_success}/{summary.n_scored} sessions agree with gold, "
                    f"mean NMI {_fmt(summary.nmi[0])}, mean reg {_fmt(summary.reg_time_s, 1)} s"
                )
                cells.append(
                    f'<td style="background:{_rate_color(rate)}" title="{html.escape(title)}">{text}</td>'
                )
        body.append(f"<tr>{''.join(cells)}</tr>")

    counts = "; ".join(
        f"coarse {c}: {int(round(span_deg / c)) + 1}^3" for c in coarse_values
    )
    fine_counts = "; ".join(
        f"fine {f}: {int(round(span_deg / f)) + 1}^3" for f in fine_values
    )
    return (
        "<h2>Success rate by coarse x fine</h2>"
        '<table class="matrix"><thead><tr><th class="l"></th>'
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
        + f'<p class="sub">Search span {span_deg:.0f} deg per axis. Coarse grid ({counts}) '
        f"optimises translation at every node; fine grid ({fine_counts}) evaluates the cost once "
        "per node on translations interpolated from the coarse grid.</p>"
    )


def _summary_table(summaries: dict[str, Summary]) -> str:
    def rank(summary: Summary) -> tuple[float, float]:
        rate = summary.success_rate
        nmi = summary.nmi[0]
        # NaN sorts last on both keys rather than poisoning the comparison.
        return (
            -(rate if not math.isnan(rate) else -1.0),
            -(nmi if not math.isnan(nmi) else -1.0),
        )

    ordered = sorted(summaries.values(), key=rank)
    best = ordered[0].param_set if ordered else ""
    rows = []
    for summary in ordered:
        rate = summary.success_rate
        rows.append(
            f'<tr class="{"best" if summary.param_set == best else ""}"'
            f' data-rate="{_attr(rate)}" data-nmi="{_attr(summary.nmi[0])}"'
            f' data-ncc="{_attr(summary.ncc[0])}" data-cost="{_attr(summary.cost)}"'
            f' data-time="{_attr(summary.reg_time_s)}" data-err="{summary.errors}">'
            f'<td class="l">{html.escape(summary.param_set)}</td>'
            f"<td>{summary.coarse}</td><td>{summary.fine}</td>"
            f'<td>{"-" if math.isnan(rate) else f"{100 * rate:.0f}%"} '
            f"({summary.n_success}/{summary.n_scored})</td>"
            f"<td>{_fmt_ms(summary.nmi)}</td><td>{_fmt_ms(summary.ncc)}</td>"
            f"<td>{_fmt(summary.cost, 5)}</td><td>{_fmt(summary.reg_time_s, 1)}</td>"
            f"<td>{summary.errors}</td></tr>"
        )
    return (
        "<h2>Parameter summary</h2>"
        '<table class="sortable" data-default-sort="rate" data-default-asc="false"><thead><tr>'
        '<th class="l sortable" data-sort="param_set">param_set</th>'
        '<th class="sortable" data-sort="coarse">coarse</th>'
        '<th class="sortable" data-sort="fine">fine</th>'
        '<th class="sortable" data-sort="rate">success</th>'
        '<th class="sortable" data-sort="nmi">NMI</th>'
        '<th class="sortable" data-sort="ncc">NCC</th>'
        '<th class="sortable" data-sort="cost">FLIRT cost</th>'
        '<th class="sortable" data-sort="time">reg s</th>'
        '<th class="sortable" data-sort="err">errors</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _detail_table(rows: Sequence[Row], golds: dict[str, str]) -> str:
    body = []
    for row in sorted(rows, key=lambda r: (r.image, r.param_set)):
        is_gold = golds.get(row.image) == row.param_set
        badge = ""
        if row.status != "ok":
            badge = '<span class="badge bad">error</span>'
        elif is_gold:
            badge = '<span class="badge gold">gold</span>'
        elif row.success == "1":
            badge = '<span class="badge ok">ok</span>'
        elif row.success == "0":
            badge = '<span class="badge bad">off</span>'
        body.append(
            f'<tr data-nmi="{_attr(row.nmi)}" data-ncc="{_attr(row.ncc)}"'
            f' data-cost="{_attr(row.flirt_cost)}" data-rms="{_attr(row.rms_to_gold_mm)}"'
            f' data-time="{_attr(row.reg_time_s)}">'
            f'<td class="l">{html.escape(row.image)}</td>'
            f'<td class="l">{html.escape(row.param_set)} {badge}</td>'
            f"<td>{_fmt(row.rms_to_gold_mm, 2)}</td>"
            f"<td>{_fmt(row.nmi)}</td><td>{_fmt(row.ncc)}</td><td>{_fmt(row.flirt_cost, 5)}</td>"
            f"<td>{_fmt(row.rot_x_deg, 1)}, {_fmt(row.rot_y_deg, 1)}, {_fmt(row.rot_z_deg, 1)}</td>"
            f"<td>{_fmt(row.trans_x_mm, 1)}, {_fmt(row.trans_y_mm, 1)}, {_fmt(row.trans_z_mm, 1)}</td>"
            f"<td>{_fmt(row.reg_time_s, 1)}</td>"
            f'<td class="l">{html.escape(row.error[:80])}</td></tr>'
        )
    return (
        "<h2>Per-session detail</h2>"
        '<table class="sortable" data-default-sort="image" data-default-asc="true"><thead><tr>'
        '<th class="l sortable" data-sort="image">session</th>'
        '<th class="l sortable" data-sort="param_set">param_set</th>'
        '<th class="sortable" data-sort="rms">RMS to gold (mm)</th>'
        '<th class="sortable" data-sort="nmi">NMI</th>'
        '<th class="sortable" data-sort="ncc">NCC</th>'
        '<th class="sortable" data-sort="cost">FLIRT cost</th>'
        "<th>rot x,y,z (deg)</th><th>trans x,y,z (mm)</th>"
        '<th class="sortable" data-sort="time">reg s</th>'
        '<th class="l">error</th>'
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )


def _qc_grid(rows: Sequence[Row], golds: dict[str, str], report_path: Path) -> str:
    cards = []
    for row in sorted(rows, key=lambda r: (r.param_set, r.image)):
        if not row.qc_path:
            continue
        is_gold = golds.get(row.image) == row.param_set
        failed = row.status != "ok" or row.success == "0"
        classes = "card" + (" fail" if failed else "") + (" gold" if is_gold else "")
        badge = (
            '<span class="badge gold">gold</span>'
            if is_gold
            else '<span class="badge bad">off</span>'
            if row.success == "0"
            else '<span class="badge ok">ok</span>'
            if row.success == "1"
            else ""
        )
        key = f"{row.image}::{row.param_set}"
        cards.append(
            f'<div class="{classes}"><p class="cap">'
            f"<span>{html.escape(row.image)} &middot; {html.escape(row.param_set)}</span>"
            f"<span>{badge} RMS {_fmt(row.rms_to_gold_mm, 1)}</span></p>"
            f'<img loading="lazy" src="{html.escape(_rel(row.qc_path, report_path))}" alt="">'
            f'<p class="cap"><label><input type="checkbox" class="qc-fail-cb" '
            f'data-k="{html.escape(key)}"> looks wrong</label>'
            f"<span>NMI {_fmt(row.nmi, 3)}</span></p></div>"
        )
    return (
        "<h2>QC overlays</h2>"
        '<div class="controls"><label><input type="checkbox" id="only-fail"> '
        "show only failures and runs I marked wrong</label></div>"
        '<div class="grid">' + "".join(cards) + "</div>"
    )


def generate_report(
    report_path: Path,
    rows: Sequence[Row],
    golds: dict[str, str],
    kept: Sequence[Combo],
    skipped: Sequence[Combo],
    span_deg: float,
    consensus_rms_mm: float,
    done: int,
    total: int,
    auto_refresh_sec: int,
) -> None:
    summaries = summarize(rows)
    refresh = (
        f'<meta http-equiv="refresh" content="{auto_refresh_sec}">'
        if auto_refresh_sec
        else ""
    )
    unscored = sorted({r.image for r in rows if r.success == ""} - set(golds))
    caveat = (
        '<div class="note"><b>Gold is consensus, not ground truth.</b> Each session\'s gold '
        "transform is the medoid of the largest group of runs agreeing within "
        f"{consensus_rms_mm:g} mm RMS. That measures reproducibility: if every combo fails the "
        "same way, the consensus is wrong too. Check the QC overlays, and pin a verified run via "
        "<code>GOLD_OVERRIDE</code> to override the cluster."
        + (
            f" No consensus for: {html.escape(', '.join(unscored))}."
            if unscored
            else ""
        )
        + "</div>"
    )
    body = "".join(
        [
            "<h1>FLIRT coarse/fine sweep - func conform</h1>",
            f'<p class="sub">{done}/{total} runs complete &middot; '
            f"{len(summaries)} combos &middot; {len({r.image for r in rows})} sessions"
            + (
                " &middot; running, auto-refreshing"
                if auto_refresh_sec
                else " &middot; finished"
            )
            + "</p>",
            caveat,
            _heat_matrix(summaries, kept, skipped, span_deg),
            _summary_table(summaries),
            _detail_table(rows, golds),
            _qc_grid(rows, golds, report_path),
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = report_path.with_suffix(".html.tmp")
    tmp.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>func conform FLIRT sweep</title>{refresh}<style>{_REPORT_CSS}</style></head>"
        f"<body data-report-id='{html.escape(report_path.stem)}'>{body}"
        f"<script>{_REPORT_JS}</script></body></html>"
    )
    tmp.replace(report_path)


# %% Sweep driver
def _already_scored(store: dict[tuple[str, str], Row], spec: RunSpec) -> bool:
    """True when a prior pass scored this run and its artifacts survive on disk."""
    if not spec.resume:
        return False
    row = store.get((spec.stem, spec.label))
    if row is None or row.status != "ok" or math.isnan(row.nmi):
        return False
    return (spec.run_dir / f"{XFM_PREFIX}.mat").is_file() and _loadable(
        spec.run_dir / CONFORMED_NAME
    )


def run_sweep(
    input_dir: Path,
    output_dir: Path,
    sessions: Sequence[str] | None,
    coarse_values: Sequence[int],
    fine_values: Sequence[int],
    ratio_min: float,
    ratio_max: float,
    base_flirt: dict[str, Any],
    workers: int,
    resume: bool,
    consensus_rms_mm: float,
    gold_override: dict[str, str],
    num_slices: int,
    report_refresh_sec: int,
    verbose: bool,
) -> Path:
    fixed_f = validate_input_file(input_dir / FIXED_NAME, logger)
    moving_items = discover_moving(input_dir, sessions)
    span_deg = float(base_flirt["searchrx"][1] - base_flirt["searchrx"][0])
    kept, skipped = build_grid(
        coarse_values, fine_values, ratio_min, ratio_max, span_deg
    )
    if not kept:
        raise ValueError(
            f"Ratio window [{ratio_min}, {ratio_max}] excluded every coarse x fine cell"
        )

    logger.info(
        "GRID: %d combos kept, %d skipped by ratio window", len(kept), len(skipped)
    )
    per_session = 0.0
    for combo in kept:
        coarse_nodes, fine_nodes = combo.nodes(span_deg)
        estimate = estimated_seconds(combo, span_deg)
        per_session += estimate
        logger.info(
            "GRID: %-11s coarse %2d^3 = %9s nodes (optimised) | fine %3d^3 = %11s nodes "
            "(interpolated) | ~%.1f min/session",
            combo.label,
            coarse_nodes,
            f"{coarse_nodes**3:,}",
            fine_nodes,
            f"{fine_nodes**3:,}",
            estimate / 60,
        )
    logger.info(
        "GRID: ~%.0f min/session over %d combos -> ~%.1f CPU-hours total, ~%.1f h at %d workers",
        per_session / 60,
        len(kept),
        per_session * len(moving_items) / 3600,
        per_session * len(moving_items) / 3600 / max(workers, 1),
        workers,
    )

    # Template prep is shared by every session on the same target voxel size, so do it
    # once per distinct size in the parent before fanning out.
    preps: dict[float, Prep] = {}
    for stem, moving_f in moving_items:
        target = target_voxel_size(moving_f)
        if target not in preps:
            tag = f"vox_{target:.2f}".replace(".", "p")
            preps[target] = prepare_template(
                fixed_f, target, output_dir / "prep" / tag, resume
            )
        logger.info("INPUT %s: target %.2f mm", stem, target)

    specs: list[RunSpec] = []
    for stem, moving_f in moving_items:
        prep = preps[target_voxel_size(moving_f)]
        for combo in kept:
            specs.append(
                RunSpec(
                    stem=stem,
                    moving=moving_f,
                    template_for_reg=prep.template_for_reg,
                    template_for_xfm=prep.template_for_xfm,
                    coarse=combo.coarse,
                    fine=combo.fine,
                    base_flirt=base_flirt,
                    run_dir=output_dir / "runs" / stem / combo.label,
                    qc_path=output_dir / "qc" / f"qc_{combo.label}_{stem}.png",
                    num_slices=num_slices,
                    resume=resume,
                )
            )

    csv_path = output_dir / "metrics.csv"
    report_path = output_dir / "report.html"
    store = read_rows(csv_path) if resume else {}

    # A run already scored in the CSV whose artifacts are still on disk needs no worker
    # at all -- skip it here rather than paying the re-scoring cost inside run_one.
    pending = [s for s in specs if not _already_scored(store, s)]
    total = len(specs)
    done = total - len(pending)
    logger.info(
        "SWEEP: %d runs (%d sessions x %d combos), %d already complete, %d workers",
        total,
        len(moving_items),
        len(kept),
        done,
        workers,
    )

    def refresh(completed: int, auto: int) -> None:
        rows = list(store.values())
        golds = apply_consensus(store, consensus_rms_mm, gold_override)
        write_rows(csv_path, sorted(rows, key=lambda r: (r.image, r.param_set)))
        generate_report(
            report_path,
            rows,
            golds,
            kept,
            skipped,
            span_deg,
            consensus_rms_mm,
            completed,
            total,
            auto,
        )

    refresh(done, report_refresh_sec if pending else 0)

    with ProcessPoolExecutor(
        max_workers=workers, initializer=_worker_init, initargs=(verbose,)
    ) as pool:
        futures = {pool.submit(run_one, spec): spec for spec in pending}
        for future in as_completed(futures):
            spec = futures[future]
            try:
                row = future.result()
            except (
                Exception
            ) as exc:  # noqa: BLE001 - a killed worker must not stop the sweep
                logger.exception("WORKER died for %s/%s", spec.stem, spec.label)
                row = Row(
                    image=spec.stem,
                    param_set=spec.label,
                    coarsesearch=spec.coarse,
                    finesearch=spec.fine,
                    status="failed",
                    error=f"worker died: {type(exc).__name__}: {exc}"[:400],
                )
            # A cached re-score has no registration of its own to time; keep the timing
            # from whichever pass actually ran FLIRT.
            previous = store.get(row.key)
            if previous is not None and math.isnan(row.reg_time_s):
                row.reg_time_s = previous.reg_time_s
            store[row.key] = row
            done += 1
            logger.info(
                "DONE %d/%d %s/%s status=%s nmi=%s reg=%s s",
                done,
                total,
                row.image,
                row.param_set,
                row.status,
                _fmt(row.nmi, 3),
                _fmt(row.reg_time_s, 1),
            )
            refresh(done, report_refresh_sec)

    refresh(done, 0)
    logger.info("SWEEP complete: %s", report_path)
    return report_path


def check_dependencies() -> None:
    missing = [
        tool
        for tool in ("flirt", "avscale", "3dresample")
        if shutil.which(tool) is None
    ]
    if missing:
        raise RuntimeError(f"Required tools not on PATH: {', '.join(missing)}")
    if not os.environ.get("FSLDIR"):
        logger.warning("FSLDIR is unset; FLIRT cost measurement will be skipped")


# %% --- PARAMS (edit here) ---
INPUT_DIR = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/input_func_newcastle"
)
OUTPUT_DIR = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/results_func_newcastle"
)

# None = every moving_* in INPUT_DIR. Narrow this to a couple of stems for a fast pass.
SESSIONS: list[str] | None = None

# Sweep axes. cs30_fs10 is the current production setting (FLIRT_CONFORM_CONFIG_FUNC),
# kept as the known-failing control.
#
# Why this range: FLIRT searches at 8 mm sampling, so a rotation stays inside the correct
# basin only while it displaces the brain surface by less than roughly that blur scale.
# At the macaque head radius (MACAQUE_HEAD_RADIUS_MM = 27) that is ~8/27 rad ~= 17 deg of
# capture, and the worst case distance from the truth to the nearest node is coarse/2 --
# so coarse must stay under ~34 deg to guarantee a node lands in the basin. 30 sits right
# on that boundary (adequate on clean data, marginal on distorted EPI), which is why the
# ladder starts there and goes down rather than up: 36 and above are provably outside
# capture for this head size. 10 is the practical floor at ~18 min/session.
#
# Every step must divide 180, or its grid straddles 0 deg instead of sampling it and the
# identity rotation is never tested -- that rules out 8, 24 and 40. build_grid() warns.
COARSESEARCH = (30, 20, 15, 10)
FINESEARCH = (10, 6, 4)
# Keep only cells with RATIO_MIN <= fine/coarse <= RATIO_MAX. Below the floor the fine
# grid resolves the error in translations interpolated across coarse cells, not signal;
# above the ceiling it adds nothing over the coarse grid. Set to (0.0, 1.0) to run the
# full rectangular grid.
#
# fine=2 is deliberately absent: at +/-180 its grid is 181^3 = 5.9M cost evaluations,
# ~107 min/session on its own -- more than the rest of the sweep combined -- and it sits
# far below the interpolation floor for every coarse value here.
RATIO_MIN = 1 / 6
RATIO_MAX = 1 / 2

# Everything FLIRT gets besides coarsesearch/finesearch; matches FLIRT_CONFORM_CONFIG_FUNC.
# Add another axis by sweeping over variants of this dict.
# The +/-180 full range is deliberate and must stay: scanner orientation is not assumed.
BASE_FLIRT: dict[str, Any] = {
    "cost": "mutualinfo",
    "searchcost": "mutualinfo",
    "searchrx": (-180, 180),
    "searchry": (-180, 180),
    "searchrz": (-180, 180),
}

WORKERS = 4  # 8 cores on this box, shared with other jobs
RESUME = True
CONSENSUS_RMS_MM = 2.0
# Pin a visually verified run as a session's gold, e.g. {"ses-01_run-1": "cs15_fs4"}.
GOLD_OVERRIDE: dict[str, str] = {}
QC_NUM_SLICES = 4
REPORT_REFRESH_SEC = 15
VERBOSE = False


# %%
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if VERBOSE else logging.INFO,
        format="%(asctime)s [%(process)d] %(levelname)s %(name)s: %(message)s",
    )
    set_numerical_threads(1)
    check_dependencies()
    run_sweep(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        sessions=SESSIONS,
        coarse_values=COARSESEARCH,
        fine_values=FINESEARCH,
        ratio_min=RATIO_MIN,
        ratio_max=RATIO_MAX,
        base_flirt=BASE_FLIRT,
        workers=WORKERS,
        resume=RESUME,
        consensus_rms_mm=CONSENSUS_RMS_MM,
        gold_override=GOLD_OVERRIDE,
        num_slices=QC_NUM_SLICES,
        report_refresh_sec=REPORT_REFRESH_SEC,
        verbose=VERBOSE,
    )
