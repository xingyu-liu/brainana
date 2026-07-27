# %%
import os
import subprocess
import numpy as np
import nibabel as nib
import pathlib
import matplotlib.pyplot as plt
from matplotlib import colors, cm
import sys
from pathlib import Path

# Add src/ to path (scripts/dev/nhp_mriprep/ -> scripts/dev/ -> scripts/ -> repo root)
_src_dir = Path(__file__).resolve().parents[3] / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.quality_control.mri_plotting import (
    create_grid_mri_image,
    PLOT_VOL_DPI,
)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from surfplot import Plot

    SURFPLOT_AVAILABLE = True
except Exception:
    SURFPLOT_AVAILABLE = False

# %%
# set path
dataset_root = pathlib.Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_taskval"
)
subid = "sub-baby10"
sesid = "ses-161030"
min_tp = 10
cmap = "magma"

overwrite = False

output_dir = pathlib.Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_taskval/tSNR"
)
output_dir.mkdir(parents=True, exist_ok=True)

# %%
# list all the preprocessed func files in T1w space
func_dir = dataset_root / subid / sesid / "func"
func_f_list = sorted(func_dir.glob("*space-T1w*desc-preproc_bold.nii.gz"))
func_f_list.sort()

# list all the mask files if exists
mask_f_list = sorted(func_dir.glob("*space-T1w*desc-brain_mask.nii.gz"))
mask_f_list.sort()
mask_lookup = {f.name: f for f in mask_f_list}

# find the freesurfer recon all folder if exists
fs_subjects_dir = dataset_root / "fastsurfer"
fs_subject_dir = fs_subjects_dir / subid
if not fs_subject_dir.exists():
    fs_subject_dir = None


# %%
def get_run_statmean_path(func_f, out_dir):
    out_name = pathlib.Path(func_f).name.replace(
        "desc-preproc_bold",
        "stat-tsnr_boldmap",
    )
    return out_dir / out_name


def find_mask_for_func(func_f):
    expected_name = pathlib.Path(func_f).name.replace(
        "desc-preproc_bold.nii.gz",
        "desc-brain_mask.nii.gz",
    )
    return mask_lookup.get(expected_name)


def compute_tSNR(func_f, min_n_tp=10, mask_f=None):
    func_img = nib.load(str(func_f))
    func = func_img.get_fdata()
    # make sure it is 4D, otherwise return None
    if func.ndim != 4:
        print(f"Skip {func_f.name}: not a 4D file.")
        return None, None

    # also make sure it has over n timepoints, otherwise return None
    if func.shape[-1] < min_n_tp:
        print(f"Skip {func_f.name}: only {func.shape[-1]} timepoints (< {min_n_tp}).")
        return None, None

    mask = None
    if mask_f is not None and pathlib.Path(mask_f).exists():
        mask_img = nib.load(str(mask_f))
        mask = mask_img.get_fdata() > 0
        if mask.shape != func.shape[:3]:
            print(f"Warning: mask shape mismatch for {func_f.name}; ignore mask.")
            mask = None

    # compute tSNR, fabs(mean)/stdev
    with np.errstate(divide="ignore", invalid="ignore"):
        tSNR = np.abs(np.nanmean(func, axis=-1) / np.nanstd(func, axis=-1))
    tSNR[~np.isfinite(tSNR)] = 0.0
    if mask is not None:
        tSNR[~mask] = 0.0

    return tSNR, func_img


def save_tsnr_nifti(tsnr_data, ref_img, out_f):
    out_img = nib.Nifti1Image(
        tsnr_data.astype(np.float32), ref_img.affine, ref_img.header
    )
    nib.save(out_img, str(out_f))


def project_tsnr_to_surface(tsnr_nifti_f, out_prefix, fs_subject_dir):
    if fs_subject_dir is None:
        return

    hemi_map = {"L": "lh", "R": "rh"}
    env = os.environ.copy()
    env["SUBJECTS_DIR"] = str(fs_subjects_dir)
    base_name = out_prefix.name
    stat_suffix = "_stat-tsnr_boldmap"

    for hemi in ("L", "R"):
        if base_name.endswith(stat_suffix):
            stem = base_name[: -len(stat_suffix)]
            out_name = f"{stem}_hemi-{hemi}{stat_suffix}.surf.gii"
        else:
            out_name = f"{base_name}_hemi-{hemi}_stat-tsnr_boldmap.surf.gii"
        out_f = out_prefix.parent / out_name
        if out_f.exists() and (not overwrite):
            continue
        cmd = [
            "mri_vol2surf",
            "--mov",
            str(tsnr_nifti_f),
            "--regheader",
            subid,
            "--hemi",
            hemi_map[hemi],
            "--projfrac",
            "0.5",
            "--surf-fwhm",
            "2",
            "--out_type",
            "gii",
            "--o",
            str(out_f),
        ]
        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
        except FileNotFoundError:
            print("mri_vol2surf not found; skip surface projection.")
            return
        except subprocess.CalledProcessError as exc:
            print(f"Failed surface projection for {out_f.name}: {exc.stderr}")


