/*
 * Functional processing modules for macacaMRIprep Nextflow pipeline
 */

process FUNC_REORIENT {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir { 
        def sesPath = session_id ? "/ses-${session_id}" : ""
        "${params.output_dir}/sub-${subject_id}${sesPath}/func"
    },
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-reorient_bold.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_reorient
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.templates import resolve_template
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from macacaMRIprep.utils.nextflow import load_config, save_metadata, create_output_link, init_cmd_log_for_nextflow
    from pathlib import Path
    import shutil
    import os
    
    # Initialize command log file
    # Extract task and run from run_identifier if needed (for backward compatibility with logging)
    run_identifier = '${run_identifier}'
    # Parse run_identifier to extract task and run for logging
    import re
    task_match = re.search(r'task-([^_]+)', run_identifier)
    run_match = re.search(r'run-([^_]+)', run_identifier)
    task_name = task_match.group(1) if task_match else None
    run = run_match.group(1) if run_match else None
    
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_REORIENT',
        task_name=task_name,
        run=run
    )
    
    # Load config
    config = load_config('${config_file}')
    
    # Get BIDS naming template (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Get effective output_space (CLI > YAML > default)
    from macacaMRIprep.utils.nextflow import get_effective_output_space
    effective_output_space = get_effective_output_space('${params.output_space}', '${config_file}')
    
    # Resolve template if needed
    template_file = None
    if effective_output_space:
        template_file = Path(resolve_template(effective_output_space))
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='func_reoriented.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
    )
    
    # Run step
    result = func_reorient(input_obj, template_file=template_file)
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix='desc-reorient',
        modality='bold'
    )
    
    # Create BIDS-compliant symlink for Nextflow output and publishDir
    create_output_link(result.output_file, bids_output_filename)
    
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    save_metadata(result.metadata)
    EOF
    """
}

process FUNC_SLICE_TIMING {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-sliceTiming_bold.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_slice_timing_correction
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import shutil
    import os
    from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow
    
    # Initialize command log file
    # Extract task and run from run_identifier if needed
    run_identifier = '${run_identifier}'
    import re
    task_match = re.search(r'task-([^_]+)', run_identifier)
    run_match = re.search(r'run-([^_]+)', run_identifier)
    task_name = task_match.group(1) if task_match else None
    run = run_match.group(1) if run_match else None
    
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_SLICE_TIMING',
        task_name=task_name,
        run=run
    )
    
    # Load config
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    
    # Get original file path (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Load BIDS metadata from JSON file and update config
    from macacaMRIprep.utils.bids import find_bids_metadata
    from macacaMRIprep.config.bids_adapter import update_config_from_bids_metadata
    import logging
    logger = logging.getLogger(__name__)
    
    # Find BIDS dataset directory (parent of subject directory)
    bids_file_path = Path('${bids_naming_template}')
    # Navigate up from func/ to ses/ to sub/ to dataset root
    dataset_dir = bids_file_path.parent.parent.parent.parent
    func_metadata = find_bids_metadata(bids_file_path, dataset_dir)
    
    if func_metadata:
        logger.info(f"Data: found BIDS metadata - {len(func_metadata)} keys")
        config = update_config_from_bids_metadata(config, func_metadata, logger)
        logger.info(f"Config: updated slice timing configuration from BIDS metadata")
    else:
        logger.warning(f"Data: no BIDS metadata found for {bids_file_path}")
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='func_slice_timed.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
    )
    
    # Run step
    result = func_slice_timing_correction(input_obj)
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix='desc-sliceTiming',
        modality='bold'
    )
    
    # Create BIDS-compliant symlink for Nextflow output and publishDir
    create_output_link(result.output_file, bids_output_filename)
    
    # Copy additional files (e.g., tmean) with BIDS-compliant names
    for key, f in result.additional_files.items():
        if key == 'tmean':
            # Create BIDS-compliant name for tmean (use boldref suffix)
            tmean_bids_name = create_bids_output_filename(
                original_file_path=bids_naming_template,
                suffix='desc-sliceTiming',
                modality='boldref'
            )
            shutil.copy2(f, tmean_bids_name)
        else:
            shutil.copy2(f, f.name)
    
    # Save metadata
    save_metadata(result.metadata)
    EOF
    """
}

process FUNC_MOTION_CORRECTION {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,tsv}'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-motion_bold.nii.gz"), path("*desc-motion_boldref.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-confounds_timeseries.tsv"), emit: motion_params
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_motion_correction
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import shutil
    import os
    from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow
    
    # Initialize command log file
    # Extract task and run from run_identifier if needed
    run_identifier = '${run_identifier}'
    import re
    task_match = re.search(r'task-([^_]+)', run_identifier)
    run_match = re.search(r'run-([^_]+)', run_identifier)
    task_name = task_match.group(1) if task_match else None
    run = run_match.group(1) if run_match else None
    
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_MOTION_CORRECTION',
        task_name=task_name,
        run=run
    )
    
    # Load config
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    
    # Get original file path (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='func_motion_corrected.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
    )
    
    # Run step
    result = func_motion_correction(input_obj)
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix='desc-motion',
        modality='bold'
    )
    
    # Create BIDS-compliant symlink for Nextflow output and publishDir
    create_output_link(result.output_file, bids_output_filename)
    
    # Copy additional files with BIDS-compliant names
    for key, f in result.additional_files.items():
        if key == 'tmean':
            # Create BIDS-compliant name for tmean (use boldref suffix)
            tmean_bids_name = create_bids_output_filename(
                original_file_path=bids_naming_template,
                suffix='desc-motion',
                modality='boldref'
            )
            shutil.copy2(f, tmean_bids_name)
        elif key == 'motion_params':
            # Create BIDS-compliant name for motion parameters
            from macacaMRIprep.utils.bids import get_filename_stem
            original_stem = get_filename_stem(bids_naming_template)
            bids_prefix = original_stem.replace('_bold', '')
            motion_bids_name = f"{bids_prefix}_desc-confounds_timeseries.tsv"
            shutil.copy2(f, motion_bids_name)
        else:
            shutil.copy2(f, f.name)
    
    # Save metadata
    save_metadata(result.metadata)
    EOF
    """
}

process FUNC_GENERATE_TMEAN {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(bold_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path("*_bold.nii.gz"), path("*_boldref.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.utils.mri import calculate_func_tmean
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from macacaMRIprep.utils.nextflow import load_config, save_metadata, create_output_link, init_cmd_log_for_nextflow
    from pathlib import Path
    import shutil
    import os
    import logging
    
    # Initialize logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
    
    # Initialize command log file
    run_identifier = '${run_identifier}'
    import re
    task_match = re.search(r'task-([^_]+)', run_identifier)
    run_match = re.search(r'run-([^_]+)', run_identifier)
    task_name = task_match.group(1) if task_match else None
    run = run_match.group(1) if run_match else None
    
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_GENERATE_TMEAN',
        task_name=task_name,
        run=run
    )
    
    # Load config
    config = load_config('${config_file}')
    
    # Get BIDS naming template
    bids_naming_template = Path('${bids_naming_template}')
    
    # Input BOLD file
    bold_file = Path('${bold_file}')
    
    # Create symlink to BOLD file - preserve exact input structure
    # Simply use the input filename as-is (it's already BIDS-compliant)
    bids_bold_filename = bids_naming_template.name
    create_output_link(bold_file, bids_bold_filename)
    
    # Generate tmean file
    # Convert _bold to _boldref while preserving all other parts of the filename
    tmean_basename = bids_naming_template.name.replace('_bold.nii.gz', '_boldref.nii.gz')
    tmean_output_path = Path('work') / tmean_basename
    
    # Create work directory if it doesn't exist
    tmean_output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Calculate tmean
    logger.info(f"Step: generating temporal mean from {bold_file.name}")
    calculate_func_tmean(str(bold_file), str(tmean_output_path), logger)
    
    # Create BIDS-compliant symlink for tmean (just replace _bold with _boldref)
    bids_tmean_filename = tmean_basename
    create_output_link(tmean_output_path, bids_tmean_filename)
    
    # Save metadata
    metadata = {
        'step': 'FUNC_GENERATE_TMEAN',
        'subject_id': '${subject_id}',
        'session_id': '${session_id}' if '${session_id}' else None,
        'run_identifier': run_identifier,
        'input_file': str(bold_file),
        'output_bold': str(bids_bold_filename),
        'output_tmean': str(bids_tmean_filename)
    }
    save_metadata(metadata)
    EOF
    """
}

