/*
 * Anatomical processing modules for macacaMRIprep Nextflow pipeline
 */

process ANAT_SYNTHESIS {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), path(anat_files)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), file("original_file_path.txt"), emit: synthesized
    path "metadata.json", emit: metadata
    
    script:
    def anat_files_list = anat_files.collect { "'${it}'" }.join(', ')
    def first_file = anat_files[0]
    """
    \${PYTHON:-python3} <<'PYTHON_EOF' > /dev/null
from macacaMRIprep.steps.anatomical import anat_synthesis
from macacaMRIprep.utils.bids import parse_bids_entities, create_bids_filename, get_filename_stem
from macacaMRIprep.utils import init_cmd_log_file, create_output_link
from pathlib import Path
import json
import yaml
import shutil
import os

# Initialize command log file (saves to output_dir/reports/commands.log)
# Set job/step context for command logging
job_id = f"sub-${subject_id}"
if '${session_id}':
    job_id += f"_ses-${session_id}"
init_cmd_log_file(
    output_dir='${params.output_dir}',
    job_id=job_id,
    step_name='ANAT_SYNTHESIS',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None
)

# Load config
with open('${config_file}') as f:
    config = yaml.safe_load(f)

# Get anatomical files
anat_files = [Path(f) for f in [${anat_files_list}]]

# Get original file path for BIDS filename generation
original_file_path = Path('${first_file}')

# Determine modality from original filename
original_stem = get_filename_stem(original_file_path)
modality = 'T1w'  # default
if '_T2w' in original_stem or original_stem.endswith('_T2w'):
    modality = 'T2w'
elif '_T1w' in original_stem or original_stem.endswith('_T1w'):
    modality = 'T1w'

# Run synthesis (anat_synthesis function works for all anatomical modalities via underlying synthesis_multiple_anatomical)
result = anat_synthesis(
    anat_files=anat_files,
    working_dir=Path('work'),
    config=config
)

# Check if synthesis actually occurred
synthesized = result.metadata.get("synthesized", False)

# Generate BIDS-compliant output filename
# Parse entities from original file and remove 'run' entity for synthesized output
entities = parse_bids_entities(original_file_path.name)
# Remove 'run' entity since synthesis combines multiple runs
if 'run' in entities:
    del entities['run']

# Create BIDS filename: preserve entities (without run), add detected modality
bids_output_filename = create_bids_filename(
    entities=entities,
    suffix=modality,
    extension='.nii.gz'
)

# Use symlinks to avoid duplication - Nextflow publishDir will handle final copy
if synthesized:
    # Actual synthesis occurred - create symlink to synthesized file
    create_output_link(result.output_file, bids_output_filename)
else:
    # No synthesis (single file) - create hard link to avoid duplicating data
    try:
        os.link(result.output_file, bids_output_filename)
    except (OSError, AttributeError):
        # Hard link not possible (different filesystem or Windows), use copy
        shutil.copy2(result.output_file, bids_output_filename)

# Save metadata
with open('metadata.json', 'w') as f:
    json.dump(result.metadata, f, indent=2)

# Determine what to write to original_file_path.txt for downstream steps
# If synthesis occurred, use the synthesized filename (without run) as the "original" path
# If synthesis didn't occur, use the original file path (preserves run for single files)
if synthesized:
    # For synthesized files, construct a path using the synthesized filename
    # This ensures downstream steps don't include run identifiers
    # Use the same directory structure as the original file
    synthesized_path = original_file_path.parent / bids_output_filename
    original_file_path_for_downstream = str(synthesized_path)
else:
    # For single files (no synthesis), use the original file path
    original_file_path_for_downstream = str(original_file_path)

# Write the appropriate path to file for Nextflow value output
with open('original_file_path.txt', 'w') as f:
    f.write(original_file_path_for_downstream)
PYTHON_EOF
    """
}

