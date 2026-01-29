# %%
import re
import os

import sys
from pathlib import Path

# Add parent directory to path to import macacaMRIprep modules
script_dir = Path(__file__).parent.resolve()
parent_dir = script_dir.parent.resolve()  # This is macacaMRIprep/
package_parent = parent_dir.parent.resolve()  # This is banana/
if str(package_parent) not in sys.path:
    sys.path.insert(0, str(package_parent))

from FastSurferRecon.fastsurfer_recon.processing.surface_fix import fix_mc_surface_header
from FastSurferRecon.fastsurfer_recon.wrappers.mris import mris_info

# %%
subj_dir = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/NMT2Sym_reuse'
surface_path = os.path.join(subj_dir, 'surf', 'hemixxx.white')
vol_path = os.path.join(subj_dir, 'mri', 'wm.mgz')
output_path = os.path.join(subj_dir, 'surf', 'hemixxx.white.fixed')

hemis = ['lh']

# %%
for hemi in hemis:
    # fix header after extraction (mris_extract_main_component may reset it)
    print(f"Re-fixing surface header after extraction for {hemi}")
    fix_mc_surface_header(
        surface_path=surface_path.replace('hemixxx', hemi),
        pretess_path=vol_path,
        output_path=output_path.replace('hemixxx', hemi),
    )

    # Verify surfaceRAS header again after extraction
    info = mris_info(surface_path.replace('hemixxx', hemi))
    # Check for surfaceRAS with flexible whitespace (mris_info uses variable spacing)
    if not re.search(r"vertex\s+locs\s*:\s*surfaceRAS", info):
        print(f"mris_info full output after extraction:\n{info}")
        raise RuntimeError(
            f"Incorrect header in {output_path} after extraction: "
            "vertex locs is not set to surfaceRAS"
        )

# %%
