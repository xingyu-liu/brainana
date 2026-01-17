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
# Always use create_output_link() which resolves symlinks to original source
create_output_link(result.output_file, bids_output_filename)

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

# Get effective_output_space from effective config file
config = load_config('${config_file}')
effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')

# Resolve template if needed
template_file = None
if effective_output_space:
    template_file = Path(resolve_template(effective_output_space))

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
    // Transforms: [sub, ses, forward_transform, inverse_transform]
    tuple val(subject_id), val(session_id), path("*from-scanner_to-*_mode-image_xfm*"), path("*from-*_to-scanner_mode-image_xfm*"), emit: transforms
    // Reference: [sub, ses, reference]
    tuple val(subject_id), val(session_id), path("template_resampled.nii.gz"), emit: reference
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

# Get effective_output_space from effective config file
config = load_config('${config_file}')
effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')

# Resolve template
template_file = Path(resolve_template(effective_output_space))

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

# Create symlink to reference file for QC (file is in work/ subdirectory, needs to be at root for Nextflow output)
# Use create_output_link() for consistency and proper symlink resolution
if "template_resampled" in result.additional_files:
    reference_src = result.additional_files["template_resampled"]
    if reference_src.exists():
        # Create symlink at root level so Nextflow output pattern can find it
        reference_dest = Path('template_resampled.nii.gz')
        create_output_link(reference_src, str(reference_dest))

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
    # Thread environment variables are set by Nextflow's beforeScript based on task.cpus
    # Python code reads OMP_NUM_THREADS from environment
    
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
import json

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
    tuple val(subject_id), val(session_id), path("*_desc-brain_hemimask.nii.gz"), optional: true, emit: brain_hemimask
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

# Create symlinks for additional files with BIDS-compliant names
# Keep large files (masks, segmentations) as symlinks until published - saves storage
atlas_name = result.metadata.get('atlas_name')

if "brain_mask" in result.additional_files:
    bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_mask.nii.gz"
    create_output_link(result.additional_files["brain_mask"], bids_additional_name)

if "segmentation" in result.additional_files:
    if atlas_name:
        bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_atlas{atlas_name}.nii.gz"
    else:
        bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_segmentation.nii.gz"
    create_output_link(result.additional_files["segmentation"], bids_additional_name)

if "hemimask" in result.additional_files:
    bids_additional_name = f"{bids_prefix_wo_modality}_desc-brain_hemimask.nii.gz"
    create_output_link(result.additional_files["hemimask"], bids_additional_name)

