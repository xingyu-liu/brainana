# %%
import glob
import sys
from pathlib import Path

# Add src/ to path for nhp_mri_prep imports (scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
try:
    from nhp_mri_prep.quality_control.reports import generate_qc_report
    from nhp_mri_prep.utils.nextflow import load_config
except ImportError:
    raise ImportError("Failed to import generate_qc_report from nhp_mri_prep.quality_control.reports")

# %%
dataset_dir = '/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_multianat_v2'

# %%
# get sub dir list
sublist = glob.glob(f'{dataset_dir}/sub-*')
sublist = [Path(sub) for sub in sublist if Path(sub).is_dir()]

# %%
config = load_config(f'{dataset_dir}/nextflow_reports/config.yaml')
for sub in sublist:
    snapshot_dir = sub / 'figures'
    report_path = sub.parent / f'{sub.name}_new.html'
    generate_qc_report(
        snapshot_dir=snapshot_dir,
        report_path=report_path,
        config=config
    )
# %%
