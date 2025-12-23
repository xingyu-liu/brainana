#!/usr/bin/env python3
"""
Test script for surface atlas plot visualization.

This script creates surface plots using surfplot showing ARM2 atlas on:
- Row 1: smoothwm surfaces
- Row 2: pial surfaces
- Row 3: inflated surfaces
All in lateral view.
"""
# %%
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import nibabel as nib

# Try to import surfplot
SURFPLOT_AVAILABLE = False
try:
    from surfplot import Plot
    SURFPLOT_AVAILABLE = True
except (ImportError, ValueError, Exception) as e:
    print(f"Warning: surfplot not available ({type(e).__name__}: {e})")
    print("Please install surfplot: pip install surfplot")
    SURFPLOT_AVAILABLE = False

# Add parent directory to path to import macacaMRIprep modules
# The script is in macacaMRIprep/scripts/, so parent_dir is macacaMRIprep/
script_dir = Path(__file__).parent.resolve()
parent_dir = script_dir.parent.resolve()  # This is macacaMRIprep/
# Add the parent of macacaMRIprep to path so we can import macacaMRIprep
package_parent = parent_dir.parent.resolve()  # This is banana/
if str(package_parent) not in sys.path:
    sys.path.insert(0, str(package_parent))

# %%
# Demo example path
demo_path = Path("/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/bids_reorient_upright/fastsurfer/sub-baby31")