process ANAT_REORIENT {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.anatomical import anat_reorient
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.templates import resolve_template
    from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
    from macacaMRIprep.utils import init_cmd_log_file, create_output_link
    from pathlib import Path
    import json
    import yaml
    import shutil
    
    # Initialize command log file (saves to output_dir/reports/commands.log)
    # Set job/step context for command logging
    job_id = f"sub-${subject_id}"
    if '${session_id}':
        job_id += f"_ses-${session_id}"
    init_cmd_log_file(
        output_dir='${params.output_dir}',
        job_id=job_id,
        step_name='ANAT_REORIENT',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None
    )
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Determine modality from original filename
    original_stem = get_filename_stem(original_file_path)
    modality = 'T1w'  # default
    if '_T2w' in original_stem or original_stem.endswith('_T2w'):
        modality = 'T2w'
    elif '_T1w' in original_stem or original_stem.endswith('_T1w'):
        modality = 'T1w'
    
    # Resolve template if needed
    template_file = None
    if '${params.output_space}':
        template_file = Path(resolve_template('${params.output_space}'))
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='anat_reoriented.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}'
        }
    )
    
    # Run step
    result = anat_reorient(input_obj, template_file=template_file)
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=original_file_path,
        suffix='desc-reorient',
        modality=modality
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    EOF
    """
}

process ANAT_CONFORM {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,mat}'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.mat", emit: transforms
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.anatomical import anat_conform
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.templates import resolve_template
    from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
    from macacaMRIprep.utils import init_cmd_log_file, create_output_link
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Initialize command log file (saves to output_dir/reports/commands.log)
    # Set job/step context for command logging
    job_id = f"sub-${subject_id}"
    if '${session_id}':
        job_id += f"_ses-${session_id}"
    init_cmd_log_file(
        output_dir='${params.output_dir}',
        job_id=job_id,
        step_name='ANAT_CONFORM',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None
    )
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Determine modality from original filename
    original_stem = get_filename_stem(original_file_path)
    modality = 'T1w'  # default
    if '_T2w' in original_stem or original_stem.endswith('_T2w'):
        modality = 'T2w'
    elif '_T1w' in original_stem or original_stem.endswith('_T1w'):
        modality = 'T1w'
    
    # Resolve template
    template_file = Path(resolve_template('${params.output_space}'))
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='anat_conformed.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}'
        }
    )
    
    # Run step
    result = anat_conform(input_obj, template_file=template_file)
    
    # Generate BIDS-compliant output filename
    bids_output_filename = create_bids_output_filename(
        original_file_path=original_file_path,
        suffix='desc-conform',
        modality=modality
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    
    # Generate BIDS prefix (filename stem without modality)
    original_stem = get_filename_stem(original_file_path)
    bids_prefix = original_stem.replace(f"_{modality}", "")
    
    # Copy transform files with BIDS-compliant names
    for f in result.additional_files:
        if f.suffix == '.mat':
            # Determine if this is forward or inverse transform based on filename
            # Forward: conform_scanner2native.mat -> from-scanner_to-{modality}
            # Inverse: conform_scanner2native_inverse.mat -> from-{modality}_to-scanner
            if 'inverse' in f.name.lower():
                # Inverse transform: from-{modality}_to-scanner
                bids_transform_name = f"{bids_prefix}_from-{modality}_to-scanner_mode-image_xfm.mat"
            else:
                # Forward transform: from-scanner_to-{modality}
                bids_transform_name = f"{bids_prefix}_from-scanner_to-{modality}_mode-image_xfm.mat"
            
            # Copy with BIDS-compliant name
            shutil.copy2(f, bids_transform_name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    EOF
    """
}