process FUNC_DESPIKE {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path(bold_file), path(tmean_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-despike_bold.nii.gz"), path("*desc-despike_boldref.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_despike
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import shutil
    import os
    from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow
    
    # Initialize command log file
    # Extract task and run from run_identifier if needed
    run_identifier = '${run_identifier}'
    import re
    task_match = re.search(r'task-([^_]+)', run_identifier)
    run_match = re.search(r'run-([^_]+)', run_identifier)
    task_name = task_match.group(1) if task_match else None
    run = run_match.group(1) if run_match else None
    
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_DESPIKE',
        task_name=task_name,
        run=run
    )
    
    # Load config
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    
    # Get original file path (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Create step input (process BOLD, inherit tmean)
    input_obj = StepInput(
        input_file=Path('${bold_file}'),  # Process BOLD
        working_dir=Path('work'),
        config=config,
        output_name='func_despiked.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
    )
    
    # Run step (processes BOLD, generates new tmean)
    result = func_despike(input_obj)
    
    # Inherit tmean from input if step doesn't generate one, otherwise use generated tmean
    # func_despike generates tmean, so we use it
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix='desc-despike',
        modality='bold'
    )
    
    # Create BIDS-compliant symlink for Nextflow output and publishDir
    create_output_link(result.output_file, bids_output_filename)
    
    # Copy additional files (e.g., tmean) with BIDS-compliant names
    for key, f in result.additional_files.items():
        if key == 'tmean' or key == 'imagef_despiked_tmean':
            # Create BIDS-compliant name for tmean (use boldref suffix)
            tmean_bids_name = create_bids_output_filename(
                original_file_path=bids_naming_template,
                suffix='desc-despike',
                modality='boldref'
            )
            shutil.copy2(f, tmean_bids_name)
        else:
            shutil.copy2(f, f.name)
    
    # Save metadata
    save_metadata(result.metadata)
    EOF
    """
}

process FUNC_BIAS_CORRECTION {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*desc-biasCorrection_boldref.nii.gz',
        saveAs: { filename -> filename }
    
    input:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    // Use stageAs to automatically create bold_inherited.nii.gz symlink (avoids duplicate symlinks)
    tuple val(subject_id), val(session_id), val(run_identifier), path(bold_file, stageAs: 'bold_inherited.nii.gz'), path(tmean_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path("bold_inherited.nii.gz"), path("*desc-biasCorrection_boldref.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    # Set thread environment variables from config
    THREADS=\$(\${PYTHON:-python3} <<'PYTHON'
import yaml
with open('${config_file}') as f:
    config = yaml.safe_load(f)
threads = config.get('func', {}).get('bias_correction', {}).get('threads', 8)
threads = min(threads, 32)  # Cap at 32 to prevent oversubscription
print(threads)
PYTHON
    )
    
    export OMP_NUM_THREADS=\$THREADS
    export MKL_NUM_THREADS=\$THREADS
    export NUMEXPR_NUM_THREADS=\$THREADS
    export OPENBLAS_NUM_THREADS=\$THREADS
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=\$THREADS
    
    echo "Set thread environment variables to \$THREADS"
    
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.functional import func_bias_correction
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.bids import create_bids_output_filename
from pathlib import Path
import shutil
import os
from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow

# Initialize command log file
# Extract task and run from run_identifier if needed
run_identifier = '${run_identifier}'
import re
task_match = re.search(r'task-([^_]+)', run_identifier)
run_match = re.search(r'run-([^_]+)', run_identifier)
task_name = task_match.group(1) if task_match else None
run = run_match.group(1) if run_match else None

init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='FUNC_BIAS_CORRECTION',
    task_name=task_name,
    run=run
)

# Load config
from macacaMRIprep.utils.nextflow import load_config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# bold_inherited.nii.gz is automatically created by Nextflow via stageAs parameter
# No need to manually create symlink - Nextflow handles it
bold_inherited = Path('bold_inherited.nii.gz')

# Verify the file exists (Nextflow should have staged it)
if not bold_inherited.exists():
    raise FileNotFoundError(f"BOLD inherited file does not exist: {bold_inherited}. Nextflow stageAs may have failed.")

# Create step input (process tmean, inherit BOLD via symlink)
input_obj = StepInput(
    input_file=Path('${tmean_file}'),  # Process tmean
    working_dir=Path('work'),
    config=config,
    output_name='func_bias_corrected.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
)

# Run step
result = func_bias_correction(input_obj)

# Generate BIDS-compliant output filename (bias correction operates on tmean, so use boldref)
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-biasCorrection',
    modality='boldref'
)

# Create BIDS-compliant symlink for Nextflow output and publishDir
create_output_link(result.output_file, bids_output_filename)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process FUNC_CONFORM {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,mat}',
        saveAs: { filename -> filename == 'template_resampled.nii.gz' ? null : filename }
    
    input:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path(bold_file), path(tmean_file), val(bids_naming_template)
    path(anat_brain_file)
    path config_file
    
    output:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-conform_bold.nii.gz"), path("*desc-conform_boldref.nii.gz"), val(bids_naming_template), emit: output
    path "*.mat", emit: transforms
    tuple val(subject_id), val(session_id), val(run_identifier), path("template_resampled.nii.gz"), val(bids_naming_template), emit: template_resampled
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_conform
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.templates import resolve_template
    from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
    from pathlib import Path
    import shutil
    import os
    import sys
    from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow
    
    # Initialize command log file
    # Extract task and run from run_identifier if needed
    run_identifier = '${run_identifier}'
    import re
    task_match = re.search(r'task-([^_]+)', run_identifier)
    run_match = re.search(r'run-([^_]+)', run_identifier)
    task_name = task_match.group(1) if task_match else None
    run = run_match.group(1) if run_match else None
    
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_CONFORM',
        task_name=task_name,
        run=run
    )
    
    # Load config
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    
    # Get original file path (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Determine target file (anatomical or template based on pipeline)
    registration_pipeline = config.get('func', {}).get('registration_pipeline', 'func2anat2template')
    
    # Check if anatomical brain file is available
    anat_brain_path_str = '${anat_brain_file}'
    has_anat_brain = anat_brain_path_str and anat_brain_path_str.strip() != '' and '.dummy' not in anat_brain_path_str
    
    # Get effective output_space (CLI > YAML > default)
    from macacaMRIprep.utils.nextflow import get_effective_output_space
    effective_output_space = get_effective_output_space('${params.output_space}', '${config_file}')
    
    if registration_pipeline == 'func2template':
        # Always use template for func2template pipeline
        target_file = Path(resolve_template(effective_output_space))
    elif registration_pipeline in ['func2anat', 'func2anat2template']:
        # Use anatomical brain if available, otherwise fallback to template
        if has_anat_brain:
            anat_brain_path = Path(anat_brain_path_str)
            if anat_brain_path.exists():
                target_file = anat_brain_path
            else:
                # Anatomical file doesn't exist, use template
                target_file = Path(resolve_template(effective_output_space))
        else:
            # No anatomical brain provided, use template
            target_file = Path(resolve_template(effective_output_space))
    else:
        # Default: use template
        target_file = Path(resolve_template(effective_output_space))
    
    # Create step input for tmean (used for conform registration)
    tmean_input_obj = StepInput(
        input_file=Path('${tmean_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='func_tmean_conformed.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
    )
    
    # Run step (conforms tmean and applies transform to 4D BOLD)
    result = func_conform(tmean_input_obj, target_file=target_file, bold_4d_file=Path('${bold_file}'))
    
    # Generate BIDS-compliant output filenames
    # Output 1: conformed tmean (boldref)
    bids_output_filename_tmean = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix='desc-conform',
        modality='boldref'
    )
    
    # Output 2: conformed 4D BOLD (bold)
    bids_output_filename_bold = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix='desc-conform',
        modality='bold'
    )
    
    # Create BIDS-compliant symlinks for Nextflow output and publishDir
    create_output_link(result.output_file, bids_output_filename_tmean)
    
    # Handle 4D BOLD output if present
    if 'bold_4d_conformed' in result.additional_files:
        create_output_link(result.additional_files['bold_4d_conformed'], bids_output_filename_bold)
    else:
        # For session-level operations (e.g., when run_identifier is "session-01"),
        # there may be no 4D BOLD file to conform. Create a symlink to tmean as placeholder
        # to satisfy Nextflow output requirements. This dummy file will be ignored downstream
        # when only tmean is needed.
        # Use the conformed tmean file as source (result.output_file points to the actual file in work/)
        create_output_link(result.output_file, bids_output_filename_bold)
        print(f"INFO: Created dummy BOLD output (symlink to tmean) for session-level operation: {bids_output_filename_bold}", file=sys.stderr)
    
    # Copy additional files (e.g., transforms) with BIDS-compliant names
    original_stem = get_filename_stem(bids_naming_template)
    bids_prefix = original_stem.replace('_bold', '')
    
    for key, f in result.additional_files.items():
        if key == 'forward_transform':
            # Forward transform: from-scanner_to-bold
            bids_transform_name = f"{bids_prefix}_from-scanner_to-bold_mode-image_xfm.mat"
            shutil.copy2(f, bids_transform_name)
        elif key == 'inverse_transform':
            # Inverse transform: from-bold_to-scanner
            bids_transform_name = f"{bids_prefix}_from-bold_to-scanner_mode-image_xfm.mat"
            shutil.copy2(f, bids_transform_name)
        elif key == 'template_resampled':
            # Create symlink at root level for Nextflow output pattern
            template_resampled_dest = Path('template_resampled.nii.gz')
            if template_resampled_dest.exists() or template_resampled_dest.is_symlink():
                template_resampled_dest.unlink()
            os.symlink(f.resolve(), template_resampled_dest)
        else:
            shutil.copy2(f, f.name)
    
    # Save metadata
    save_metadata(result.metadata)
    EOF
    """
}

