/*
 * Main Nextflow workflow for banana
 * 
 * This workflow processes BIDS datasets using per-step parallelization
 * for maximum efficiency.
 * 
 * BIDS discovery is performed by a Python script BEFORE this workflow runs.
 * The discovery script validates the BIDS dataset, discovers all jobs, and
 * saves JSON files that this workflow reads to create channels.
 */

nextflow.enable.dsl=2

// Include anatomical processing modules
include { ANAT_SYNTHESIS } from './modules/anatomical.nf'
include { ANAT_REORIENT } from './modules/anatomical.nf'
include { ANAT_CONFORM } from './modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION } from './modules/anatomical.nf'
include { ANAT_SKULLSTRIPPING } from './modules/anatomical.nf'
include { ANAT_REGISTRATION } from './modules/anatomical.nf'

// Include functional processing modules
include { FUNC_REORIENT } from './modules/functional.nf'
include { FUNC_SLICE_TIMING } from './modules/functional.nf'
include { FUNC_MOTION_CORRECTION } from './modules/functional.nf'
include { FUNC_DESPIKE } from './modules/functional.nf'
include { FUNC_BIAS_CORRECTION } from './modules/functional.nf'
include { FUNC_CONFORM } from './modules/functional.nf'
include { FUNC_SKULLSTRIPPING } from './modules/functional.nf'
include { FUNC_REGISTRATION } from './modules/functional.nf'
include { FUNC_APPLY_TRANSFORMS } from './modules/functional.nf'

// Include QC modules
include { QC_ANATOMICAL } from './modules/qc.nf'
include { QC_FUNCTIONAL } from './modules/qc.nf'