# %%
# loop through all the func files and
# 0. if mask file exists, apply the mask to the func file, otherwise use the whole brain
# 1. compute the tSNR
# 2. save the tSNR to nifti (run-level only; surface projection is done for session average only, below)
run_tsnr_files = []

for func_f in func_f_list:
    print(f"Processing {func_f.name} ...")
    tsnr_out_f = get_run_statmean_path(func_f, output_dir)

    if tsnr_out_f.exists() and (not overwrite):
        run_tsnr_files.append(tsnr_out_f)
        continue

    mask_f = find_mask_for_func(func_f)
    tsnr_data, ref_img = compute_tSNR(func_f, min_n_tp=min_tp, mask_f=mask_f)
    if tsnr_data is None:
        continue

    save_tsnr_nifti(tsnr_data, ref_img, tsnr_out_f)
    run_tsnr_files.append(tsnr_out_f)

# %%
# generate session-average tSNR volume, then project that volume to surface (mri_vol2surf)
# skip session nifti if the output already exists (unless overwrite)
# surfaces: ..._hemi-L_stat-tsnr_boldmap.surf.gii, ..._hemi-R_stat-tsnr_boldmap.surf.gii
session_vol_out_f = output_dir / f"{subid}_{sesid}_stat-tsnr_boldmap.nii.gz"
if (not session_vol_out_f.exists()) or overwrite:
    if len(run_tsnr_files) > 0:
        vol_stack = np.stack(
            [nib.load(str(f)).get_fdata() for f in run_tsnr_files], axis=-1
        )
        session_tsnr = np.nanmean(vol_stack, axis=-1)
        save_tsnr_nifti(
            session_tsnr, nib.load(str(run_tsnr_files[0])), session_vol_out_f
        )
    else:
        print("No valid runwise tSNR volumes found; skip session average volume.")

if session_vol_out_f.exists():
    session_prefix = output_dir / f"{subid}_{sesid}_stat-tsnr_boldmap"
    project_tsnr_to_surface(session_vol_out_f, session_prefix, fs_subject_dir)


# %%
def add_right_colorbar(
    fig,
    vmin,
    vmax,
    cmap_name,
    *,
    map_right=0.9,
    bar_height_ratio=0.5,
    bar_width_to_height=0.06,
    gap_ratio=0.05,
    text_color="white",
):
    fig.subplots_adjust(right=map_right)
    fig_width_in, fig_height_in = fig.get_size_inches()

    # Make colorbar size proportional to figure size.
    bar_height = bar_height_ratio
    bar_width = (
        bar_height * bar_width_to_height * (fig_height_in / fig_width_in)
        if fig_width_in > 0
        else 0.015
    )
    gap_frac = gap_ratio
    cbar_x = map_right + gap_frac
    cbar_x = min(cbar_x, 0.99 - bar_width)
    cbar_y = (1.0 - bar_height) / 2.0

    cax = fig.add_axes([cbar_x, cbar_y, bar_width, bar_height])
    norm = colors.Normalize(vmin=vmin, vmax=vmax)
    sm = cm.ScalarMappable(norm=norm, cmap=cmap_name)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax, label="tSNR")
    cb.ax.yaxis.set_label_position("left")
    cb.ax.yaxis.tick_left()
    cb.ax.yaxis.label.set_color(text_color)
    cb.ax.tick_params(colors=text_color)
    for spine in cb.ax.spines.values():
        spine.set_edgecolor(text_color)


# %%
# plot QC snapshots
# create a volume map and surf map separately, then patch them together
vol_png = output_dir / f"{subid}_{sesid}_stat-tsnr_boldmap_vol.png"
surf_png = output_dir / f"{subid}_{sesid}_stat-tsnr_boldmap_surf.png"
qc_png = output_dir / f"{subid}_{sesid}_stat-tsnr_boldmap_qc.png"

