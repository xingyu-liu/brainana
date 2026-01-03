# banana Nextflow Pipeline

This directory contains a Nextflow implementation of the banana preprocessing pipeline, enabling maximum parallelization through per-step processing.

## Keeping Your Project Directory Clean

Nextflow creates several files and directories when running:
- `.nextflow/` - Cache and session directory
- `.nextflow.log*` - Log files
- `work/` - Work directory (intermediate files)

To keep your project directory clean, **always use the wrapper script**:

```bash
./run_nextflow.sh run main.nf --bids_dir /path/to/bids --output_dir /path/to/output
```

Or set environment variables before running Nextflow directly:

```bash
export NXF_HOME="$HOME/.nextflow"
export NXF_LOG="$HOME/.nextflow/logs/nextflow.log"
export NXF_WORK="$HOME/.nextflow/work"
nextflow -log "$NXF_LOG" run main.nf ...
```

The wrapper script automatically:
- Redirects `.nextflow/` to `$HOME/.nextflow/run/`
- Redirects log files to `$HOME/.nextflow/logs/`
- Uses the centralized work directory from `nextflow.config`

## Overview

The Nextflow pipeline breaks down preprocessing into individual steps that can run in parallel across subjects, sessions, and runs. This provides:

- **Maximum Parallelization**: All subjects' bias correction runs simultaneously
- **GPU Efficiency**: Skullstripping jobs queue for GPU resources automatically
- **Better Resource Utilization**: CPU-heavy and GPU steps run independently
- **Easy Debugging**: Failed steps are isolated and can be rerun independently
- **Resumability**: Nextflow can resume from any step automatically
- **Scalability**: Works on HPC clusters with job schedulers (SLURM, SGE, etc.)

## Architecture

### Processing Steps

**Anatomical Pipeline:**
1. `T1W_SYNTHESIS` - Synthesize multiple T1w runs (if needed)
2. `ANAT_REORIENT` - Reorient to template/RAS
3. `ANAT_CONFORM` - Conform to template space
4. `ANAT_BIAS_CORRECTION` - Bias field correction
5. `ANAT_SKULLSTRIPPING` - Skull stripping (GPU)
6. `ANAT_REGISTRATION` - Register to template

**Functional Pipeline:**
1. `FUNC_REORIENT` - Reorient + generate tmean
2. `FUNC_SLICE_TIMING` - Slice timing correction
3. `FUNC_MOTION_CORRECTION` - Motion correction
4. `FUNC_DESPIKE` - Despiking
5. `FUNC_BIAS_CORRECTION` - Bias correction on tmean
6. `FUNC_CONFORM` - Conform tmean to target
7. `FUNC_SKULLSTRIPPING` - Skull stripping on tmean (GPU)
8. `FUNC_REGISTRATION` - Register tmean to target
9. `FUNC_APPLY_TRANSFORMS` - Apply transforms to full 4D BOLD

**Quality Control:**
- `QC_ANATOMICAL` - Generate anatomical QC snapshots
- `QC_FUNCTIONAL` - Generate functional QC snapshots

## Prerequisites

1. **Nextflow** (>= 23.0)
   ```bash
   curl -s https://get.nextflow.io | bash
   # Or install via conda: conda install -c bioconda nextflow
   ```

2. **Docker** (for containerized execution)
   ```bash
   # Build the Docker image
   docker build -t banana:latest .
   ```

3. **Java** (>= 11, required by Nextflow)

## Quick Start

### Basic Usage

```bash
nextflow run main.nf \
  --bids_dir /path/to/bids \
  --output_dir /path/to/output \
  --output_space "NMT2Sym:res-1"
```

### With Custom Config

```bash
nextflow run main.nf \
  --bids_dir /path/to/bids \
  --output_dir /path/to/output \
  --output_space "NMT2Sym:res-1" \
  --config_file /path/to/config.yaml
```

### Filter Specific Subjects/Sessions

```bash
nextflow run main.nf \
  --bids_dir /path/to/bids \
  --output_dir /path/to/output \
  --output_space "NMT2Sym:res-1" \
  --subjects "01 02 03" \
  --sessions "001 002"
```

### Run on HPC (SLURM)

```bash
nextflow run main.nf \
  -profile slurm \
  --bids_dir /path/to/bids \
  --output_dir /path/to/output \
  --output_space "NMT2Sym:res-1"
```

### With GPU Support

```bash
nextflow run main.nf \
  -profile slurm \
  --bids_dir /path/to/bids \
  --output_dir /path/to/output \
  --output_space "NMT2Sym:res-1" \
  --gpu_enabled true
```

## Configuration

### Parameters

All parameters can be set via command line or in `nextflow.config`:

- `--bids_dir`: Path to BIDS dataset (required)
- `--output_dir`: Path to output directory (required)
- `--output_space`: Template space specification (e.g., "NMT2Sym:res-1")
- `--config_file`: Path to configuration YAML file (optional)
- `--subjects`: Comma-separated list of subject IDs (optional)
- `--sessions`: Comma-separated list of session IDs (optional)
- `--tasks`: Comma-separated list of task names (optional)
- `--runs`: Comma-separated list of run numbers (optional)
- `--anat_only`: Process only anatomical data
- `--overwrite`: Overwrite existing outputs

### Executor Profiles

The pipeline supports multiple execution environments:

- `local`: Local execution (default)
- `slurm`: SLURM HPC cluster
- `sge`: SGE HPC cluster
- `awsbatch`: AWS Batch
- `google`: Google Cloud Life Sciences

Example:
```bash
nextflow run main.nf -profile slurm ...
```

## Output Structure

Outputs maintain BIDS derivatives structure:

```
output_dir/
├── sub-01/
│   ├── ses-001/
│   │   ├── anat/
│   │   │   ├── sub-01_ses-001_desc-preproc_T1w.nii.gz
│   │   │   ├── sub-01_ses-001_space-NMT2Sym_desc-preproc_T1w.nii.gz
│   │   │   └── ...
│   │   ├── func/
│   │   │   ├── sub-01_ses-001_task-rest_space-NMT2Sym_desc-preproc_bold.nii.gz
│   │   │   └── ...
│   │   └── figures/
│   │       ├── sub-01_ses-001_desc-registration_T1w.png
│   │       └── ...
│   └── ...
└── reports/
    ├── nextflow_report.html
    ├── nextflow_timeline.html
    └── nextflow_dag.svg
```

## Resource Requirements

### CPU Steps
- Reorientation, conform, bias correction: ~2-4 GB RAM, 1-2 CPUs
- Registration: ~8-16 GB RAM, 4-8 CPUs

### GPU Steps
- Skullstripping: ~8 GB VRAM, 1 GPU

### Memory
- Minimum: 4 GB per process
- Recommended: 8-16 GB per process for registration steps

## Troubleshooting

### Common Issues

1. **Docker image not found**
   ```bash
   # Build the image
   docker build -t banana:latest .
   ```

2. **Out of memory errors**
   - Increase memory allocation in `nextflow.config`
   - Reduce parallel processes: `--max_cpus 4`

3. **GPU not available**
   - Check GPU queue configuration
   - Verify Docker GPU access: `docker run --gpus all banana:latest nvidia-smi`

4. **BIDS discovery fails**
   - Verify BIDS dataset structure
   - Check that `dataset_description.json` exists

## Advanced Usage

### Custom Resource Allocation

Edit `nextflow.config` to set process-specific resources:

```nextflow
process {
    withLabel: 'gpu' {
        clusterOptions = '--gres=gpu:1'
        cpus = 4
        memory = '16 GB'
    }
    
    withLabel: 'cpu' {
        cpus = 2
        memory = '8 GB'
    }
}
```

### Resuming Failed Runs

Nextflow automatically resumes from the last successful step:

```bash
nextflow run main.nf -resume ...
```

### Viewing Workflow DAG

After running, view the workflow graph:

```bash
# Open in browser
open output_dir/reports/nextflow_dag.svg
```

## Integration with Existing Code

The Nextflow pipeline uses the same step functions as the original CLI:

- `macacaMRIprep.steps.anatomical.*` - Anatomical step functions
- `macacaMRIprep.steps.functional.*` - Functional step functions
- `macacaMRIprep.steps.qc.*` - QC step functions

This ensures consistency between CLI and Nextflow execution.

## Performance

Expected speedup compared to sequential processing:

- **Small dataset** (1-5 subjects): 2-3x faster
- **Medium dataset** (10-20 subjects): 5-10x faster
- **Large dataset** (50+ subjects): 10-20x faster

Actual speedup depends on:
- Number of available CPUs/GPUs
- I/O bandwidth
- Network latency (for distributed execution)

## Support

For issues or questions:
- Check the main [README](../README_for_inz.rst)
- Review Nextflow logs in `output_dir/reports/`
- Check individual process logs in `output_dir/work/`

## Command Logs

After refactoring to Nextflow, command logs are available in several places:

### 1. Nextflow Process Command Logs
Each process creates a `command.log` file in its work directory:
```bash
# Find all command.log files
find ~/.nextflow/work -name "command.log" -type f

# Check a specific process
ls -la ~/.nextflow/work/*/command.log
```

### 2. Python Command Logs
Commands executed via `run_command()` are logged to:
- Process stdout/stderr (captured by Nextflow in work directories)
- Optional command log file (if enabled)

To enable a dedicated command log file that tracks all Python commands:
```python
from macacaMRIprep.utils import set_cmd_log_file
from pathlib import Path

# Set command log file (e.g., in your workflow initialization)
cmd_log_path = Path("output_dir") / "commands.log"
set_cmd_log_file(cmd_log_path)
```

All commands executed via `run_command()` will be written to this file in a format similar to FreeSurfer's `.cmd` files.

**Automatic Log Rotation**: To prevent log files from growing too large on big datasets, automatic rotation is enabled:
- Logs are rotated when they exceed 20 MB (configurable, default: 20 MB)
- Old logs are compressed (`.gz`) and numbered using standard convention:
  - `commands.log.1.gz` = most recent rotated log
  - `commands.log.2.gz` = older
  - `commands.log.3.gz` = even older
  - Higher numbers = older logs
- Up to 5 rotated logs are kept (oldest are automatically deleted)

To customize rotation settings:
```python
from macacaMRIprep.utils import set_cmd_log_rotation_config

set_cmd_log_rotation_config(
    max_size_mb=200.0,  # Rotate at 200 MB
    max_files=10,       # Keep 10 rotated files
    compress=True        # Compress old logs (default: True)
)
```

### 3. Nextflow Main Log
Overall workflow execution log:
```bash
cat ~/.nextflow/logs/nextflow.log
```

