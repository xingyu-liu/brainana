/*
 * Functional processing modules for macacaMRIprep Nextflow pipeline
 */

process FUNC_REORIENT {
    label 'cpu'
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir { 
        def sesPath = session_id ? "/ses-${session_id}" : ""
        "${params.output_dir}/sub-${subject_id}${sesPath}/func"
    },
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-reorient_bold.nii.gz"), val(bids_naming_template), emit: output
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
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_REORIENT',
        task_name='${task_name}',
        run='${run}'
    )
    
    # Load config
    config = load_config('${config_file}')
    
    # Get BIDS naming template (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Resolve template if needed
    template_file = None
    if '${params.output_space}':
        template_file = Path(resolve_template('${params.output_space}'))
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='func_reoriented.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'task': '${task_name}',
            'run': '${run}'
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
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-sliceTiming_bold.nii.gz"), val(bids_naming_template), emit: output
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
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_SLICE_TIMING',
        task_name='${task_name}',
        run='${run}'
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
            'task': '${task_name}',
            'run': '${run}'
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
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,tsv}'
    
    input:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-motion_bold.nii.gz"), path("*desc-motion_boldref.nii.gz"), val(bids_naming_template), emit: combined
    // Keep separate outputs for backward compatibility
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-motion_bold.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-motion_boldref.nii.gz"), val(bids_naming_template), emit: tmean
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-confounds_timeseries.tsv"), emit: motion_params
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
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_MOTION_CORRECTION',
        task_name='${task_name}',
        run='${run}'
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
            'task': '${task_name}',
            'run': '${run}'
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