# %%
def create_surface_atlas_plot(
    smoothwm_surf_lh: Path,
    smoothwm_surf_rh: Path,
    pial_surf_lh: Path,
    pial_surf_rh: Path,
    inflated_surf_lh: Path,
    inflated_surf_rh: Path,
    atlas_annot_lh: Path,
    atlas_annot_rh: Path,
    curv_lh: Path,
    curv_rh: Path,
    thickness_lh: Path,
    thickness_rh: Path,
    output_path: Path
):
    """
    Create surface plots showing different data on three surface types:
    - Row 1: smoothwm with curvature
    - Row 2: pial with segmentation (atlas labels)
    - Row 3: inflated with thickness
    
    Uses surfplot for clean 3D surface visualization.
    
    Args:
        smoothwm_surf_lh: Path to left hemisphere smoothwm surface
        smoothwm_surf_rh: Path to right hemisphere smoothwm surface
        pial_surf_lh: Path to left hemisphere pial surface
        pial_surf_rh: Path to right hemisphere pial surface
        inflated_surf_lh: Path to left hemisphere inflated surface
        inflated_surf_rh: Path to right hemisphere inflated surface
        atlas_annot_lh: Path to left hemisphere ARM2 annotation file
        atlas_annot_rh: Path to right hemisphere ARM2 annotation file
        curv_lh: Path to left hemisphere curvature file
        curv_rh: Path to right hemisphere curvature file
        thickness_lh: Path to left hemisphere thickness file
        thickness_rh: Path to right hemisphere thickness file
        output_path: Path to save output image
    """
    if not SURFPLOT_AVAILABLE:
        raise ImportError("surfplot is not available. Please install it: pip install surfplot")
    
    print("Loading data files...")
    
    # Load annotations (for pial surface)
    try:
        lh_labels, lh_ctab, lh_names = nib.freesurfer.read_annot(str(atlas_annot_lh))
        rh_labels, rh_ctab, rh_names = nib.freesurfer.read_annot(str(atlas_annot_rh))
        print(f"Loaded annotations: {len(lh_names)} labels for LH, {len(rh_names)} labels for RH")
    except Exception as e:
        print(f"Error loading annotations: {e}")
        raise
    
    # Load curvature (for smoothwm surface)
    try:
        lh_curv = nib.freesurfer.read_morph_data(str(curv_lh))
        rh_curv = nib.freesurfer.read_morph_data(str(curv_rh))
        print(f"Loaded curvature data")
    except Exception as e:
        print(f"Error loading curvature: {e}")
        raise
    
    # Load thickness (for inflated surface)
    try:
        lh_thickness = nib.freesurfer.read_morph_data(str(thickness_lh))
        rh_thickness = nib.freesurfer.read_morph_data(str(thickness_rh))
        print(f"Loaded thickness data")
    except Exception as e:
        print(f"Error loading thickness: {e}")
        raise
    
    # Create a figure with 3 rows and 4 columns
    # Each row: LH lateral, LH medial, RH lateral, RH medial
    print("Creating surface plots (4 views per row)...")
    
    # Compute curvature distribution and symmetric range centered at 0
    all_curv = np.concatenate([lh_curv, rh_curv])
    curv_min = np.percentile(all_curv, 33)
    curv_max = np.percentile(all_curv, 66)
    # Make symmetric around 0
    curv_abs_max = max(abs(curv_min), abs(curv_max))
    curv_vmin = -curv_abs_max
    curv_vmax = curv_abs_max
    print(f"Curvature distribution:")
    print(f"  Min: {all_curv.min():.4f}, Max: {all_curv.max():.4f}")
    print(f"  5th percentile: {curv_min:.4f}, 95th percentile: {curv_max:.4f}")
    print(f"  Symmetric range: vmin={curv_vmin:.4f}, vmax={curv_vmax:.4f} (centered at 0)")
    
    # Compute thickness percentiles for clipping
    all_thickness = np.concatenate([lh_thickness, rh_thickness])
    thickness_vmin = np.percentile(all_thickness, 5)
    thickness_vmax = np.percentile(all_thickness, 95)
    print(f"Thickness distribution:")
    print(f"  Min: {all_thickness.min():.4f}, Max: {all_thickness.max():.4f}")
    print(f"  5th percentile: {thickness_vmin:.4f}, 95th percentile: {thickness_vmax:.4f}")
    
    # Surface types with their surfaces and corresponding data
    surface_configs = [
        ('smoothwm', smoothwm_surf_lh, smoothwm_surf_rh, 'curvature', {'left': lh_curv, 'right': rh_curv}),
        ('pial', pial_surf_lh, pial_surf_rh, 'segmentation', {'left': lh_labels, 'right': rh_labels}),
        ('inflated', inflated_surf_lh, inflated_surf_rh, 'thickness', {'left': lh_thickness, 'right': rh_thickness})
    ]
    
    # Views: (hemisphere, view_name)
    views = [
        ('left', 'lateral'),
        ('left', 'medial'),
        ('right', 'lateral'),
        ('right', 'medial')
    ]
    
    # Create individual plots for each surface type and view combination
    import tempfile
    from PIL import Image
    
    temp_dir = tempfile.mkdtemp()
    temp_images = {}  # Dictionary: (surf_name, hemi, view) -> image_path
    
    try:
        for surf_name, surf_lh, surf_rh, data_type, data_dict in surface_configs:
            print(f"  Creating {surf_name} surface plots with {data_type}...")
            for hemi, view in views:
                # Create plot for single hemisphere and view
                # According to tutorial, single hemisphere plots as a row
                if hemi == 'left':
                    p = Plot(
                        surf_lh=str(surf_lh),
                        views=view,
                        size=(400, 200),  # Adjust size for single hemisphere
                        zoom=1.2
                    )
                    # Add data layer based on surface type
                    if data_type == 'curvature':
                        # Curvature: use signed values, clip to symmetric range centered at 0
                        curv_data = np.clip(data_dict['left'], curv_vmin, curv_vmax)
                        p.add_layer(
                            {'left': curv_data},
                            cmap='coolwarm_r',  # Reversed: red (negative/sulci) to blue (positive/gyri)
                            cbar=False
                        )
                    elif data_type == 'segmentation':
                        # Segmentation: use discrete colormap for labels
                        p.add_layer(
                            {'left': data_dict['left']},
                            cmap='tab20',
                            cbar=False
                        )
                    else:  # thickness
                        # Thickness: clip to 5th/95th percentiles
                        thickness_data = np.clip(data_dict['left'], thickness_vmin, thickness_vmax)
                        p.add_layer(
                            {'left': thickness_data},
                            cmap='viridis',
                            cbar=False
                        )
                else:  # right
                    p = Plot(
                        surf_rh=str(surf_rh),
                        views=view,
                        size=(400, 200),  # Adjust size for single hemisphere
                        zoom=1.2
                    )
                    # Add data layer based on surface type
                    if data_type == 'curvature':
                        # Curvature: use signed values, clip to symmetric range centered at 0
                        curv_data = np.clip(data_dict['right'], curv_vmin, curv_vmax)
                        p.add_layer(
                            {'right': curv_data},
                            cmap='coolwarm_r',  # Reversed: red (negative/sulci) to blue (positive/gyri)
                            cbar=False
                        )
                    elif data_type == 'segmentation':
                        p.add_layer(
                            {'right': data_dict['right']},
                            cmap='tab20',
                            cbar=False
                        )
                    else:  # thickness
                        # Thickness: clip to 5th/95th percentiles
                        thickness_data = np.clip(data_dict['right'], thickness_vmin, thickness_vmax)
                        p.add_layer(
                            {'right': thickness_data},
                            cmap='viridis',
                            cbar=False
                        )
                
                # Build the figure
                fig = p.build()
                
                # Save to temporary file with minimal padding
                temp_path = Path(temp_dir) / f"{surf_name}_{hemi}_{view}.png"
                fig.savefig(temp_path, dpi=150, bbox_inches='tight', pad_inches=0.05, facecolor='white')
                temp_images[(surf_name, hemi, view)] = temp_path
                plt.close(fig)
        
        # Load and combine images
        print("Combining images...")
        
        # Load all images and crop white space
        loaded_images = []
        for row_idx, (surf_name, _, _, _, _) in enumerate(surface_configs):
            row_images = []
            for col_idx, (hemi, view) in enumerate(views):
                img_path = temp_images[(surf_name, hemi, view)]
                img = Image.open(img_path)
                
                # Crop white space from edges
                # Convert to numpy array for easier cropping
                img_array = np.array(img)
                
                # Find bounding box of non-white pixels
                # Check if image is not all white
                if img_array.size > 0:
                    # Get mask of non-white pixels (with some tolerance)
                    mask = np.any(img_array < 250, axis=2) if len(img_array.shape) == 3 else img_array < 250
                    if np.any(mask):
                        coords = np.argwhere(mask)
                        y_min, x_min = coords.min(axis=0)
                        y_max, x_max = coords.max(axis=0)
                        # Add small padding
                        padding = 5
                        y_min = max(0, y_min - padding)
                        x_min = max(0, x_min - padding)
                        y_max = min(img_array.shape[0], y_max + padding)
                        x_max = min(img_array.shape[1], x_max + padding)
                        img = img.crop((x_min, y_min, x_max, y_max))
                
                row_images.append(img)
            loaded_images.append(row_images)
        
        # Get dimensions - use the maximum width and height from all images
        max_width = max(img.width for row in loaded_images for img in row)
        max_height = max(img.height for row in loaded_images for img in row)
        
        # Create combined image: 3 rows x 4 columns with minimal spacing
        spacing = 2  # Minimal spacing between subplots
        combined_width = max_width * 4 + spacing * 3
        combined_height = max_height * 3 + spacing * 2
        combined_img = Image.new('RGB', (combined_width, combined_height), 'white')
        
        # Paste images in grid: 3 rows (surface types) x 4 columns (views)
        for row_idx, row_images in enumerate(loaded_images):
            for col_idx, img in enumerate(row_images):
                # Center the image in its cell if it's smaller than max dimensions
                x_offset = (max_width - img.width) // 2
                y_offset = (max_height - img.height) // 2
                
                x_pos = col_idx * (max_width + spacing) + x_offset
                y_pos = row_idx * (max_height + spacing) + y_offset
                combined_img.paste(img, (x_pos, y_pos))
        
        # Save combined image
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined_img.save(output_path, dpi=(150, 150))
        print(f"Saved surface atlas plot to: {output_path}")
        
    finally:
        # Clean up temporary files
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