process FUNC_SKULLSTRIPPING {
    label 'gpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*desc-brain_mask.nii.gz'  // Only publish mask, not brain (brain is intermediate)
    
    input:
    // Combined channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
    // Use stageAs to automatically create bold_inherited.nii.gz symlink (avoids duplicate symlinks)
    tuple val(subject_id), val(session_id), val(run_identifier), path(bold_file, stageAs: 'bold_inherited.nii.gz'), path(tmean_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: 6 elements [sub, ses, run_identifier, bold_file, tmean_file (brain_file), bids_template]
    // brain mask channel: 5 elements [sub, ses, run_identifier, mask_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path("bold_inherited.nii.gz"), path("*_boldref_brain.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-brain_mask.nii.gz"), val(bids_naming_template), emit: brain_mask
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_skullstripping
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import get_filename_stem
    from pathlib import Path
    import shutil
    import os
    from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow
    
    # Initialize command log file
    # Extract task and run from run_identifier if needed
    run_identifier = '${run_identifier}'
    import re
    task_match = re.search(r'task-([^_]+)', run_identifier)
    run_match = re.search(r'run-([^_]+)', run_identifier)
    task_name = task_match.group(1) if task_match else None
    run = run_match.group(1) if run_match else None
    
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_SKULLSTRIPPING',
        task_name=task_name,
        run=run
    )
    
    # Load config
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    
    # Get original file path (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # bold_inherited.nii.gz is automatically created by Nextflow via stageAs parameter
    # No need to manually create symlink - Nextflow handles it
    bold_inherited = Path('bold_inherited.nii.gz')
    
    # Verify the file exists (Nextflow should have staged it)
    if not bold_inherited.exists():
        raise FileNotFoundError(f"BOLD inherited file does not exist: {bold_inherited}. Nextflow stageAs may have failed.")
    
    # Create step input (process tmean → brain, inherit BOLD via symlink)
    input_obj = StepInput(
        input_file=Path('${tmean_file}'),  # Process tmean → brain
        working_dir=Path('work'),
        config=config,
        output_name='func_brain.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
    )
    
    # Run step (processes tmean to create brain)
    result = func_skullstripping(input_obj)
    
    # Generate BIDS-compliant output filename for mask
    # Format: {prefix}_desc-brain_mask.nii.gz
    original_stem = get_filename_stem(bids_naming_template)
    bids_prefix_wobold = original_stem.replace("_bold", "").replace("_boldref", "")
    
    # Create symlink for mask with BIDS-compliant name (will be published)
    if "brain_mask" in result.additional_files:
        bids_additional_name = f"{bids_prefix_wobold}_desc-brain_mask.nii.gz"
        # Create symlink from work directory to process output directory
        create_output_link(result.additional_files["brain_mask"], bids_additional_name)
    
    # Create symlink for brain file (in working dir, but not published to BIDS output)
    # Format: {prefix}_boldref_brain.nii.gz
    if result.output_file.exists():
        bids_brain_name = f"{bids_prefix_wobold}_boldref_brain.nii.gz"
        # Create symlink from work directory to process output directory
        create_output_link(result.output_file, bids_brain_name)
    
    # Save metadata
    save_metadata(result.metadata)
    EOF
    """
}

process FUNC_REGISTRATION {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,h5}'
    
    input:
    // 3-input pattern - EXACTLY like T2W_TO_T1W_REGISTRATION: (tuple, path, path)
    // Tuple: 8 elements [sub, ses, run_identifier, bold_file, tmean_file, bids_template, anat_session_id, is_across_ses]
    // anat_brain: separate path input (like t1w_file in T2W)
    // config_file: config path
    tuple val(subject_id), val(session_id), val(run_identifier), path(bold_file), path(tmean_file), val(bids_naming_template), val(anat_session_id), val(is_across_ses)
    path(anat_brain)
    path config_file
    
    output:
    // Combined channel: [sub, ses, run_identifier, bold_file, registered_tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(run_identifier), path("bold_inherited.nii.gz"), path("*space-*boldref.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(run_identifier), path("*from-bold_to-*_mode-image_xfm.h5"), emit: transforms
    tuple val(subject_id), val(session_id), val(run_identifier), path("*from-*_to-bold_mode-image_xfm.h5"), emit: inverse_transforms
    // Reference file used for registration (resampled target if keep_func_resolution=True)
    tuple val(subject_id), val(session_id), val(run_identifier), path("*target_res-func_for_registration.nii.gz"), emit: reference
    // Metadata file: contains target_type and target2template (tab-separated)
    tuple val(subject_id), val(session_id), val(run_identifier), path("registration_metadata.txt"), emit: metadata
    // Anatomical session ID used for registration (for matching with anat_reg_transforms)
    tuple val(subject_id), val(session_id), val(run_identifier), val(anat_session_id), emit: anat_session
    path "*.json", emit: metadata_json
    
    script:
    def template_name = params.output_space.split(':')[0]
    """
    # Set thread environment variables from config
    THREADS=\$(\${PYTHON:-python3} <<'PYTHON'
import yaml
with open('${config_file}') as f:
    config = yaml.safe_load(f)
threads = config.get('registration', {}).get('threads', 8)
threads = min(threads, 32)  # Cap at 32 to prevent oversubscription
print(threads)
PYTHON
    )
    
    export OMP_NUM_THREADS=\$THREADS
    export MKL_NUM_THREADS=\$THREADS
    export NUMEXPR_NUM_THREADS=\$THREADS
    export OPENBLAS_NUM_THREADS=\$THREADS
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=\$THREADS
    
    echo "Set thread environment variables to \$THREADS"
    
    # Check if using anatomical from different session
    if [ "${is_across_ses}" = "true" ]; then
        echo "WARNING: Functional session ${session_id} for subject ${subject_id} does not have anatomical data." >&2
        echo "WARNING: Using anatomical data from session ${anat_session_id} instead." >&2
        echo "WARNING: This may affect registration quality if sessions have different head positions." >&2
    fi
    
    python3 <<EOF
from macacaMRIprep.steps.functional import func_registration
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.templates import resolve_template
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path
import shutil
import os
import sys
from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow

# Initialize command log file
# Extract task and run from run_identifier if needed
run_identifier = '${run_identifier}'
import re
task_match = re.search(r'task-([^_]+)', run_identifier)
run_match = re.search(r'run-([^_]+)', run_identifier)
task_name = task_match.group(1) if task_match else None
run = run_match.group(1) if run_match else None

init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='FUNC_REGISTRATION',
    task_name=task_name,
    run=run
)