if "input_cropped" in result.additional_files:
    # Keep original name for input_cropped (or define BIDS name if needed)
    create_output_link(result.additional_files["input_cropped"], result.additional_files["input_cropped"].name)

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
        pattern: '*.{nii.gz,h5,mat}',
        saveAs: { filename -> filename.contains('ref_from_anat_reg.nii.gz') ? null : filename }
    
    input:
    tuple val(subject_id), val(session_id), path(input_file), val(bids_naming_template), path(unskullstripped_file)
    path config_file  // Effective config file with all resolved parameters
    
    output:
    // Output: [sub, ses, registered_file, bids_template]
    tuple val(subject_id), val(session_id), path("*space-*.nii.gz"), val(bids_naming_template), emit: output
    // Transforms: [sub, ses, forward_transform, inverse_transform]
    // Use patterns that match the actual naming: forward starts with from-T1w_to- or from-T2w_to-, inverse ends with _to-T1w or _to-T2w
    tuple val(subject_id), val(session_id), path("*from-T1w_to-*_mode-image_xfm*"), path("*from-*_to-T1w_mode-image_xfm*"), emit: transforms
    // Reference: [sub, ses, reference_file]
    tuple val(subject_id), val(session_id), path("*ref_from_anat_reg.nii.gz"), emit: reference
    path "*.json", emit: metadata
    
    script:
    """
    # Get effective_output_space from effective config file
    EFFECTIVE_OUTPUT_SPACE=\$(\${PYTHON:-python3} <<'PYTHON_OUTPUT_SPACE'
from macacaMRIprep.utils.nextflow import load_config
config = load_config('${config_file}')
effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')
print(effective_output_space)
PYTHON_OUTPUT_SPACE
    )
    TEMPLATE_NAME=\$(echo "\$EFFECTIVE_OUTPUT_SPACE" | cut -d':' -f1)
    
    # Thread environment variables are set by Nextflow's beforeScript based on task.cpus
    # Python code reads OMP_NUM_THREADS from environment
    
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

# Get effective_output_space from effective config file
effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')
template_name = effective_output_space.split(':')[0] if effective_output_space else 'NMT2Sym'

# Resolve template
template_file = Path(resolve_template(effective_output_space))

# Check if unskullstripped version is provided and different from input file
unskullstripped_path = Path('${unskullstripped_file}')
input_path = Path('${input_file}')
use_unskullstripped = (unskullstripped_path.exists() and 
                       unskullstripped_path.stat().st_size > 0 and
                       str(unskullstripped_path) != str(input_path))

# Create step input for registration (use skullstripped version for computing transform)
input_obj = StepInput(
    input_file=input_path,
    working_dir=Path('work'),
    config=config,
    output_name='anat_registered.nii.gz',
    metadata={
        'subject_id': '${subject_id}',
        'session_id': '${session_id}'
    }
)

# Run step to compute transform (on skullstripped version)
result = anat_registration(input_obj, template_file=template_file, template_name=template_name)

# If unskullstripped version is provided and different, apply transform to it instead
if use_unskullstripped:
    from macacaMRIprep.operations.registration import ants_apply_transforms
    
    # Get the forward transform file
    forward_transform = result.additional_files.get("forward_transform")
    if not forward_transform or not forward_transform.exists():
        raise FileNotFoundError(f"Forward transform file not found: {forward_transform}")
    
    # Apply the transform to the unskullstripped version
    # Use LanczosWindowedSinc for continuous-value anatomical images (high-quality interpolation)
    apply_result = ants_apply_transforms(
        movingf=str(unskullstripped_path),
        moving_type=0,  # 0: scalar (anatomical image)
        interpolation='LanczosWindowedSinc',
        outputf_name='anat_registered.nii.gz',
        fixedf=str(template_file),
        working_dir=str(Path('work')),
        transformf=[str(forward_transform)],
        reff=str(template_file),
        logger=None
    )
    
    # Update the output file to point to the unskullstripped registered version
    result.output_file = Path(apply_result["imagef_registered"])

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

# Create symlinks for transform files with BIDS-compliant names
# .h5 files can be large, so use symlinks until published - saves storage
if "forward_transform" in result.additional_files:
    # Forward transform: from-{modality}_to-{template_name}
    bids_transform_name = f"{bids_prefix_wo_modality}_from-{modality}_to-{template_name}_mode-image_xfm.h5"
    create_output_link(result.additional_files["forward_transform"], bids_transform_name)

if "inverse_transform" in result.additional_files:
    # Inverse transform: from-{template_name}_to-{modality}
    bids_transform_name = f"{bids_prefix_wo_modality}_from-{template_name}_to-{modality}_mode-image_xfm.h5"
    create_output_link(result.additional_files["inverse_transform"], bids_transform_name)

# Create ref_from_anat_reg.nii.gz for QC reference
# This is the template file used as the reference for registration
ref_from_anat_reg_path = Path(f"{bids_prefix_wo_modality}_ref_from_anat_reg.nii.gz")

# Create symlink to template file (the actual template used during registration)
# Use symlink - keep as symlink until published - saves storage
if template_file.exists():
    create_output_link(template_file, str(ref_from_anat_reg_path))
else:
    raise FileNotFoundError(f"Template file not found: {template_file}")

# Ensure file exists
if not ref_from_anat_reg_path.exists():
    raise FileNotFoundError(f"Failed to create ref_from_anat_reg.nii.gz: {ref_from_anat_reg_path}")

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
    // Transforms: [sub, ses, forward_transform, inverse_transform]
    tuple val(subject_id), val(session_id), path("*from-T2w_to-T1w_mode-image_xfm*"), path("*from-T1w_to-T2w_mode-image_xfm*"), emit: transforms
    path "*.json", emit: metadata
    
    script:
    """
    # Thread environment variables are set by Nextflow's beforeScript based on task.cpus
    # Python code reads OMP_NUM_THREADS from environment
    
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

