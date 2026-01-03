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
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_reorient
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.templates import resolve_template
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
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
        original_file_path=original_file_path,
        suffix='desc-reorient',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
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
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_slice_timing_correction
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
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
        original_file_path=original_file_path,
        suffix='desc-sliceTiming',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
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
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.tsv"), emit: motion_params
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_motion_correction
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
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
        original_file_path=original_file_path,
        suffix='desc-motion',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
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
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_despike
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
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
    
    # Run step
    result = func_despike(input_obj)
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=original_file_path,
        suffix='desc-despike',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
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
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path)  // This should be tmean
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
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
    
    python3 <<EOF
    from macacaMRIprep.steps.functional import func_bias_correction
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
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
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=original_file_path,
        suffix='desc-biasCorrection',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    EOF
    """
}

process FUNC_CONFORM {
    label 'cpu'
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.{nii.gz,mat}'
    
    input:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path)  // This should be tmean
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.mat", emit: transforms
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_conform
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.templates import resolve_template
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Determine target file (anatomical or template based on pipeline)
    registration_pipeline = config.get('func', {}).get('registration_pipeline', 'func2anat2template')
    if registration_pipeline == 'func2template':
        target_file = Path(resolve_template('${params.output_space}'))
    else:
        # For func2anat2template, target will be provided in registration step
        target_file = Path(resolve_template('${params.output_space}'))
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
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
    
    # Run step
    result = func_conform(input_obj, target_file=target_file)
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=original_file_path,
        suffix='desc-conform',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    EOF
    """
}

process FUNC_SKULLSTRIPPING {
    label 'gpu'
    tag "${subject_id}_${session_id}_${task_name}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/func",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path)  // This should be tmean
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*_desc-brain_mask.nii.gz"), emit: brain_mask
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_skullstripping
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import get_filename_stem
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
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
    
    # Run step
    result = func_skullstripping(input_obj)
    
    # Generate BIDS-compliant output filename for brain-only version
    # Format: {prefix}_desc-preproc_bold_brain.nii.gz
    original_stem = get_filename_stem(original_file_path)
    bids_prefix_wobold = original_stem.replace("_bold", "")
    bids_output_filename = f"{bids_prefix_wobold}_desc-preproc_bold_brain.nii.gz"
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    
    # Copy and rename additional files with BIDS-compliant names
    if "brain_mask" in result.additional_files:
        bids_additional_name = f"{bids_prefix_wobold}_desc-brain_mask.nii.gz"
        shutil.copy2(result.additional_files["brain_mask"], bids_additional_name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
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
    // Combined channel: [sub, ses, task, run, func_file, orig_path, anat_reg, anat_trans, anat_ses, is_fallback]
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(input_file), val(original_file_path), path(anat_registered), path(anat_transforms), val(anat_session_id), val(is_fallback)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), val(original_file_path), emit: output
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.h5"), emit: transforms
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
    import json
    import yaml
    import shutil
    import os
    import sys
    from macacaMRIprep.utils import create_output_link
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Check if anatomical data is available
    is_fallback = '${is_fallback}' == 'true'
    anat_session_id = '${anat_session_id}'
    func_session_id = '${session_id}'
    
    # Determine target based on registration pipeline
    registration_pipeline = config.get('func', {}).get('registration_pipeline', 'func2anat2template')
    template_name = '${template_name}'
    
    # Check if anatomical file exists (handle missing anatomical data)
    anat_registered_path_str = '${anat_registered}'
    # Check if path is a dummy/placeholder (contains .dummy or is empty)
    is_dummy_anat = '.dummy' in anat_registered_path_str or not anat_registered_path_str or anat_registered_path_str.strip() == ''
    if is_dummy_anat:
        has_anat = False
        anat_registered_path = None
    else:
        anat_registered_path = Path(anat_registered_path_str)
        has_anat = anat_registered_path.exists()
    
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
            # Use anatomical file as target
            target_file = anat_registered_path
            target_type = 'anat'
            # Extract anatomical target name from filename
            anat_filename = anat_registered_path.name
            if 'space-' in anat_filename:
                target_name = anat_filename.split('space-')[1].split('_')[0]
            else:
                target_name = 'anat'
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
            # First register to anatomical
            target_file = anat_registered_path
            target_type = 'anat'
            # Extract anatomical target name from filename
            anat_filename = anat_registered_path.name
            if 'space-' in anat_filename:
                target_name = anat_filename.split('space-')[1].split('_')[0]
            else:
                target_name = 'anat'
            if is_fallback:
                print(f"WARNING: Using anatomical from session {anat_session_id} for functional session {func_session_id}", file=sys.stderr)
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
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
    # Format: space-{target_name}_desc-preproc_bold.nii.gz
    bids_output_filename = create_bids_output_filename(
        original_file_path=original_file_path,
        suffix=f'space-{target_name}_desc-preproc',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
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
    tuple val(subject_id), val(session_id), val(task_name), val(run), path(tmean_registered), path(transforms), val(original_file_path)
    path(func_4d_file)  // Original 4D BOLD file
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), path("*.nii.gz"), emit: output
    path "*.json", emit: metadata
    
    script:
    def template_name = params.output_space.split(':')[0]
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.functional import func_apply_transforms
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename
    from macacaMRIprep.utils import create_output_link
    from pathlib import Path
    import json
    import yaml
    import glob
    import shutil
    import os
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Get transform files
    transform_files = [Path(f) for f in glob.glob('${transforms}/*.h5')]
    
    # Use tmean as reference
    reference_file = Path('${tmean_registered}')
    
    # Determine target name from tmean filename
    tmean_filename = Path('${tmean_registered}').name
    if 'space-' in tmean_filename:
        target_name = tmean_filename.split('space-')[1].split('_')[0]
    else:
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
        original_file_path=original_file_path,
        suffix=f'space-{target_name}_desc-preproc',
        modality='bold'
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    # Copy additional files (e.g., tmean)
    for key, f in result.additional_files.items():
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    EOF
    """
}