# Load config
from macacaMRIprep.utils.nextflow import load_config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Check if anatomical data is available
is_across_ses = '${is_across_ses}' == 'true'
anat_session_id = '${anat_session_id}'
func_session_id = '${session_id}'

# Determine target based on registration pipeline
registration_pipeline = config.get('func', {}).get('registration_pipeline', 'func2anat2template')
template_name = '${template_name}'

# Check if anatomical brain file exists (handle missing anatomical data)
anat_brain_path_str = '${anat_brain}'
# Check if path is a dummy/placeholder (contains .dummy or is empty)
is_dummy_anat = '.dummy' in anat_brain_path_str or not anat_brain_path_str or anat_brain_path_str.strip() == ''
if is_dummy_anat:
    has_anat = False
    anat_brain_path = None
else:
    anat_brain_path = Path(anat_brain_path_str)
    has_anat = anat_brain_path.exists()

# Get effective output_space (CLI > YAML > default)
from macacaMRIprep.utils.nextflow import get_effective_output_space
effective_output_space = get_effective_output_space('${params.output_space}', '${config_file}')
is_native_space = effective_output_space and effective_output_space.lower() == 'native'

# Determine target based on registration pipeline
# FUNC_REGISTRATION registers functional tmean/brain to anatomical skull-stripped brain
if registration_pipeline == 'func2template' or not has_anat:
    # Direct to template registration (no anatomical needed)
    target_file = Path(resolve_template(effective_output_space))
    target_type = 'template'
    target_name = template_name
    target2template = False
    if not has_anat:
        print(f"INFO: No anatomical data available, registering directly to template", file=sys.stderr)
elif registration_pipeline == 'func2anat':
    if not has_anat:
        # Fallback to template if no anatomical data
        target_file = Path(resolve_template(effective_output_space))
        target_type = 'template'
        target_name = template_name
        target2template = False
        print(f"INFO: No anatomical data available for func2anat pipeline, using template instead", file=sys.stderr)
    else:
        # Use anatomical skull-stripped brain as target
        target_file = anat_brain_path
        target_type = 'anat'
        target_name = 'anat'  # Registering to anatomical brain (not in template space yet)
        target2template = False
        if is_across_ses:
            print(f"WARNING: Using anatomical from session {anat_session_id} for functional session {func_session_id}", file=sys.stderr)
else:  # func2anat2template
    if not has_anat:
        # Fallback to template if no anatomical data
        target_file = Path(resolve_template(effective_output_space))
        target_type = 'template'
        target_name = template_name
        target2template = False
        print(f"INFO: No anatomical data available for func2anat2template pipeline, using template instead", file=sys.stderr)
    else:
        # First register to anatomical skull-stripped brain
        target_file = anat_brain_path
        target_type = 'anat'
        target_name = 'anat'  # Registering to anatomical brain (not in template space yet)
        target2template = not is_native_space  # True if not native space, False if native
        if is_across_ses:
            print(f"WARNING: Using anatomical from session {anat_session_id} for functional session {func_session_id}", file=sys.stderr)

# Create symlink to inherited BOLD file for output
bold_input = Path('${bold_file}')
bold_inherited = Path('bold_inherited.nii.gz')

# Ensure source file exists
if not bold_input.exists():
    raise FileNotFoundError(f"BOLD input file does not exist: {bold_input}")

# Check if input and output are the same file (resolve to check actual file)
bold_input_resolved = bold_input.resolve()
bold_inherited_resolved = bold_inherited.resolve()

# If they're the same file, no need to create symlink - just use it
if bold_input_resolved == bold_inherited_resolved:
    # Input is already the output file - nothing to do
    pass
