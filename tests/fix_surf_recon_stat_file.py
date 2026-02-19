# %%
import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt

import sys
from pathlib import Path
import shutil

import subprocess

# %%
dataset_root = Path('/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana')

replace_dict = {'SII':'SI/SII', 
                'STSd': 'STG/STSd',
                'belt': 'core/belt'}

# %%
site_list = list(dataset_root.glob('site-*'))
site_list = [i for i in site_list if i.is_dir()]
site_list.sort()
print(site_list)

# %%
# 2. prepare the surface input files
for site_dir in site_list:
    site_dir = Path(site_dir)
    site_name = site_dir.name
    print(f'Processing {site_name}...')

    # create a working directory for the site
    fastsurfer_dir = site_dir / 'fastsurfer'
    if not fastsurfer_dir.exists():
        print(f'{site_name} fastsurfer dir not found')
        continue

    # loop through all the subjects in the site
    sub_list = site_dir.glob('sub-*')
    sub_list = [i for i in sub_list if i.is_dir()]
    sub_list.sort()
    for sub_dir in sub_list:
        sub_dir = Path(sub_dir)
        sub = sub_dir.name
        print(f'Processing {site_name} / {sub}...')

        fs_sub_dir = fastsurfer_dir / sub
        if not fs_sub_dir.exists():
            print(f'{site_name} / {sub} fastsurfer sub dir not found')
            continue

        hemis = ['lh', 'rh']
        for hemi in hemis:
            stats_file = fs_sub_dir / 'stats' / f'{hemi}.aparc.ARM2atlas.mapped.stats'
            if not stats_file.exists():
                print(f'{site_name} / {sub} / {hemi} stats file not found')
                continue
        
            # replace one by one, but only when the key is in the file and the value is not in file
            # use | as sed delimiter since values contain / (e.g. SI/SII, STG/STSd)
            for key, value in replace_dict.items():
                if key in stats_file.read_text():
                    if value not in stats_file.read_text():
                        cmd = f'sed -i "s|{key}|{value}|g" {stats_file}'
                        subprocess.run(cmd, shell=True)
                    else:
                        print(f'{site_name} / {sub} / {hemi} stats file already has {value}')
                else:
                    print(f'{site_name} / {sub} / {hemi} stats file does not have {key}')
        
# %%
