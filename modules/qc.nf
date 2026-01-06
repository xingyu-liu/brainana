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
    suffix='desc-biasCorrection',
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
    suffix='desc-skullStripping',
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
    tuple val(subject_id), val(session_id), path(registered_file), path(transforms)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_registration
from macacaMRIprep.utils.templates import resolve_template
from pathlib import Path
import glob

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Resolve template
template_file = Path(resolve_template('${params.output_space}'))

# Find the registered file (handle glob pattern)
registered_files = glob.glob('*.nii.gz')
if not registered_files:
    raise FileNotFoundError("No registered file found")
registered_file = Path(registered_files[0])

# Extract modality from filename
filename = registered_file.name
modality_suffix = 'T1w'  # default
if '_T2w' in filename:
    modality_suffix = 'T2w'
elif '_T1w' in filename:
    modality_suffix = 'T1w'

# Generate BIDS-compliant QC output filename
# Extract BIDS entities from registered filename
from macacaMRIprep.utils.bids import parse_bids_entities, create_bids_filename
entities = parse_bids_entities(registered_file.name)
entities['desc'] = 'anat2template'
qc_output_filename = create_bids_filename(
    entities=entities,
    suffix=modality_suffix,
    extension='.png'
)

# Generate QC
result = qc_registration(
    image_file=registered_file,
    template_file=template_file,
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
    tuple val(subject_id), val(session_id), path(registered_t2w_file), path(t1w_reference_file)
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

# Get T1w reference file
t1w_reference = Path('${t1w_reference_file}')

# Get the registered T2w file directly from input
registered_t2w = Path('${registered_t2w_file}')
if not registered_t2w.exists():
    raise FileNotFoundError(f"Registered T2w file not found: {registered_t2w}")

# Get BIDS naming template (for BIDS filename generation)
bids_naming_template = Path('${bids_naming_template}')

# Determine modality from BIDS naming template filename
original_stem = get_filename_stem(bids_naming_template)
modality = 'T2w'

# Generate BIDS-compliant QC output filename
# Format: {prefix}_desc-T2w2T1w_T2w.png
bids_prefix_wo_modality = original_stem.replace(f"_{modality}", "")
qc_output_filename = f"{bids_prefix_wo_modality}_desc-T2w2T1w_{modality}.png"

# Generate QC
result = qc_registration(
    image_file=registered_t2w,
    template_file=t1w_reference,  # Use T1w reference instead of template
    output_path=Path(qc_output_filename),
    modality='T2w2T1w',
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
    tag "${subject_id}_${session_id}_${task}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(task), val(run), path(motion_params_file), path(input_file), val(bids_naming_template)
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
    tag "${subject_id}_${session_id}_${task}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(task), val(run), path(original_file), path(corrected_file), val(bids_naming_template)
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
    suffix='desc-biasCorrection',
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

process QC_SKULLSTRIPPING_FUNC {
    label 'cpu'
    tag "${subject_id}_${session_id}_${task}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(task), val(run), path(brain_file), path(mask_file), val(bids_naming_template)
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
    suffix='desc-skullStripping',
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
    tag "${subject_id}_${session_id}_${task}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}/figures",
        mode: 'copy',
        pattern: '*.png'
    
    input:
    tuple val(subject_id), val(session_id), val(task), val(run), path(registered_file)
    path config_file
    
    output:
    path "*.png", emit: qc_files
    path "*.json", emit: metadata
    
    script:
    """
    \${PYTHON:-python3} <<EOF
from macacaMRIprep.steps.qc import qc_registration
from macacaMRIprep.utils.templates import resolve_template
from pathlib import Path
import glob

# Load config
from macacaMRIprep.utils.nextflow import load_config, detect_modality, save_metadata
config = load_config('${config_file}')

# Resolve template
template_file = Path(resolve_template('${params.output_space}'))

# Find the registered file (handle glob pattern)
registered_files = glob.glob('*.nii.gz')
if not registered_files:
    raise FileNotFoundError("No registered file found")
registered_file = Path(registered_files[0])

# Extract BIDS entities from registered filename
from macacaMRIprep.utils.bids import parse_bids_entities, create_bids_filename
entities = parse_bids_entities(registered_file.name)
entities['desc'] = 'func2template'
qc_output_filename = create_bids_filename(
    entities=entities,
    suffix='bold',
    extension='.png'
)

# Generate QC
result = qc_registration(
    image_file=registered_file,
    template_file=template_file,
    output_path=Path(qc_output_filename),
    modality='func2template',
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