else:
    # Remove existing symlink/file if present
    if bold_inherited.exists() or bold_inherited.is_symlink():
        bold_inherited.unlink()

    # Create symlink using relative path (works better with Nextflow file staging)
    # Get the relative path from bold_inherited's parent to bold_input
    try:
        # Use relative path for symlink (more reliable with Nextflow staging)
        bold_input_rel = os.path.relpath(str(bold_input), str(bold_inherited.parent))
        os.symlink(bold_input_rel, str(bold_inherited))
    except OSError as e:
        # If relative symlink fails, try absolute path
        try:
            os.symlink(str(bold_input_resolved), str(bold_inherited_resolved))
        except OSError as e2:
            # If symlink fails completely, try copying the file instead
            print(f"WARNING: Symlink creation failed ({e2}), copying file instead", file=sys.stderr)
            shutil.copy2(str(bold_input_resolved), str(bold_inherited_resolved))

# Verify the output file exists
if not bold_inherited.exists():
    raise FileNotFoundError(f"Failed to create bold_inherited.nii.gz: symlink/copy failed")

# Create step input
input_obj = StepInput(
    input_file=Path('${tmean_file}'),  # Process tmean → registered tmean, inherit BOLD via symlink
    working_dir=Path('work'),
    config=config,
    output_name='func_tmean_registered.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
)

# Run step
result = func_registration(input_obj, target_file=target_file, target_type=target_type)

# Generate BIDS-compliant output filename with space entity
# Format: space-{target_name}_boldref.nii.gz (registered tmean/brain)
# Remove _bold from original stem and add space entity with boldref suffix
original_stem = get_filename_stem(bids_naming_template)
bids_prefix_wo_modality = original_stem.replace('_bold', '')
# For anatomical registration, use 'T1w' as space name (standard BIDS convention)
if target_type == 'anat':
    space_name = 'T1w'
else:
    space_name = target_name
bids_output_filename = f"{bids_prefix_wo_modality}_space-{space_name}_boldref.nii.gz"

# Create BIDS-compliant symlink for Nextflow output and publishDir
create_output_link(result.output_file, bids_output_filename)

# Copy additional files (e.g., transforms) with BIDS-compliant names
bids_prefix = bids_prefix_wo_modality

for key, f in result.additional_files.items():
    if key == 'forward_transform':
        # Forward transform: from-bold_to-{space_name}
        # Use space_name (T1w for anatomical, template name for template)
        bids_transform_name = f"{bids_prefix}_from-bold_to-{space_name}_mode-image_xfm.h5"
        create_output_link(f, bids_transform_name)
    elif key == 'inverse_transform':
        # Inverse transform: from-{space_name}_to-bold
        bids_transform_name = f"{bids_prefix}_from-{space_name}_to-bold_mode-image_xfm.h5"
        create_output_link(f, bids_transform_name)
    else:
        create_output_link(f, f.name)

# Save reference file if it was created (for apply transforms and QC)
working_dir = Path('work')
reference_file = working_dir / "target_res-func_for_registration.nii.gz"
reference_output_name = f"{bids_prefix}_target_res-func_for_registration.nii.gz"
keep_func_resolution = config.get("registration.keep_func_resolution", True)

if reference_file.exists():
    # Check if file is empty
    file_size = reference_file.stat().st_size
    if file_size == 0:
        if keep_func_resolution:
            raise ValueError(f"Reference file exists but is empty: {reference_file}. This may indicate an error during resampling.")
        else:
            # Empty file is expected when keep_func_resolution is False
            Path(reference_output_name).touch()
            print(f"Output: reference file is empty (keep_func_resolution=False)", file=sys.stderr)
    else:
        # Copy reference file to output directory with BIDS-compliant name
        shutil.copy2(reference_file, reference_output_name)
        print(f"Output: reference file saved: {reference_output_name}, size: {file_size} bytes", file=sys.stderr)
elif keep_func_resolution:
    # If keep_func_resolution is True, the file should have been created
    raise FileNotFoundError(f"Reference file should have been created but is missing: {reference_file}. This may indicate an error during resampling.")
else:
    # Create empty file as placeholder (Nextflow requires output) when keep_func_resolution is False
    Path(reference_output_name).touch()
    print(f"Output: no reference file created (keep_func_resolution=False)", file=sys.stderr)

# Save metadata JSON
save_metadata(result.metadata)

# Output metadata for Nextflow tuple channel
# Write target_type and target2template to a single file (tab-separated)
with open('registration_metadata.txt', 'w') as f:
    f.write(f"{target_type}\t{target2template}")
