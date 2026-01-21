/*
 * Quality control modules for macacaMRIprep Nextflow pipeline
 */

// ============================================
// ANATOMICAL QC PROCESSES
// ============================================

process QC_CONFORM {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(conformed_file), val(bids_naming_template), path(template_resampled_file, stageAs: 'template.nii.gz')
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_conform
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from original filename
modality = detect_modality(bids_naming_template)

# Use the resampled template file from conform step (matches the conformed image space)
# File is staged as 'template.nii.gz' to avoid filename collisions
template_file = Path('template.nii.gz')

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-conform',
    modality=modality
).replace('.nii.gz', '.png')

# Generate QC
result = qc_conform(
    conformed_file=Path('${conformed_file}'),
    template_file=template_file,
    output_path=Path(qc_output_filename),
    modality='anat',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_BIAS_CORRECTION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(original_file), path(corrected_file), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_bias_correction
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from original filename
modality = detect_modality(bids_naming_template)

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-biascorrect',
    modality=modality
).replace('.nii.gz', '.png')

# Generate QC
result = qc_bias_correction(
    original_file=Path('${original_file}'),
    corrected_file=Path('${corrected_file}'),
    output_path=Path(qc_output_filename),
    modality='anat',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_SKULLSTRIPPING {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(brain_file), path(mask_file), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_skullstripping
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from original filename
modality = detect_modality(bids_naming_template)

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-skullstrip',
    modality=modality
).replace('.nii.gz', '.png')

# Generate QC
result = qc_skullstripping(
    underlay_file=Path('${brain_file}'),
    mask_file=Path('${mask_file}'),
    output_path=Path(qc_output_filename),
    modality='anat',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_ATLAS_SEGMENTATION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(brain_file), path(segmentation_file), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", optional: true, emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_atlas_segmentation
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from original filename
modality = detect_modality(bids_naming_template)

# Check if segmentation file exists
segmentation_file = Path('${segmentation_file}')
if not segmentation_file.exists():
    logger.warning(f"QC: Atlas segmentation file not found - {segmentation_file}. Skipping atlas segmentation QC.")
    # Create empty metadata file
    save_metadata({"step": "qc_atlas_segmentation", "skipped": True, "reason": "segmentation_file_not_found"})
else:
    # Generate BIDS-compliant QC output filename
    qc_output_filename = create_bids_output_filename(
        original_file_path=bids_naming_template,
        suffix='desc-atlasSegmentation',
        modality=modality
    ).replace('.nii.gz', '.png')
    
    # Generate QC
    result = qc_atlas_segmentation(
        underlay_file=Path('${brain_file}'),
        atlas_file=segmentation_file,
        output_path=Path(qc_output_filename),
        modality='anat',
        config=config
    )
    
    # Save metadata
    save_metadata(result.metadata)
EOF
    """
}

process QC_REGISTRATION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(registered_file, stageAs: 'registered.nii.gz'), path(reference_file, stageAs: 'reference.nii.gz'), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_registration
from macacaMRIprep.utils.bids import parse_bids_entities, create_bids_filename, create_bids_output_filename
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get the registered file and reference file directly from input
# Files are staged with unique names to avoid collisions
registered_file = Path('registered.nii.gz')
if not registered_file.exists():
    raise FileNotFoundError(f"Registered file not found: {registered_file}")

reference_file = Path('reference.nii.gz')
if not reference_file.exists():
    raise FileNotFoundError(f"Reference file not found: {reference_file}")

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
modality = detect_modality(bids_naming_template)

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-anat2template',
    modality=modality
).replace('.nii.gz', '.png')

# Generate QC
result = qc_registration(
    image_file=registered_file,
    template_file=reference_file,  # Use reference file from registration output
    output_path=Path(qc_output_filename),
    modality='anat2template',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_T2W_TO_T1W_REGISTRATION {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(t2w_in_t1w_space), path(t1w_brain)
    val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_registration
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get T1w brain file (skullstripped T1w for contour overlay)
t1w_brain = Path('${t1w_brain}')
if not t1w_brain.exists():
    raise FileNotFoundError(f"T1w brain file not found: {t1w_brain}")

# Get conformed T2w (after applying conform transform)
conformed_t2w = Path('${t2w_in_t1w_space}')
if not conformed_t2w.exists():
    raise FileNotFoundError(f"Conformed T2w file not found: {conformed_t2w}")

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
original_stem = get_filename_stem(bids_naming_template)
modality = 'T2w'

# Generate BIDS-compliant QC output filename
# Format: {prefix}_desc-T2w2T1w_T2w.png
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")
qc_output_filename = f"{bids_prefix_wo_modality}_desc-T2w2T1w_{modality}.png"

# Generate QC: Conformed T2w (underlay) with T1w brain contours (overlay)
result = qc_registration(
    image_file=conformed_t2w,
    template_file=t1w_brain,  # T1w brain for contour overlay
    output_path=Path(qc_output_filename),
    modality='T2w2T1w',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_T2W_TEMPLATE_SPACE {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(t2w_in_template_space), path(template_reference)
    val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_registration
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get template reference file (for contour overlay)
template_reference = Path('${template_reference}')
if not template_reference.exists():
    raise FileNotFoundError(f"Template reference file not found: {template_reference}")

# Get T2w in template space (after all transforms)
t2w_in_template_space = Path('${t2w_in_template_space}')
if not t2w_in_template_space.exists():
    raise FileNotFoundError(f"T2w in template space file not found: {t2w_in_template_space}")

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
original_stem = get_filename_stem(bids_naming_template)
modality = 'T2w'

# Generate BIDS-compliant QC output filename
# Format: {prefix}_desc-T2w2template_T2w.png
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")
qc_output_filename = f"{bids_prefix_wo_modality}_desc-T2w2template_{modality}.png"

# Generate QC: T2w in template space (underlay) with template reference contours (overlay)
result = qc_registration(
    image_file=t2w_in_template_space,
    template_file=template_reference,  # Template reference for contour overlay
    output_path=Path(qc_output_filename),
    modality='T2w2template',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_SURF_RECON_TISSUE_SEG {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(fs_subject_dir), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_surf_recon_tissue_seg
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from original filename
modality = detect_modality(bids_naming_template)

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-surfReconTissueSeg',
    modality=modality
).replace('.nii.gz', '.png')

# Since ANAT_SURFACE_RECONSTRUCTION uses publishDir with mode: 'move',
# the directory has been moved to the published location, not staged.
# Use the published directory path directly.
fs_subject_dir_resolved = Path('${params.output_dir}/fastsurfer/sub-${subject_id}').resolve()

# Generate QC
result = qc_surf_recon_tissue_seg(
    fs_subject_dir=fs_subject_dir_resolved,
    output_path=Path(qc_output_filename),
    modality='anat',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_CORTICAL_SURF_AND_MEASURES {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(fs_subject_dir), val(bids_naming_template), val(atlas_name)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_cortical_surf_and_measures
from macacaMRIprep.utils.bids import create_bids_output_filename, get_filename_stem
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from original filename
modality = detect_modality(bids_naming_template)

# Get atlas name (remove "atlas" suffix if present for compatibility)
atlas_name = '${atlas_name}'.rstrip('atlas') if '${atlas_name}'.endswith('atlas') else '${atlas_name}'
if not atlas_name:
    atlas_name = 'ARM2'  # default

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-corticalSurfAndMeasures',
    modality=modality
).replace('.nii.gz', '.png')

# Since ANAT_SURFACE_RECONSTRUCTION uses publishDir with mode: 'move',
# the directory has been moved to the published location, not staged.
# Use the published directory path directly.
fs_subject_dir_resolved = Path('${params.output_dir}/fastsurfer/sub-${subject_id}').resolve()

# Generate QC
result = qc_cortical_surf_and_measures(
    fs_subject_dir=fs_subject_dir_resolved,
    output_path=Path(qc_output_filename),
    atlas_name=atlas_name,
    modality='anat',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

// ============================================
// FUNCTIONAL QC PROCESSES
// ============================================

process QC_MOTION_CORRECTION {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(motion_params_file), path(input_file), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_motion_correction
from macacaMRIprep.utils.bids import create_bids_output_filename
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-motion',
    modality='bold'
).replace('.nii.gz', '.png')

# Generate QC
result = qc_motion_correction(
    motion_params_file=Path('${motion_params_file}'),
    output_path=Path(qc_output_filename),
    input_file=Path('${input_file}'),
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_BIAS_CORRECTION_FUNC {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(original_file), path(corrected_file), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_bias_correction
from macacaMRIprep.utils.bids import create_bids_output_filename
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-biascorrect',
    modality='bold'
).replace('.nii.gz', '.png')

# Generate QC
result = qc_bias_correction(
    original_file=Path('${original_file}'),
    corrected_file=Path('${corrected_file}'),
    output_path=Path(qc_output_filename),
    modality='func',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}


process QC_CONFORM_FUNC {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(conformed_file), val(bids_naming_template), path(template_resampled_file, stageAs: 'template.nii.gz')
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_conform
from macacaMRIprep.utils.bids import create_bids_output_filename
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Use the resampled template file from conform step (matches the conformed image space)
# File is staged as 'template.nii.gz' to avoid filename collisions
template_file = Path('template.nii.gz')

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-conform',
    modality='bold'
).replace('.nii.gz', '.png')

# Generate QC
result = qc_conform(
    conformed_file=Path('${conformed_file}'),
    template_file=template_file,
    output_path=Path(qc_output_filename),
    modality='func',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_SKULLSTRIPPING_FUNC {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(brain_file), path(mask_file), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_skullstripping
from macacaMRIprep.utils.bids import create_bids_output_filename
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Generate BIDS-compliant QC output filename
qc_output_filename = create_bids_output_filename(
    original_file_path=bids_naming_template,
    suffix='desc-skullstrip',
    modality='bold'
).replace('.nii.gz', '.png')

# Generate QC
result = qc_skullstripping(
    underlay_file=Path('${brain_file}'),
    mask_file=Path('${mask_file}'),
    output_path=Path(qc_output_filename),
    modality='func',
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_REGISTRATION_FUNC {
    label 'cpu'
    tag "${subject_id}_${session_id}_${run_identifier}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(run_identifier), path(registered_file), path(reference_file), val(bids_name)
    val(modality)  // Modality for QC: 'func2anat' or 'func2target' (default)
    path config_file  // Effective config file with all resolved parameters
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_registration
from pathlib import Path
import glob
import os

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
from macacaMRIprep.utils.templates import resolve_template
config = load_config('${config_file}')

# Get registered file and reference file
# Handle case where registered_file might contain multiple files (space-separated)
registered_file_str = '${registered_file}'
reference_file = Path('${reference_file}')

# If registered_file contains spaces, it means multiple files were matched
# Select the file in the final template space (not intermediate T1w space)
if ' ' in registered_file_str:
    # Split by space to get individual file paths
    file_paths = registered_file_str.split()
    # Get template name from output_space (e.g., "NMT2Sym:res-1" -> "NMT2Sym")
    # Get effective_output_space from effective config file
    from macacaMRIprep.utils.nextflow import load_config
    config = load_config('${config_file}')
    effective_output_space = config.get('template', {}).get('output_space', 'NMT2Sym:res-05')
    template_name = effective_output_space.split(':')[0] if effective_output_space else 'NMT2Sym'
    # Find the file in template space (final registered file)
    registered_file = None
    for fp in file_paths:
        if f'space-{template_name}' in fp:
            registered_file = Path(fp)
            break
    # Fallback: if not found, use the last file (should be template space)
    if registered_file is None or not registered_file.exists():
        registered_file = Path(file_paths[-1])
else:
    registered_file = Path(registered_file_str)

# Verify file exists
if not registered_file.exists():
    raise FileNotFoundError(f"Registered file not found: {registered_file}")

# Get modality from input (default to 'func2target' if not provided)
qc_modality = '${modality}' if '${modality}' else 'func2target'
desc_value = 'func2anat' if qc_modality == 'func2anat' else 'func2target'

# Get bids_name for filename construction
bids_name = Path('${bids_name}') if '${bids_name}' else None

# Construct QC output filename
# For intermediate files (func2anat), use bids_name directly since intermediate file names aren't BIDS-compliant
# For final files (func2target), try to parse from registered_file first, fallback to bids_name
from macacaMRIprep.utils.bids import parse_bids_entities, create_bids_filename, create_bids_output_filename
if qc_modality == 'func2anat' and bids_name:
    # Use create_bids_output_filename for intermediate case
    qc_output_filename = create_bids_output_filename(
        original_file_path=bids_name,
        suffix=f'desc-{desc_value}',
        modality='bold'
    ).replace('.nii.gz', '.png')
else:
    # Try to parse from registered_file name, fallback to bids_name
    try:
        entities = parse_bids_entities(registered_file.name)
        entities['desc'] = desc_value
        qc_output_filename = create_bids_filename(
            entities=entities,
            suffix='bold',
            extension='.png'
        )
    except (ValueError, KeyError):
        # Fallback to bids_name if parsing fails
        if bids_name:
            qc_output_filename = create_bids_output_filename(
                original_file_path=bids_name,
                suffix=f'desc-{desc_value}',
                modality='bold'
            ).replace('.nii.gz', '.png')
        else:
            # Last resort: construct from registered_file stem
            qc_output_filename = f"{registered_file.stem}_desc-{desc_value}_bold.png"

# Generate QC
result = qc_registration(
    image_file=registered_file,
    template_file=reference_file,
    output_path=Path(qc_output_filename),
    modality=qc_modality,
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

process QC_WITHIN_SES_COREG {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), path(tmean_run1), path(tmean_averaged), val(bids_naming_template)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_within_ses_coreg
from macacaMRIprep.utils.bids import create_bids_output_filename, parse_bids_entities, create_bids_filename
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, save_metadata
config = load_config('${config_file}')

# Get original file path (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Generate BIDS-compliant QC output filename
# Remove run-specific entities (other than sub and ses), add desc-func_coreg, ends with _boldref
# Parse the original filename to get entities
parsed = parse_bids_entities(str(bids_naming_template))
# Keep only sub and ses entities, then add desc
parsed = {k: v for k, v in parsed.items() if k in ['sub', 'ses']}
parsed['desc'] = 'func_coreg'
qc_output_filename = create_bids_filename(parsed, 'boldref', extension='.png')

# Generate QC
result = qc_within_ses_coreg(
    tmean_run1=Path('${tmean_run1}'),
    tmean_averaged=Path('${tmean_averaged}'),
    output_path=Path(qc_output_filename),
    config=config
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}

// ============================================
// REPORT GENERATION
// ============================================

process QC_GENERATE_REPORT {
    label 'cpu'
    tag "${subject_id}"
    
    publishDir "${params.output_dir}",
        mode: 'copy',
        pattern: '*.html'
    
    input:
    tuple val(subject_id), path(snapshot_dir), path(config_file)
    
    output:
    path "*.html", emit: report
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_generate_report
from pathlib import Path

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Set paths:
# - snapshot_dir: use published directory path where snapshots are located
# - report_path: write to work directory (Nextflow will copy to publishDir)
# Note: organize_by_hierarchy will derive the published report path from snapshot_dir
# for correct relative path calculation
snapshot_dir = Path('${params.output_dir}/sub-${subject_id}/figures')
report_path = Path('sub-${subject_id}.html')

# Generate report
result = qc_generate_report(
    snapshot_dir=snapshot_dir,
    report_path=report_path,
    config=config,
    snapshot_paths=None  # Auto-discover from directory
)

# Save metadata
save_metadata(result.metadata)
EOF
    """
}
