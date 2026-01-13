/*
 * Main Nextflow workflow for banana
 * 
 * This workflow processes BIDS datasets using per-step parallelization
 * for maximum efficiency.
 * 
 * BIDS discovery is performed by a Python script BEFORE this workflow runs.
 * The discovery script validates the BIDS dataset, discovers all jobs, and
 * saves JSON files that this workflow reads to create channels.
 * 
 * ============================================
 * CHANNEL STRUCTURE DOCUMENTATION
 * ============================================
 * 
 * Standard channel structures used throughout the workflow:
 * 
 * Anatomical channels:
 *   - [sub, ses, file, bids_template] (4 elements) - standard anatomical tuple
 *   - [sub, ses, file_paths, needs_synth, suffix, needs_t1w_reg] (6 elements) - from discovery
 * 
 * Functional channels:
 *   - [sub, ses, run_identifier, file, bids_template] (5 elements) - initial functional tuple
 *   - [sub, ses, run_identifier, bold_file, tmean_file, bids_template] (6 elements) - after MOTION_CORRECTION
 *   - [sub, ses, run_identifier, anat_file, anat_ses, is_cross_ses] (6 elements) - anatomical selection result
 * 
 * Transform channels:
 *   - [sub, ses, transform_file] (3 elements) - anatomical transforms
 *   - [sub, ses, run_identifier, transform_file] (4 elements) - functional transforms
 * 
 * QC channels:
 *   - [sub, ses, metadata_file] (3 elements) - QC metadata
 *   - [sub, ses, run_identifier, metadata_file] (4 elements) - functional QC metadata
 * 
 * Note: run_identifier contains all non-sub/ses BIDS entities as a sorted string
 *       e.g., "acq-RevPol_task-rest_run-1" or "rec-realigned_task-rest_run-1"
 */

nextflow.enable.dsl=2

// Include anatomical processing modules
include { ANAT_SYNTHESIS } from './modules/anatomical.nf'
include { ANAT_REORIENT } from './modules/anatomical.nf'
// Process aliases for T2w special processing pipeline
// Note: Nextflow requires process aliases when the same process needs to be called with different
// channel inputs in the same workflow. ANAT_REORIENT_T2W and ANAT_BIAS_CORRECTION_T2W are
// identical to their non-aliased counterparts but allow separate channel tracking for T2w files
// that need special processing (REORIENT → REG_TO_T1W → BIAS_CORRECTION, skipping CONFORM/SKULLSTRIP/REG).
include { ANAT_REORIENT as ANAT_REORIENT_T2W } from './modules/anatomical.nf'
include { ANAT_CONFORM } from './modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION } from './modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION as ANAT_BIAS_CORRECTION_T2W } from './modules/anatomical.nf'
include { ANAT_SKULLSTRIPPING } from './modules/anatomical.nf'
include { ANAT_SURFACE_RECONSTRUCTION } from './modules/anatomical.nf'
include { ANAT_REGISTRATION } from './modules/anatomical.nf'
include { ANAT_T2W_TO_T1W_REGISTRATION } from './modules/anatomical.nf'
// Include pass-through processes for skipped steps
include { ANAT_CONFORM_PASSTHROUGH } from './modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION_PASSTHROUGH } from './modules/anatomical.nf'
include { ANAT_REGISTRATION_PASSTHROUGH } from './modules/anatomical.nf'

// Include functional processing modules
include { FUNC_REORIENT } from './modules/functional.nf'
include { FUNC_SLICE_TIMING } from './modules/functional.nf'
include { FUNC_MOTION_CORRECTION } from './modules/functional.nf'
include { FUNC_GENERATE_TMEAN } from './modules/functional.nf'
include { FUNC_DESPIKE } from './modules/functional.nf'
include { FUNC_BIAS_CORRECTION } from './modules/functional.nf'
include { FUNC_CONFORM } from './modules/functional.nf'
include { FUNC_COMPUTE_CONFORM } from './modules/functional.nf'
include { FUNC_COMPUTE_BRAIN_MASK } from './modules/functional.nf'
include { FUNC_COMPUTE_REGISTRATION } from './modules/functional.nf'
include { FUNC_APPLY_CONFORM } from './modules/functional.nf'
include { FUNC_APPLY_BRAIN_MASK } from './modules/functional.nf'
include { FUNC_SKULLSTRIPPING } from './modules/functional.nf'
include { FUNC_REGISTRATION } from './modules/functional.nf'
include { FUNC_APPLY_TRANSFORMS } from './modules/functional.nf'
include { FUNC_WITHIN_SES_COREG } from './modules/functional.nf'
// FUNC_WRITE_TMEAN_LIST removed - file paths passed directly to FUNC_AVERAGE_TMEAN
include { FUNC_AVERAGE_TMEAN } from './modules/functional.nf'

// Include QC modules
include { QC_CONFORM } from './modules/qc.nf'
include { QC_BIAS_CORRECTION } from './modules/qc.nf'
include { QC_SKULLSTRIPPING } from './modules/qc.nf'
include { QC_ATLAS_SEGMENTATION } from './modules/qc.nf'
include { QC_SURF_RECON_TISSUE_SEG } from './modules/qc.nf'
include { QC_CORTICAL_SURF_AND_MEASURES } from './modules/qc.nf'
include { QC_REGISTRATION } from './modules/qc.nf'
include { QC_T2W_TO_T1W_REGISTRATION } from './modules/qc.nf'

include { QC_MOTION_CORRECTION } from './modules/qc.nf'
include { QC_CONFORM_FUNC } from './modules/qc.nf'
include { QC_BIAS_CORRECTION_FUNC } from './modules/qc.nf'
include { QC_SKULLSTRIPPING_FUNC } from './modules/qc.nf'
include { QC_REGISTRATION_FUNC } from './modules/qc.nf'
include { QC_WITHIN_SES_COREG } from './modules/qc.nf'

include { QC_GENERATE_REPORT } from './modules/qc.nf'

