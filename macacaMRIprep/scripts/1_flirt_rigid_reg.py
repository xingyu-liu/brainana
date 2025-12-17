'''generate the affine transformation matrix from the input image to the target'''

#%%
import os
import subprocess

# %%
data_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_freddie_mixed'
input_f = os.path.join(data_dir, 'brain.nii.gz')
target_f = '/home/star/github/banana/templatezoo/tpl-NMT2Sym_res-05_T1w_brain.nii.gz'
affine_f = os.path.join(data_dir, 'test.mat')

# Validate input files exist
if not os.path.exists(input_f):
    raise FileNotFoundError(f"Input file not found: {input_f}")
if not os.path.exists(target_f):
    raise FileNotFoundError(f"Target file not found: {target_f}")

# Ensure output directory exists
output_dir = os.path.dirname(affine_f)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}")

# %%
# equivalent to 
# flirt -in brain -ref /home/star/github/banana/templatezoo/tpl-NMT2Sym_res-05_T1w_brain.nii.gz -out brain_NMT.nii.gz -dof 6 -searchrx -180 180 -searchry -180 180 -searchrz -180 180 -noresample -omat test.mat
cmd = [
    'flirt',
    '-in', input_f,
    '-ref', target_f,
    '-dof', '6',
    '-searchrx', '-180', '180',
    '-searchry', '-180', '180',
    '-searchrz', '-180', '180',
    '-omat', affine_f
]
print(f"Running FLIRT registration...")
print(f"Command: {' '.join(cmd)}")
subprocess.run(cmd, check=True)
print(f"Done! Transformation matrix saved to: {affine_f}")
