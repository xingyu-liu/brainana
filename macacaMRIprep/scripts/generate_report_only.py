# %%
import glob
import sys
from pathlib import Path

# Add the macacaMRIprep package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from macacaMRIprep.quality_control.reports import generate_qc_report
    from macacaMRIprep.utils.nextflow import load_config
except ImportError:
    raise ImportError("Failed to import generate_qc_report from macacaMRIprep.quality_control.reports")

# %%
dataset_dir = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_UNC_batch1'

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
