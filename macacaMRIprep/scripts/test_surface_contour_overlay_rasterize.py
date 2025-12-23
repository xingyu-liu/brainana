#!/usr/bin/env python3
"""
Test script for surface contour overlay visualization using rasterization approach.

This script creates a 3xN grid image with T1w underlay and white/pial surface contours.
Uses 3D Bresenham line rasterization to create volume masks.
"""

import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import nibabel as nib

# Add parent directory to path to import macacaMRIprep modules
script_dir = Path(__file__).parent.resolve()
parent_dir = script_dir.parent.resolve()  # This is macacaMRIprep/
package_parent = parent_dir.parent.resolve()  # This is banana/
if str(package_parent) not in sys.path:
    sys.path.insert(0, str(package_parent))

# Try to import, but handle import errors gracefully
try:
    from macacaMRIprep.quality_control.mri_plotting import create_grid_mri_image
except (ImportError, ModuleNotFoundError, OSError) as e:
    print(f"Warning: Could not import macacaMRIprep.quality_control.mri_plotting ({type(e).__name__})")
    print("This is likely due to missing dependencies (e.g., torch).")
    print("The script will try to work without it, but some features may be limited.")
    def create_grid_mri_image(*args, **kwargs):
        raise ImportError("create_grid_mri_image not available due to import errors. Please install required dependencies.")

# Demo example path
demo_path = Path("/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/bids_reorient_upright/fastsurfer/sub-baby31")

def load_freesurfer_surface(surf_path: Path):
    """Load FreeSurfer surface file."""
    try:
        vertices, faces = nib.freesurfer.read_geometry(str(surf_path))
        return vertices, faces
    except Exception as e:
        print(f"Error loading surface {surf_path}: {e}")
        raise

def rasterize_line_3d_bresenham(p0, p1, shape):
    """
    Rasterize a 3D line using 3D Bresenham algorithm.
    Ensures single-voxel thickness to avoid double contours.
    """
    p0 = np.array(p0, dtype=int)
    p1 = np.array(p1, dtype=int)
    
    if np.all(p0 == p1):
        if (0 <= p0[0] < shape[0] and 0 <= p0[1] < shape[1] and 0 <= p0[2] < shape[2]):
            return [tuple(p0)]
        return []
    
    points = []
    dx = abs(p1[0] - p0[0])
    dy = abs(p1[1] - p0[1])
    dz = abs(p1[2] - p0[2])
    
    xs = 1 if p1[0] > p0[0] else -1
    ys = 1 if p1[1] > p0[1] else -1
    zs = 1 if p1[2] > p0[2] else -1
    
    # Determine which dimension has the largest change
    if dx >= dy and dx >= dz:
        # X is the driving axis
        p1_err = 2 * dy - dx
        p2_err = 2 * dz - dx
        x, y, z = p0[0], p0[1], p0[2]
        for _ in range(dx + 1):
            if (0 <= x < shape[0] and 0 <= y < shape[1] and 0 <= z < shape[2]):
                points.append((x, y, z))
            if x == p1[0]:
                break
            if p1_err > 0:
                y += ys
                p1_err -= 2 * dx
            if p2_err > 0:
                z += zs
                p2_err -= 2 * dx
            p1_err += 2 * dy
            p2_err += 2 * dz
            x += xs
    elif dy >= dx and dy >= dz:
        # Y is the driving axis
        p1_err = 2 * dx - dy
        p2_err = 2 * dz - dy
        x, y, z = p0[0], p0[1], p0[2]
        for _ in range(dy + 1):
            if (0 <= x < shape[0] and 0 <= y < shape[1] and 0 <= z < shape[2]):
                points.append((x, y, z))
            if y == p1[1]:
                break
            if p1_err > 0:
                x += xs
                p1_err -= 2 * dy
            if p2_err > 0:
                z += zs
                p2_err -= 2 * dy
            p1_err += 2 * dx
            p2_err += 2 * dz
            y += ys
    else:
        # Z is the driving axis
        p1_err = 2 * dy - dz
        p2_err = 2 * dx - dz
        x, y, z = p0[0], p0[1], p0[2]
        for _ in range(dz + 1):
            if (0 <= x < shape[0] and 0 <= y < shape[1] and 0 <= z < shape[2]):
                points.append((x, y, z))
            if z == p1[2]:
                break
            if p1_err > 0:
                y += ys
                p1_err -= 2 * dz
            if p2_err > 0:
                x += xs
                p2_err -= 2 * dz
            p1_err += 2 * dy
            p2_err += 2 * dx
            z += zs
    
    return points