# Create symlinks for transform files with BIDS-compliant names
# .h5 files can be large, so use symlinks until published - saves storage
if "forward_transform" in result.additional_files:
    # Forward transform: from-T2w_to-T1w
    bids_transform_name = f"{bids_prefix_wo_modality}_from-T2w_to-T1w_mode-image_xfm.h5"
    create_output_link(result.additional_files["forward_transform"], bids_transform_name)

if "inverse_transform" in result.additional_files:
    # Inverse transform: from-T1w_to-T2w
    bids_transform_name = f"{bids_prefix_wo_modality}_from-T1w_to-T2w_mode-image_xfm.h5"
    create_output_link(result.additional_files["inverse_transform"], bids_transform_name)

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
    path config_file  // Effective config file with all resolved parameters
    
    output:
    tuple val(subject_id), val(session_id), path("*desc-conform*.nii.gz"), val(bids_naming_template), emit: output
    // Transforms: [sub, ses, forward_transform, inverse_transform]
    tuple val(subject_id), val(session_id), path("*from-scanner_to-*_mode-image_xfm*"), path("*from-*_to-scanner_mode-image_xfm*"), emit: transforms
    // Reference: [sub, ses, reference]
    tuple val(subject_id), val(session_id), path("reference.nii.gz"), emit: reference
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import detect_modality, save_metadata, create_output_link
from pathlib import Path
import shutil
import os
import numpy as np
import json

# Get BIDS naming template
bids_naming_template = Path('${bids_naming_template}')

# Determine modality
modality = detect_modality(bids_naming_template)
original_stem = get_filename_stem(bids_naming_template)

# Pass through input file (create symlink)
# Use create_output_link() for consistency and proper symlink resolution
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-conform',
    modality=modality
)
create_output_link(Path('${input_file}'), bids_output_filename)

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

# Create dummy reference (symlink to input for QC compatibility)
# Keep as symlink until published - saves storage
reference_name = 'reference.nii.gz'
create_output_link(Path('${input_file}'), reference_name)

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
from macacaMRIprep.utils.nextflow import detect_modality, save_metadata, create_output_link
from pathlib import Path
import os

# Get BIDS naming template
bids_naming_template = Path('${bids_naming_template}')

# Determine modality
modality = detect_modality(bids_naming_template)
original_stem = get_filename_stem(bids_naming_template)