workflow {
    // ============================================
    // INPUT VALIDATION
    // ============================================
    if (!params.bids_dir) {
        error "Missing required parameter: --bids_dir"
    }
    if (!params.output_dir) {
        error "Missing required parameter: --output_dir"
    }
    
    // Validate paths exist (validation happens in processes, but we can check strings here)
    def bids_dir_path = file(params.bids_dir)
    def bids_dir_str = params.bids_dir.toString()
    if (!new File(bids_dir_str).exists()) {
        error "BIDS directory not found: ${params.bids_dir}"
    }
    
    // Load config file (default or provided)
    def config_file_path = params.config_file ?: "${projectDir}/macacaMRIprep/config/defaults.yaml"
    def config_file = file(config_file_path)
    if (!new File(config_file_path).exists()) {
        error "Config file not found: ${config_file_path}"
    }
    
    // Read anat_only and func_only from YAML config file
    // Command-line params take precedence, but if not set, read from config file
    def anat_only = params.anat_only
    def func_only = params.func_only
    
    // Read from config file using Python (more reliable than trying to parse YAML in Groovy)
    try {
        // Use a Python script to read the config value
        def anat_only_script = """
import yaml
import sys
try:
    with open('${config_file_path}', 'r') as f:
        config = yaml.safe_load(f)
    value = config.get('general', {}).get('anat_only', False)
    print('true' if value else 'false')
except Exception as e:
    print('false')
    sys.exit(1)
"""
        // Use a simpler approach: write script to temp file and execute
        def temp_script = File.createTempFile("read_anat_only", ".py")
        temp_script.text = anat_only_script
        def anat_only_proc = ["python3", temp_script.absolutePath].execute()
        def anat_only_output = new StringBuffer()
        def anat_only_error = new StringBuffer()
        anat_only_proc.consumeProcessOutput(anat_only_output, anat_only_error)
        anat_only_proc.waitFor()
        def anat_only_result = anat_only_output.toString().trim()
        def anat_only_err = anat_only_error.toString().trim()
        temp_script.delete()
        if (anat_only_err) {
            println "Debug: Python stderr for anat_only: ${anat_only_err}"
        }
        println "Debug: Read anat_only from config: '${anat_only_result}' (exit code: ${anat_only_proc.exitValue()})"
        if (anat_only_result == "true") {
            anat_only = true
            println "Config: Reading anat_only = true from config file"
        } else if (anat_only_proc.exitValue() != 0) {
            println "Warning: Error reading anat_only from config file (exit code: ${anat_only_proc.exitValue()})"
        }
    } catch (Exception e) {
        println "Warning: Could not read anat_only from config file: ${e.message}, using param value: ${params.anat_only}"
    }
    
    try {
        def func_only_script = """
import yaml
import sys
try:
    with open('${config_file_path}', 'r') as f:
        config = yaml.safe_load(f)
    value = config.get('general', {}).get('func_only', False)
    print('true' if value else 'false')
except Exception as e:
    print('false')
    sys.exit(1)
"""
        // Use a simpler approach: write script to temp file and execute
        def temp_script2 = File.createTempFile("read_func_only", ".py")
        temp_script2.text = func_only_script
        def func_only_proc = ["python3", temp_script2.absolutePath].execute()
        def func_only_output = new StringBuffer()
        def func_only_error = new StringBuffer()
        func_only_proc.consumeProcessOutput(func_only_output, func_only_error)
        func_only_proc.waitFor()
        def func_only_result = func_only_output.toString().trim()
        def func_only_err = func_only_error.toString().trim()
        temp_script2.delete()
        if (func_only_err) {
            println "Debug: Python stderr for func_only: ${func_only_err}"
        }
        println "Debug: Read func_only from config: '${func_only_result}' (exit code: ${func_only_proc.exitValue()})"
        if (func_only_result == "true") {
            func_only = true
            println "Config: Reading func_only = true from config file"
        } else if (func_only_proc.exitValue() != 0) {
            println "Warning: Error reading func_only from config file (exit code: ${func_only_proc.exitValue()})"
        }
    } catch (Exception e) {
        println "Warning: Could not read func_only from config file: ${e.message}, using param value: ${params.func_only}"
    }
    
    // Print final values being used
    println "Processing mode: anat_only = ${anat_only}, func_only = ${func_only}"
    
    // Parse filtering parameters
    def subjects_str = params.subjects ?: ''
    def sessions_str = params.sessions ?: ''
    def tasks_str = params.tasks ?: ''
    def runs_str = params.runs ?: ''
    
    println "============================================"
    println "banana Nextflow Pipeline"
    println "============================================"
    println "BIDS directory: ${params.bids_dir}"
    println "Output directory: ${params.output_dir}"
    println "Output space: ${params.output_space}"
    if (subjects_str) println "Subjects filter: ${subjects_str}"
    if (sessions_str) println "Sessions filter: ${sessions_str}"
    if (tasks_str) println "Tasks filter: ${tasks_str}"
    if (runs_str) println "Runs filter: ${runs_str}"
    println "============================================"
    
    // ============================================
    // LOAD PRE-DISCOVERED JOB LISTS
    // ============================================
    // Discovery was performed by Python script before Nextflow started
    // Read the JSON files created by the discovery script
    def anat_jobs_file = file("${params.output_dir}/reports/anatomical_jobs.json")
    def func_jobs_file = file("${params.output_dir}/reports/functional_jobs.json")
    
    // Check that discovery files exist
    if (!new File("${params.output_dir}/reports/anatomical_jobs.json").exists()) {
        error "Discovery file not found: ${params.output_dir}/reports/anatomical_jobs.json\n" +
              "Please run the discovery script before starting Nextflow."
    }
    if (!new File("${params.output_dir}/reports/functional_jobs.json").exists()) {
        error "Discovery file not found: ${params.output_dir}/reports/functional_jobs.json\n" +
              "Please run the discovery script before starting Nextflow."
    }
    
    // ============================================
    // PARSE DISCOVERY RESULTS INTO CHANNELS
    // ============================================
    // Parse anatomical jobs JSON into channel
    Channel.fromPath(anat_jobs_file)
        .splitJson()
        .map { job ->
            def sub = job.subject_id.toString()
            def ses = job.session_id ? job.session_id.toString() : null
            def needs_synth = job.needs_synthesis ?: false
            def file_paths = job.file_paths ?: [job.file_path]
            def suffix = job.suffix.toString()
            
            [sub, ses, file_paths, needs_synth, suffix]
        }
        .filter { sub, ses, file_paths, needs_synth, suffix ->
            !func_only
        }
        .set { anat_jobs_ch }
    
    // Parse functional jobs JSON into channel
    Channel.fromPath(func_jobs_file)
        .splitJson()
        .map { job ->
            def sub = job.subject_id.toString()
            def ses = job.session_id ? job.session_id.toString() : null
            def task = job.task ? job.task.toString() : null
            def run = job.run ? job.run.toString() : null
            def file_path = job.file_path
            
            // Pass original file path for BIDS filename generation
            [sub, ses, task, run, file(file_path), file_path]
        }
        .filter { sub, ses, task, run, file_path, original_file_path ->
            !anat_only
        }
        .set { func_jobs_ch }
    
    // ============================================
    // ANATOMICAL PIPELINE
    // ============================================
    if (!func_only) {
        // Separate synthesis jobs from regular jobs (for all anatomical modalities)
        anat_jobs_ch
            .filter { sub, ses, file_paths, needs_synth, suffix ->
                needs_synth
            }
            .map { sub, ses, file_paths, needs_synth, suffix ->
                def files = file_paths.collect { file(it) }
                [sub, ses, files]
            }
            .set { anat_synthesis_input }
        
        // Run synthesis process for all anatomical modalities (T1w, T2w, etc.)
        ANAT_SYNTHESIS(anat_synthesis_input, config_file)
        
        // Separate single files (no synthesis needed) by modality
        anat_jobs_ch
            .filter { sub, ses, file_paths, needs_synth, suffix ->
                !needs_synth
            }
            .map { sub, ses, file_paths, needs_synth, suffix ->
                // Pass original file path for BIDS filename generation
                def original_file = file(file_paths[0])
                [sub, ses, original_file, file_paths[0]]
            }
            .set { anat_single_jobs }
        
        // Combine synthesized anatomical files (waits for synthesis) and single files (immediate)
        // For synthesis output, read original_file_path from file and convert to value
        def anat_input_ch = ANAT_SYNTHESIS.out.synthesized
            .map { sub, ses, synthesized_file, original_file_path_file ->
                def original_file_path = original_file_path_file.text.trim()
                [sub, ses, synthesized_file, original_file_path]
            }
            .mix(anat_single_jobs)
        
        // Anatomical processing steps
        // Note: The dependency is correctly enforced:
        // - Files requiring synthesis wait for ANAT_SYNTHESIS to complete
        // - Single files (no synthesis) proceed immediately
        ANAT_REORIENT(anat_input_ch, config_file)
        ANAT_CONFORM(ANAT_REORIENT.out.output, config_file)
        ANAT_BIAS_CORRECTION(ANAT_CONFORM.out.output, config_file)
        ANAT_SKULLSTRIPPING(ANAT_BIAS_CORRECTION.out.output, config_file)
        ANAT_REGISTRATION(ANAT_SKULLSTRIPPING.out.output, config_file)
        
        // QC for anatomical (needs both output and transforms)
        // Join by subject_id (index 0) and session_id (index 1)
        ANAT_REGISTRATION.out.output
            .join(ANAT_REGISTRATION.out.transforms, by: [0, 1])
            .map { sub, ses, reg_file, trans -> 
                [sub, ses, reg_file, trans]
            }
            .set { anat_reg_for_qc }
        
        QC_ANATOMICAL(anat_reg_for_qc, config_file)
    }
    
    // ============================================
    // FUNCTIONAL PIPELINE
    // ============================================
    if (!anat_only) {
        // Functional processing steps
        FUNC_REORIENT(func_jobs_ch, config_file)
        FUNC_SLICE_TIMING(FUNC_REORIENT.out.output, config_file)
        FUNC_MOTION_CORRECTION(FUNC_SLICE_TIMING.out.output, config_file)
        FUNC_DESPIKE(FUNC_MOTION_CORRECTION.out.output, config_file)
        FUNC_BIAS_CORRECTION(FUNC_DESPIKE.out.output, config_file)
        FUNC_CONFORM(FUNC_BIAS_CORRECTION.out.output, config_file)
        FUNC_SKULLSTRIPPING(FUNC_CONFORM.out.output, config_file)
        
        // Functional registration (depends on anatomical if available)
        // Join by subject_id (index 0) and session_id (index 1)
        def anat_reg_ch = func_only ? Channel.empty() : ANAT_REGISTRATION.out.output
            .join(ANAT_REGISTRATION.out.transforms, by: [0, 1])
            .map { sub, ses, reg_file, trans -> 
                [sub, ses, reg_file, trans]
            }
        FUNC_REGISTRATION(FUNC_SKULLSTRIPPING.out.output, anat_reg_ch, config_file)
        
        // Join registration outputs (tmean_registered and transforms) for apply_transforms
        // Join by subject_id (0), session_id (1), task_name (2), run (3)
        def func_reg_tuple_ch = FUNC_REGISTRATION.out.output
            .join(FUNC_REGISTRATION.out.transforms, by: [0, 1, 2, 3])
            .map { sub, ses, task, run, tmean_reg, trans, orig_path -> 
                [sub, ses, task, run, tmean_reg, trans, orig_path]
            }
        
        // Join with 4D file from DESPIKE (last step that processes 4D)
        // Match by subject/session/task/run to ensure correct pairing
        // func_reg_tuple_ch: [sub, ses, task, run, tmean_reg, trans, orig_path]
        // FUNC_DESPIKE.out.output: [sub, ses, task, run, func_4d, orig_path]
        // After join by [0,1,2,3]: [sub, ses, task, run, tmean_reg, trans, orig_path_reg, func_4d, orig_path_despike]
        def func_joined_ch = func_reg_tuple_ch
            .join(FUNC_DESPIKE.out.output, by: [0, 1, 2, 3])
        
        // Create the two input channels from the joined channel
        // Channel 1: tuple with registration info (use orig_path from registration)
        def func_reg_input = func_joined_ch.map { sub, ses, task, run, tmean_reg, trans, orig_path_reg, func_4d, orig_path_despike ->
            [sub, ses, task, run, tmean_reg, trans, orig_path_reg]
        }
        
        // Channel 2: 4D file path
        def func_4d_input = func_joined_ch.map { sub, ses, task, run, tmean_reg, trans, orig_path_reg, func_4d, orig_path_despike ->
            func_4d
        }
        
        // FUNC_APPLY_TRANSFORMS expects: (tuple with reg info), (4D file path), (config file)
        FUNC_APPLY_TRANSFORMS(func_reg_input, func_4d_input, config_file)
        
        // QC for functional
        QC_FUNCTIONAL(FUNC_APPLY_TRANSFORMS.out.output, config_file)
    }
    
    println "============================================"
    println "Pipeline execution started"
    println "============================================"
}