print(f"Metadata: target_type={target_type}, target2template={target2template}", file=sys.stderr)
EOF
    """
}

process FUNC_APPLY_TRANSFORMS {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,h5}'
    
    input:
    // Input structure: [sub, ses, run_identifier, tmean_registered, func2target_transform, anat2template_transform, bids_template, target_type, target2template, reference_file]
    // For sequential: anat2template_transform is real file
    // For single: anat2template_transform is dummy file
    tuple val(subject_id), val(session_id), val(run_identifier), path(tmean_registered, stageAs: 'tmean_reference.nii.gz'), path("*from-bold_to-*_mode-image_xfm.h5"), path(anat2template_transform), val(bids_naming_template), val(target_type), val(target2template), path(reference_file)
    path(func_4d_file)  // Original 4D BOLD file
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(run_identifier), path("*space-*desc-preproc_bold.nii.gz"), path("*space-*desc-preproc_boldref.nii.gz"), val(bids_naming_template), emit: output
    // Reference file for QC: final target reference at appropriate resolution
    tuple val(subject_id), val(session_id), val(run_identifier), path("*target_final.nii.gz"), emit: reference
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.functional import func_apply_transforms
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow, get_effective_output_space
from pathlib import Path
import glob
import shutil
import os

# Get effective output_space (CLI > YAML > default)
effective_output_space = get_effective_output_space('${params.output_space}', '${config_file}')
template_name = effective_output_space.split(':')[0] if effective_output_space else 'NMT2Sym'

# Initialize command log file
# Extract task and run from run_identifier if needed
run_identifier = '${run_identifier}'
import re
task_match = re.search(r'task-([^_]+)', run_identifier)
run_match = re.search(r'run-([^_]+)', run_identifier)
task_name = task_match.group(1) if task_match else None
run = run_match.group(1) if run_match else None

init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='FUNC_APPLY_TRANSFORMS',
    task_name=task_name,
    run=run
)

# Load config
from macacaMRIprep.utils.nextflow import load_config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Get input parameters
target_type = '${target_type}'
target2template = '${target2template}' == 'true'
# Get func2target transform from glob (from-bold_to-*)
func2target_transform_files = [Path(f) for f in glob.glob('*from-bold_to-*_mode-image_xfm.h5')]
if not func2target_transform_files:
    raise FileNotFoundError("No func2target transform file found")
func2target_transform = func2target_transform_files[0]

# Handle anat2template_transform - may be a single file or space-separated string
anat2template_transform_str = '${anat2template_transform}'
if ' ' in anat2template_transform_str:
    # Multiple files - get the forward transform (from-T1w_to-*)
    anat2template_files = [Path(f.strip()) for f in anat2template_transform_str.split() if f.strip()]
    anat2template_transform_path = None
    for f in anat2template_files:
        if 'from-T1w_to-' in str(f) or 'from-anat_to-' in str(f):
            anat2template_transform_path = f
            break
    if anat2template_transform_path is None:
        anat2template_transform_path = anat2template_files[0] if anat2template_files else Path('')
else:
    anat2template_transform_path = Path(anat2template_transform_str)

reference_file_input = Path('${reference_file}')
func_4d_input = Path('${func_4d_file}')

# Check if anat2template_transform is a dummy file
is_dummy_anat2template = '.dummy' in str(anat2template_transform_path) or not anat2template_transform_path.exists() or anat2template_transform_path == Path('')

# Determine if sequential transforms are needed
is_sequential = target2template and target_type == 'anat' and not is_dummy_anat2template

# Import additional modules needed for sequential transforms
from macacaMRIprep.operations.registration import ants_apply_transforms as ants_apply_transforms_op
from macacaMRIprep.utils.templates import resolve_template
from macacaMRIprep.utils import get_image_resolution
import numpy as np
from macacaMRIprep.utils import run_command
import sys
import logging

# Create logger for functions that require it
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

working_dir = Path('work')
working_dir.mkdir(parents=True, exist_ok=True)

if is_sequential:
    # Sequential transforms: func2anat then anat2template
    print("INFO: Applying sequential transforms: func2anat then anat2template", file=sys.stderr)
    
    # Validate reference file exists and is valid
    if not reference_file_input.exists():
        raise FileNotFoundError(f"Reference file does not exist: {reference_file_input}")
    file_size = reference_file_input.stat().st_size
    if file_size == 0:
        raise ValueError(f"Reference file is empty: {reference_file_input}")
    print(f"INFO: Reference file exists: {reference_file_input}, size: {file_size} bytes", file=sys.stderr)
    
    # Step 1: Apply func2anat transform
    anat_target_name = "T1w"
    anat_fixedf = reference_file_input  # Use reference from registration (resampled anat if available)
    
    # Prepare resampled anat for reference if needed
    if config.get("registration.keep_func_resolution", True):
        anat_reff = reference_file_input
        print(f"INFO: Using resampled anat from registration for apply transforms", file=sys.stderr)
    else:
        # Need to get original anat file - this should be passed, but for now use reference
        anat_reff = reference_file_input
    
    # Apply func2anat transform to 4D BOLD
    result_anat = ants_apply_transforms_op(
        movingf=str(func_4d_input),
        moving_type=3,  # 3D time series
        interpolation=config.get("registration", {}).get("interpolation", "LanczosWindowedSinc"),
        outputf_name="func2anat.nii.gz",
        fixedf=str(anat_reff),
        transformf=[str(func2target_transform)],
        reff=str(anat_reff),
        working_dir=str(working_dir),
        generate_tmean=True,
        logger=logger
    )
    
    func_all_anat = Path(result_anat["imagef_registered"])
    func_tmean_anat = Path(result_anat.get("imagef_registered_tmean", func_all_anat))
    
    # Save functional data in anat space
    func_anat_output_name = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix=f'space-{anat_target_name}_desc-preproc',
        modality='bold'
    )
    create_output_link(func_all_anat, func_anat_output_name)
    
    # Save boldref in anat space
    func_anat_boldref_name = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix=f'space-{anat_target_name}_desc-preproc',
        modality='boldref'
    )
    create_output_link(func_tmean_anat, func_anat_boldref_name)
    
    # Step 2: Apply anat2template transform
    template_fixedf = Path(resolve_template(effective_output_space))
    
    # Resample template to func resolution if needed
    if config.get("registration.keep_func_resolution", True):
        template_reff = working_dir / "template_res-func_for_apply_transforms.nii.gz"
        func_res = np.round(get_image_resolution(str(func_all_anat), logger=logger), 1)
        cmd_resample = ['3dresample', 
                        '-input', str(template_fixedf), '-prefix', str(template_reff), 
                        '-rmode', 'Cu',
                        '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])]
        run_command(cmd_resample, step_logger=logger)
        print(f"INFO: Template resampled to func resolution", file=sys.stderr)
    else:
        template_reff = template_fixedf
    
    # Apply anat2template transform to 4D BOLD
    result_template = ants_apply_transforms_op(
        movingf=str(func_all_anat),
        moving_type=3,  # 3D time series
        interpolation=config.get("registration", {}).get("interpolation", "LanczosWindowedSinc"),
        outputf_name="func2template.nii.gz",
        fixedf=str(template_fixedf),
        transformf=[str(anat2template_transform_path)],
        reff=str(template_reff),
        working_dir=str(working_dir),
        generate_tmean=True,
        logger=logger
    )
    
    func_all_template = Path(result_template["imagef_registered"])
    func_tmean_template = Path(result_template.get("imagef_registered_tmean", func_all_template))
    
    # Save functional data in template space (final output)
    func_template_output_name = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix=f'space-{template_name}_desc-preproc',
        modality='bold'
    )
    create_output_link(func_all_template, func_template_output_name)
    
    # Save boldref in template space (final output)
    func_template_boldref_name = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix=f'space-{template_name}_desc-preproc',
        modality='boldref'
    )
    create_output_link(func_tmean_template, func_template_boldref_name)
    
    # Output final reference file for QC: template at appropriate resolution
    # Sequential transforms: final space is template
    bids_prefix = get_filename_stem(bids_naming_template).replace('_bold', '')
    target_final_output = f"{bids_prefix}_target_final.nii.gz"
    target_final_path = Path(target_final_output)
    
    # Determine final reference based on keep_func_resolution
    # If keep_func_resolution=True: use template_reff (resampled to func resolution)
    # If keep_func_resolution=False: use template_fixedf (original template)
    if config.get("registration.keep_func_resolution", True):
        # Use resampled template (already created above)
        if template_reff.exists() and template_reff != template_fixedf:
            if template_reff.resolve() != target_final_path.resolve():
                shutil.copy2(template_reff, target_final_output)
                print(f"INFO: Created target_final.nii.gz from resampled template (func resolution)", file=sys.stderr)
            else:
                # Same file - read and write to create a new file
                data = template_reff.read_bytes()
                target_final_path.write_bytes(data)
                print(f"INFO: Created target_final.nii.gz from resampled template (func resolution)", file=sys.stderr)
        else:
            raise FileNotFoundError(f"Resampled template reference not found: {template_reff}")
    else:
        # Use original template
        if template_fixedf.exists():
            if template_fixedf.resolve() != target_final_path.resolve():
                shutil.copy2(template_fixedf, target_final_output)
                print(f"INFO: Created target_final.nii.gz from original template (native resolution)", file=sys.stderr)
            else:
                # Same file - read and write to create a new file
                data = template_fixedf.read_bytes()
                target_final_path.write_bytes(data)
                print(f"INFO: Created target_final.nii.gz from original template (native resolution)", file=sys.stderr)
        else:
            raise FileNotFoundError(f"Template file not found: {template_fixedf}")
    
    # Ensure file exists
    if not target_final_path.exists():
        raise FileNotFoundError(f"Failed to create target_final.nii.gz: {target_final_path}")
    print(f"INFO: target_final.nii.gz created, size: {target_final_path.stat().st_size} bytes", file=sys.stderr)
    
    # Final outputs are in template space
    final_output_file = func_all_template
    final_boldref_file = func_tmean_template
    final_space_name = template_name
    
else:
    # Single transform: func2anat or func2template
    print(f"INFO: Applying single transform: func2{target_type}", file=sys.stderr)
    
    if target_type == 'anat':
        target_name = "T1w"
    else:
        target_name = template_name
    
    # Prepare reference file
    if config.get("registration.keep_func_resolution", True):
        reff = reference_file_input
    else:
        if target_type == 'anat':
            reff = reference_file_input  # Should be original anat file, but use reference for now
        else:
            reff = Path(resolve_template(effective_output_space))
    
    # Validate reference file exists and is valid (if not template)
    if reff == reference_file_input:
        if not reference_file_input.exists():
            raise FileNotFoundError(f"Reference file does not exist: {reference_file_input}")
        file_size = reference_file_input.stat().st_size
        if file_size == 0:
            raise ValueError(f"Reference file is empty: {reference_file_input}")
        print(f"INFO: Reference file exists: {reference_file_input}, size: {file_size} bytes", file=sys.stderr)
    
    # Apply single transform
    result = func_apply_transforms(
        StepInput(
            input_file=func_4d_input,
            working_dir=working_dir,
            config=config,
            output_name='func_registered.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
        ),
        transform_files=[func2target_transform],
        reference_file=reff
    )
    
    # Generate BIDS-compliant output filename with space entity
    bids_output_filename = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix=f'space-{target_name}_desc-preproc',
        modality='bold'
    )
    create_output_link(result.output_file, bids_output_filename)
    
    # Generate BIDS-compliant output filename for tmean (boldref)
    if "tmean" in result.additional_files:
        bids_boldref_filename = create_bids_output_filename(
            original_file_path=bids_naming_template,
            suffix=f'space-{target_name}_desc-preproc',
            modality='boldref'
        )
        create_output_link(result.additional_files["tmean"], bids_boldref_filename)
    
    # Output final reference file for QC: target at appropriate resolution
    bids_prefix = get_filename_stem(bids_naming_template).replace('_bold', '')
    target_final_output = f"{bids_prefix}_target_final.nii.gz"
    target_final_path = Path(target_final_output)
    
    # Determine final reference based on keep_func_resolution and target_type
    keep_func_resolution = config.get("registration.keep_func_resolution", True)
    
    if target_type == 'anat':
        # func2anat: final space is anatomical
        if keep_func_resolution:
            # Use resampled anat from registration (reference_file_input)
            if reference_file_input.exists():
                if reference_file_input.resolve() != target_final_path.resolve():
                    shutil.copy2(reference_file_input, target_final_output)
                    print(f"INFO: Created target_final.nii.gz from resampled anat (func resolution)", file=sys.stderr)
                else:
                    # Same file - read and write to create a new file
                    data = reference_file_input.read_bytes()
                    target_final_path.write_bytes(data)
                    print(f"INFO: Created target_final.nii.gz from resampled anat (func resolution)", file=sys.stderr)
            else:
                raise FileNotFoundError(f"Resampled anat reference not found: {reference_file_input}")
        else:
            # Use original anat (reff should be original anat, but we use reference_file_input as fallback)
            # Note: In practice, if keep_func_resolution=False, reference_file_input might still be resampled
            # This is a limitation - we'd need the original anat file passed in
            if reff.exists() and reff != Path(resolve_template(effective_output_space)):
                if reff.resolve() != target_final_path.resolve():
                    shutil.copy2(reff, target_final_output)
                    print(f"INFO: Created target_final.nii.gz from original anat (native resolution)", file=sys.stderr)
                else:
                    data = reff.read_bytes()
                    target_final_path.write_bytes(data)
                    print(f"INFO: Created target_final.nii.gz from original anat (native resolution)", file=sys.stderr)
            else:
                # Fallback: use reference_file_input (might be resampled, but better than nothing)
                if reference_file_input.exists():
                    shutil.copy2(reference_file_input, target_final_output)
                    print(f"INFO: Created target_final.nii.gz from reference (fallback, may be resampled)", file=sys.stderr)
                else:
                    raise FileNotFoundError(f"Anatomical reference file not found for target_final.nii.gz")
    else:
        # func2template: final space is template
        template_fixedf = Path(resolve_template(effective_output_space))
        if keep_func_resolution:
            # Resample template to func resolution
            template_reff = working_dir / "template_res-func_for_apply_transforms.nii.gz"
            func_res = np.round(get_image_resolution(str(func_4d_input), logger=logger), 1)
            cmd_resample = ['3dresample', 
                            '-input', str(template_fixedf), '-prefix', str(template_reff), 
                            '-rmode', 'Cu',
                            '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])]
            run_command(cmd_resample, step_logger=logger)
            print(f"INFO: Template resampled to func resolution for target_final.nii.gz", file=sys.stderr)
            
            if template_reff.exists():
                if template_reff.resolve() != target_final_path.resolve():
                    shutil.copy2(template_reff, target_final_output)
                    print(f"INFO: Created target_final.nii.gz from resampled template (func resolution)", file=sys.stderr)
                else:
                    data = template_reff.read_bytes()
                    target_final_path.write_bytes(data)
                    print(f"INFO: Created target_final.nii.gz from resampled template (func resolution)", file=sys.stderr)
            else:
                raise FileNotFoundError(f"Failed to resample template for target_final.nii.gz")
        else:
            # Use original template
            if template_fixedf.exists():
                if template_fixedf.resolve() != target_final_path.resolve():
                    shutil.copy2(template_fixedf, target_final_output)
                    print(f"INFO: Created target_final.nii.gz from original template (native resolution)", file=sys.stderr)
                else:
                    data = template_fixedf.read_bytes()
                    target_final_path.write_bytes(data)
                    print(f"INFO: Created target_final.nii.gz from original template (native resolution)", file=sys.stderr)
            else:
                raise FileNotFoundError(f"Template file not found: {template_fixedf}")
    
    # Ensure file exists
    if not target_final_path.exists():
        raise FileNotFoundError(f"Failed to create target_final.nii.gz: {target_final_path}")
    print(f"INFO: target_final.nii.gz created, size: {target_final_path.stat().st_size} bytes", file=sys.stderr)
    
    final_output_file = result.output_file
    final_boldref_file = result.additional_files.get("tmean", result.output_file)
    final_space_name = target_name

# Save metadata
save_metadata({
    "step": "apply_transforms",
    "modality": "func",
    "target_type": target_type,
    "target2template": target2template,
    "is_sequential": is_sequential,
    "space": final_space_name
})

EOF
    """
}