# Pass through input file (create symlink)
# Use create_output_link() for consistency and proper symlink resolution
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-preproc',
    modality=modality
)
create_output_link(Path('${input_file}'), bids_output_filename)

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
    path config_file  // Effective config file with all resolved parameters
    
    output:
    // Output: [sub, ses, registered_file, bids_template]
    tuple val(subject_id), val(session_id), path("*.nii.gz"), val(bids_naming_template), emit: output
    // Transforms: [sub, ses, forward_transform, inverse_transform]
    // Forward: from-{modality}_to-{template} (e.g., from-T1w_to-NMT2Sym)
    // Inverse: from-{template}_to-{modality} (e.g., from-NMT2Sym_to-T1w)
    // Use patterns that match the actual naming: forward starts with from-T1w_to- or from-T2w_to-, inverse ends with _to-T1w or _to-T2w
    tuple val(subject_id), val(session_id), path("*from-T1w_to-*_mode-image_xfm*"), path("*from-*_to-T1w_mode-image_xfm*"), emit: transforms
    // Reference: [sub, ses, reference_file]
    tuple val(subject_id), val(session_id), path("*ref_from_anat_reg.nii.gz"), emit: reference
    path "*.json", emit: metadata
    
    script:
    """
    # Get effective_output_space from effective config file
    EFFECTIVE_OUTPUT_SPACE=\$(\${PYTHON:-python3} <<'PYTHON_OUTPUT_SPACE'
from macacaMRIprep.utils.nextflow import load_config
config = load_config('${config_file}')
effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')
print(effective_output_space)
PYTHON_OUTPUT_SPACE
    )
    TEMPLATE_NAME=\$(echo "\$EFFECTIVE_OUTPUT_SPACE" | cut -d':' -f1)
    
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.templates import resolve_template
from macacaMRIprep.utils.nextflow import detect_modality, save_metadata, create_output_link, load_config
from pathlib import Path
import os
import subprocess
import shutil

# Get BIDS naming template
bids_naming_template = Path('${bids_naming_template}')

# Determine modality
modality = detect_modality(bids_naming_template)
original_stem = get_filename_stem(bids_naming_template)

# Get effective_output_space from effective config file
config = load_config('${config_file}')
effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')
template_name = effective_output_space.split(':')[0] if effective_output_space else 'NMT2Sym'

# Pass through input file (create symlink with space entity)
# Use create_output_link() for consistency and proper symlink resolution
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix=f'space-{template_name}_desc-preproc',
    modality=modality
)
create_output_link(Path('${input_file}'), bids_output_filename)

# Generate BIDS prefix
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")

# Get effective_output_space from effective config file
config = load_config('${config_file}')
effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')

# Create identity transform using ANTs
# Create identity affine transform file first
template_file = Path(resolve_template(effective_output_space))
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
# Use symlink since it's the same file - saves storage
inverse_transform_name = f"{bids_prefix_wo_modality}_from-{template_name}_to-{modality}_mode-image_xfm.h5"
create_output_link(forward_transform_name, inverse_transform_name)

# Create ref_from_anat_reg.nii.gz for QC reference (same as in ANAT_REGISTRATION) 
# Use symlink - keep as symlink until published - saves storage
ref_from_anat_reg_path = Path(f"{bids_prefix_wo_modality}_ref_from_anat_reg.nii.gz")

# Create symlink to template file
if template_file.exists():
    create_output_link(template_file, str(ref_from_anat_reg_path))
else:
    raise FileNotFoundError(f"Template file not found: {template_file}")

# Ensure file exists
if not ref_from_anat_reg_path.exists():
    raise FileNotFoundError(f"Failed to create ref_from_anat_reg.nii.gz: {ref_from_anat_reg_path}")

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

// ============================================
// ANATOMICAL APPLY MODULES (for T2w processing)
// ============================================
// These modules apply T1w's computed transforms/masks to T2w data

process ANAT_APPLY_CONFORM {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,mat}'
    
    input:
    // Input: [sub, ses, t2w_file, t2w_bids_name, conform_transform, conformed_reference, anat_ses]
    // Stage conformed_reference as reg_reference.nii.gz to avoid output pattern collision
    tuple val(subject_id), val(session_id), path(t2w_file), val(bids_naming_template), path(conform_transform), path(conformed_reference, stageAs: 'reg_reference.nii.gz'), val(anatomical_session)
    path config_file
    
    output:
    // Output: [sub, ses, conformed_t2w, t2w_bids_name, anat_ses]
    tuple val(subject_id), val(session_id), path("*desc-conform_T2w.nii.gz"), val(bids_naming_template), val(anatomical_session), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.operations.registration import flirt_apply_transforms
from macacaMRIprep.utils.bids import create_bids_output_filename
from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow, load_config
from pathlib import Path

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_APPLY_CONFORM'
)

# Load config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Apply conform transform to T2w
t2w_result = flirt_apply_transforms(
    movingf=str(Path('${t2w_file}')),
    outputf_name='t2w_conformed.nii.gz',
    reff=str(Path('reg_reference.nii.gz')),
    working_dir='work',
    transformf=str(Path('${conform_transform}')),
    logger=None,
    interpolation='trilinear',
    generate_tmean=False
)

if not t2w_result.get("imagef_registered"):
    raise FileNotFoundError("Failed to apply conform transform to T2w")

# Generate BIDS-compliant output filename
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-conform',
    modality='T2w'
)

# Create symlink
create_output_link(Path(t2w_result["imagef_registered"]), bids_output_filename)

# Save metadata
save_metadata({
    "step": "apply_conform",
    "modality": "T2w",
    "t2w_file": str(Path('${t2w_file}')),
    "conform_transform": str(Path('${conform_transform}')),
    "anatomical_session": '${anatomical_session}'
})
EOF
    """
}