# %%
def main():
    """Main function to test surface atlas plot."""
    
    # Define paths
    fs_dir = demo_path
    surf_dir = fs_dir / "surf"
    label_dir = fs_dir / "label"
    
    # Surface files for all three surface types
    smoothwm_lh = surf_dir / "lh.smoothwm"
    smoothwm_rh = surf_dir / "rh.smoothwm"
    pial_lh = surf_dir / "lh.pial"
    pial_rh = surf_dir / "rh.pial"
    inflated_lh = surf_dir / "lh.inflated"
    inflated_rh = surf_dir / "rh.inflated"
    
    # Data files: curvature and thickness
    curv_lh = surf_dir / "lh.curv"
    curv_rh = surf_dir / "rh.curv"
    thickness_lh = surf_dir / "lh.thickness"
    thickness_rh = surf_dir / "rh.thickness"
    
    # Annotation files (ARM2 atlas)
    # Try mapped version first, then fallback to non-mapped
    atlas_annot_lh = label_dir / "lh.aparc.ARM2atlas.mapped.annot"
    atlas_annot_rh = label_dir / "rh.aparc.ARM2atlas.mapped.annot"
    if not atlas_annot_lh.exists():
        atlas_annot_lh = label_dir / "lh.aparc.ARM2atlas.annot"
    if not atlas_annot_rh.exists():
        atlas_annot_rh = label_dir / "rh.aparc.ARM2atlas.annot"
    
    # Check if files exist
    print("Checking required files...")
    required_files = [
        smoothwm_lh, smoothwm_rh, pial_lh, pial_rh, inflated_lh, inflated_rh,
        curv_lh, curv_rh, thickness_lh, thickness_rh
    ]
    missing = [f for f in required_files if not f.exists()]
    if missing:
        print(f"Missing required files: {missing}")
        return
    
    # Output paths - save to FastSurfer subject directory's tmp folder
    output_dir = fs_dir / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    surface_output = output_dir / "surface_atlas.png"
    
    # Create surface atlas plot
    print("\n" + "="*80)
    print("Creating surface atlas plot")
    print("="*80)
    try:
        if atlas_annot_lh.exists() and atlas_annot_rh.exists():
            create_surface_atlas_plot(
                smoothwm_surf_lh=smoothwm_lh,
                smoothwm_surf_rh=smoothwm_rh,
                pial_surf_lh=pial_lh,
                pial_surf_rh=pial_rh,
                inflated_surf_lh=inflated_lh,
                inflated_surf_rh=inflated_rh,
                atlas_annot_lh=atlas_annot_lh,
                atlas_annot_rh=atlas_annot_rh,
                curv_lh=curv_lh,
                curv_rh=curv_rh,
                thickness_lh=thickness_lh,
                thickness_rh=thickness_rh,
                output_path=surface_output
            )
            print("✓ Surface atlas plot created successfully")
        else:
            print(f"⚠ Annotation files not found, skipping surface atlas plot")
            print(f"  Expected: {atlas_annot_lh}, {atlas_annot_rh}")
    except Exception as e:
        print(f"✗ Failed to create surface atlas plot: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("Testing complete!")
    print(f"Output saved to: {surface_output}")
    print("="*80)

if __name__ == "__main__":
    main()

