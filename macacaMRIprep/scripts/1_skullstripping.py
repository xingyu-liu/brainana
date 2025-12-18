# %%
import os
import sys
import subprocess
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from NHPskullstripNN.inference.prediction import skullstripping

#%%
data_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/anat/anat_marge_conform'
input_f = os.path.join(data_dir, 'input.nii.gz')
output_f = os.path.join(data_dir, 'mask.nii.gz')
brain_f = os.path.join(data_dir, 'brain.nii.gz')

# skullstripping with NHPskullstripNN
print(f"Starting skullstripping for: {input_f}")
result = skullstripping(
    input_image=input_f,
    modal='anat',  # Use 'anat' for T1w, 'func' for EPI
    output_path=output_f,
    device_id='auto'
)
print(f"Mask saved to: {result['brain_mask']}")

# %%
# apply mask to input
print(f"Applying mask to input image...")
cmd = ['fslmaths', input_f, '-mas', output_f, brain_f]
try:
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(f"Brain-extracted image saved to: {brain_f}")
except subprocess.CalledProcessError as e:
    print(f"Error applying mask: {e.stderr}")
    sys.exit(1)
