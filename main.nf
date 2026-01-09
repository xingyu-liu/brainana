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
include { QC_SURF_RECON_TISSUE_SEG } from './modules/qc.nf'
include { QC_CORTICAL_SURF_AND_MEASURES } from './modules/qc.nf'
include { QC_REGISTRATION } from './modules/qc.nf'
include { QC_T2W_TO_T1W_REGISTRATION } from './modules/qc.nf'

include { QC_MOTION_CORRECTION } from './modules/qc.nf'
include { QC_CONFORM_FUNC } from './modules/qc.nf'
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
    
    // Helper function to read YAML config boolean values using Python
    def readYamlBool = { config_path, key_path, default_bool ->
        try {
            def default_str = default_bool ? 'true' : 'false'
            // Create a simple Python script that properly handles nested dictionary access
            // Use command-line arguments to avoid embedding long paths in the script string
            def temp_script = File.createTempFile("read_yaml_", ".py")
            temp_script.text = """import yaml
import sys
try:
    config_file = sys.argv[1]
    key_path = sys.argv[2]
    default_bool = sys.argv[3] == 'true'
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f) or {}
    keys = key_path.split('.')
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k, {})
        else:
            value = default_bool
            break
    # If we ended up with a dict, use default; otherwise use the value
    result = value if not isinstance(value, dict) else default_bool
    print('true' if result else 'false')
except Exception as e:
    print('${default_str}')
    sys.exit(0)
"""
            def proc = ["python3", temp_script.absolutePath, config_path, key_path, default_str].execute()
            def output = new StringBuffer()
            def error = new StringBuffer()
            proc.consumeProcessOutput(output, error)
            proc.waitFor()
            def result_str = output.toString().trim()
            temp_script.delete()
            if (proc.exitValue() != 0 && error.toString().trim()) {
                println "Warning: Error reading ${key_path} from config: ${error.toString().trim()}"
            }
            return result_str == "true"
        } catch (Exception e) {
            println "Warning: Could not read ${key_path} from config: ${e.message}, using default: ${default_bool}"
            return default_bool
        }
    }
    
    // Note: output_space priority is handled by processes themselves:
    // 1. CLI argument (--output_space) - highest priority
    // 2. YAML config file (template.output_space) - medium priority  
    // 3. Nextflow config default (NMT2Sym:res-05) - lowest priority
    // Processes use get_effective_output_space() utility function to determine the correct value.
    
    // Calculate effective output_space for display (same logic as processes)
    def default_output_space = 'NMT2Sym:res-05'
    def effective_output_space = default_output_space
    if (params.output_space != default_output_space) {
        // CLI explicitly set, use it
        effective_output_space = params.output_space
    } else {
        // Read from YAML config file
        try {
            def python_code = """import yaml, sys
try:
    with open('${config_file_path}', 'r') as f:
        config = yaml.safe_load(f) or {}
    value = config.get('template', {}).get('output_space', '')
    if value and isinstance(value, str) and value.strip():
        print(value.strip(), end='')
    else:
        print('${default_output_space}', end='')
except:
    print('${default_output_space}', end='')
"""
            def temp_script = File.createTempFile("get_output_space_", ".py")
            temp_script.text = python_code
            def proc = ["python3", temp_script.absolutePath].execute()
            def output = proc.text.trim()
            proc.waitFor()
            temp_script.delete()
            if (proc.exitValue() == 0 && output) {
                effective_output_space = output
            }
        } catch (Exception e) {
            // Fallback to default
            effective_output_space = default_output_space
        }
    }
    
    // Strategy: If --anat_only is explicitly set to true, use it. Otherwise, read from config file.
    // This allows command-line to force true, while config file controls the default/false case.
    def anat_only_from_config = readYamlBool(config_file_path, "general.anat_only", false)
    def anat_only = params.anat_only == true ? true : anat_only_from_config
    def surf_recon_enabled = readYamlBool(config_file_path, "anat.surface_reconstruction.enabled", true)
    
    // Read all step enabled flags
    def anat_reorient_enabled = readYamlBool(config_file_path, "anat.reorient.enabled", true)
    def anat_conform_enabled = readYamlBool(config_file_path, "anat.conform.enabled", true)
    def anat_bias_correction_enabled = readYamlBool(config_file_path, "anat.bias_correction.enabled", true)
    def anat_skullstripping_enabled = readYamlBool(config_file_path, "anat.skullstripping_segmentation.enabled", true)
    def anat_registration_enabled = readYamlBool(config_file_path, "registration.enabled", true)
    
    def func_reorient_enabled = readYamlBool(config_file_path, "func.reorient.enabled", true)
    def func_slice_timing_enabled = readYamlBool(config_file_path, "func.slice_timing_correction.enabled", true)
    def func_motion_correction_enabled = readYamlBool(config_file_path, "func.motion_correction.enabled", true)
    def func_despike_enabled = readYamlBool(config_file_path, "func.despike.enabled", true)
    def func_bias_correction_enabled = readYamlBool(config_file_path, "func.bias_correction.enabled", true)
    def func_conform_enabled = readYamlBool(config_file_path, "func.conform.enabled", true)
    def func_skullstripping_enabled = readYamlBool(config_file_path, "func.skullstripping.enabled", true)
    
    // Ensure boolean type
    anat_only = anat_only as Boolean
    
    println "Processing mode: anat_only = ${anat_only}, surface_reconstruction = ${surf_recon_enabled}"
    println "Step enabled flags:"
    println "  ANAT: reorient=${anat_reorient_enabled}, conform=${anat_conform_enabled}, bias_correction=${anat_bias_correction_enabled}, skullstripping=${anat_skullstripping_enabled}, registration=${anat_registration_enabled}"
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
    Channel.fromPath(anat_jobs_file)
        .splitJson()
        .map { job ->
            def sub = job.subject_id.toString()
            def ses = job.session_id ? job.session_id.toString() : null
            def needs_synth = job.needs_synthesis ?: false
            def file_paths = job.file_paths ?: [job.file_path]
            def suffix = job.suffix.toString()
            def needs_t1w_reg = job.needs_t1w_registration ?: false
            
            [sub, ses, file_paths, needs_synth, suffix, needs_t1w_reg]
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
            
            // Pass BIDS naming template for BIDS filename generation
            [sub, ses, task, run, file(file_path), file_path]
        }
        .filter { sub, ses, task, run, file_path, bids_naming_template ->
            !anat_only
        }
        .set { func_jobs_ch }
    
    // ============================================
    // ANATOMICAL PIPELINE
    // ============================================
    // Helper closures for common operations
    // Extract single file path from file_paths (handles both List and single value)
    def getSingleFilePath = { file_paths ->
        file_paths instanceof List ? file_paths[0] : file_paths
    }
    
    // Map single-file job tuple to [sub, ses, file, bids_template] format
    def mapSingleFileJob = { item ->
        def sub = item[0]
        def ses = item[1]
        def file_paths = item[2]
        def file_path = getSingleFilePath(file_paths)
        def anat_file = file(file_path)
        [sub, ses, anat_file, file_path]
    }
    
    // Filter predicate for T1w files (checks bids_template)
    def isT1wFile = { sub, ses, file, bids_template ->
        bids_template.toString().contains('T1w')
    }
    
    // Pass-through mapping helper (preserves channel structure when step is disabled)
    def passThroughAnat = { sub, ses, file, bids_template ->
        [sub, ses, file, bids_template]
    }
    
    // Pass-through mapping helper for functional (preserves 6-element tuple structure)
    def passThroughFunc = { sub, ses, task, run, file, bids_template ->
        [sub, ses, task, run, file, bids_template]
    }
    
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
    
    // Process synthesis jobs: convert file paths to file objects
    anat_branched.synthesis
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_paths = item[2]
            
            // Ensure file_paths is a list and convert to file objects
            def paths_list = file_paths instanceof List ? file_paths : [file_paths]
            def file_objects = paths_list.findAll { it != null && it.toString().trim() != '' }
                .collect { file(it.toString()) }
            
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
    
    // Check if T2w files exist by getting first item (if any)
    // Split channel to check without consuming: use into to split, then first() on check branch
    // Use multiMap to split the channel (more reliable than into for empty channels)
    anat_t2w_with_t1w_jobs
        .multiMap { item ->
            processing: item
            check: item
        }
        .set { anat_t2w_split }
    
    def anat_t2w_with_t1w_jobs_for_processing = anat_t2w_split.processing
    def anat_t2w_with_t1w_jobs_for_check = anat_t2w_split.check
    
    // Check if T2w files exist - if first() emits, we know there are T2w files
    def t2w_has_items = anat_t2w_with_t1w_jobs_for_check.first()
    
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
    if (anat_registration_enabled) {
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
    if (anat_registration_enabled) {
        // Use ANAT_REGISTRATION output directly - it's already a 3-element tuple
        // tuple val(subject_id), val(session_id), path("*.nii.gz")
        QC_REGISTRATION(ANAT_REGISTRATION.out.output, config_file)
    }    
    
    // ============================================
    // SURFACE RECONSTRUCTION
    // ============================================
    // Surface reconstruction: needs non-skullstripped T1w file, segmentation, and brain mask
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
    // Only process if T2w files exist (t2w_has_items emits a value)
    
    // Gate processing: only process if t2w_has_items emits (meaning T2w files exist)
    // Use combine to create a gated channel - only emits when both channels have items
    // If t2w_has_items is empty, t2w_processing_enabled will be empty, and all processes will be skipped
    // t2w_has_items: [sub, ses, file, bids_template] (4 elements)
    // anat_t2w_with_t1w_jobs_for_processing: [sub, ses, file, bids_template] (4 elements)
    // combine creates cartesian product, so we need to extract the actual job item
    def t2w_processing_enabled = t2w_has_items
        .combine(anat_t2w_with_t1w_jobs_for_processing, by: [0, 1])  // Combine by subject and session to match items
        .map { sub, ses, file1, bids_template1, file2, bids_template2 ->
            // Use the actual job item (file2, bids_template2) from anat_t2w_with_t1w_jobs_for_processing
            [sub, ses, file2, bids_template2]
        }
    
    // Step 1: REORIENT T2w files (using aliased process)
    def t2w_after_reorient = t2w_processing_enabled
    if (anat_reorient_enabled) {
        ANAT_REORIENT_T2W(t2w_processing_enabled, config_file)
        t2w_after_reorient = ANAT_REORIENT_T2W.out.output
    } else {
        // Pass through: create channel with same structure
        t2w_after_reorient = t2w_processing_enabled.map(passThroughAnat)
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
    // Process signature: (tuple, t1w_reference, config_file)
    ANAT_T2W_TO_T1W_REGISTRATION(t2w_reg_multi.combined, t2w_reg_multi.reference, config_file)
    def t2w_after_reg_to_t1w = ANAT_T2W_TO_T1W_REGISTRATION.out.output
    
    // Step 5: BIAS_CORRECTION for registered T2w (using aliased process)
    def t2w_after_bias_final = t2w_after_reg_to_t1w
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION_T2W(t2w_after_reg_to_t1w, config_file)
        t2w_after_bias_final = ANAT_BIAS_CORRECTION_T2W.out.output
    } else {
        // Pass through: create channel with same structure
        t2w_after_bias_final = t2w_after_reg_to_t1w.map(passThroughAnat)
    }
    
    // QC for T2w→T1w registration
    // Join bias-corrected T2w output with skull-stripped T1w brain reference (for overlaid contour)
    // Process expects: combined [sub, ses, registered_t2w_file, t1w_reference_file], bids_naming_template, config_file
    // Get skull-stripped T1w brain files from the main pipeline for overlay contours
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
    if (!anat_only) {
        // Functional processing steps (conditionally enabled)
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
            // Pass through: create channel with same structure
            func_after_reorient = func_after_slice.map(passThroughFunc)
        }
        
        // ------------------------------------------------------------
        // MOTION_CORRECTION
        def func_after_motion = func_after_reorient
        def func_motion_params = Channel.empty()
        if (func_motion_correction_enabled) {
            FUNC_MOTION_CORRECTION(func_after_reorient, config_file)
            func_after_motion = FUNC_MOTION_CORRECTION.out.output  // Combined channel: [sub, ses, task, run, bold, tmean, bids_template]
            func_motion_params = FUNC_MOTION_CORRECTION.out.motion_params
        } else {
            // Create combined channel from single input (use same file for both BOLD and tmean)
            func_after_motion = func_after_reorient.map { sub, ses, task, run, file, bids_template ->
                [sub, ses, task, run, file, file, bids_template]
            }
        }
        
        // ------------------------------------------------------------
        // DESPIKE
        def func_after_despike = func_after_motion
        if (func_despike_enabled) {
            FUNC_DESPIKE(func_after_motion, config_file)
            func_after_despike = FUNC_DESPIKE.out.output  // Combined channel: [sub, ses, task, run, bold, tmean, bids_template]
        } else {
            // Pass through combined channel unchanged
            func_after_despike = func_after_motion
        }
        
        // ------------------------------------------------------------
        // BIAS_CORRECTION
        // operates on tmean, inherits BOLD
        def func_after_bias = func_after_despike
        if (func_bias_correction_enabled) {
            FUNC_BIAS_CORRECTION(func_after_despike, config_file)
            func_after_bias = FUNC_BIAS_CORRECTION.out.output  // Combined channel: [sub, ses, task, run, bold, tmean, bids_template]
        } else {
            // Pass through combined channel unchanged
            func_after_bias = func_after_despike
        }
        
        // ------------------------------------------------------------
        // ANATOMICAL SELECTION
        // runs before CONFORM and REGISTRATION
        //
        // Strategy: Determine case for each functional job first, then select anatomical data
        // Case 1: Within-session anatomical data (exact match by subject AND session)
        // Case 2: Across-session anatomical data (same subject, different session)
        // Case 3: No anatomical data (use dummy file, Python code will fallback to template)

        // Get T1w skull-stripped brain files from anatomical pipeline
        // 4 elements: [sub, ses, anat_file, bids_template]
        def anat_for_func = anat_after_skull
            .filter(isT1wFile)
        
        // Step 1: Build lookup structures for anatomical data
        // Lookup 1: Same-session map - structure: [sub, ses, anat_file, bids_template]
        // (flattened for combine by [0, 1])
        def anat_same_ses_lookup = anat_for_func
            .map { sub, ses, anat_file, bids_template ->
                [sub, ses, anat_file, bids_template]
            }
            .unique { sub, ses, anat_file, bids_template ->
                [sub, ses]  // Deduplicate by [sub, ses] - take first if multiple
            }
        
        // Lookup 2: Across-session map sub -> [ses, anat_file] (first session per subject)
        def anat_across_ses_lookup = anat_for_func
            .map { sub, ses, anat_file, bids_template ->
                [sub, ses, anat_file]
            }
            .groupTuple(by: 0)  // Group by subject_id
            .map { sub, ses_list, file_list ->
                def sessions = [ses_list, file_list].transpose()
                def sorted_sessions = sessions.sort { a, b ->
                    def ses_a = a[0] ?: ''
                    def ses_b = b[0] ?: ''
                    ses_a <=> ses_b
                }
                def first_session = sorted_sessions[0]
                [sub, first_session[0], first_session[1]]  // [sub, ses, anat_file]
            }
        
        // Step 2: For each functional job, determine case and select anatomical data
        // Strategy: Try cases in order (1 -> 2 -> 3), track matched jobs, process remaining
        
        // Case 1: Same-session match (exact match by [sub, ses])
        def func_with_anat_same_ses = func_after_bias
            .combine(anat_same_ses_lookup, by: [0, 1])  // Combine by [sub, ses]
            .map { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_file, anat_bids_template ->
                // Case 1: same session, is_cross_ses = false
                [sub, ses, task, run, anat_file, ses, false]
            }
        
        // Get keys that matched Case 1 (for filtering out from subsequent cases)
        def func_matched_case1 = func_with_anat_same_ses
            .map { sub, ses, task, run, anat_file, anat_ses, is_cross_ses ->
                [sub, ses, task, run]  // Key format for matching
            }
            .unique()
        
        // Case 2: Across-session match (for jobs not matched in Case 1)
        // Get all func job keys, then find which ones are NOT in Case 1
        // Use mix + groupTuple to identify unmatched jobs
        def all_func_keys = func_after_bias
            .map { sub, ses, task, run, bold_file, tmean_file, bids_template ->
                [sub, ses, task, run]
            }
            .unique()
        
        // Find func jobs that didn't match Case 1
        // Mix matched and all keys, then group by entire key tuple
        def func_unmatched_case1_keys = func_matched_case1
            .map { sub, ses, task, run -> [[sub, ses, task, run], 'matched'] }
            .mix(all_func_keys.map { sub, ses, task, run -> [[sub, ses, task, run], 'all'] })
            .groupTuple()
            .filter { key, flags ->
                // Keep only keys that appear once with 'all' flag (not matched)
                flags.size() == 1 && flags[0] == 'all'
            }
            .map { key, flags ->
                key  // Return just the key [sub, ses, task, run]
            }
        
        // Get func jobs for Case 2 (those not matched in Case 1)
        def func_for_case2 = func_after_bias
            .map { sub, ses, task, run, bold_file, tmean_file, bids_template ->
                [[sub, ses, task, run], [sub, ses, task, run, bold_file, tmean_file, bids_template]]
            }
            .combine(func_unmatched_case1_keys.map { key -> [key, true] }.groupTuple(), by: 0)
            .map { key, func_data, matched_flags ->
                func_data  // Extract original functional job data
            }
        
        // Try to match remaining jobs with across-session anatomical data
        def func_with_anat_across_ses = func_for_case2
            .combine(anat_across_ses_lookup, by: 0)  // Combine by subject_id only
            .map { sub, ses_func, task, run, bold_file, tmean_file, bids_template, ses_anat, anat_file ->
                // Case 2: different session, is_cross_ses = true
                [sub, ses_func, task, run, anat_file, ses_anat, true]
            }
        
        // Get keys that matched Case 2 (for filtering out from Case 3)
        def func_matched_case2 = func_with_anat_across_ses
            .map { sub, ses, task, run, anat_file, anat_ses, is_cross_ses ->
                [sub, ses, task, run]  // Key format for matching
            }
            .unique()
        
        // Case 3: No anatomical data (for jobs not matched in Case 1 or 2)
        // Find func jobs that didn't match Case 2 (from func_unmatched_case1_keys)
        def func_matched_case1_or_2 = func_matched_case1
            .mix(func_matched_case2)
            .unique()
        
        def func_unmatched_case2_keys = func_matched_case1_or_2
            .map { sub, ses, task, run -> [[sub, ses, task, run], 'matched'] }
            .mix(all_func_keys.map { sub, ses, task, run -> [[sub, ses, task, run], 'all'] })
            .groupTuple()
            .filter { key, flags ->
                // Keep only keys that appear once with 'all' flag (not matched in Case 1 or 2)
                flags.size() == 1 && flags[0] == 'all'
            }
            .map { key, flags ->
                key  // Return just the key [sub, ses, task, run]
            }
        
        // Get func jobs for Case 3 (those not matched in Case 1 or 2)
        def func_for_case3 = func_after_bias
            .map { sub, ses, task, run, bold_file, tmean_file, bids_template ->
                [[sub, ses, task, run], [sub, ses, task, run, bold_file, tmean_file, bids_template]]
            }
            .combine(func_unmatched_case2_keys.map { key -> [key, true] }.groupTuple(), by: 0)
            .map { key, func_data, matched_flags ->
                func_data  // Extract original functional job data
            }
            .map { sub, ses, task, run, bold_file, tmean_file, bids_template ->
                // Case 3: no anatomical data, use dummy file
                def dummy_anat = file("${workDir}/dummy_anat.dummy")
                // anat_ses = ses_func (functional session), is_cross_ses = false
                [sub, ses, task, run, dummy_anat, ses, false]
            }
        
        // Step 3: Combine all cases (each job appears in exactly one case)
        func_anat_selection = func_with_anat_same_ses
            .mix(func_with_anat_across_ses)
            .mix(func_for_case3)

        // ------------------------------------------------------------
        // CONFORM 
        // processes both BOLD and tmean
        def func_after_conform = func_after_bias
        def func_conform_transforms = Channel.empty()
        if (func_conform_enabled) {
            // Join functional data with anatomical selection to get anatomical file
            def func_conform_with_anat = func_after_bias
                .join(func_anat_selection, by: [0, 1, 2, 3])  // Join by [sub, ses, task, run]
                .map { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_file, anat_ses, is_cross_ses ->
                    [sub, ses, task, run, bold_file, tmean_file, bids_template, anat_file]
                }
            
            def func_conform_tuple = func_conform_with_anat
                .multiMap { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_file ->
                    combined: [sub, ses, task, run, bold_file, tmean_file, bids_template]
                    reference: anat_file
                }
                .set { func_conform_multi }
            
            FUNC_CONFORM(func_conform_multi.combined, func_conform_multi.reference, config_file)
            func_after_conform = FUNC_CONFORM.out.output  
            func_conform_transforms = FUNC_CONFORM.out.transforms
        }
        
        // ------------------------------------------------------------
        // SKULLSTRIPPING 
        // operates on tmean → brain, inherits BOLD
        def func_after_skull_processed = Channel.empty()
        def func_after_skull_passthrough = Channel.empty()
        def func_mask = Channel.empty()
        
        if (func_skullstripping_enabled) {
            FUNC_SKULLSTRIPPING(func_after_conform, config_file)
            func_after_skull_processed = FUNC_SKULLSTRIPPING.out.output
            func_mask = FUNC_SKULLSTRIPPING.out.brain_mask

            // // debug: view the first element of func_after_skull_processed
            // func_after_skull_processed.first().view { tuple ->
            //     "DEBUG [FUNC_SKULLSTRIPPING: func_after_skull_processed]: ${tuple}"
            // }
            // // debug: view the first element of func_mask
            // func_mask.first().view { tuple ->
            //     "DEBUG [FUNC_SKULLSTRIPPING: func_mask]: ${tuple}"

        } else {
            // Only assign passthrough when skullstripping is disabled
            func_after_skull_passthrough = func_after_conform
        }
        
        // Mix both channels - only one will have data based on the condition
        // processed channel should be 7 elements: [sub, ses, task, run, bold_file, tmean_file (brain_file), bids_template
        def func_after_skull = func_after_skull_processed.mix(func_after_skull_passthrough)

        // ------------------------------------------------------------
        // FUNC_REGISTRATION 
        // registers functional tmean/brain to anatomical skull-stripped brain OR template
        def func_after_reg = func_after_skull
        def func_reg_transforms = Channel.empty()
        def func_reg_reference = Channel.empty()
        def func_reg_metadata = Channel.empty()  // [sub, ses, task, run, target_type, target2template]
        
        if (anat_registration_enabled) {
            // Join functional data with anatomical selection (reuse selection from before CONFORM)
            def func_reg_with_anat = func_after_skull
                .join(func_anat_selection, by: [0, 1, 2, 3])  // Join by [sub, ses, task, run]
                .map { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_brain, anat_ses, is_cross_ses ->
                    [sub, ses, task, run, bold_file, tmean_file, bids_template, anat_brain, anat_ses, is_cross_ses]
                }
            
            // Split using multiMap
            func_reg_with_anat
                .multiMap { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_brain, anat_ses, is_cross_ses ->
                    combined: [sub, ses, task, run, bold_file, tmean_file, bids_template, anat_ses, is_cross_ses]
                    reference: anat_brain
                }
                .set { func_reg_multi }

            FUNC_REGISTRATION(func_reg_multi.combined, func_reg_multi.reference, config_file)
            func_after_reg = FUNC_REGISTRATION.out.output
            func_reg_transforms = FUNC_REGISTRATION.out.transforms
            func_reg_reference = FUNC_REGISTRATION.out.reference
            func_reg_metadata = FUNC_REGISTRATION.out.metadata
            func_reg_anat_session = FUNC_REGISTRATION.out.anat_session
        } else {
            // Pass through combined channel unchanged
            func_after_reg = func_after_skull
        }
        
        // ------------------------------------------------------------
        // APPLY_TRANSFORMS
        // only if registration was enabled
        def func_apply_reg = func_after_reg
        def func_apply_reg_reference = Channel.empty()  // Reference files for QC
        if (anat_registration_enabled) {
            // Parse metadata to extract target_type and target2template
            def func_reg_metadata_parsed = func_reg_metadata
                .map { sub, ses, task, run, metadata_file ->
                    // Read metadata file (tab-separated: target_type, target2template)
                    def metadata_text = metadata_file.text.trim()
                    def parts = metadata_text.split('\t')
                    def target_type = parts[0]
                    def target2template = parts.length > 1 ? parts[1].toBoolean() : false
                    [sub, ses, task, run, target_type, target2template]
                }
            
            // func_after_reg: [sub, ses, task, run, bold_file, registered_tmean, bids_template] (7 elements)
            // func_reg_transforms: [sub, ses, task, run, forward_transform] (5 elements)
            // func_reg_metadata_parsed: [sub, ses, task, run, target_type, target2template] (6 elements)
            // func_reg_reference: [sub, ses, task, run, reference_file] (5 elements)
            
            // Join all registration outputs together
            def func_reg_complete = func_after_reg
                .join(func_reg_transforms, by: [0, 1, 2, 3])
                .join(func_reg_metadata_parsed, by: [0, 1, 2, 3])
                .join(func_reg_reference, by: [0, 1, 2, 3])
                .join(func_reg_anat_session, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    [sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses]
                }
            
            // DEBUG: Count func_reg_complete
            func_reg_complete
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    "DEBUG [func_reg_complete]: ${sub}_${ses}_${task}_${run} | target_type=${target_type}, target2template=${target2template}, anat_ses=${anat_ses}"
                }
                .view()
            
            // Split into sequential transforms (func2anat2template) and single transform cases
            def func_sequential = func_reg_complete
                .filter { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    target2template && target_type == 'anat'  // Sequential: func2anat then anat2template
                }
            
            // DEBUG: Count func_sequential
            func_sequential
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    "DEBUG [func_sequential]: ${sub}_${ses}_${task}_${run} | anat_ses=${anat_ses}"
                }
                .view()
            
            def func_single = func_reg_complete
                .filter { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    !(target2template && target_type == 'anat')  // Single transform: func2anat or func2template
                }
            
            // DEBUG: Count func_single
            func_single
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    "DEBUG [func_single]: ${sub}_${ses}_${task}_${run}"
                }
                .view()
            
            // Handle sequential transforms: need anat2template transform
            // Create dummy empty file for single transforms (anat2template not needed)
            def dummy_anat2template = file("${workDir}/dummy_anat2template.dummy")
            
            // DEBUG: Check anat_reg_transforms
            anat_reg_transforms
                .map { sub, ses, transform_file ->
                    "DEBUG [anat_reg_transforms]: ${sub}_${ses}"
                }
                .view()
            
            // Join sequential transforms with anatomical registration transforms
            // Join by [sub, anat_ses] to match the exact anatomical session used for registration
            // This ensures each functional run uses the transform from the anatomical session it was registered to
            // anat_reg_transforms structure: [sub, ses, transform_file]
            // func_sequential structure: [sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses]
            // We need to join where func_sequential.anat_ses == anat_reg_transforms.ses
            def func_sequential_joined = func_sequential
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    // Rearrange for join: [sub, anat_ses, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file]
                    [sub, anat_ses, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file]
                }
                .join(anat_reg_transforms.map { sub, ses, transform_file -> [sub, ses, transform_file] }, by: [0, 1])  // Join by [sub, anat_ses] where anat_ses == ses
                .map { sub, anat_ses, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, transform_file ->
                    [sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, transform_file, target_type, target2template, reference_file]
                }
            
            // DEBUG: Count func_sequential_joined
            func_sequential_joined
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
                    "DEBUG [func_sequential_joined]: ${sub}_${ses}_${task}_${run}"
                }
                .view()
            
            // Find items in func_sequential that didn't join (shouldn't happen normally, but handle gracefully)
            def func_sequential_joined_keys = func_sequential_joined
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
                    [sub, ses, task, run]
                }
                .unique()
            
            // Items that didn't join get dummy transform
            def func_sequential_no_match = func_sequential
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    [sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file]
                }
                .combine(func_sequential_joined_keys.groupTuple(), by: [0, 1, 2, 3])
                .filter { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, matched_keys ->
                    !matched_keys || matched_keys.isEmpty()
                }
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file ->
                    [sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, dummy_anat2template, target_type, target2template, reference_file]
                }
            
            // DEBUG: Count func_sequential_no_match
            func_sequential_no_match
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
                    "DEBUG [func_sequential_no_match]: ${sub}_${ses}_${task}_${run}"
                }
                .view()
            
            def func_sequential_with_anat2template = func_sequential_joined
                .mix(func_sequential_no_match)
            
            // DEBUG: Count func_sequential_with_anat2template
            func_sequential_with_anat2template
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
                    "DEBUG [func_sequential_with_anat2template]: ${sub}_${ses}_${task}_${run}"
                }
                .view()
            
            // Add dummy anat2template for single transforms
            def func_single_with_dummy = func_single
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
                    [sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, dummy_anat2template, target_type, target2template, reference_file]
                }
            
            // DEBUG: Count func_single_with_dummy
            func_single_with_dummy
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
                    "DEBUG [func_single_with_dummy]: ${sub}_${ses}_${task}_${run}"
                }
                .view()
            
            // Combine all (sequential and single) with consistent structure
            def func_all_for_apply = func_sequential_with_anat2template
                .mix(func_single_with_dummy)
            
            // DEBUG: Count func_all_for_apply (final count before multiMap)
            func_all_for_apply
                .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
                    "DEBUG [func_all_for_apply]: ${sub}_${ses}_${task}_${run}"
                }
                .view()
            
            // Prepare for FUNC_APPLY_TRANSFORMS
            // Use multiMap to split into two channels - they will be aligned by index
            func_all_for_apply
                .multiMap { sub, ses, task, run, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
                    reg_combined: [sub, ses, task, run, registered_tmean, forward_transform, anat2template_transform, bids_template, target_type, target2template, reference_file]
                    func_4d_file: bold_file
                }
                .set { func_apply_multi }
            
            // DEBUG: Count channels after multiMap
            func_apply_multi.reg_combined
                .map { sub, ses, task, run, registered_tmean, forward_transform, anat2template_transform, bids_template, target_type, target2template, reference_file ->
                    "DEBUG [func_apply_multi.reg_combined]: ${sub}_${ses}_${task}_${run}"
                }
                .view()
            
            func_apply_multi.func_4d_file
                .map { bold_file ->
                    "DEBUG [func_apply_multi.func_4d_file]: ${bold_file}"
                }
                .view()
            
            FUNC_APPLY_TRANSFORMS(func_apply_multi.reg_combined, func_apply_multi.func_4d_file, config_file)
            func_apply_reg = FUNC_APPLY_TRANSFORMS.out.output
            func_apply_reg_reference = FUNC_APPLY_TRANSFORMS.out.reference

            // // debug: view the first element of func_apply_reg
            // func_apply_reg.first().view { tuple ->
            //     "DEBUG [FUNC_APPLY_TRANSFORMS: func_apply_reg]: ${tuple}"
        }

        // ============================================
        // QC for functional - individual steps
        // ============================================
        // FUNC_QC_MOTION_CORRECTION
        if (func_motion_correction_enabled) {
            func_after_motion
                .join(func_motion_params, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, bold_file, tmean_file, bids_template, motion_file ->
                    // Extract tmean for QC (before motion correction)
                    [sub, ses, task, run, motion_file, tmean_file, bids_template]
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
        
        // QC_CONFORM_FUNC: needs conformed file + template_resampled (same space as conformed image)
        if (func_conform_enabled) {
            // Join conform output with template_resampled
            FUNC_CONFORM.out.output
                .join(FUNC_CONFORM.out.template_resampled, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, bold_file, tmean_file, bids_template, template_file, template_bids_naming ->
                    // Extract tmean (conformed) for QC
                    [sub, ses, task, run, tmean_file, bids_template, template_file]
                }
                .set { func_conform_qc_input }
            QC_CONFORM_FUNC(func_conform_qc_input, config_file)
        }
        
        // QC_SKULLSTRIPPING_FUNC: needs original (non-skullstripped) file + mask file
        // Use conform output (input to skullstripping) as underlay, not the skullstripped brain
        if (func_skullstripping_enabled) {
            func_after_conform
                .join(func_mask, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, bold_file, tmean_file, bids_template, mask_file, bids_template_mask ->
                    // Extract tmean (before skullstripping) for QC
                    [sub, ses, task, run, tmean_file, mask_file, bids_template]
                }
                .set { func_skull_qc_input }
            QC_SKULLSTRIPPING_FUNC(func_skull_qc_input, config_file)
        }

        // QC_REGISTRATION_FUNC: needs registered file
        if (anat_registration_enabled) {
            // Extract registered boldref (tmean) from combined channel
            // func_apply_reg: [sub, ses, task, run, bold_file, boldref_file, bids_template] (7 elements)
            // func_apply_reg_reference: [sub, ses, task, run, reference_file] (5 elements)
            // Join produces: [sub, ses, task, run, bold_file, boldref_file, bids_template, reference_file] (8 elements)
            // Process expects: [sub, ses, task, run, registered_file, reference_file] (6 elements)
            func_apply_reg
                .join(func_apply_reg_reference, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, bold_file, registered_boldref, bids_template, reference_file ->
                    // Use boldref_file (index 5) as the registered_file for QC
                    [sub, ses, task, run, registered_boldref, reference_file]
                }
                .set { func_reg_qc_input }
            QC_REGISTRATION_FUNC(func_reg_qc_input, config_file)
        }      
    }  

    // ============================================
    // QC REPORT GENERATION (per subject)
    // ============================================
    // Ensure all QC processes complete before report generation
    // Use QC_REGISTRATION outputs as the final dependency (since it runs last)
    
    // Create completion signal - wait for all QC processes to complete
    // Collect all QC metadata channels that are actually enabled
    def anat_qc_channels = Channel.empty()
    
    // Add QC channels based on enabled steps
    if (anat_registration_enabled) {
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
        // if (func_bias_correction_enabled) {
        //     func_qc_channels = func_qc_channels.mix(QC_BIAS_CORRECTION_FUNC.out.metadata)
        // }
        if (func_conform_enabled) {
            func_qc_channels = func_qc_channels.mix(QC_CONFORM_FUNC.out.metadata)
        }
        if (func_skullstripping_enabled) {
            func_qc_channels = func_qc_channels.mix(QC_SKULLSTRIPPING_FUNC.out.metadata)
        }
        if (anat_registration_enabled) {
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
        all_subjects = all_subjects.mix(func_jobs_ch.map { sub, ses, task, run, file_path, bids_naming_template -> sub }.unique())
    }
    
    // Create snapshot directory path for each subject
    // Combine with QC completion signal to ensure all QC processes finish first
    // QC_GENERATE_REPORT expects: tuple (subject_id, snapshot_dir, config_file)
    def qc_report_input = all_subjects
        .unique()  // Ensure unique subjects before combining
        .combine(qc_completion_signal)  // Combine ensures QC processes complete before report generation
        .map { sub, completion_signal ->
            def snapshot_dir = file("${params.output_dir}/sub-${sub}/figures")
            [sub, snapshot_dir, config_file]
        }
    
    QC_GENERATE_REPORT(qc_report_input)
}