process FUNC_DESPIKE {
    label 'cpu'
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(bold_file), path(tmean_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-despike_bold.nii.gz"), path("*desc-despike_boldref.nii.gz"), val(bids_naming_template), emit: combined
    // Keep separate outputs for backward compatibility
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-despike_bold.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-despike_boldref.nii.gz"), val(bids_naming_template), emit: tmean
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
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_DESPIKE',
        task_name='${task_name}',
        run='${run}'
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
            'task': '${task_name}',
            'run': '${run}'
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
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(bold_file), path(tmean_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("bold_inherited.nii.gz"), path("*desc-biasCorrection_boldref.nii.gz"), val(bids_naming_template), emit: combined
    // Keep separate output for backward compatibility
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-biasCorrection_boldref.nii.gz"), val(bids_naming_template), emit: output
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
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='FUNC_BIAS_CORRECTION',
    task_name='${task_name}',
    run='${run}'
)

# Load config
from macacaMRIprep.utils.nextflow import load_config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Create symlink to inherited BOLD file for output
bold_input = Path('${bold_file}')
bold_inherited = Path('bold_inherited.nii.gz')

# Ensure source file exists
if not bold_input.exists():
    raise FileNotFoundError(f"BOLD input file does not exist: {bold_input}")

# Remove existing symlink/file if present
if bold_inherited.exists() or bold_inherited.is_symlink():
    bold_inherited.unlink()

# Create symlink using absolute path to ensure it works
bold_input_abs = bold_input.resolve()
bold_inherited_abs = bold_inherited.resolve()

try:
    os.symlink(str(bold_input_abs), str(bold_inherited_abs))
except OSError as e:
    # If symlink fails, try copying the file instead
    print(f"WARNING: Symlink creation failed ({e}), copying file instead", file=sys.stderr)
    shutil.copy2(str(bold_input_abs), str(bold_inherited_abs))

# Verify the output file exists
if not bold_inherited.exists():
    raise FileNotFoundError(f"Failed to create bold_inherited.nii.gz: symlink/copy failed")

# Create step input (process tmean, inherit BOLD via symlink)
input_obj = StepInput(
    input_file=Path('${tmean_file}'),  # Process tmean
    working_dir=Path('work'),
    config=config,
    output_name='func_bias_corrected.nii.gz',
    metadata={
        'subject_id': '${subject_id}',
        'session_id': '${session_id}',
        'task': '${task_name}',
        'run': '${run}'
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
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,mat}',
        saveAs: { filename -> filename == 'template_resampled.nii.gz' ? null : filename }
    
    input:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(bold_file), path(tmean_file), val(bids_naming_template)
    path(anat_brain_file)  // Optional anatomical brain file (skull-stripped) to use as target
    path config_file
    
    output:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-conform_bold.nii.gz"), path("*desc-conform_boldref.nii.gz"), val(bids_naming_template), emit: combined
    // Keep separate outputs for backward compatibility
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-conform_bold.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-conform_boldref.nii.gz"), val(bids_naming_template), emit: tmean
    path "*.mat", emit: transforms
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("template_resampled.nii.gz"), val(bids_naming_template), emit: template_resampled
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
    from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow
    
    # Initialize command log file
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_CONFORM',
        task_name='${task_name}',
        run='${run}'
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
    
    if registration_pipeline == 'func2template':
        # Always use template for func2template pipeline
        target_file = Path(resolve_template('${params.output_space}'))
    elif registration_pipeline in ['func2anat', 'func2anat2template']:
        # Use anatomical brain if available, otherwise fallback to template
        if has_anat_brain:
            anat_brain_path = Path(anat_brain_path_str)
            if anat_brain_path.exists():
                target_file = anat_brain_path
            else:
                # Anatomical file doesn't exist, use template
                target_file = Path(resolve_template('${params.output_space}'))
        else:
            # No anatomical brain provided, use template
            target_file = Path(resolve_template('${params.output_space}'))
    else:
        # Default: use template
        target_file = Path(resolve_template('${params.output_space}'))
    
    # Create step input for tmean (used for conform registration)
    tmean_input_obj = StepInput(
        input_file=Path('${tmean_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='func_tmean_conformed.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'task': '${task_name}',
            'run': '${run}'
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
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*desc-brain_mask.nii.gz'  // Only publish mask, not brain (brain is intermediate)
    
    input:
    // Combined channel: [sub, ses, task, run, bold_file, tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(bold_file), path(tmean_file), val(bids_naming_template)
    path config_file
    
    output:
    // Combined channel: [sub, ses, task, run, bold_file, brain_file, bids_template]
    // Note: brain_file replaces tmean_file (it's the skull-stripped tmean)
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("bold_inherited.nii.gz"), path("*_boldref_brain.nii.gz"), val(bids_naming_template), emit: combined
    // Keep separate outputs for backward compatibility
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*desc-brain_mask.nii.gz"), val(bids_naming_template), emit: brain_mask
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*_boldref_brain.nii.gz"), val(bids_naming_template), emit: brain
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
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_SKULLSTRIPPING',
        task_name='${task_name}',
        run='${run}'
    )
    
    # Load config
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    
    # Get original file path (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Create symlink to inherited BOLD file for output
    bold_input = Path('${bold_file}')
    bold_inherited = Path('bold_inherited.nii.gz')
    
    # Ensure source file exists
    if not bold_input.exists():
        raise FileNotFoundError(f"BOLD input file does not exist: {bold_input}")
    
    # Remove existing symlink/file if present
    if bold_inherited.exists() or bold_inherited.is_symlink():
        bold_inherited.unlink()
    
    # Create symlink using absolute path to ensure it works
    bold_input_abs = bold_input.resolve()
    bold_inherited_abs = bold_inherited.resolve()
    
    try:
        os.symlink(str(bold_input_abs), str(bold_inherited_abs))
    except OSError as e:
        # If symlink fails, try copying the file instead
        import shutil
        print(f"WARNING: Symlink creation failed ({e}), copying file instead", file=sys.stderr)
        shutil.copy2(str(bold_input_abs), str(bold_inherited_abs))
    
    # Verify the output file exists
    if not bold_inherited.exists():
        raise FileNotFoundError(f"Failed to create bold_inherited.nii.gz: symlink/copy failed")
    
    # Create step input (process tmean → brain, inherit BOLD via symlink)
    input_obj = StepInput(
        input_file=Path('${tmean_file}'),  # Process tmean → brain
        working_dir=Path('work'),
        config=config,
        output_name='func_brain.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'task': '${task_name}',
            'run': '${run}'
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
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,h5}'
    
    input:
    // 3-input pattern - EXACTLY like T2W_TO_T1W_REGISTRATION: (tuple, path, path)
    // Tuple: 9 elements [sub, ses, task, run, bold_file, tmean_file, bids_template, anat_session_id, is_fallback]
    // anat_brain: separate path input (like t1w_file in T2W)
    // config_file: config path
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(bold_file), path(tmean_file), val(bids_naming_template), val(anat_session_id), val(is_fallback)
    path(anat_brain)
    path config_file
    
    output:
    // Combined channel: [sub, ses, task, run, bold_file, registered_tmean_file, bids_template]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("bold_inherited.nii.gz"), path("*space-*boldref.nii.gz"), val(bids_naming_template), emit: combined
    // Keep separate outputs for backward compatibility
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*space-*boldref.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*from-bold_to-*_mode-image_xfm.h5"), emit: transforms
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*from-*_to-bold_mode-image_xfm.h5"), emit: inverse_transforms
    path "*.json", emit: metadata
    
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
    
    # Check if using anatomical from different session (fallback case)
    if [ "${is_fallback}" = "true" ]; then
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
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='FUNC_REGISTRATION',
    task_name='${task_name}',
    run='${run}'
)

# Load config
from macacaMRIprep.utils.nextflow import load_config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Check if anatomical data is available
is_fallback = '${is_fallback}' == 'true'
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

# Determine target based on registration pipeline
# FUNC_REGISTRATION registers functional tmean/brain to anatomical skull-stripped brain
if registration_pipeline == 'func2template' or not has_anat:
    # Direct to template registration (no anatomical needed)
    target_file = Path(resolve_template('${params.output_space}'))
    target_type = 'template'
    target_name = template_name
    if not has_anat:
        print(f"INFO: No anatomical data available, registering directly to template", file=sys.stderr)
elif registration_pipeline == 'func2anat':
    if not has_anat:
        # Fallback to template if no anatomical data
        target_file = Path(resolve_template('${params.output_space}'))
        target_type = 'template'
        target_name = template_name
        print(f"INFO: No anatomical data available for func2anat pipeline, using template instead", file=sys.stderr)
    else:
        # Use anatomical skull-stripped brain as target
        target_file = anat_brain_path
        target_type = 'anat'
        target_name = 'anat'  # Registering to anatomical brain (not in template space yet)
        if is_fallback:
            print(f"WARNING: Using anatomical from session {anat_session_id} for functional session {func_session_id}", file=sys.stderr)
else:  # func2anat2template
    if not has_anat:
        # Fallback to template if no anatomical data
        target_file = Path(resolve_template('${params.output_space}'))
        target_type = 'template'
        target_name = template_name
        print(f"INFO: No anatomical data available for func2anat2template pipeline, using template instead", file=sys.stderr)
    else:
        # First register to anatomical skull-stripped brain
        target_file = anat_brain_path
        target_type = 'anat'
        target_name = 'anat'  # Registering to anatomical brain (not in template space yet)
        if is_fallback:
            print(f"WARNING: Using anatomical from session {anat_session_id} for functional session {func_session_id}", file=sys.stderr)

# Create symlink to inherited BOLD file for output
bold_input = Path('${bold_file}')
bold_inherited = Path('bold_inherited.nii.gz')

# Ensure source file exists
if not bold_input.exists():
    raise FileNotFoundError(f"BOLD input file does not exist: {bold_input}")

# Remove existing symlink/file if present
if bold_inherited.exists() or bold_inherited.is_symlink():
    bold_inherited.unlink()

# Create symlink using absolute path to ensure it works
bold_input_abs = bold_input.resolve()
bold_inherited_abs = bold_inherited.resolve()

try:
    os.symlink(str(bold_input_abs), str(bold_inherited_abs))
except OSError as e:
    # If symlink fails, try copying the file instead
    print(f"WARNING: Symlink creation failed ({e}), copying file instead", file=sys.stderr)
    shutil.copy2(str(bold_input_abs), str(bold_inherited_abs))

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
        'task': '${task_name}',
        'run': '${run}'
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
        shutil.copy2(f, bids_transform_name)
    elif key == 'inverse_transform':
        # Inverse transform: from-{space_name}_to-bold
        bids_transform_name = f"{bids_prefix}_from-{space_name}_to-bold_mode-image_xfm.h5"
        shutil.copy2(f, bids_transform_name)
    else:
        shutil.copy2(f, f.name)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process FUNC_APPLY_TRANSFORMS {
    label 'cpu'
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    // Stage tmean_registered with a different name to avoid conflict with output filename
    // Only forward transform is needed (from-bold_to-template)
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(tmean_registered, stageAs: 'tmean_reference.nii.gz'), path("*from-bold_to-*_mode-image_xfm.h5"), val(bids_naming_template)
    path(func_4d_file)  // Original 4D BOLD file
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*space-*desc-preproc*.nii.gz"), emit: output
    path "*.json", emit: metadata
    
    script:
    def template_name = params.output_space.split(':')[0]
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_apply_transforms
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow
    from pathlib import Path
    import glob
    import shutil
    import os
    
    # Initialize command log file
    init_cmd_log_for_nextflow(
        output_dir='${params.output_dir}',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None,
        step_name='FUNC_APPLY_TRANSFORMS',
        task_name='${task_name}',
        run='${run}'
    )
    
    # Load config
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    
    # Get original file path (for BIDS filename generation)
    bids_naming_template = Path('${bids_naming_template}')
    
    # Get transform files (staged in work directory)
    # Only forward transform is needed (from-bold_to-template)
    transform_files = [Path(f) for f in glob.glob('*from-bold_to-*_mode-image_xfm.h5')]
    
    # Use tmean as reference (staged as 'tmean_reference.nii.gz' to avoid filename conflict with output)
    reference_file = Path('tmean_reference.nii.gz')
    
    # Use template name directly from params (already extracted as template_name in script preamble)
    target_name = '${template_name}'
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${func_4d_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='func_registered.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}',
            'task': '${task_name}',
            'run': '${run}'
        }
    )
    
    # Run step
    result = func_apply_transforms(
        input_obj,
        transform_files=transform_files,
        reference_file=reference_file
    )
    
    # Generate BIDS-compliant output filename with space entity
    # Format: space-{target_name}_desc-preproc_bold.nii.gz
    bids_output_filename = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix=f'space-{target_name}_desc-preproc',
        modality='bold'
    )
    
    # Ensure output file exists
    output_file_path = Path(result.output_file)
    if not output_file_path.exists():
        raise FileNotFoundError(f"Output file not found: {output_file_path}")
    
    # Create BIDS-compliant output file for Nextflow
    # Use symlink to avoid duplicating large files (Nextflow publishDir will copy actual content)
    create_output_link(result.output_file, bids_output_filename)
    
    # Save metadata
    save_metadata(result.metadata)
    EOF
    """
}