process ANAT_APPLY_BRAIN_MASK {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    // Input: [sub, ses, conformed_t2w, t2w_bids_name, brain_mask, anat_ses]
    tuple val(subject_id), val(session_id), path(conformed_t2w), val(bids_naming_template), path(brain_mask), val(anatomical_session)
    path config_file
    
    output:
    // Output: [sub, ses, masked_t2w, t2w_bids_name, anat_ses]
    tuple val(subject_id), val(session_id), path("*desc-conform_desc-brain_T2w.nii.gz"), val(bids_naming_template), val(anatomical_session), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.operations.preprocessing import apply_mask
from macacaMRIprep.utils.bids import create_bids_output_filename
from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow, load_config
from pathlib import Path
import logging

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_APPLY_BRAIN_MASK'
)

# Load config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Apply brain mask to T2w using apply_mask function
logger = logging.getLogger(__name__)

masked_t2w_path = Path('work') / 't2w_masked.nii.gz'
result = apply_mask(
    imagef=str(Path('${conformed_t2w}')),
    maskf=str(Path('${brain_mask}')),
    working_dir=Path('work'),
    output_name='t2w_masked.nii.gz',
    logger=logger,
    generate_tmean=False
)

masked_t2w_path = Path(result['imagef_masked'])
if not masked_t2w_path.exists():
    raise FileNotFoundError("Failed to apply brain mask to T2w")

# Generate BIDS-compliant output filename
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-conform_desc-brain',
    modality='T2w'
)

# Create symlink
create_output_link(masked_t2w_path, bids_output_filename)

# Save metadata
save_metadata({
    "step": "apply_brain_mask",
    "modality": "T2w",
    "t2w_file": str(Path('${conformed_t2w}')),
    "mask_file": str(Path('${brain_mask}')),
    "anatomical_session": '${anatomical_session}'
})
EOF
    """
}

process ANAT_APPLY_TRANSFORMATION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.{nii.gz,h5}',
        saveAs: { filename -> filename.contains('target_final.nii.gz') ? null : filename }
    
    input:
    // Input: [sub, ses, masked_t2w, t2w_bids_name, registration_transform, registration_reference]
    tuple val(subject_id), val(session_id), path(masked_t2w), val(bids_naming_template), path(registration_transform), path(registration_reference)
    path config_file
    
    output:
    // Output: [sub, ses, registered_t2w, t2w_bids_name]
    tuple val(subject_id), val(session_id), path("*space-*desc-preproc_T2w.nii.gz"), val(bids_naming_template), emit: output
    // Reference file for QC: final target reference at appropriate resolution
    tuple val(subject_id), val(session_id), path("*target_final.nii.gz"), emit: reference
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.operations.registration import ants_apply_transforms
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow, load_config
from pathlib import Path
import re
import shutil

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_APPLY_TRANSFORMATION'
)

# Load config
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine output space from transform filename
transform_path = Path('${registration_transform}')
transform_stem = get_filename_stem(transform_path)

# Extract template name from transform filename (e.g., "from-T1w_to-NMT2Sym" -> "NMT2Sym")
space_match = re.search(r'to-([A-Za-z0-9]+)', transform_stem)
if space_match:
    template_name = space_match.group(1)
else:
    # Fallback: get from config
    template_name = config.get('template', {}).get('output_space', 'NMT2Sym:res-05').split(':')[0]

# Apply registration transform to T2w
# Use LanczosWindowedSinc for continuous-value anatomical images (high-quality interpolation)
t2w_result = ants_apply_transforms(
    movingf=str(Path('${masked_t2w}')),
    moving_type=0,  # 0: scalar (anatomical image)
    interpolation='LanczosWindowedSinc',
    outputf_name='t2w_registered.nii.gz',
    fixedf=str(Path('${registration_reference}')),
    working_dir='work',
    transformf=[str(Path('${registration_transform}'))],
    reff=str(Path('${registration_reference}')),
    logger=None
)

if not t2w_result.get("imagef_registered"):
    raise FileNotFoundError("Failed to apply registration transform to T2w")

# Generate BIDS-compliant output filename with space entity
bids_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix=f'space-{template_name}_desc-preproc',
    modality='T2w'
)

# Create symlink
create_output_link(Path(t2w_result["imagef_registered"]), bids_output_filename)

# Create reference file for QC (copy of registration_reference)
ref_from_reg_path = Path(f"{get_filename_stem(bids_output_filename)}_target_final.nii.gz")
shutil.copy2(Path('${registration_reference}'), ref_from_reg_path)

# Save metadata
save_metadata({
    "step": "apply_registration",
    "modality": "T2w",
    "t2w_file": str(Path('${masked_t2w}')),
    "registration_transform": str(Path('${registration_transform}')),
    "template_name": template_name
})
EOF
    """
}