process ANAT_BIAS_CORRECTION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    # Set thread environment variables from config
    THREADS=\$(\${PYTHON:-python3} <<'PYTHON'
import yaml
with open('${config_file}') as f:
    config = yaml.safe_load(f)
threads = config.get('anat', {}).get('bias_correction', {}).get('threads', 8)
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
    
    \${PYTHON:-python3} <<'PYTHON_EOF'
from macacaMRIprep.steps.anatomical import anat_bias_correction
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils import init_cmd_log_file, create_output_link
from pathlib import Path
import json
import yaml
import shutil
import os
from macacaMRIprep.utils import create_output_link

# Initialize command log file (saves to output_dir/reports/commands.log)
# Set job/step context for command logging
job_id = f"sub-${subject_id}"
if '${session_id}':
    job_id += f"_ses-${session_id}"
init_cmd_log_file(
    output_dir='${params.output_dir}',
    job_id=job_id,
    step_name='ANAT_BIAS_CORRECTION',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None
)

# Load config
with open('${config_file}') as f:
    config = yaml.safe_load(f)

# Get original file path (for BIDS filename generation)
original_file_path = Path('${original_file_path}')

# Determine modality from original filename
original_stem = get_filename_stem(original_file_path)
modality = 'T1w'  # default
if '_T2w' in original_stem or original_stem.endswith('_T2w'):
    modality = 'T2w'
elif '_T1w' in original_stem or original_stem.endswith('_T1w'):
    modality = 'T1w'

# Create step input
input_obj = StepInput(
    input_file=Path('${input_file}'),
    working_dir=Path('work'),
    config=config,
    output_name='anat_bias_corrected.nii.gz',
    metadata={
        'subject_id': '${subject_id}',
        'session_id': '${session_id}'
    }
)

# Run step
result = anat_bias_correction(input_obj)

# Generate BIDS-compliant output filename (main preprocessed file)
bids_output_filename = create_bids_output_filename(
    original_file_path=original_file_path,
    suffix='desc-preproc',
    modality=modality
)

# Use symlink to avoid duplication - Nextflow publishDir will handle final copy
create_output_link(result.output_file, bids_output_filename)

# Save metadata
with open('metadata.json', 'w') as f:
    json.dump(result.metadata, f, indent=2)
PYTHON_EOF
    """
}

process ANAT_SKULLSTRIPPING {
    label 'gpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(original_file_path), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.anatomical import anat_skullstripping
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
    from macacaMRIprep.utils import init_cmd_log_file, create_output_link
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Initialize command log file (saves to output_dir/reports/commands.log)
    # Set job/step context for command logging
    job_id = f"sub-${subject_id}"
    if '${session_id}':
        job_id += f"_ses-${session_id}"
    init_cmd_log_file(
        output_dir='${params.output_dir}',
        job_id=job_id,
        step_name='ANAT_SKULLSTRIPPING',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None
    )
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Determine modality from original filename
    original_stem = get_filename_stem(original_file_path)
    modality = 'T1w'  # default
    if '_T2w' in original_stem or original_stem.endswith('_T2w'):
        modality = 'T2w'
    elif '_T1w' in original_stem or original_stem.endswith('_T1w'):
        modality = 'T1w'
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='anat_brain.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}'
        }
    )
    
    # Run step
    result = anat_skullstripping(input_obj)
    
    # Generate BIDS-compliant output filename for brain-only version
    # Format: {prefix}_desc-preproc_{modality}_brain.nii.gz
    # We need to handle _brain specially since it's not part of the modality
    from macacaMRIprep.utils.bids import get_filename_stem
    original_stem = get_filename_stem(original_file_path)
    bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")
    bids_output_filename = f"{bids_prefix_wo_modality}_desc-preproc_{modality}_brain.nii.gz"
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    
    # Copy additional files (masks, segmentations) - keep original names for now
    # These could be enhanced with BIDS naming later
    for f in result.additional_files:
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    EOF
    """
}

process ANAT_REGISTRATION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,h5}'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(original_file_path)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), emit: output
    tuple val(subject_id), val(session_id), path("*.h5"), emit: transforms
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
    
    \${PYTHON:-python3} <<EOF
    from macacaMRIprep.steps.anatomical import anat_registration
    from macacaMRIprep.steps.types import StepInput
    from macacaMRIprep.utils.templates import resolve_template
    from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
    from macacaMRIprep.utils import init_cmd_log_file, create_output_link
    from pathlib import Path
    import json
    import yaml
    import shutil
    import os
    from macacaMRIprep.utils import create_output_link
    
    # Initialize command log file (saves to output_dir/reports/commands.log)
    # Set job/step context for command logging
    job_id = f"sub-${subject_id}"
    if '${session_id}':
        job_id += f"_ses-${session_id}"
    init_cmd_log_file(
        output_dir='${params.output_dir}',
        job_id=job_id,
        step_name='ANAT_REGISTRATION',
        subject_id='${subject_id}',
        session_id='${session_id}' if '${session_id}' else None
    )
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Get original file path (for BIDS filename generation)
    original_file_path = Path('${original_file_path}')
    
    # Determine modality from original filename
    original_stem = get_filename_stem(original_file_path)
    modality = 'T1w'  # default
    if '_T2w' in original_stem or original_stem.endswith('_T2w'):
        modality = 'T2w'
    elif '_T1w' in original_stem or original_stem.endswith('_T1w'):
        modality = 'T1w'
    
    # Resolve template
    template_file = Path(resolve_template('${params.output_space}'))
    template_name = '${template_name}'
    
    # Create step input
    input_obj = StepInput(
        input_file=Path('${input_file}'),
        working_dir=Path('work'),
        config=config,
        output_name='anat_registered.nii.gz',
        metadata={
            'subject_id': '${subject_id}',
            'session_id': '${session_id}'
        }
    )
    
    # Run step
    result = anat_registration(input_obj, template_file=template_file, template_name=template_name)
    
    # Generate BIDS-compliant output filename with space entity
    # Format: space-{template}_desc-preproc_{modality}.nii.gz
    bids_output_filename = create_bids_output_filename(
        original_file_path=original_file_path,
        suffix=f'space-{template_name}_desc-preproc',
        modality=modality
    )
    
    # Use symlink to avoid duplication - Nextflow publishDir will handle final copy
    create_output_link(result.output_file, bids_output_filename)
    
    # Copy transform files - keep original names for now
    # These could be enhanced with BIDS naming later
    for f in result.additional_files:
        shutil.copy2(f, f.name)
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    EOF
    """
}