def create_surface_mask_from_mesh(surface_vertices, surface_faces, volume_img):
    """
    Create a boundary mask from surface mesh using rasterization approach.
    Computes neighbors from faces and rasterizes edges only between neighbor pairs.
    Uses 3D Bresenham algorithm for single-voxel-thick lines.
    """
    volume_shape = volume_img.shape[:3]
    
    # Get TkReg RAS to voxel transformation
    try:
        vox2ras_tkr = volume_img.header.get_vox2ras_tkr()
    except AttributeError:
        vox2ras_tkr = volume_img.affine
    
    # Transform vertices from TkReg RAS to voxel space
    inv_affine = np.linalg.inv(vox2ras_tkr)
    vertices_ras = np.column_stack([surface_vertices, np.ones(len(surface_vertices))])
    vertices_vox = (inv_affine @ vertices_ras.T).T[:, :3]
    
    # Create output mask
    surface_mask = np.zeros(volume_shape, dtype=np.uint8)
    
    # Compute neighbors from faces (1-ring neighbors)
    n_vertices = len(vertices_vox)
    neighbors = [set() for _ in range(n_vertices)]
    
    for face in surface_faces:
        v0_idx, v1_idx, v2_idx = face
        if (0 <= v0_idx < n_vertices and 
            0 <= v1_idx < n_vertices and 
            0 <= v2_idx < n_vertices):
            neighbors[v0_idx].add(v1_idx)
            neighbors[v0_idx].add(v2_idx)
            neighbors[v1_idx].add(v0_idx)
            neighbors[v1_idx].add(v2_idx)
            neighbors[v2_idx].add(v0_idx)
            neighbors[v2_idx].add(v1_idx)
    
    # Rasterize edges only between neighbor pairs
    drawn_edges = set()
    for v_idx in range(n_vertices):
        for neighbor_idx in neighbors[v_idx]:
            edge_key = (min(v_idx, neighbor_idx), max(v_idx, neighbor_idx))
            if edge_key not in drawn_edges:
                drawn_edges.add(edge_key)
                v0 = np.round(vertices_vox[v_idx]).astype(int)
                v1 = np.round(vertices_vox[neighbor_idx]).astype(int)
                line_points = rasterize_line_3d_bresenham(v0, v1, volume_shape)
                for point in line_points:
                    surface_mask[point[0], point[1], point[2]] = 1
    
    return surface_mask

