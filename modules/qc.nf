/*
 * Quality control modules for macacaMRIprep Nextflow pipeline
 */

process QC_ANATOMICAL {
    label 'cpu'
    tag "${subject_id}_${session_id}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/figures",
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
    import json
    import yaml
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Resolve template
    template_file = Path(resolve_template('${params.output_space}'))
    
    # Generate QC
    output_path = Path('anat_registration_qc.png')
    result = qc_registration(
        image_file=Path('${registered_file}'),
        template_file=template_file,
        output_path=output_path,
        modality='anat2template',
        config=config
    )
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    
    # Copy QC file
    import shutil
    if result.qc_files:
        shutil.copy2(result.qc_files[0], 'anat_registration_qc.png')
    EOF
    """
}

process QC_FUNCTIONAL {
    label 'cpu'
    tag "${subject_id}_${session_id}_${task}_${run}"
    
    publishDir "${params.output_dir}/sub-${subject_id}${session_id ? "/ses-${session_id}" : ""}/figures",
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
    import json
    import yaml
    
    # Load config
    with open('${config_file}') as f:
        config = yaml.safe_load(f)
    
    # Resolve template
    template_file = Path(resolve_template('${params.output_space}'))
    
    # Generate QC
    output_path = Path('func_registration_qc.png')
    result = qc_registration(
        image_file=Path('${registered_file}'),
        template_file=template_file,
        output_path=output_path,
        modality='func2template',
        config=config
    )
    
    # Save metadata
    with open('metadata.json', 'w') as f:
        json.dump(result.metadata, f, indent=2)
    
    # Copy QC file
    import shutil
    if result.qc_files:
        shutil.copy2(result.qc_files[0], 'func_registration_qc.png')
    EOF
    """
}