process ANAT_APPLY_TRANSFORM_MASK {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/anat",
        mode: 'copy',
        pattern: '*.nii.gz'
    
    input:
    // Input: [sub, ses, mask_file, registration_transform, registration_reference]
    tuple val(subject_id), val(session_id), path(mask_file), path(registration_transform), path(registration_reference)
    path config_file
    
    output:
    // Output: [sub, ses, transformed_mask]
    tuple val(subject_id), val(session_id), path("*space-*desc-brain_mask.nii.gz"), emit: output
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.operations.registration import ants_apply_transforms
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from macacaMRIprep.utils.nextflow import create_output_link, save_metadata, init_cmd_log_for_nextflow, load_config
from pathlib import Path
import re

# Initialize command log file
init_cmd_log_for_nextflow(
    output_dir='${params.output_dir}',
    subject_id='${subject_id}',
    session_id='${session_id}' if '${session_id}' else None,
    step_name='ANAT_APPLY_TRANSFORM_MASK'
)

# Load config
config = load_config('${config_file}')

# Get mask file path
mask_file = Path('${mask_file}')

# Determine output space from transform filename
transform_path = Path('${registration_transform}')
transform_stem = get_filename_stem(transform_path)

# Extract template name from transform filename (e.g., "from-T1w_to-NMT2Sym" -> "NMT2Sym")
space_match = re.search(r'to-([A-Za-z0-9]+)', transform_stem)
if space_match:
    template_name = space_match.group(1)
else:
    # Fallback: get from config
    template_name = config.get('template', {}).get('output_space', 'NMT2Sym:res-05').split(':')[0]

# Apply registration transform to mask using NearestNeighbor interpolation (for binary masks)
mask_result = ants_apply_transforms(
    movingf=str(mask_file),
    moving_type=0,  # 0: scalar
    interpolation='NearestNeighbor',  # NearestNeighbor for binary masks
    outputf_name='mask_registered.nii.gz',
    fixedf=str(Path('${registration_reference}')),
    working_dir='work',
    transformf=[str(transform_path)],
    reff=str(Path('${registration_reference}')),
    logger=None,
    generate_tmean=False
)

if not mask_result.get("imagef_registered"):
    raise FileNotFoundError("Failed to apply registration transform to mask")

# Generate BIDS-compliant output filename with space entity
# Extract original filename stem to preserve subject/session entities
mask_stem = get_filename_stem(mask_file)
# Parse entities from original mask filename
import json
from macacaMRIprep.utils.bids import parse_bids_entities, create_bids_filename

try:
    # Try to parse BIDS entities from original mask filename
    entities = parse_bids_entities(str(mask_file))
    # Add space entity
    entities['space'] = template_name
    entities['desc'] = 'brain'
    # Create new filename
    bids_output_filename = create_bids_filename(entities, 'mask', extension='.nii.gz')
except:
    # Fallback: use create_bids_output_filename with space entity
    bids_output_filename = create_bids_output_filename(
        original_file_path=mask_file,
        suffix=f'space-{template_name}_desc-brain',
        modality='mask'
    )

# Create symlink
create_output_link(Path(mask_result["imagef_registered"]), bids_output_filename)

# Save metadata
save_metadata({
    "step": "apply_mask_transform",
    "mask_file": str(mask_file),
    "registration_transform": str(transform_path),
    "template_name": template_name,
    "interpolation": "NearestNeighbor"
})
EOF
    """
}