def create_surface_contour_overlay(
    t1w_file: Path,
    white_surf_lh: Path,
    white_surf_rh: Path,
    pial_surf_lh: Path,
    pial_surf_rh: Path,
    output_path: Path,
    num_cols: int = 4
):
    """Create 3xN grid showing T1w with white (blue) and pial (red) surface contours on the same figure."""
    print(f"Loading T1w image: {t1w_file}")
    t1w_img = nib.load(str(t1w_file))
    t1w_data = t1w_img.get_fdata()
    
    # Load surfaces
    print("Loading surfaces...")
    white_lh_verts, white_lh_faces = load_freesurfer_surface(white_surf_lh)
    white_rh_verts, white_rh_faces = load_freesurfer_surface(white_surf_rh)
    pial_lh_verts, pial_lh_faces = load_freesurfer_surface(pial_surf_lh)
    pial_rh_verts, pial_rh_faces = load_freesurfer_surface(pial_surf_rh)
    
    # Create masks from surface meshes
    print("Creating masks from surface meshes (rasterization approach)...")
    white_mask = np.zeros_like(t1w_data, dtype=np.uint8)
    pial_mask = np.zeros_like(t1w_data, dtype=np.uint8)
    
    for verts, faces in [(white_lh_verts, white_lh_faces), (white_rh_verts, white_rh_faces)]:
        mask = create_surface_mask_from_mesh(verts, faces, t1w_img)
        white_mask = np.maximum(white_mask, mask)
    
    for verts, faces in [(pial_lh_verts, pial_lh_faces), (pial_rh_verts, pial_rh_faces)]:
        mask = create_surface_mask_from_mesh(verts, faces, t1w_img)
        pial_mask = np.maximum(pial_mask, mask)
    
    # Combine masks into a single multi-label overlay
    # Label 1 = white surface (blue), Label 2 = pial surface (red)
    # If both overlap, pial (label 2) takes precedence
    print("Combining white and pial surface masks...")
    combined_mask = np.zeros_like(t1w_data, dtype=np.uint8)
    combined_mask[white_mask > 0] = 1  # White surface = label 1 (blue)
    combined_mask[pial_mask > 0] = 2   # Pial surface = label 2 (red), overwrites white where they overlap
    
    # Create combined surface overlay with both white (blue) and pial (red) contours
    print("Creating combined surface overlay (white=blue, pial=red)...")
    # Use discrete contour type for multi-label masks - this avoids double lines
    # For discrete type, we need overlay_colors (list) with colors for each label
    fig = create_grid_mri_image(
        underlay_data=t1w_file,
        overlay_data=combined_mask,
        num_cols=num_cols,
        perspectives=["axial", "sagittal", "coronal"],
        overlay_colors=['mediumpurple', 'mediumseagreen'],  # Label 1 (white), Label 2 (pial)
        alpha=0.7,
        num_contour_levels=1,
        show_title=False,
        col_margin=1,
        figsize_per_col=(5, 5),
        contour_linewidth=1.0,
        contour_type='discrete'  # Use discrete for multi-label masks to avoid double lines
    )
    
    # Save figure
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='black')
    plt.close(fig)
    print(f"Saved surface contour overlay to: {output_path}")

def main():
    """Main function to test surface contour overlay."""
    fs_dir = demo_path
    surf_dir = fs_dir / "surf"
    mri_dir = fs_dir / "mri"
    
    white_lh = surf_dir / "lh.smoothwm"
    white_rh = surf_dir / "rh.smoothwm"
    pial_lh = surf_dir / "lh.pial"
    pial_rh = surf_dir / "rh.pial"
    
    t1w_file = mri_dir / "T1.mgz"
    if not t1w_file.exists():
        t1w_file = mri_dir / "brain.finalsurfs.mgz"
    
    print("Checking required files...")
    required_files = [white_lh, white_rh, pial_lh, pial_rh, t1w_file]
    missing = [f for f in required_files if not f.exists()]
    if missing:
        print(f"Missing required files: {missing}")
        return
    
    output_dir = fs_dir / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    contour_output = output_dir / "surface_contours_rasterize.png"
    
    print("\n" + "="*80)
    print("Creating surface contour overlay (Rasterization Approach)")
    print("="*80)
    try:
        create_surface_contour_overlay(
            t1w_file=t1w_file,
            white_surf_lh=white_lh,
            white_surf_rh=white_rh,
            pial_surf_lh=pial_lh,
            pial_surf_rh=pial_rh,
            output_path=contour_output,
            num_cols=4
        )
        print("✓ Surface contour overlay created successfully")
    except Exception as e:
        print(f"✗ Failed to create surface contour overlay: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("Testing complete!")
    print(f"Output saved to: {contour_output}")
    print("="*80)

if __name__ == "__main__":
    main()

