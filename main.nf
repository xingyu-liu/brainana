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
include { ANAT_SURFACE_RECONSTRUCTION } from './modules/anatomical.nf'
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
include { QC_CONFORM } from './modules/qc.nf'
include { QC_BIAS_CORRECTION } from './modules/qc.nf'
include { QC_SKULLSTRIPPING } from './modules/qc.nf'
include { QC_ATLAS_SEGMENTATION } from './modules/qc.nf'
include { QC_REGISTRATION } from './modules/qc.nf'
include { QC_MOTION_CORRECTION } from './modules/qc.nf'
include { QC_BIAS_CORRECTION_FUNC } from './modules/qc.nf'
include { QC_SKULLSTRIPPING_FUNC } from './modules/qc.nf'
include { QC_REGISTRATION_FUNC } from './modules/qc.nf'
include { QC_GENERATE_REPORT } from './modules/qc.nf'

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
    
    // Read anat_only from YAML config file
    // Command-line params take precedence, but if not set, read from config file
    def anat_only = params.anat_only
    
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
    
    // Print final values being used
    println "Processing mode: anat_only = ${anat_only}"
    
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
    // Separate synthesis jobs from regular jobs (for all anatomical modalities)
    // Filter for jobs that need synthesis
    anat_jobs_ch
        .filter { sub, ses, file_paths, needs_synth, suffix ->
            needs_synth == true && file_paths != null && file_paths.size() > 0
        }
        .map { sub, ses, file_paths, needs_synth, suffix ->
            // Ensure file_paths is a list
            def paths_list = file_paths instanceof List ? file_paths : [file_paths]
            // Convert each path string to a file object
            // Nextflow path() input accepts a list/collection of files
            def file_objects = []
            paths_list.each { path_str ->
                file_objects.add(file(path_str.toString()))
            }
            // Return tuple with exactly 3 elements: [sub, ses, file_list]
            [sub, ses, file_objects]
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
        
        // Surface reconstruction: needs conformed file, segmentation, and brain mask
        // Join brain file with segmentation and conformed file (all outputs are now tuples with subject/session keys)
        ANAT_SKULLSTRIPPING.out.output
            .join(ANAT_SKULLSTRIPPING.out.brain_segmentation, by: [0, 1])
            .join(ANAT_CONFORM.out.output, by: [0, 1])
            .map { sub, ses, brain_file, orig_path1, seg_file, conf_file, orig_path2 ->
                [sub, ses, brain_file, orig_path2, conf_file, seg_file]
            }
            .set { surf_recon_input_base }
        
        // Join with brain mask
        surf_recon_input_base
            .join(ANAT_SKULLSTRIPPING.out.brain_mask, by: [0, 1])
            .map { sub, ses, brain_file, orig_path, conf_file, seg_file, mask_file ->
                [sub, ses, brain_file, orig_path, conf_file, seg_file, mask_file ?: file("")]
            }
            .set { surf_recon_input }
        
        ANAT_SURFACE_RECONSTRUCTION(surf_recon_input, config_file)
        
        ANAT_REGISTRATION(ANAT_SKULLSTRIPPING.out.output, config_file)
        
        // QC for anatomical - individual steps
        // QC_CONFORM: needs conformed file + resampled template (same space as conformed image)
        ANAT_CONFORM.out.output
            .join(ANAT_CONFORM.out.template_resampled, by: [0, 1])
            .map { sub, ses, conf_file, orig_path, template_resampled ->
                [sub, ses, conf_file, orig_path, template_resampled]
            }
            .set { conform_qc_input }
        QC_CONFORM(conform_qc_input, config_file)
        
        // QC_BIAS_CORRECTION: needs original (from CONFORM) + corrected (from BIAS_CORRECTION)
        ANAT_CONFORM.out.output
            .join(ANAT_BIAS_CORRECTION.out.output, by: [0, 1])
            .map { sub, ses, conf_file, orig_path1, bias_file, orig_path2 ->
                [sub, ses, conf_file, bias_file, orig_path2]
            }
            .set { bias_qc_input }
        QC_BIAS_CORRECTION(bias_qc_input, config_file)
        
        // QC_SKULLSTRIPPING: needs brain file + mask file
        ANAT_SKULLSTRIPPING.out.output
            .join(ANAT_SKULLSTRIPPING.out.brain_mask, by: [0, 1])
            .map { sub, ses, brain_file, orig_path, mask_file ->
                [sub, ses, brain_file, mask_file, orig_path]
            }
            .set { skull_qc_input }
        QC_SKULLSTRIPPING(skull_qc_input, config_file)
        
        // QC_ATLAS_SEGMENTATION: needs brain file + segmentation file (optional)
        ANAT_SKULLSTRIPPING.out.output
            .join(ANAT_SKULLSTRIPPING.out.brain_segmentation, by: [0, 1])
            .map { sub, ses, brain_file, orig_path, seg_file ->
                [sub, ses, brain_file, seg_file, orig_path]
            }
            .set { atlas_qc_input }
        QC_ATLAS_SEGMENTATION(atlas_qc_input, config_file)
        
        // QC_REGISTRATION: needs registered file + transforms
        ANAT_REGISTRATION.out.output
            .join(ANAT_REGISTRATION.out.transforms, by: [0, 1])
            .map { sub, ses, reg_file, trans -> 
                [sub, ses, reg_file, trans]
            }
            .set { anat_reg_for_qc }
        QC_REGISTRATION(anat_reg_for_qc, config_file)
    
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
        // Strategy: Join by subject AND session first, then fallback to first available anatomical session for same subject
        // Prepare anatomical channel: [sub, ses, reg_file, trans]
        def anat_reg_ch = ANAT_REGISTRATION.out.output
            .join(ANAT_REGISTRATION.out.transforms, by: [0, 1])
            .map { sub, ses, reg_file, trans -> 
                [sub, ses, reg_file, trans]
            }
        
        // Create a map of subject -> first anatomical session for fallback
        // Group by subject and take the first session (sorted by session_id)
        def anat_by_subject = anat_reg_ch
            .groupTuple(by: 0)  // Group by subject_id (index 0)
            .map { sub, sessions ->
                // sessions is a list of [ses, reg_file, trans] tuples
                // Sort by session_id (handle null as empty string) and take the first one
                def sorted_sessions = sessions.sort { a, b ->
                    def ses_a = a[0] ?: ''
                    def ses_b = b[0] ?: ''
                    ses_a <=> ses_b
                }
                def first_session = sorted_sessions[0]
                [sub, first_session[0], first_session[1], first_session[2]]  // [sub, ses, reg_file, trans]
            }
        
        // Join functional data with anatomical data by subject AND session (exact match)
        // FUNC_SKULLSTRIPPING.out.output: [sub, ses, task, run, file, orig_path]
        // anat_reg_ch: [sub, ses, reg_file, trans]
        def func_anat_exact = FUNC_SKULLSTRIPPING.out.output
            .join(anat_reg_ch, by: [0, 1])  // Join by [subject_id, session_id]
            .map { sub, ses, task, run, func_file, orig_path, anat_reg, anat_trans ->
                // Exact match - same subject and session
                [sub, ses, task, run, func_file, orig_path, anat_reg, anat_trans, ses, false]  // Last two: anat_ses, is_fallback
            }
        
        // For functional sessions without exact anatomical match, use first available anatomical for same subject
        // Combine all functional with first anatomical per subject, then filter to only unmatched cases
        def func_anat_fallback = FUNC_SKULLSTRIPPING.out.output
            .combine(anat_by_subject, by: 0)  // Combine by subject_id only
            .filter { sub, ses_func, task, run, func_file, orig_path, ses_anat, anat_reg, anat_trans ->
                // Only keep if functional session doesn't match anatomical session (fallback case)
                ses_func != ses_anat
            }
            .map { sub, ses_func, task, run, func_file, orig_path, ses_anat, anat_reg, anat_trans ->
                // Using anatomical from different session - add warning flag
                [sub, ses_func, task, run, func_file, orig_path, anat_reg, anat_trans, ses_anat, true]  // Last two: anat_ses, is_fallback
            }
        
        // Combine exact matches and fallbacks
        def func_anat_joined = func_anat_exact
            .mix(func_anat_fallback)
        
        FUNC_REGISTRATION(func_anat_joined, config_file)
        
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
        
        // QC for functional - individual steps
        // QC_MOTION_CORRECTION: needs motion params + input file
        FUNC_MOTION_CORRECTION.out.output
            .join(FUNC_MOTION_CORRECTION.out.motion_params, by: [0, 1, 2, 3])
            .map { sub, ses, task, run, func_file, orig_path, motion_file ->
                [sub, ses, task, run, motion_file, func_file, orig_path]
            }
            .set { motion_qc_input }
        QC_MOTION_CORRECTION(motion_qc_input, config_file)
        
        // QC_BIAS_CORRECTION_FUNC: needs original (from DESPIKE) + corrected (from BIAS_CORRECTION)
        FUNC_DESPIKE.out.output
            .join(FUNC_BIAS_CORRECTION.out.output, by: [0, 1, 2, 3])
            .map { sub, ses, task, run, despike_file, orig_path1, bias_file, orig_path2 ->
                [sub, ses, task, run, despike_file, bias_file, orig_path2]
            }
            .set { func_bias_qc_input }
        QC_BIAS_CORRECTION_FUNC(func_bias_qc_input, config_file)
        
        // QC_SKULLSTRIPPING_FUNC: needs brain file + mask file
        FUNC_SKULLSTRIPPING.out.output
            .join(FUNC_SKULLSTRIPPING.out.brain_mask, by: [0, 1, 2, 3])
            .map { sub, ses, task, run, brain_file, orig_path, mask_file ->
                [sub, ses, task, run, brain_file, mask_file, orig_path]
            }
            .set { func_skull_qc_input }
        QC_SKULLSTRIPPING_FUNC(func_skull_qc_input, config_file)
        
        // QC_REGISTRATION_FUNC: needs registered file
        QC_REGISTRATION_FUNC(FUNC_APPLY_TRANSFORMS.out.output, config_file)
    }
    
    // ============================================
    // QC REPORT GENERATION (per subject)
    // ============================================
    // Ensure all QC processes complete before report generation
    // Use QC_REGISTRATION outputs as the final dependency (since it runs last)
    
    // Collect all QC_REGISTRATION metadata files to create a completion signal
    // Group them to ensure all complete before proceeding
    def anat_qc_completion = QC_REGISTRATION.out.metadata
        .groupTuple()  // Collect all anatomical QC_REGISTRATION metadata files
    
    // Create completion signal - wait for anatomical, and functional if applicable
    def qc_completion_signal = anat_qc_completion
    if (!anat_only) {
        def func_qc_completion = QC_REGISTRATION_FUNC.out.metadata
            .groupTuple()  // Collect all functional QC_REGISTRATION metadata files
        // Combine both signals - ensures both anatomical and functional QC complete
        qc_completion_signal = anat_qc_completion
            .combine(func_qc_completion)
            .map { anat_meta, func_meta -> anat_meta }  // Use anatomical as the signal
    }
    
    // Get unique subjects from anatomical or functional jobs
    def all_subjects = Channel.empty()
    all_subjects = all_subjects.mix(anat_jobs_ch.map { sub, ses, file_paths, needs_synth, suffix -> sub }.unique())
    if (!anat_only) {
        all_subjects = all_subjects.mix(func_jobs_ch.map { sub, ses, task, run, file_path, original_file_path -> sub }.unique())
    }
    
    // Create snapshot directory path for each subject
    // Combine with QC completion signal to ensure all QC processes finish first
    // QC_GENERATE_REPORT expects: tuple (subject_id, snapshot_dir, config_file)
    def qc_report_input = all_subjects
        .combine(qc_completion_signal)  // Combine ensures QC processes complete before report generation
        .map { sub, meta_files ->
            def snapshot_dir = file("${params.output_dir}/sub-${sub}/figures")
            [sub, snapshot_dir, config_file]
        }
        .groupTuple(by: 0)  // Group by subject_id to remove duplicates
        .map { sub, items -> items[0] }  // Take first item from each group
    
    QC_GENERATE_REPORT(qc_report_input)

}