/*
 * Additional functional processes for within-session coregistration
 */

process FUNC_WITHIN_SES_COREG {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*desc-coreg_bold*.nii.gz',
        saveAs: { filename -> filename }
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(bold_file), path(tmean_file), val(bids_naming_template)
    path(reference_tmean)
    val(reference_run_identifier)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(run_identifier), path("*desc-coreg_bold.nii.gz"), path("*desc-coreg_boldref.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(run_identifier), path("from-${run_identifier}_to-${reference_run_identifier}_mode-image_xfm.h5"), emit: transforms
    path "*.json", emit: metadata
    
    script:
    """
    # Set thread environment variables from config
    THREADS=\$(\${PYTHON:-python3} <<'PYTHON'
import yaml
with open('${config_file}') as f:
    config = yaml.safe_load(f)
threads = config.get('registration', {}).get('threads', 8)
threads = min(threads, 32)  # Cap at 32 to prevent oversubscription
print(threads)
PYTHON
    )
    
    export OMP_NUM_THREADS=\$THREADS
    export MKL_NUM_THREADS=\$THREADS
    export NUMEXPR_NUM_THREADS=\$THREADS
    export OPENBLAS_NUM_THREADS=\$THREADS
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=\$THREADS
    
    echo "Set thread environment variables to \$THREADS"
    
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.functional import func_within_ses_coreg
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import shutil
import os

# Initialize command log file
# Extract task and run from run_identifier if needed
run_identifier = '${run_identifier}'
import re
task_match = re.search(r'task-([^_]+)', run_identifier)
run_match = re.search(r'run-([^_]+)', run_identifier)
task_name = task_match.group(1) if task_match else None
run = run_match.group(1) if run_match else None

init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='FUNC_WITHIN_SES_COREG',
    task_name=task_name,
    run=run
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Get reference tmean and run_identifier
reference_tmean = Path('${reference_tmean}')
reference_run_identifier = '${reference_run_identifier}'
current_run_identifier = '${run_identifier}'

# Get BOLD file
bold_file = Path('${bold_file}')

# Create step input (tmean is the input file for coregistration)
input_obj = StepInput(
    input_file=Path('${tmean_file}'),
    working_dir=Path('work'),
    config=config,
    output_name='tmean_coregistered.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'run_identifier': run_identifier
        }
)

# Run step
result = func_within_ses_coreg(
    input_obj,
    reference_tmean=reference_tmean,
    reference_run=reference_run_identifier,
    current_run=current_run_identifier,
    bold_file=bold_file
)

# Generate BIDS-compliant output filename for tmean (with desc-coreg)
bids_tmean_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-coreg',
    modality='boldref'
)

# Generate BIDS-compliant output filename for BOLD (with desc-coreg)
bids_bold_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-coreg',
    modality='bold'
)

# Create symlinks for coregistered BOLD and tmean (these match the output pattern)
create_output_link(result.output_file, bids_tmean_filename)
if "bold_coregistered" in result.additional_files:
    create_output_link(result.additional_files["bold_coregistered"], bids_bold_filename)
else:
    raise FileNotFoundError("Coregistered BOLD file not found in result")

# Generate BIDS prefix (filename stem without modality)
original_stem = get_filename_stem(bids_naming_template)
bids_prefix_wo_modality = original_stem.replace("_bold", "").replace("_boldref", "")

# Create transform files for Nextflow pattern matching (but don't publish them - they're intermediate files)
if "forward_transform" in result.additional_files:
    # Create the expected output file name for Nextflow pattern matching
    shutil.copy2(result.additional_files["forward_transform"], f"from-${run_identifier}_to-${reference_run_identifier}_mode-image_xfm.h5")

if "inverse_transform" in result.additional_files:
    # Create the expected output file name for Nextflow pattern matching (if needed)
    # Note: inverse transform is not currently used in output, but create it for completeness
    pass  # Inverse transform not needed for output pattern matching

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process FUNC_AVERAGE_TMEAN {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*desc-coreg_boldref.nii.gz',
        saveAs: { filename -> filename }
    
    input:
    val(tmean_files)  // List of tmean file paths (as strings) - direct input, avoids staging name collisions and file list overhead
    val(subject_id)
    val(session_id)
    val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*desc-coreg_boldref.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    
    \${PYTHON:-python3} <<'PYTHON_EOF'
from macacaMRIprep.steps.functional import func_average_tmean
from macacaMRIprep.utils.bids import create_bids_output_filename, parse_bids_entities, create_bids_filename
from macacaMRIprep.utils.nextflow import (
    load_config, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import shutil
import os
import json
import sys
import ast

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='FUNC_AVERAGE_TMEAN'
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template
bids_naming_template = Path('${bids_naming_template}')

# Parse tmean_files from Nextflow (passed as JSON string for reliable parsing)
tmean_files_json = '${tmean_files}'
tmean_files_list = []

# Parse JSON (most reliable method)
try:
    parsed = json.loads(tmean_files_json)
    if isinstance(parsed, list):
        tmean_files_list = parsed
    else:
        # Single file wrapped in JSON
        tmean_files_list = [parsed]
except json.JSONDecodeError:
    # Fallback: If JSON parsing fails, try ast.literal_eval (for backward compatibility)
    try:
        parsed = ast.literal_eval(tmean_files_json)
        if isinstance(parsed, list):
            tmean_files_list = parsed
        else:
            tmean_files_list = [parsed]
    except:
        # Last resort: treat as single file path
        cleaned = tmean_files_json.strip().strip('"').strip("'")
        if cleaned:
            tmean_files_list = [cleaned]

# Convert to Path objects and filter to only existing files
tmean_file_paths = []
for file_path_str in tmean_files_list:
    if not file_path_str:
        continue
    # Final cleanup - remove any remaining brackets or quotes
    file_path_str = file_path_str.strip().strip('[').strip(']').strip('"').strip("'")
    if not file_path_str:
        continue
    file_path = Path(file_path_str)
    # Resolve to absolute path if relative
    if not file_path.is_absolute():
        file_path = file_path.resolve()
    if file_path.exists():
        tmean_file_paths.append(file_path)
    else:
        print(f"Warning: Tmean file does not exist: {file_path}", file=sys.stderr)

if len(tmean_file_paths) == 0:
    raise ValueError(f"No valid tmean files found for averaging. Input was: {tmean_files_json}")

# Create working directory if it doesn't exist
work_dir = Path('work')
work_dir.mkdir(parents=True, exist_ok=True)

# Run averaging
result = func_average_tmean(
    tmean_files=tmean_file_paths,
    working_dir=work_dir,
    config=config
)

# Generate BIDS-compliant output filename
# Remove all run-specific entities (keep only sub, ses), add desc-coreg, ends with _boldref
# Format: sub-XX[_ses-XX]_desc-coreg_boldref.nii.gz
# Parse the original filename to get entities
parsed = parse_bids_entities(str(bids_naming_template))
# Keep only sub and ses entities (remove all run-specific identifiers like task, run, acq, etc.)
# Create a new dict with only sub and ses
filtered_entities = {}
if 'sub' in parsed:
    filtered_entities['sub'] = parsed['sub']
if 'ses' in parsed:
    filtered_entities['ses'] = parsed['ses']
# Add desc entity for coregistration
filtered_entities['desc'] = 'coreg'
# Rebuild filename with suffix 'boldref'
bids_output_filename = create_bids_filename(filtered_entities, 'boldref', extension='.nii.gz')

# Create symlink with BIDS-compliant name (this matches the output pattern)
create_output_link(result.output_file, bids_output_filename)

# Save metadata
save_metadata(result.metadata)
PYTHON_EOF
    """
}
