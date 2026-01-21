#! /usr/bin/env python3

# %%
import sys
import pathlib
import subprocess
import nibabel as nib

# %%
working_dir = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_downsampled_v5/fastsurfer/sub-032309/wb_test'
working_dir = pathlib.Path(working_dir)

lh_pial_f = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_downsampled_v5/fastsurfer/sub-032309/surf/lh.pial'
rh_pial_f = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_downsampled_v5/fastsurfer/sub-032309/surf/rh.pial'
lh_white_f = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_downsampled_v5/fastsurfer/sub-032309/surf/lh.white'
rh_white_f = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_downsampled_v5/fastsurfer/sub-032309/surf/rh.white'
brain_f = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_downsampled_v5/fastsurfer/sub-032309/mri/brain.finalsurfs.mgz'

scene_file = pathlib.Path('/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_downsampled_v5/fastsurfer/sub-032309/wb_test/Vol_Surface.scene')

# %%
# 1. **Convert FreeSurfer surfaces to GIFTI format**
print("Converting surfaces to GIFTI format...")
# Append .surf.gii to preserve the original filename (scene file expects lh.white.surf.gii, etc.)
lh_pial_gii = working_dir / 'lh.pial.surf.gii'
rh_pial_gii = working_dir / 'rh.pial.surf.gii'
lh_white_gii = working_dir / 'lh.white.surf.gii'
rh_white_gii = working_dir / 'rh.white.surf.gii'

subprocess.run(f'mris_convert {lh_pial_f} {lh_pial_gii}', shell=True, check=True)
subprocess.run(f'mris_convert {rh_pial_f} {rh_pial_gii}', shell=True, check=True)
subprocess.run(f'mris_convert {lh_white_f} {lh_white_gii}', shell=True, check=True)
subprocess.run(f'mris_convert {rh_white_f} {rh_white_gii}', shell=True, check=True)

# %%
# 2. **Convert norm.mgz to NIfTI**
print("Converting volume to NIfTI format...")
brain_nii = working_dir / 'brain.finalsurfs.nii.gz'
subprocess.run(f'mri_convert {brain_f} {brain_nii}', shell=True, check=True)

# %%
# 3. **Create Affine Matrix**
print("Creating affine matrix from surface CRAS values...")
affine_mat = working_dir / 'affine.mat'

# Read CRAS (center of RAS) from lh.white surface file header
_, _, header_info = nib.freesurfer.read_geometry(lh_white_f, read_metadata=True)
c_ras = header_info['cras']

# Create affine matrix with CRAS as translation components (convert numpy types to float)
affine_list = [
    [1, 0, 0, float(c_ras[0])],
    [0, 1, 0, float(c_ras[1])],
    [0, 0, 1, float(c_ras[2])],
    [0, 0, 0, 1]
]

with open(affine_mat, 'w') as f:
    for line in affine_list:
        # Format as space-separated values (matching original format)
        f.write(str(line)[1:-1].replace(',', '    ') + '\n')

print(f"Created affine matrix: {affine_mat}")
print(f"CRAS values: {c_ras}")

# %%
# 4. **Apply Affine Transformation to Surfaces**
print("Applying affine transformation to surfaces...")
# Apply affine to each surface (in-place, overwriting the original GIFTI files)
subprocess.run(f'wb_command -surface-apply-affine {lh_white_gii} {affine_mat} {lh_white_gii}', shell=True, check=True)
subprocess.run(f'wb_command -surface-apply-affine {rh_white_gii} {affine_mat} {rh_white_gii}', shell=True, check=True)
subprocess.run(f'wb_command -surface-apply-affine {lh_pial_gii} {affine_mat} {lh_pial_gii}', shell=True, check=True)
subprocess.run(f'wb_command -surface-apply-affine {rh_pial_gii} {affine_mat} {rh_pial_gii}', shell=True, check=True)

# %%
# 5. **Render Scene using Connectome Workbench**
print("Rendering scene with Connectome Workbench...")
output_png = working_dir / 'Vol_Surface.png'

if not scene_file.exists():
    print(f"ERROR: Scene file not found: {scene_file}")
    sys.exit(1)

subprocess.run(f'wb_command -show-scene {scene_file} 1 {output_png} 2400 1000', shell=True, check=True)
print(f"Rendered image saved to: {output_png}")

# %%
