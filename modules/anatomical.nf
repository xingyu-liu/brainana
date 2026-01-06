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
    tuple val(subject_id), val(session_id), path("*.nii.gz"), file("bids_naming_template.txt"), emit: synthesized
    path "metadata.json", emit: metadata
    
    script:
    def anat_files_list = anat_files.collect { "'${it}'" }.join(', ')
    def first_file = anat_files[0]
    """
    \${PYTHON:-python3} <<'PYTHON_EOF' > /dev/null
from macacaMRIprep.steps.anatomical import anat_synthesis
from macacaMRIprep.utils.bids import parse_bids_entities, create_bids_filename
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import json
import shutil
import os

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_SYNTHESIS'
)

# Load config
config = load_config('${config_file}')

# Get anatomical files
anat_files = [Path(f) for f in [${anat_files_list}]]

# Get BIDS naming template for BIDS filename generation
bids_naming_template = Path('${first_file}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

# Run synthesis (anat_synthesis function works for all anatomical modalities via underlying synthesis_multiple_anatomical)
result = anat_synthesis(
    anat_files=anat_files,
    working_dir=Path('work'),
    config=config
)

# Check if synthesis actually occurred
synthesized = result.metadata.get("synthesized", False)

# Generate BIDS-compliant output filename
# Parse entities from BIDS naming template and remove 'run' entity for synthesized output
entities = parse_bids_entities(bids_naming_template.name)
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
save_metadata(result.metadata)

# Determine what to write to bids_naming_template.txt for downstream steps
# If synthesis occurred, use the synthesized filename (without run) as the BIDS naming template
# If synthesis didn't occur, use the original file path (preserves run for single files)
if synthesized:
    # For synthesized files, construct a path using the synthesized filename
    # This ensures downstream steps don't include run identifiers
    # Use the same directory structure as the original file
    synthesized_path = bids_naming_template.parent / bids_output_filename
    bids_naming_template_for_downstream = str(synthesized_path)
else:
    # For single files (no synthesis), use the original file path
    bids_naming_template_for_downstream = str(bids_naming_template)

# Write the appropriate path to file for Nextflow value output
with open('bids_naming_template.txt', 'w') as f:
    f.write(bids_naming_template_for_downstream)
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
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.anatomical import anat_reorient
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.templates import resolve_template
from macacaMRIprep.utils.bids import create_bids_output_filename
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_REORIENT'
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

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
    original_file_path=bids_naming_template,
    suffix='desc-reorient',
    modality=modality
)

# Use symlink to avoid duplication - Nextflow publishDir will handle final copy
create_output_link(result.output_file, bids_output_filename)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process ANAT_CONFORM {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,mat}',
        saveAs: { filename -> filename == 'template_resampled.nii.gz' ? null : filename }
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*desc-conform*.nii.gz"), val(bids_naming_template), emit: output
    path "*.mat", emit: transforms
    tuple val(subject_id), val(session_id), path("template_resampled.nii.gz"), emit: template_resampled
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.anatomical import anat_conform
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.templates import resolve_template
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import shutil
import os

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_CONFORM'
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

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
    original_file_path=bids_naming_template,
    suffix='desc-conform',
    modality=modality
)

# Use symlink to avoid duplication - Nextflow publishDir will handle final copy
create_output_link(result.output_file, bids_output_filename)

# Generate BIDS prefix (filename stem without modality)
original_stem = get_filename_stem(bids_naming_template)
bids_prefix = original_stem.replace(f"_{modality}", "")

# Copy transform files with BIDS-compliant names
if "forward_transform" in result.additional_files:
    # Forward transform: from-scanner_to-{modality}
    bids_transform_name = f"{bids_prefix}_from-scanner_to-{modality}_mode-image_xfm.mat"
    shutil.copy2(result.additional_files["forward_transform"], bids_transform_name)

if "inverse_transform" in result.additional_files:
    # Inverse transform: from-{modality}_to-scanner
    bids_transform_name = f"{bids_prefix}_from-{modality}_to-scanner_mode-image_xfm.mat"
    shutil.copy2(result.additional_files["inverse_transform"], bids_transform_name)

# Create symlink to template_resampled file for QC (file is in work/ subdirectory, needs to be at root for Nextflow output)
if "template_resampled" in result.additional_files:
    template_resampled_src = result.additional_files["template_resampled"]
    if template_resampled_src.exists():
        # Create symlink at root level so Nextflow output pattern can find it
        template_resampled_dest = Path('template_resampled.nii.gz')
        if os.path.exists(template_resampled_dest):
            os.remove(template_resampled_dest)
        os.symlink(template_resampled_src, template_resampled_dest)

# Save metadata
save_metadata(result.metadata)
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
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(bids_naming_template), emit: output
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
from macacaMRIprep.utils.bids import create_bids_output_filename
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import shutil
import os

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_BIAS_CORRECTION'
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

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
    original_file_path=bids_naming_template,
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
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*_desc-preproc_*_brain.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), path("*_desc-brain_mask.nii.gz"), emit: brain_mask
    tuple val(subject_id), val(session_id), path("*_desc-brain_atlas*.nii.gz"), optional: true, emit: brain_segmentation
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.anatomical import anat_skullstripping
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.bids import create_bids_output_filename
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import shutil
import os

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_SKULLSTRIPPING'
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

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
original_stem = get_filename_stem(bids_naming_template)
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")
bids_output_filename = f"{bids_prefix_wo_modality}_desc-preproc_{modality}_brain.nii.gz"

# Use symlink to avoid duplication - Nextflow publishDir will handle final copy
create_output_link(result.output_file, bids_output_filename)

# Copy and rename additional files with BIDS-compliant names
atlas_name = result.metadata.get('atlas_name')

if "brain_mask" in result.additional_files:
    bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_mask.nii.gz"
    shutil.copy2(result.additional_files["brain_mask"], bids_additional_name)

if "segmentation" in result.additional_files:
    if atlas_name:
        bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_atlas{atlas_name}.nii.gz"
    else:
        bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_segmentation.nii.gz"
    shutil.copy2(result.additional_files["segmentation"], bids_additional_name)

if "hemimask" in result.additional_files:
    bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_hemimask.nii.gz"
    shutil.copy2(result.additional_files["hemimask"], bids_additional_name)

if "input_cropped" in result.additional_files:
    # Keep original name for input_cropped (or define BIDS name if needed)
    shutil.copy2(result.additional_files["input_cropped"], result.additional_files["input_cropped"].name)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process ANAT_SURFACE_RECONSTRUCTION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/fastsurfer",
        mode: 'copy',
        pattern: 'fastsurfer/**',
        saveAs: { filename -> 
            // Strip 'fastsurfer/' prefix to move sub-XXX directly to output_dir/fastsurfer/sub-XXX
            filename.replace('fastsurfer/', '')
        }
    
    input:
    tuple val(subject_id), val(session_id), path(t1w_file), val(bids_naming_template), path(segmentation_file), path(brain_mask)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("fastsurfer/sub-${subject_id}"), emit: subject_dir
    tuple val(subject_id), val(session_id), path("metadata.json"), emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.anatomical import anat_surface_reconstruction
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.nextflow import (
    load_config, init_cmd_log_for_nextflow, save_metadata
)
from pathlib import Path
import os

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_SURFACE_RECONSTRUCTION'
)

# Load config
config = load_config('${config_file}')

# Create step input
input_obj = StepInput(
    input_file=Path('${t1w_file}'),
    working_dir=Path('work'),
    config=config,
    output_name='surface_reconstruction',
    metadata={
        'subject_id': '${subject_id}',
        'session_id': '${session_id}'
    }
)

# Get brain mask if provided (check if file exists and is not empty)
brain_mask_path = None
if '${brain_mask}' and Path('${brain_mask}').exists() and Path('${brain_mask}').stat().st_size > 0:
    brain_mask_path = Path('${brain_mask}')

# Run surface reconstruction
result = anat_surface_reconstruction(
    input_obj,
    t1w_file=Path('${t1w_file}'),
    segmentation_file=Path('${segmentation_file}'),
    brain_mask=brain_mask_path
)

# Copy directory to work directory root so Nextflow can find it
# The output is created in work/fastsurfer/sub-XXX, but Nextflow expects fastsurfer/sub-XXX
# We copy (not symlink) to ensure actual content is moved, not just a symlink
output_subject_dir = result.output_file
expected_path = Path('fastsurfer') / 'sub-${subject_id}'

# Ensure the output directory exists
if not output_subject_dir.exists():
    raise FileNotFoundError(f"Surface reconstruction output not found: {output_subject_dir}")

# Get absolute paths for reliable copying
output_abs = output_subject_dir.resolve()
expected_abs = expected_path.resolve()

# Create the expected path location
expected_abs.parent.mkdir(parents=True, exist_ok=True)

# Remove existing symlink/directory if it exists
if expected_abs.exists() or expected_abs.is_symlink():
    import shutil
    if expected_abs.is_symlink() or expected_abs.is_file():
        expected_abs.unlink()
    elif expected_abs.is_dir():
        shutil.rmtree(expected_abs)

# Always copy the directory (not symlink) to ensure actual content is moved
import shutil
shutil.copytree(output_abs, expected_abs, dirs_exist_ok=True)

# Verify the expected path exists (check relative path for Nextflow)
if not expected_path.exists():
    raise FileNotFoundError(f"Failed to create expected output path: {expected_path} (absolute: {expected_abs})")

# Save metadata
save_metadata(result.metadata)
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
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
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
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import shutil
import os

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_REGISTRATION'
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

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
    original_file_path=bids_naming_template,
    suffix=f'space-{template_name}_desc-preproc',
    modality=modality
)

# Use symlink to avoid duplication - Nextflow publishDir will handle final copy
create_output_link(result.output_file, bids_output_filename)

# Get filename stem for BIDS-compliant transform naming
original_stem = get_filename_stem(bids_naming_template)

# Generate BIDS prefix (filename stem without modality)
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")

# Copy transform files with BIDS-compliant names
if "forward_transform" in result.additional_files:
    # Forward transform: from-{modality}_to-{template_name}
    bids_transform_name = f"{bids_prefix_wo_modality}_from-{modality}_to-{template_name}_mode-image_xfm.h5"
    shutil.copy2(result.additional_files["forward_transform"], bids_transform_name)

if "inverse_transform" in result.additional_files:
    # Inverse transform: from-{template_name}_to-{modality}
    bids_transform_name = f"{bids_prefix_wo_modality}_from-{template_name}_to-{modality}_mode-image_xfm.h5"
    shutil.copy2(result.additional_files["inverse_transform"], bids_transform_name)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process ANAT_T2W_TO_T1W_REGISTRATION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,h5}'
    
    input:
    tuple val(subject_id), val(session_id), path(t2w_file), val(bids_naming_template)
    path(t1w_reference)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(bids_naming_template), emit: output
    tuple val(subject_id), val(session_id), path("*.h5"), emit: transforms
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
from macacaMRIprep.steps.anatomical import anat_t2w_to_t1w_registration
from macacaMRIprep.steps.types import StepInput
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import (
    load_config, detect_modality, init_cmd_log_for_nextflow, save_metadata, create_output_link
)
from pathlib import Path
import shutil
import os

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_T2W_TO_T1W_REGISTRATION'
)

# Load config
config = load_config('${config_file}')

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

# Get filename stem for BIDS-compliant transform naming
original_stem = get_filename_stem(bids_naming_template)

# Get T1w reference file
t1w_reference = Path('${t1w_reference}')

# Create step input
input_obj = StepInput(
    input_file=Path('${t2w_file}'),
    working_dir=Path('work'),
    config=config,
    output_name='t2w_to_t1w_registered.nii.gz',
    metadata={
        'subject_id': '${subject_id}',
        'session_id': '${session_id}'
    }
)

# Run step
result = anat_t2w_to_t1w_registration(input_obj, t1w_reference=t1w_reference)

# Generate BIDS-compliant output filename with space-T1w entity
# Format: space-T1w_desc-reorient_T2w.nii.gz (after reorient, before bias correction)
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='space-T1w_desc-reorient',
    modality=modality
)

# Use symlink to avoid duplication - Nextflow publishDir will handle final copy
create_output_link(result.output_file, bids_output_filename)

# Generate BIDS prefix (filename stem without modality)
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")

# Copy transform files with BIDS-compliant names
if "forward_transform" in result.additional_files:
    # Forward transform: from-T2w_to-T1w
    bids_transform_name = f"{bids_prefix_wo_modality}_from-T2w_to-T1w_mode-image_xfm.h5"
    shutil.copy2(result.additional_files["forward_transform"], bids_transform_name)

if "inverse_transform" in result.additional_files:
    # Inverse transform: from-T1w_to-T2w
    bids_transform_name = f"{bids_prefix_wo_modality}_from-T1w_to-T2w_mode-image_xfm.h5"
    shutil.copy2(result.additional_files["inverse_transform"], bids_transform_name)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

// ============================================
// PASS-THROUGH HELPER PROCESSES (for skipped steps)
// ============================================

process ANAT_CONFORM_PASSTHROUGH {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,mat}'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*desc-conform*.nii.gz"), val(bids_naming_template), emit: output
    path "*.mat", emit: transforms
    tuple val(subject_id), val(session_id), path("template_resampled.nii.gz"), emit: template_resampled
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import detect_modality, save_metadata
from pathlib import Path
import shutil
import os
import numpy as np

# Get BIDS naming template
bids_naming_template = Path('${bids_naming_template}')

# Determine modality
modality = detect_modality(bids_naming_template)
original_stem = get_filename_stem(bids_naming_template)

# Pass through input file (create symlink)
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-conform',
    modality=modality
)
os.symlink(Path('${input_file}').resolve(), bids_output_filename)

# Generate BIDS prefix
bids_prefix = original_stem.replace(f"_{modality}", "")

# Create identity transform matrices (FLIRT format: 4x4 matrix)
# Identity matrix: 1.0 on diagonal, 0.0 elsewhere
identity_matrix = np.eye(4)

# Forward transform: from-scanner_to-{modality}
forward_transform_name = f"{bids_prefix}_from-scanner_to-{modality}_mode-image_xfm.mat"
np.savetxt(forward_transform_name, identity_matrix, fmt='%.6f', delimiter=' ')

# Inverse transform: from-{modality}_to-scanner
inverse_transform_name = f"{bids_prefix}_from-{modality}_to-scanner_mode-image_xfm.mat"
np.savetxt(inverse_transform_name, identity_matrix, fmt='%.6f', delimiter=' ')

# Create dummy template_resampled (copy of input for QC compatibility)
template_resampled_name = 'template_resampled.nii.gz'
shutil.copy2(Path('${input_file}'), template_resampled_name)

# Save metadata
metadata = {
    "step": "conform",
    "skipped": True,
    "reason": "disabled in configuration",
    "modality": modality
}
with open('metadata.json', 'w') as f:
    json.dump(metadata, f, indent=2)
EOF
    """
}