// Load external Groovy files for channel operations
// Use evaluate() to load and execute Groovy scripts
def channelHelpers = evaluate(new File("${projectDir}/workflows/channel_helpers.groovy").text)
def funcChannels = evaluate(new File("${projectDir}/workflows/functional_channels.groovy").text)

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
    
    // Read all config values in a single batch call for efficiency
    // This avoids spawning multiple Python processes during initialization
    def batch_script = "${projectDir}/macacaMRIprep/nextflow_scripts/read_yaml_config.py"
    def config_keys = [
        "general.anat_only",
        "anat.surface_reconstruction.enabled",
        "anat.reorient.enabled",
        "anat.conform.enabled",
        "anat.bias_correction.enabled",
        "anat.skullstripping_segmentation.enabled",
        "registration.enabled",
        "func.reorient.enabled",
        "func.slice_timing_correction.enabled",
        "func.motion_correction.enabled",
        "func.despike.enabled",
        "func.bias_correction.enabled",
        "func.conform.enabled",
        "func.skullstripping.enabled",
        "func.coreg_runs_within_session",
        "template.output_space"
    ]
    def config_defaults = [
        "false", "true", "true", "true", "true", "true", "true",
        "true", "true", "true", "true", "true", "true", "true",
        "false",
        "NMT2Sym:res-05"
    ]
    
    def config_values = [:]
    try {
        def cmd = ["python3", batch_script, config_file_path] + config_keys + ["--defaults=" + config_defaults.join(",")]
        def proc = cmd.execute()
        def output = new StringBuffer()
        def error = new StringBuffer()
        proc.consumeProcessOutput(output, error)
        proc.waitFor()
        
        if (proc.exitValue() == 0) {
            def results = output.toString().trim().split('\t')
            config_keys.eachWithIndex { key, idx ->
                def value = (idx < results.length && results[idx]) ? results[idx] : config_defaults[idx]
                if (idx < 15) {  // Boolean values (first 15)
                    config_values[key] = value == "true"
                } else {  // String value (last one)
                    config_values[key] = value
                }
            }
        } else {
            // Fallback to defaults on error
            config_keys.eachWithIndex { key, idx ->
                if (idx < 15) {
                    config_values[key] = config_defaults[idx] == "true"
                } else {
                    config_values[key] = config_defaults[idx]
                }
            }
            if (error.toString().trim()) {
                println "Warning: Error reading config: ${error.toString().trim()}, using defaults"
            }
        }
    } catch (Exception e) {
        println "Warning: Could not read config: ${e.message}, using defaults"
        // Fallback to defaults
        config_keys.eachWithIndex { key, idx ->
            if (idx < 15) {
                config_values[key] = config_defaults[idx] == "true"
            } else {
                config_values[key] = config_defaults[idx]
            }
        }
    }
    
    // Helper function for reading individual values (uses cached config_values)
    def readYamlBool = { key_path, default_bool ->
        return config_values.get(key_path, default_bool) as Boolean
    }
    
    def readYamlValue = { key_path, default_value, value_type = 'str' ->
        def value = config_values.get(key_path, default_value)
        if (value_type == 'bool') {
            return value as Boolean
        }
        return value.toString()
    }
    
    // Note: output_space priority is handled by processes themselves:
    // 1. CLI argument (--output_space) - highest priority
    // 2. YAML config file (template.output_space) - medium priority  
    // 3. Nextflow config default (NMT2Sym:res-05) - lowest priority
    // Processes use get_effective_output_space() utility function to determine the correct value.
    
    // Calculate effective output_space for display (same logic as processes)
    def default_output_space = config_defaults[15]  // "template.output_space" default
    def effective_output_space = default_output_space
    if (params.output_space != default_output_space) {
        // CLI explicitly set, use it
        effective_output_space = params.output_space
    } else {
        // Use cached value from batch read
        effective_output_space = readYamlValue("template.output_space", default_output_space, 'str')
    }
    
    // Strategy: If --anat_only is explicitly set to true, use it. Otherwise, read from config file.
    // This allows command-line to force true, while config file controls the default/false case.
    def anat_only_from_config = readYamlBool("general.anat_only", false)
    def anat_only = params.anat_only == true ? true : anat_only_from_config
    def surf_recon_enabled = readYamlBool("anat.surface_reconstruction.enabled", true)
    
    // Read all step enabled flags from cached config_values
    def anat_reorient_enabled = readYamlBool("anat.reorient.enabled", true)
    def anat_conform_enabled = readYamlBool("anat.conform.enabled", true)
    def anat_bias_correction_enabled = readYamlBool("anat.bias_correction.enabled", true)
    def anat_skullstripping_enabled = readYamlBool("anat.skullstripping_segmentation.enabled", true)
    def registration_enabled = readYamlBool("registration.enabled", true)
    
    def func_reorient_enabled = readYamlBool("func.reorient.enabled", true)
    def func_slice_timing_enabled = readYamlBool("func.slice_timing_correction.enabled", true)
    def func_motion_correction_enabled = readYamlBool("func.motion_correction.enabled", true)
    def func_despike_enabled = readYamlBool("func.despike.enabled", true)
    def func_bias_correction_enabled = readYamlBool("func.bias_correction.enabled", true)
    def func_conform_enabled = readYamlBool("func.conform.enabled", true)
    def func_skullstripping_enabled = readYamlBool("func.skullstripping.enabled", true)
    def func_coreg_runs_within_session = readYamlBool("func.coreg_runs_within_session", false)
    
    // Ensure boolean type
    anat_only = anat_only as Boolean
    
    println "Processing mode: anat_only = ${anat_only}, surface_reconstruction = ${surf_recon_enabled}"
    println "Step enabled flags:"
    println "  ANAT: reorient=${anat_reorient_enabled}, conform=${anat_conform_enabled}, bias_correction=${anat_bias_correction_enabled}, skullstripping=${anat_skullstripping_enabled}, registration=${registration_enabled}"
    if (!anat_only) {
        println "  FUNC: reorient=${func_reorient_enabled}, slice_timing=${func_slice_timing_enabled}, motion=${func_motion_correction_enabled}, despike=${func_despike_enabled}, bias_correction=${func_bias_correction_enabled}, conform=${func_conform_enabled}, skullstripping=${func_skullstripping_enabled}"
    }
    
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
    println "Output space: ${effective_output_space}"
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
    def anat_jobs_file = file("${params.output_dir}/nextflow_reports/anatomical_jobs.json")
    def func_jobs_file = file("${params.output_dir}/nextflow_reports/functional_jobs.json")
    
    // Check that discovery files exist
    if (!new File(anat_jobs_file.toString()).exists()) {
        error "Discovery file not found: ${anat_jobs_file}\n" +
              "Please run the discovery script before starting Nextflow."
    }
    if (!new File(func_jobs_file.toString()).exists()) {
        error "Discovery file not found: ${func_jobs_file}\n" +
              "Please run the discovery script before starting Nextflow."
    }
    
    // ============================================
    // PARSE DISCOVERY RESULTS INTO CHANNELS
    // ============================================
    // Parse anatomical jobs JSON into channel
    // Convert file_paths to file objects immediately to avoid passing string lists as values
    // Avoid calling .toString() on JSON-parsed strings to prevent string length limit issues
    Channel.fromPath(anat_jobs_file)
        .splitJson()
        .map { job ->
            def sub = job.subject_id.toString()
            def ses = job.session_id ? job.session_id.toString() : null
            def needs_synth = job.needs_synthesis ?: false
            def file_paths_raw = job.file_paths ?: [job.file_path]
            // Convert string paths to file objects immediately (avoids serializing string lists)
            // Pass values directly to file() without calling .toString() to avoid string length limit
            def file_paths_list = file_paths_raw instanceof List ? file_paths_raw : [file_paths_raw]
            def file_objects = file_paths_list.collect { path_val ->
                // Use string coercion instead of .toString() to avoid creating new string objects
                file(path_val as String)
            }
            def suffix = job.suffix.toString()
            def needs_t1w_reg = job.needs_t1w_registration ?: false
            
            [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg]
        }
        .set { anat_jobs_ch }
    
    // Parse functional jobs JSON into channel
    // Skip parsing entirely if anat_only is true to avoid string length limit issues
    def func_jobs_ch
    if (!anat_only) {
        // Avoid calling .toString() on JSON-parsed strings to prevent string length limit issues
        func_jobs_ch = Channel.fromPath(func_jobs_file)
            .splitJson()
            .map { job ->
                def sub = job.subject_id.toString()
                def ses = job.session_id ? job.session_id.toString() : null
                // Use string coercion instead of .toString() to avoid creating new string objects
                // This prevents Nextflow from serializing long strings during compilation
                def file_obj = file(job.file_path as String)
                // Extract path from file object (done at runtime, not during JSON parsing)
                def bids_naming_template = file_obj.toString()
                
                // Extract run_identifier from BIDS filename (all non-sub/ses entities)
                def run_identifier = channelHelpers.extractRunIdentifier(bids_naming_template)
                
                [sub, ses, run_identifier, file_obj, bids_naming_template]
            }
    } else {
        func_jobs_ch = Channel.empty()
    }
    
    // ============================================
    // ANATOMICAL PIPELINE
    // ============================================
    // Use helper closures from external file
    def getSingleFilePath = channelHelpers.getSingleFilePath
    def mapSingleFileJob = channelHelpers.mapSingleFileJob
    def isT1wFile = channelHelpers.isT1wFile
    def passThroughAnat = channelHelpers.passThroughAnat
    def passThroughFunc = channelHelpers.passThroughFunc
    def findUnmatched = channelHelpers.findUnmatched
    
    // First, extract all subjects from anat_jobs_ch for later use
    anat_jobs_ch
        .map { it[0] }  // Get subject_id (index 0)
        .unique()
        .set { anat_subjects_ch }
    
    // Use branch operator to split jobs into categories (more efficient than multiple filters)
    anat_jobs_ch.branch {
        synthesis: it[3] == true  // needs_synth is at index 3
        t1w_single: it[3] == false && it[4] == "T1w"  // suffix is at index 4
        t2w_with_t1w: it[3] == false && it[4] == "T2w" && it[5] == true  // needs_t1w_reg is at index 5
        t2w_only: it[3] == false && it[4] == "T2w" && it[5] == false
    }.set { anat_branched }
    
    // Process synthesis jobs: file objects already converted in anat_jobs_ch
    anat_branched.synthesis
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_objects = item[2]  // Already file objects from anat_jobs_ch
            
            [sub, ses, file_objects]
        }
        .set { anat_synthesis_input }
    
    // ------------------------------------------------------------
    // ANAT_SYNTHESIS
    // Run synthesis process for all anatomical modalities (T1w, T2w, etc.)
    ANAT_SYNTHESIS(anat_synthesis_input, config_file)
    
    // Process T1w single files (no synthesis needed)
    anat_branched.t1w_single
        .map(mapSingleFileJob)
        .set { anat_t1w_jobs }
    
    // T2w files that need special processing (with T1w in same session)
    // These go through a separate pipeline: REORIENT_T2W → REG_TO_T1W → BIAS_CORRECTION_T2W
    // Note: Process aliases (ANAT_REORIENT_T2W, ANAT_BIAS_CORRECTION_T2W) are required because
    // Nextflow doesn't allow reusing the same process name with different channel inputs.
    // The aliases are identical processes but allow separate channel tracking for T2w special processing.
    // Map T2w files that need special processing
    anat_branched.t2w_with_t1w
        .map(mapSingleFileJob)
        .set { anat_t2w_with_t1w_jobs }
    
    // T2w-only files (no T1w in session - process normally)
    anat_branched.t2w_only
        .map(mapSingleFileJob)
        .set { anat_t2w_only_jobs }
    
    // Combine T1w and T2w-only jobs for normal processing
    def anat_single_jobs = anat_t1w_jobs
        .mix(anat_t2w_only_jobs)
    
    // Create synthesis output channel with proper mapping
    def anat_synthesis_output = ANAT_SYNTHESIS.out.synthesized
        .map { sub, ses, anat_file, bids_naming_template_file ->
            def bids_naming_template = bids_naming_template_file.text.trim()
            [sub, ses, anat_file, bids_naming_template]
        }
    
    // Combine synthesized and single jobs for NORMAL pipeline (NOT including T2w-with-T1w)
    // T2w-with-T1w files go through a separate pipeline
    // Note: Nextflow's job counter shows items available when the process starts.
    // With .mix(), items arrive asynchronously, so the count may show partial
    // progress (e.g., "1 of 1" instead of "1 of 2") until all items are emitted.
    def anat_input_ch = anat_synthesis_output
        .mix(anat_single_jobs)
        // NOTE: T2w-with-T1w NOT included here - they have their own pipeline
    
    // ------------------------------------------------------------
    // ANAT_PROCESSING
    // Anatomical processing steps
    // - Files requiring synthesis wait for ANAT_SYNTHESIS to complete
    // - Single files (no synthesis) proceed immediately
    
    // ------------------------------------------------------------
    // ANAT_REORIENT
    def anat_after_reorient_normal = anat_input_ch
    if (anat_reorient_enabled) {
        ANAT_REORIENT(anat_input_ch, config_file)
        anat_after_reorient_normal = ANAT_REORIENT.out.output
    } else {
        // Pass through: create channel with same structure
        anat_after_reorient_normal = anat_input_ch.map(passThroughAnat)
    }
    
    // ------------------------------------------------------------
    // ANAT_CONFORM
    // only for normal processing (not T2w-with-T1w)
    def anat_after_conform = anat_after_reorient_normal
    def anat_conform_transforms = Channel.empty()
    def anat_conform_template_resampled = Channel.empty()
    if (anat_conform_enabled) {
        ANAT_CONFORM(anat_after_reorient_normal, config_file)
        anat_after_conform = ANAT_CONFORM.out.output
        anat_conform_transforms = ANAT_CONFORM.out.transforms
        anat_conform_template_resampled = ANAT_CONFORM.out.template_resampled
    } else {
        // Use pass-through process to create identity transforms and metadata
        ANAT_CONFORM_PASSTHROUGH(anat_after_reorient_normal, config_file)
        anat_after_conform = ANAT_CONFORM_PASSTHROUGH.out.output
        anat_conform_transforms = ANAT_CONFORM_PASSTHROUGH.out.transforms
        anat_conform_template_resampled = ANAT_CONFORM_PASSTHROUGH.out.template_resampled
    }
    
    // ------------------------------------------------------------
    // ANAT_BIAS_CORRECTION
    def anat_after_bias = anat_after_conform
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION(anat_after_conform, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION.out.output
    } else {
        // Use pass-through process
        ANAT_BIAS_CORRECTION_PASSTHROUGH(anat_after_conform, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION_PASSTHROUGH.out.output
    }
    
    // ------------------------------------------------------------
    // ANAT_SKULLSTRIPPING
    def anat_after_skull = anat_after_bias
    def anat_skull_mask = Channel.empty()
    def anat_skull_seg = Channel.empty()
    if (anat_skullstripping_enabled) {
        ANAT_SKULLSTRIPPING(anat_after_bias, config_file)
        anat_after_skull = ANAT_SKULLSTRIPPING.out.output
        anat_skull_mask = ANAT_SKULLSTRIPPING.out.brain_mask
        anat_skull_seg = ANAT_SKULLSTRIPPING.out.brain_segmentation
    } else {
        // Pass through: create channel with same structure (no mask/seg)
        anat_after_skull = anat_after_bias.map(passThroughAnat)
    }
    
    // ------------------------------------------------------------
    // ANAT_REGISTRATION
    def anat_after_reg = anat_after_skull
    def anat_reg_transforms = Channel.empty()
    if (registration_enabled) {
        ANAT_REGISTRATION(anat_after_skull, config_file)
        anat_after_reg = ANAT_REGISTRATION.out.output
        anat_reg_transforms = ANAT_REGISTRATION.out.transforms
    } else {
        // Use pass-through process to create identity transforms
        ANAT_REGISTRATION_PASSTHROUGH(anat_after_skull, config_file)
        anat_after_reg = ANAT_REGISTRATION_PASSTHROUGH.out.output
        anat_reg_transforms = ANAT_REGISTRATION_PASSTHROUGH.out.transforms
    }
    
    // ============================================
    // QC for anatomical pipeline
    // ============================================
    // ANAT_QC_CONFORM
    if (anat_conform_enabled) {
        anat_after_conform
            .join(anat_conform_template_resampled, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, template_resampled ->
                [sub, ses, anat_file, bids_naming_template, template_resampled]
            }
            .set { conform_qc_input }
        QC_CONFORM(conform_qc_input, config_file)
    }
    
    // QC_BIAS_CORRECTION: needs original (from CONFORM) + corrected (from BIAS_CORRECTION)
    if (anat_bias_correction_enabled) {
        anat_after_conform
            .join(anat_after_bias, by: [0, 1])
            .map { sub, ses, conformed_file, bids_naming_template1, bias_corrected_file, bids_naming_template2 ->
                // Both bids_naming_template values are the same, use the second one
                [sub, ses, conformed_file, bias_corrected_file, bids_naming_template2]
            }
            .set { bias_qc_input }
        QC_BIAS_CORRECTION(bias_qc_input, config_file)
    }
    
    // QC_SKULLSTRIPPING: needs original (non-skullstripped) file + mask file
    // Use bias-corrected output (input to skullstripping) as underlay, not the skullstripped brain
    if (anat_skullstripping_enabled) {
        anat_after_bias
            .join(anat_skull_mask, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, mask_file ->
                [sub, ses, anat_file, mask_file, bids_naming_template]
            }
            .set { skull_qc_input }
        QC_SKULLSTRIPPING(skull_qc_input, config_file)
        
        // QC_ATLAS_SEGMENTATION: needs brain file + segmentation file (optional)
        anat_after_skull
            .join(anat_skull_seg, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, seg_file ->
                [sub, ses, anat_file, seg_file, bids_naming_template]
            }
            .set { atlas_qc_input }
        QC_ATLAS_SEGMENTATION(atlas_qc_input, config_file)
    }
    
    // QC_REGISTRATION: needs registered file only (transforms not used)
    if (registration_enabled) {
        // Use ANAT_REGISTRATION output directly - it's already a 3-element tuple
        // tuple val(subject_id), val(session_id), path("*.nii.gz")
        QC_REGISTRATION(ANAT_REGISTRATION.out.output, config_file)
    }    
    
    // ============================================
    // SURFACE RECONSTRUCTION
    // ============================================
    // Skip if skullstripping is disabled (no mask/segmentation available)
    def surf_recon_input = Channel.empty()
    def surf_qc_input = Channel.empty()
    if (surf_recon_enabled && anat_skullstripping_enabled) {
        // Join non-skullstripped T1w (from bias correction) with segmentation and brain mask
        def surf_recon_input_base = anat_after_bias
            .join(anat_skull_seg, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, seg_file ->
                [sub, ses, anat_file, bids_naming_template, seg_file]
            }
        
        // Join with brain mask
        surf_recon_input = surf_recon_input_base
            .join(anat_skull_mask, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, seg_file, mask_file ->
                [sub, ses, anat_file, bids_naming_template, seg_file, mask_file ?: file("")]
            }
        
        ANAT_SURFACE_RECONSTRUCTION(surf_recon_input, config_file)
        
        // Surface reconstruction QC: needs subject_dir, bids_naming_template, and atlas_name from metadata
        // Join surface reconstruction outputs (subject_dir and metadata) with input to get bids_naming_template
        surf_qc_input = ANAT_SURFACE_RECONSTRUCTION.out.subject_dir
            .join(ANAT_SURFACE_RECONSTRUCTION.out.metadata, by: [0, 1])
            .join(surf_recon_input, by: [0, 1])
            .map { sub, ses, subject_dir, metadata_file, anat_file, bids_naming_template, seg_file, mask_file ->
                // Read atlas_name from metadata.json
                def atlas_name = "ARM2"  // default
                try {
                    def metadata = new groovy.json.JsonSlurper().parse(metadata_file)
                    atlas_name = metadata.atlas_name ?: "ARM2"
                } catch (Exception e) {
                    println "Warning: Could not read atlas_name from metadata, using default: ${e.message}"
                }
                [sub, ses, subject_dir, bids_naming_template, atlas_name]
            }
        
        // QC_SURF_RECON_TISSUE_SEG: needs subject_dir and bids_naming_template
        def surf_tissue_seg_qc_input = surf_qc_input
            .map { sub, ses, subject_dir, bids_naming_template, atlas_name ->
                [sub, ses, subject_dir, bids_naming_template]
            }
        QC_SURF_RECON_TISSUE_SEG(surf_tissue_seg_qc_input, config_file)
        
        // QC_CORTICAL_SURF_AND_MEASURES: needs subject_dir, bids_naming_template, and atlas_name
        QC_CORTICAL_SURF_AND_MEASURES(surf_qc_input, config_file)
    } else {
        if (surf_recon_enabled && !anat_skullstripping_enabled) {
            println "Warning: Surface reconstruction is enabled but skullstripping is disabled. Skipping surface reconstruction."
        }
    }
    
    // ============================================
    // T2W SPECIAL PROCESSING (with T1w in same session)
    // ============================================
    // Process T2w files that have T1w in the same session
    // Workflow: REORIENT → REGISTER_TO_T1W → BIAS_CORRECTION
    // Skip: CONFORM, SKULLSTRIPPING, template REGISTRATION
    // These files use separate process aliases (ANAT_REORIENT_T2W, ANAT_BIAS_CORRECTION_T2W)
    
    // Step 1: REORIENT T2w files (using aliased process)
    def t2w_after_reorient = anat_t2w_with_t1w_jobs
    if (anat_reorient_enabled) {
        ANAT_REORIENT_T2W(anat_t2w_with_t1w_jobs, config_file)
        t2w_after_reorient = ANAT_REORIENT_T2W.out.output
    } else {
        // Pass through: create channel with same structure
        t2w_after_reorient = anat_t2w_with_t1w_jobs.map(passThroughAnat)
    }
    
    // Step 2: Get T1w bias-corrected output to use as reference
    // Filter T1w files from the main pipeline
    def t1w_bias_corrected = anat_after_bias
        .filter(isT1wFile)
    
    // Step 3: Join reoriented T2w with T1w bias-corrected output and split channels
    // t2w_after_reorient: [sub, ses, t2w_file, t2w_bids_template] (4 elements)
    // t1w_bias_corrected: [sub, ses, t1w_file, t1w_bids_template] (4 elements)
    // Join by [0, 1] produces: [sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template] (6 elements)
    // If there are multiple T1w files, join creates cartesian product - take first match
    def t2w_t1w_joined = t2w_after_reorient
        .join(t1w_bias_corrected, by: [0, 1])  // Join by subject and session
        .map { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            // Ensure we have exactly 6 elements
            [sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template]
        }
    
    // Split into separate channels using multiMap
    t2w_t1w_joined
        .multiMap { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            combined: [sub, ses, t2w_file, t2w_bids_template]
            reference: t1w_file
        }
        .set { t2w_reg_multi }
    
    // Step 4: Run T2w→T1w registration
    ANAT_T2W_TO_T1W_REGISTRATION(t2w_reg_multi.combined, t2w_reg_multi.reference, config_file)
    def t2w_after_reg_to_t1w = ANAT_T2W_TO_T1W_REGISTRATION.out.output
    
    // Step 5: BIAS_CORRECTION for registered T2w (using aliased process)
    def t2w_after_bias_final = t2w_after_reg_to_t1w
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION_T2W(t2w_after_reg_to_t1w, config_file)
        t2w_after_bias_final = ANAT_BIAS_CORRECTION_T2W.out.output
    } else {
        t2w_after_bias_final = t2w_after_reg_to_t1w.map(passThroughAnat)
    }
    
    // QC for T2w→T1w registration
    // Join bias-corrected T2w output with skull-stripped T1w brain reference (for overlaid contour)
    // Process expects: combined [sub, ses, registered_t2w_file, t1w_reference_file], bids_naming_template, config_file
    def t1w_skullstripped = anat_after_skull
        .filter(isT1wFile)
    
    // Join and split channels using multiMap
    t2w_after_bias_final
        .join(t1w_skullstripped, by: [0, 1])
        .multiMap { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            combined: [sub, ses, t2w_file, t1w_file]
            bids_template: t2w_bids_template
        }
        .set { t2w_qc_channels }
    
    // QC_T2W_TO_T1W_REGISTRATION
    QC_T2W_TO_T1W_REGISTRATION(t2w_qc_channels.combined, t2w_qc_channels.bids_template, config_file)

    // ============================================
    // FUNCTIONAL PIPELINE
    // ============================================
    def func_coreg_success = false  // for QC report generation
    
    if (!anat_only) {

        // ------------------------------------------------------------
        // SLICE_TIMING
        def func_after_slice = func_jobs_ch
        if (func_slice_timing_enabled) {
            FUNC_SLICE_TIMING(func_jobs_ch, config_file)
            func_after_slice = FUNC_SLICE_TIMING.out.output
        } else {
            func_after_slice = func_jobs_ch.map(passThroughFunc)
        }

        // ------------------------------------------------------------
        // REORIENT
        def func_after_reorient = func_after_slice
        if (func_reorient_enabled) {
            FUNC_REORIENT(func_after_slice, config_file)
            func_after_reorient = FUNC_REORIENT.out.output
        } else {
            func_after_reorient = func_after_slice.map(passThroughFunc)
        }
        
        // ------------------------------------------------------------
        // MOTION_CORRECTION
        def func_after_motion = func_after_reorient
        def func_motion_params = Channel.empty()
        if (func_motion_correction_enabled) {
            FUNC_MOTION_CORRECTION(func_after_reorient, config_file)
            func_after_motion = FUNC_MOTION_CORRECTION.out.output  // Combined channel: [sub, ses, run_identifier, bold, tmean, bids_template]
            func_motion_params = FUNC_MOTION_CORRECTION.out.motion_params
        } else {
            // Generate tmean file from BOLD (motion correction disabled, but we still need tmean)
            FUNC_GENERATE_TMEAN(func_after_reorient, config_file)
            func_after_motion = FUNC_GENERATE_TMEAN.out.output  // Combined channel: [sub, ses, run_identifier, bold, tmean, bids_template]
        }
        
        // ------------------------------------------------------------
        // DESPIKE
        def func_after_despike = func_after_motion
        if (func_despike_enabled) {
            FUNC_DESPIKE(func_after_motion, config_file)
            func_after_despike = FUNC_DESPIKE.out.output  // Combined channel: [sub, ses, run_identifier, bold, tmean, bids_template]
        } else {
            func_after_despike = func_after_motion
        }
        
        // ------------------------------------------------------------
        // BIAS_CORRECTION
        // operates on tmean, inherits BOLD
        def func_after_bias = func_after_despike
        if (func_bias_correction_enabled) {
            FUNC_BIAS_CORRECTION(func_after_despike, config_file)
            func_after_bias = FUNC_BIAS_CORRECTION.out.output  // Combined channel: [sub, ses, run_identifier, bold, tmean, bids_template]
        } else {
            func_after_bias = func_after_despike
        }
        
        // ------------------------------------------------------------
        // WITHIN-SESSION COREGISTRATION (if enabled)
        // ------------------------------------------------------------
        def func_after_coreg = func_after_bias
        def func_coreg_transforms_ch = Channel.empty()
        def func_tmean_averaged_ch = Channel.empty()
        
        if (func_coreg_runs_within_session) {
            // Prepare channels using external function
            def coregChannels = funcChannels.prepareWithinSessionCoregChannels(func_after_bias, Channel)
            
            // multiMap must be done in workflow context
            coregChannels.func_later_runs
                .multiMap { sub, ses, run_identifier, bold, tmean, bids, ref_tmean, ref_run_identifier ->
                    combined: [sub, ses, run_identifier, bold, tmean, bids]
                    reference: ref_tmean
                    ref_run_identifier_val: ref_run_identifier
                }
                .set { func_coreg_multi }
            
            // Call processes in workflow context
            FUNC_WITHIN_SES_COREG(func_coreg_multi.combined, func_coreg_multi.reference, func_coreg_multi.ref_run_identifier_val, config_file)
            func_coreg_transforms_ch = FUNC_WITHIN_SES_COREG.out.transforms
            
            // Combine: first runs (unchanged) + coregistered later runs + single run sessions
            def func_all_coreg = coregChannels.func_first_runs
                .mix(FUNC_WITHIN_SES_COREG.out.output)
                .mix(coregChannels.func_single_run_ses)
            
            // func_all_coreg structure: [sub, ses, run_identifier, bold, tmean, bids_template]
            // Group by [sub, ses] to get all runs in each session for averaging
            def func_for_averaging_ch = func_all_coreg
                .groupTuple(by: [0, 1])  // Group by [sub, ses]
                .map { sub, ses, run_identifier_list, bold_list, tmean_list, bids_list ->
                    // Extract tmean files and convert to paths (strings) to avoid staging name collisions
                    // Also get bids_template (use first one, they should be similar within a session)
                    def tmean_paths = tmean_list.collect { file -> file.toString() }
                    // Serialize list as JSON for reliable parsing in Python
                    def tmean_paths_json = groovy.json.JsonOutput.toJson(tmean_paths)
                    def bids_template = bids_list[0]
                    [sub, ses, tmean_paths_json, bids_template]
                }
            
            // multiMap must be done in workflow context
            func_for_averaging_ch
                .multiMap { sub, ses, tmean_paths, bids_template ->
                    tmean_files_input: tmean_paths  // List of file paths as strings
                    subject_id_input: sub
                    session_id_input: ses
                    bids_template_input: bids_template
                }
                .set { averagingChannels }
            
            // Average tmean - pass file paths directly (no intermediate file list needed)
            FUNC_AVERAGE_TMEAN(
                averagingChannels.tmean_files_input,
                averagingChannels.subject_id_input,
                averagingChannels.session_id_input,
                averagingChannels.bids_template_input,
                config_file
            )
            
            func_tmean_averaged_ch = FUNC_AVERAGE_TMEAN.out.output
            func_after_coreg = func_all_coreg
            func_coreg_success = true
            
            // QC for within-session coregistration
            def func_coreg_qc_input = funcChannels.prepareCoregQCChannels(coregChannels.func_first_runs, func_tmean_averaged_ch)
            QC_WITHIN_SES_COREG(func_coreg_qc_input, config_file)
        }
        
        // ------------------------------------------------------------
        // ANATOMICAL SELECTION
        // Create dummy anatomical file for cases with no anatomical data
        def dummy_anat = file("${workDir}/dummy_anat.dummy")
        
        // Use function from external file to perform anatomical selection
        def func_anat_selection = funcChannels.performAnatomicalSelection(
            func_after_coreg,
            anat_after_skull,
            isT1wFile,
            findUnmatched,
            dummy_anat
        )

        // ------------------------------------------------------------
        // COMPUTE PHASE: CONFORM / SKULLSTRIPPING / REGISTRATION
        // Compute transforms and masks on tmean (session-level or per-run)
        // ------------------------------------------------------------
        def func_compute_conform_output = Channel.empty()
        def func_compute_mask_output = Channel.empty()
        def func_compute_reg_output = Channel.empty()
        
        if (func_coreg_runs_within_session && func_coreg_success) {
            // ============================================
            // SESSION-LEVEL COMPUTE PHASE (when coreg enabled)
            // ============================================
            // Use averaged tmean for session-level processing
            // Prepare input: [sub, ses, "", dummy_bold, tmean_averaged, bids_template]
            
            def func_compute_input = func_tmean_averaged_ch
                .map { sub, ses, tmean, bids ->
                    def dummy_bold = file("${workDir}/dummy_bold_${sub}_${ses}.dummy")
                    [sub, ses, "", dummy_bold, tmean, bids]  // Empty string for run_identifier
                }
            
            // COMPUTE_CONFORM
            if (func_conform_enabled) {
                // Get anatomical file for conforming
                def anat_for_conform = anat_after_skull
                    .filter(isT1wFile)
                    .map { sub, ses, anat_file, bids_template -> [sub, ses, anat_file] }
                    .unique { sub, ses, anat_file -> [sub, ses] }
                
                def dummy_anat_conform = file("${workDir}/dummy_anat_conform.dummy")
                def dummy_anat_ch = func_compute_input
                    .map { sub, ses, run_id, bold, tmean, bids -> [sub, ses, dummy_anat_conform] }
                
                def anat_for_conform_with_fallback = anat_for_conform
                    .mix(dummy_anat_ch)
                    .groupTuple(by: [0, 1])
                    .map { sub, ses, anat_files ->
                        def real_anat = anat_files.find { f -> !f.toString().contains('.dummy') }
                        [sub, ses, real_anat ?: dummy_anat_conform]
                    }
                
                def func_compute_conform_input = func_compute_input
                    .join(anat_for_conform_with_fallback, by: [0, 1])
                    .map { sub, ses, run_id, bold, tmean, bids, anat_file ->
                        [sub, ses, run_id, bold, tmean, bids, anat_file]
                    }
                
                func_compute_conform_input
                    .multiMap { sub, ses, run_id, bold, tmean, bids, anat_file ->
                        combined: [sub, ses, run_id, bold, tmean, bids]
                        reference: anat_file
                    }
                    .set { func_compute_conform_multi }
                
                FUNC_COMPUTE_CONFORM(func_compute_conform_multi.combined, func_compute_conform_multi.reference, config_file)
                // Output: [sub, ses, run_id, conformed_tmean, bids, conform_transform]
                func_compute_conform_output = FUNC_COMPUTE_CONFORM.out.output
            } else {
                // No conform - pass through with empty transform
                func_compute_conform_output = func_compute_input
                    .map { sub, ses, run_id, bold, tmean, bids ->
                        def dummy_transform = file("${workDir}/dummy_conform_transform.dummy")
                        [sub, ses, run_id, tmean, bids, dummy_transform]
                    }
            }
            
            // COMPUTE_BRAIN_MASK
            if (func_skullstripping_enabled) {
                // Input: [sub, ses, run_id, conformed_tmean, bids] (extract from compute_conform output)
                def func_compute_mask_input = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids, transform ->
                        [sub, ses, run_id, conformed_tmean, bids]
                    }
                
                FUNC_COMPUTE_BRAIN_MASK(func_compute_mask_input, config_file)
                // Output: [sub, ses, run_id, masked_tmean, bids, brain_mask]
                func_compute_mask_output = FUNC_COMPUTE_BRAIN_MASK.out.output
            } else {
                // No mask - pass through conformed tmean with empty mask
                func_compute_mask_output = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids, transform ->
                        def dummy_mask = file("${workDir}/dummy_brain_mask.dummy")
                        [sub, ses, run_id, conformed_tmean, bids, dummy_mask]
                    }
            }
            
            // COMPUTE_REGISTRATION
            if (registration_enabled) {
                // Input: [sub, ses, run_id, masked_tmean, bids] + anatomical selection
                def func_compute_reg_input = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        [sub, ses, run_id, masked_tmean, bids]
                    }
                    .join(func_anat_selection, by: [0, 1])  // Join by [sub, ses] (run_id is "" for session-level)
                    .map { sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses]
                    }
                
                func_compute_reg_input
                    .multiMap { sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses ->
                        combined: [sub, ses, run_id, masked_tmean, bids, anat_ses, is_cross_ses]
                        reference: anat_file
                    }
                    .set { func_compute_reg_multi }
                
                FUNC_COMPUTE_REGISTRATION(func_compute_reg_multi.combined, func_compute_reg_multi.reference, config_file)
                // Output: [sub, ses, run_id, registered_tmean, bids, reg_transform, anat_ses, is_cross_ses]
                func_compute_reg_output = FUNC_COMPUTE_REGISTRATION.out.output
            } else {
                // No registration - pass through masked tmean with empty transform
                func_compute_reg_output = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        def dummy_transform = file("${workDir}/dummy_reg_transform.dummy")
                        [sub, ses, run_id, masked_tmean, bids, dummy_transform, "", false]
                    }
            }
            
        } else {
            // ============================================
            // PER-RUN COMPUTE PHASE (normal workflow)
            // ============================================
            // Input: [sub, ses, run_identifier, bold_file, tmean_file, bids_template] from func_after_coreg
            def func_compute_input = func_after_coreg
            
            // COMPUTE_CONFORM
            if (func_conform_enabled) {
                def func_conform_with_anat = func_compute_input
                    .join(func_anat_selection, by: [0, 1, 2])  // Join by [sub, ses, run_identifier]
                    .map { sub, ses, run_id, bold, tmean, bids, anat_file, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, bold, tmean, bids, anat_file]
                    }
                
                func_conform_with_anat
                    .multiMap { sub, ses, run_id, bold, tmean, bids, anat_file ->
                        combined: [sub, ses, run_id, bold, tmean, bids]
                        reference: anat_file
                    }
                    .set { func_compute_conform_multi }
                
                FUNC_COMPUTE_CONFORM(func_compute_conform_multi.combined, func_compute_conform_multi.reference, config_file)
                // Output: [sub, ses, run_id, conformed_tmean, bids, conform_transform]
                func_compute_conform_output = FUNC_COMPUTE_CONFORM.out.output
            } else {
                // No conform - pass through with empty transform
                func_compute_conform_output = func_compute_input
                    .map { sub, ses, run_id, bold, tmean, bids ->
                        def dummy_transform = file("${workDir}/dummy_conform_transform.dummy")
                        [sub, ses, run_id, tmean, bids, dummy_transform]
                    }
            }
            
            // COMPUTE_BRAIN_MASK
            if (func_skullstripping_enabled) {
                def func_compute_mask_input = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids, transform ->
                        [sub, ses, run_id, conformed_tmean, bids]
                    }
                
                FUNC_COMPUTE_BRAIN_MASK(func_compute_mask_input, config_file)
                // Output: [sub, ses, run_id, masked_tmean, bids, brain_mask]
                func_compute_mask_output = FUNC_COMPUTE_BRAIN_MASK.out.output
            } else {
                // No mask - pass through conformed tmean with empty mask
                func_compute_mask_output = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids, transform ->
                        def dummy_mask = file("${workDir}/dummy_brain_mask.dummy")
                        [sub, ses, run_id, conformed_tmean, bids, dummy_mask]
                    }
            }
            
            // COMPUTE_REGISTRATION
            if (registration_enabled) {
                def func_compute_reg_input = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        [sub, ses, run_id, masked_tmean, bids]
                    }
                    .join(func_anat_selection, by: [0, 1, 2])  // Join by [sub, ses, run_identifier]
                    .map { sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses]
                    }
                
                func_compute_reg_input
                    .multiMap { sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses ->
                        combined: [sub, ses, run_id, masked_tmean, bids, anat_ses, is_cross_ses]
                        reference: anat_file
                    }
                    .set { func_compute_reg_multi }
                
                FUNC_COMPUTE_REGISTRATION(func_compute_reg_multi.combined, func_compute_reg_multi.reference, config_file)
                // Output: [sub, ses, run_id, registered_tmean, bids, reg_transform, anat_ses, is_cross_ses]
                func_compute_reg_output = FUNC_COMPUTE_REGISTRATION.out.output
            } else {
                // No registration - pass through masked tmean with empty transform
                func_compute_reg_output = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        def dummy_transform = file("${workDir}/dummy_reg_transform.dummy")
                        [sub, ses, run_id, masked_tmean, bids, dummy_transform, "", false]
                    }
            }
        }
        
        // ------------------------------------------------------------
        // APPLY PHASE: Apply transforms and masks to BOLD files
        // ------------------------------------------------------------
        // Start with BOLD files from func_after_coreg (or func_after_bias if no coreg)
        def func_apply_bold_input = func_coreg_runs_within_session && func_coreg_success ? func_after_coreg : func_after_coreg
        
        // APPLY_CONFORM
        def func_apply_conform_output = Channel.empty()
        if (func_conform_enabled) {
            // Join BOLD files with conform transform and conformed tmean reference
            def func_apply_conform_input
            if (func_coreg_runs_within_session && func_coreg_success) {
                // Session-level: join by [sub, ses] (run_id is "" for session-level compute)
                func_apply_conform_input = func_apply_bold_input
                    .join(
                        func_compute_conform_output
                            .filter { sub, ses, run_id, conformed_tmean, bids, transform ->
                                run_id == ""  // Session-level
                            }
                            .map { sub, ses, run_id, conformed_tmean, bids, transform ->
                                [sub, ses, transform, conformed_tmean]
                            },
                        by: [0, 1]  // Join by [sub, ses]
                    )
                    .map { sub, ses, run_id, bold, tmean, bids, transform, conformed_tmean ->
                        [sub, ses, run_id, bold, transform, conformed_tmean, bids]
                    }
            } else {
                // Per-run: join by [sub, ses, run_identifier]
                func_apply_conform_input = func_apply_bold_input
                    .join(
                        func_compute_conform_output
                            .map { sub, ses, run_id, conformed_tmean, bids, transform ->
                                [sub, ses, run_id, transform, conformed_tmean]
                            },
                        by: [0, 1, 2]  // Join by [sub, ses, run_identifier]
                    )
                    .map { sub, ses, run_id, bold, tmean, bids, transform, conformed_tmean ->
                        [sub, ses, run_id, bold, transform, conformed_tmean, bids]
                    }
            }
            
            FUNC_APPLY_CONFORM(func_apply_conform_input, config_file)
            // Output: [sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids]
            func_apply_conform_output = FUNC_APPLY_CONFORM.out.output
        } else {
            // No conform - pass through BOLD files
            func_apply_conform_output = func_apply_bold_input
                .map { sub, ses, run_id, bold, tmean, bids ->
                    def dummy_tmean_ref = file("${workDir}/dummy_tmean_ref.dummy")
                    [sub, ses, run_id, bold, dummy_tmean_ref, bids]
                }
        }
        
        // APPLY_BRAIN_MASK
        def func_apply_mask_output = Channel.empty()
        if (func_skullstripping_enabled) {
            // Join conformed BOLD with brain mask and masked tmean reference
            def func_apply_mask_input
            if (func_coreg_runs_within_session && func_coreg_success) {
                // Session-level: join by [sub, ses]
                func_apply_mask_input = func_apply_conform_output
                    .join(
                        func_compute_mask_output
                            .filter { sub, ses, run_id, masked_tmean, bids, mask ->
                                run_id == ""  // Session-level
                            }
                            .map { sub, ses, run_id, masked_tmean, bids, mask ->
                                [sub, ses, mask, masked_tmean]
                            },
                        by: [0, 1]
                    )
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean, bids, mask, masked_tmean ->
                        [sub, ses, run_id, conformed_bold, mask, masked_tmean, bids]
                    }
            } else {
                // Per-run: join by [sub, ses, run_identifier]
                func_apply_mask_input = func_apply_conform_output
                    .join(
                        func_compute_mask_output
                            .map { sub, ses, run_id, masked_tmean, bids, mask ->
                                [sub, ses, run_id, mask, masked_tmean]
                            },
                        by: [0, 1, 2]
                    )
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean, bids, mask, masked_tmean ->
                        [sub, ses, run_id, conformed_bold, mask, masked_tmean, bids]
                    }
            }
            
            FUNC_APPLY_BRAIN_MASK(func_apply_mask_input, config_file)
            // Output: [sub, ses, run_id, masked_bold, masked_tmean_ref, bids]
            func_apply_mask_output = FUNC_APPLY_BRAIN_MASK.out.output
        } else {
            // No mask - pass through conformed BOLD
            func_apply_mask_output = func_apply_conform_output
        }
        
        // APPLY_REGISTRATION (using existing FUNC_APPLY_TRANSFORMS)
        def func_apply_reg = func_apply_mask_output
        def func_apply_reg_reference = Channel.empty()
        if (registration_enabled) {
            // Join masked BOLD with registration transform, registered tmean reference, and anat2template transform
            // func_compute_reg_output: [sub, ses, run_id, registered_tmean, bids, reg_transform, anat_ses, is_cross_ses]
            // FUNC_COMPUTE_REGISTRATION.out.reference: [sub, ses, run_id, registered_tmean, bids, target_final]
            def dummy_anat2template = file("${workDir}/dummy_anat2template.dummy")
            
            def func_apply_reg_input
            if (func_coreg_runs_within_session && func_coreg_success) {
                // Session-level: join by [sub, ses]
                // First join compute_reg_output with reference to get target_final
                def func_compute_reg_with_ref = func_compute_reg_output
                    .join(FUNC_COMPUTE_REGISTRATION.out.reference, by: [0, 1, 2])
                    .map { sub, ses, run_id, registered_tmean, bids, reg_transform, anat_ses, is_cross_ses, registered_tmean2, bids2, target_final ->
                        [sub, ses, registered_tmean, reg_transform, target_final, anat_ses, is_cross_ses]
                    }
                
                // Then join with anat_reg_transforms to get anat2template transform
                func_apply_reg_input = func_apply_mask_output
                    .join(
                        func_compute_reg_with_ref
                            .join(
                                anat_reg_transforms.map { sub, ses, transform -> [sub, ses, transform] },
                                by: [0, 1]
                            )
                            .map { sub, ses, registered_tmean, reg_transform, target_final, anat_ses, is_cross_ses, anat2template_transform ->
                                [sub, ses, registered_tmean, reg_transform, anat2template_transform, target_final, anat_ses, is_cross_ses]
                            },
                        by: [0, 1]
                    )
                    .map { sub, ses, run_id, masked_bold, masked_tmean, bids, registered_tmean, reg_transform, anat2template_transform, target_final, anat_ses, is_cross_ses ->
                        // Determine target_type and target2template
                        def target_type = 'anat'  // Always anat for func2anat2template
                        def target2template = true
                        [sub, ses, run_id, masked_bold, registered_tmean, reg_transform, anat2template_transform, bids, target_type, target2template, target_final]
                    }
            } else {
                // Per-run: join by [sub, ses, run_identifier]
                def func_compute_reg_with_ref = func_compute_reg_output
                    .join(FUNC_COMPUTE_REGISTRATION.out.reference, by: [0, 1, 2])
                    .map { sub, ses, run_id, registered_tmean, bids, reg_transform, anat_ses, is_cross_ses, registered_tmean2, bids2, target_final ->
                        [sub, ses, run_id, registered_tmean, reg_transform, target_final, anat_ses, is_cross_ses]
                    }
                
                func_apply_reg_input = func_apply_mask_output
                    .join(
                        func_compute_reg_with_ref
                            .join(
                                anat_reg_transforms.map { sub, ses, transform -> [sub, ses, transform] },
                                by: [0, 1]
                            )
                            .map { sub, ses, run_id, registered_tmean, reg_transform, target_final, anat_ses, is_cross_ses, anat2template_transform ->
                                [sub, ses, run_id, registered_tmean, reg_transform, anat2template_transform, target_final, anat_ses, is_cross_ses]
                            },
                        by: [0, 1, 2]
                    )
                    .map { sub, ses, run_id, masked_bold, masked_tmean, bids, registered_tmean, reg_transform, anat2template_transform, target_final, anat_ses, is_cross_ses ->
                        def target_type = 'anat'
                        def target2template = true
                        [sub, ses, run_id, masked_bold, registered_tmean, reg_transform, anat2template_transform, bids, target_type, target2template, target_final]
                    }
            }
            
            func_apply_reg_input
                .multiMap { sub, ses, run_id, masked_bold, registered_tmean, reg_transform, anat2template_transform, bids, target_type, target2template, ref ->
                    reg_combined: [sub, ses, run_id, registered_tmean, reg_transform, anat2template_transform, bids, target_type, target2template, ref]
                    func_4d_file: masked_bold
                }
                .set { func_apply_reg_multi }
            
            FUNC_APPLY_TRANSFORMS(func_apply_reg_multi.reg_combined, func_apply_reg_multi.func_4d_file, config_file)
            func_apply_reg = FUNC_APPLY_TRANSFORMS.out.output
            func_apply_reg_reference = FUNC_APPLY_TRANSFORMS.out.reference
        }

        // ============================================
        // QC for functional - individual steps
        // ============================================
        // FUNC_QC_MOTION_CORRECTION
        if (func_motion_correction_enabled) {
            func_after_motion
                .join(func_motion_params, by: [0, 1, 2])
                .map { sub, ses, run_identifier, bold_file, tmean_file, bids_template, motion_file ->
                    // Extract tmean for QC (before motion correction)
                    [sub, ses, run_identifier, motion_file, tmean_file, bids_template]
                }
                .set { motion_qc_input }
            QC_MOTION_CORRECTION(motion_qc_input, config_file)
        }
        
        // // QC_BIAS_CORRECTION_FUNC: needs original (from DESPIKE) + corrected (from BIAS_CORRECTION)
        // if (func_bias_correction_enabled) {
        //     func_after_despike
        //         .join(func_after_bias, by: [0, 1, 2, 3])
        //         .map { sub, ses, task, run, bold1, tmean1, bids1, bold2, tmean2, bids2 ->
        //             // Extract tmean files for QC (before and after bias correction)
        //             [sub, ses, task, run, tmean1, tmean2, bids2]
        //         }
        //         .set { func_bias_qc_input }
        //     QC_BIAS_CORRECTION_FUNC(func_bias_qc_input, config_file)
        // }
        
        // QC_CONFORM_FUNC: needs original (bias-corrected) tmean vs conformed tmean from apply step
        // Compare before (bias-corrected) vs after (conformed from FUNC_APPLY_CONFORM)
        // Note: Even for session-level, conform is applied per-run, so we compare per-run
        if (func_conform_enabled) {
            // Join apply output with bias-corrected tmean by [sub, ses, run_identifier]
            def func_conform_qc_input = FUNC_APPLY_CONFORM.out.output
                .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids ->
                    [sub, ses, run_id, conformed_tmean_ref, bids]
                }
                .join(
                    func_after_bias
                        .map { sub, ses, run_id, bold, tmean, bids ->
                            [sub, ses, run_id, tmean]
                        },
                    by: [0, 1, 2]
                )
                .map { sub, ses, run_id, conformed_tmean_ref, bids, original_tmean ->
                    [sub, ses, run_id, original_tmean, conformed_tmean_ref, bids]
                }
            QC_CONFORM_FUNC(func_conform_qc_input, config_file)
        }
        
        // QC_SKULLSTRIPPING_FUNC: needs pre-skull-stripping tmean (conformed) + brain mask
        // Use conformed tmean from FUNC_APPLY_CONFORM (before skull stripping) + mask from FUNC_COMPUTE_BRAIN_MASK
        if (func_skullstripping_enabled) {
            // Join conformed tmean (before skull stripping) with brain mask by [sub, ses, run_identifier]
            // Note: Even for session-level, skull stripping is applied per-run, so we compare per-run
            def func_skull_qc_input = func_apply_conform_output
                .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids ->
                    [sub, ses, run_id, conformed_tmean_ref, bids]  // Extract conformed_tmean_ref (before skull stripping)
                }
                .join(
                    FUNC_COMPUTE_BRAIN_MASK.out.output
                        .map { sub, ses, run_id, masked_tmean, bids, brain_mask ->
                            [sub, ses, run_id, brain_mask]  // Extract brain_mask
                        },
                    by: [0, 1, 2]
                )
                .map { sub, ses, run_id, conformed_tmean_ref, bids, brain_mask ->
                    [sub, ses, run_id, conformed_tmean_ref, brain_mask, bids]
                }
            QC_SKULLSTRIPPING_FUNC(func_skull_qc_input, config_file)
        }

        // QC_REGISTRATION_FUNC: needs registered file
        if (registration_enabled) {
            // Extract registered boldref (tmean) from combined channel
            // func_apply_reg: [sub, ses, run_identifier, bold_file, boldref_file, bids_template] (6 elements)
            // func_apply_reg_reference: [sub, ses, run_identifier, reference_file] (4 elements)
            // Join produces: [sub, ses, run_identifier, bold_file, boldref_file, bids_template, reference_file] (7 elements)
            // Process expects: [sub, ses, run_identifier, registered_file, reference_file] (5 elements)
            func_apply_reg
                .join(func_apply_reg_reference, by: [0, 1, 2])
                .map { sub, ses, run_identifier, bold_file, registered_boldref, bids_template, reference_file ->
                    // Use boldref_file (index 4) as the registered_file for QC
                    [sub, ses, run_identifier, registered_boldref, reference_file]
                }
                .set { func_reg_qc_input }
            QC_REGISTRATION_FUNC(func_reg_qc_input, config_file)
        }      
    }  

    // ============================================
    // QC REPORT GENERATION (per subject)
    // ============================================
    // Ensure all QC processes complete before report generation    
    // Create completion signal - wait for all QC processes to complete
    def anat_qc_channels = Channel.empty()
    if (registration_enabled) {
        anat_qc_channels = anat_qc_channels.mix(QC_REGISTRATION.out.metadata)
    }
    if (surf_recon_enabled && anat_skullstripping_enabled) {
        anat_qc_channels = anat_qc_channels.mix(QC_SURF_RECON_TISSUE_SEG.out.metadata)
        anat_qc_channels = anat_qc_channels.mix(QC_CORTICAL_SURF_AND_MEASURES.out.metadata)
    }
    if (anat_conform_enabled) {
        anat_qc_channels = anat_qc_channels.mix(QC_CONFORM.out.metadata)
    }
    if (anat_bias_correction_enabled) {
        anat_qc_channels = anat_qc_channels.mix(QC_BIAS_CORRECTION.out.metadata)
    }
    if (anat_skullstripping_enabled) {
        anat_qc_channels = anat_qc_channels.mix(QC_SKULLSTRIPPING.out.metadata)
        anat_qc_channels = anat_qc_channels.mix(QC_ATLAS_SEGMENTATION.out.metadata)
    }
    // Add T2w→T1w registration QC (always enabled if T2w files with T1w exist)
    anat_qc_channels = anat_qc_channels.mix(QC_T2W_TO_T1W_REGISTRATION.out.metadata)
    
    // Wait for the last QC process to complete (ensures all finish)
    def anat_qc_completion = anat_qc_channels
        .last()  // Wait for last anatomical QC to complete
    
    // Create completion signal - wait for anatomical, and functional if applicable
    def qc_completion_signal = anat_qc_completion
    if (!anat_only) {
        def func_qc_channels = Channel.empty()
        if (func_motion_correction_enabled) {
            func_qc_channels = func_qc_channels.mix(QC_MOTION_CORRECTION.out.metadata)
        }
        // Add QC_CONFORM_FUNC metadata if it was actually called (either per-run or session-level path)
        if (func_conform_enabled) {
            func_qc_channels = func_qc_channels.mix(QC_CONFORM_FUNC.out.metadata)
        }
        if (func_skullstripping_enabled) {
            func_qc_channels = func_qc_channels.mix(QC_SKULLSTRIPPING_FUNC.out.metadata)
        }
        if (func_coreg_runs_within_session) {
            func_qc_channels = func_qc_channels.mix(QC_WITHIN_SES_COREG.out.metadata)
        }
        if (registration_enabled) {
            func_qc_channels = func_qc_channels.mix(QC_REGISTRATION_FUNC.out.metadata)
        }
        
        def func_qc_completion = func_qc_channels
            .last()  // Wait for last functional QC to complete
        
        // Combine both signals - ensures both anatomical and functional QC complete
        qc_completion_signal = anat_qc_completion
            .combine(func_qc_completion)
            .map { anat_meta, func_meta -> true }  // Simple completion signal
    }
    
    // Get unique subjects from the extracted subjects channel
    def all_subjects = anat_subjects_ch
    if (!anat_only) {
        all_subjects = all_subjects.mix(func_jobs_ch.map { sub, ses, run_identifier, file_path, bids_naming_template -> sub }.unique())
    }
    
    // Create snapshot directory path for each subject
    // Combine with QC completion signal to ensure all QC processes finish first
    // QC_GENERATE_REPORT expects: tuple (subject_id, snapshot_dir, config_file)
    def qc_report_input = all_subjects
        .unique()  // Ensure unique subjects before combining
        .combine(qc_completion_signal)
        .map { sub, completion_signal ->
            def snapshot_dir = file("${params.output_dir}/sub-${sub}/figures")
            [sub, snapshot_dir, config_file]
        }
    
    QC_GENERATE_REPORT(qc_report_input)
}