# 1) volume map
if session_vol_out_f.exists():
    if (not vol_png.exists()) or overwrite:
        vol_data = nib.load(str(session_vol_out_f)).get_fdata()
        vol_valid = vol_data[np.isfinite(vol_data)]
        if vol_valid.size == 0:
            vol_vmin, vol_vmax = 0.0, 1.0
        else:
            vol_vmin, vol_vmax = np.percentile(vol_valid, [2, 98])
            if vol_vmax <= vol_vmin:
                vol_vmax = vol_vmin + 1e-6

        fig = create_grid_mri_image(
            underlay_data=session_vol_out_f,
            overlay_data=None,
            num_cols=6,
            perspectives=["axial"],
            title="",
            alpha=0.7,
            underlay_cmap=cmap,
            show_title=False,
            underlay_vmin=vol_vmin,
            underlay_vmax=vol_vmax,
        )
        add_right_colorbar(fig, vol_vmin, vol_vmax, cmap, text_color="white")
        fig.savefig(vol_png, dpi=PLOT_VOL_DPI, bbox_inches="tight", pad_inches=0.0)
        plt.close(fig)
else:
    print(f"Skip volume QC: missing session tSNR file - {session_vol_out_f}")

# 2) surf map: 1x4 layout -> lh lateral, lh medial, rh lateral, rh medial
lh_surf = output_dir / f"{subid}_{sesid}_hemi-L_stat-tsnr_boldmap.surf.gii"
rh_surf = output_dir / f"{subid}_{sesid}_hemi-R_stat-tsnr_boldmap.surf.gii"
lh_infl = (
    fs_subject_dir / "surf" / "lh.inflated" if fs_subject_dir is not None else None
)
rh_infl = (
    fs_subject_dir / "surf" / "rh.inflated" if fs_subject_dir is not None else None
)

if (not surf_png.exists()) or overwrite:
    can_plot_surface = (
        SURFPLOT_AVAILABLE
        and fs_subject_dir is not None
        and lh_surf.exists()
        and rh_surf.exists()
        and lh_infl.exists()
        and rh_infl.exists()
    )
    if can_plot_surface:
        lh_data = np.asarray(nib.load(str(lh_surf)).darrays[0].data, dtype=np.float32)
        rh_data = np.asarray(nib.load(str(rh_surf)).darrays[0].data, dtype=np.float32)
        all_data = np.concatenate([lh_data, rh_data])
        all_data = all_data[np.isfinite(all_data)]
        if all_data.size == 0:
            vmin, vmax = 0.0, 1.0
        else:
            vmin, vmax = 0.0, np.percentile(all_data, 98)
            if vmax <= vmin:
                vmax = vmin + 1e-6

        p = Plot(
            surf_lh=str(lh_infl),
            surf_rh=str(rh_infl),
            views=["lateral", "medial"],
            layout="row",
            size=(1600, 200),
            zoom=2,
        )
        p.add_layer(
            {
                "left": np.clip(lh_data, vmin, vmax),
                "right": np.clip(rh_data, vmin, vmax),
            },
            cmap=cmap,
            cbar=False,
        )
        fig = p.build()
        fig.patch.set_facecolor("black")
        for ax in fig.axes:
            ax.set_facecolor("black")
        add_right_colorbar(fig, vmin, vmax, cmap, text_color="white")
        fig.savefig(
            surf_png,
            dpi=PLOT_VOL_DPI,
            bbox_inches="tight",
            pad_inches=0.0,
            facecolor="black",
        )
        plt.close(fig)
    else:
        print(
            "Skip surface QC: missing surfplot dependency or required surface inputs."
        )

# 3) patch volume and surface maps (stacked in one column)
if (not qc_png.exists()) or overwrite:
    if not PIL_AVAILABLE:
        print("Skip final QC patching: Pillow is not installed.")
    elif (not vol_png.exists()) and (not surf_png.exists()):
        print("Skip final QC patching: no QC panels were generated.")
    else:
        panel_paths = [p for p in (vol_png, surf_png) if p.exists()]
        panels = [Image.open(p).convert("RGB") for p in panel_paths]
        max_w = max(im.width for im in panels)
        resized = []
        for im in panels:
            if im.width != max_w:
                new_h = int(im.height * (max_w / im.width))
                im = im.resize((max_w, new_h), resample=Image.Resampling.LANCZOS)
            resized.append(im)

        pad = 0
        total_h = sum(im.height for im in resized) + pad * (len(resized) - 1)
        canvas = Image.new("RGB", (max_w, total_h), color="white")
        y = 0
        for im in resized:
            x = (max_w - im.width) // 2
            canvas.paste(im, (x, y))
            y += im.height + pad
        canvas.save(qc_png)

# %%