process ANAT_BIAS_CORRECTION_PASSTHROUGH {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(bids_naming_template), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import detect_modality, save_metadata
from pathlib import Path
import os

# Get BIDS naming template
bids_naming_template = Path('${bids_naming_template}')

# Determine modality
modality = detect_modality(bids_naming_template)
original_stem = get_filename_stem(bids_naming_template)

# Pass through input file (create symlink)
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-preproc',
    modality=modality
)
os.symlink(Path('${input_file}').resolve(), bids_output_filename)

# Save metadata
metadata = {
    "step": "bias_correction",
    "skipped": True,
    "reason": "disabled in configuration",
    "modality": modality
}
save_metadata(metadata)
EOF
    """
}

process ANAT_REGISTRATION_PASSTHROUGH {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,h5}'
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), path("*.nii.gz"), emit: output
    tuple val(subject_id), val(session_id), path("*.h5"), emit: transforms
    path "*.json", emit: metadata
    
    script:
    def template_name = params.output_space.split(':')[0]
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.templates import resolve_template
from macacaMRIprep.utils.nextflow import detect_modality, save_metadata
from pathlib import Path
import os
import subprocess
import shutil

# Get BIDS naming template
bids_naming_template = Path('${bids_naming_template}')

# Determine modality
modality = detect_modality(bids_naming_template)
original_stem = get_filename_stem(bids_naming_template)

template_name = '${template_name}'

# Pass through input file (create symlink with space entity)
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix=f'space-{template_name}_desc-preproc',
    modality=modality
)
os.symlink(Path('${input_file}').resolve(), bids_output_filename)

# Generate BIDS prefix
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")

# Create identity transform using ANTs
# Create identity affine transform file first
template_file = Path(resolve_template('${params.output_space}'))
input_file = Path('${input_file}')

# Forward transform: from-{modality}_to-{template_name}
forward_transform_name = f"{bids_prefix_wo_modality}_from-{modality}_to-{template_name}_mode-image_xfm.h5"

# Create identity affine transform (.txt format)
identity_affine = Path('identity_affine.txt')
with open(identity_affine, 'w') as f:
    f.write('#Insight Transform File V1.0\n')
    f.write('#Transform 0\n')
    f.write('Transform: AffineTransform_double_3_3\n')
    f.write('Parameters: 1 0 0 0 1 0 0 0 1 0 0 0\n')
    f.write('FixedParameters: 0 0 0\n')

# Convert to .h5 using ConvertTransformFile
try:
    cmd_convert = [
        'ConvertTransformFile', '3',
        str(identity_affine),
        forward_transform_name
    ]
    result = subprocess.run(cmd_convert, check=True, capture_output=True, text=True)
except (subprocess.CalledProcessError, FileNotFoundError):
    # If ConvertTransformFile fails, create minimal .h5 structure
    # This is a simplified approach - proper identity would need full ANTs transform structure
    with open(forward_transform_name, 'w') as f:
        f.write('#Insight Transform File V1.0\n')
        f.write('#Transform 0\n')
        f.write('Transform: AffineTransform_double_3_3\n')
        f.write('Parameters: 1 0 0 0 1 0 0 0 1 0 0 0\n')
        f.write('FixedParameters: 0 0 0\n')

# Inverse transform: from-{template_name}_to-{modality} (same as forward for identity)
inverse_transform_name = f"{bids_prefix_wo_modality}_from-{template_name}_to-{modality}_mode-image_xfm.h5"
shutil.copy2(forward_transform_name, inverse_transform_name)

# Save metadata
metadata = {
    "step": "registration",
    "skipped": True,
    "reason": "disabled in configuration",
    "modality": modality,
    "target": template_name
}
save_metadata(metadata)
EOF
    """
}

