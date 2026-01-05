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
include { ANAT_REORIENT as ANAT_REORIENT_T2W } from './modules/anatomical.nf'  // Alias for T2w special processing
include { ANAT_CONFORM } from './modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION } from './modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION as ANAT_BIAS_CORRECTION_T2W } from './modules/anatomical.nf'  // Alias for T2w special processing
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
            def temp_script = File.createTempFile("read_yaml_", ".py")
            temp_script.text = """import yaml
import sys
try:
    with open('${config_path}') as f:
        config = yaml.safe_load(f) or {}
    keys = '${key_path}'.split('.')
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k, {})
        else:
            value = ${default_bool}
            break
    # If we ended up with a dict, use default; otherwise use the value
    result = value if not isinstance(value, dict) else ${default_bool}
    print('true' if result else 'false')
except Exception as e:
    print('${default_str}')
    sys.exit(0)
"""
            def proc = ["python3", temp_script.absolutePath].execute()
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
    
    // Read config values
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
    // First, extract all subjects from anat_jobs_ch for later use
    // Use tap to keep a copy of the channel for subject extraction
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
    
    // Run synthesis process for all anatomical modalities (T1w, T2w, etc.)
    ANAT_SYNTHESIS(anat_synthesis_input, config_file)
    
    // Process T1w single files (no synthesis needed)
    anat_branched.t1w_single
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_paths = item[2]
            def file_path = file_paths instanceof List ? file_paths[0] : file_paths
            def anat_file = file(file_path)
            [sub, ses, anat_file, file_path]
        }
        .set { anat_t1w_jobs }
    
    // T2w files that need special processing (with T1w in same session)
    // These go through a separate pipeline: REORIENT_T2W → REG_TO_T1W → BIAS_CORRECTION_T2W
    anat_branched.t2w_with_t1w
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_paths = item[2]
            def file_path = file_paths instanceof List ? file_paths[0] : file_paths
            def anat_file = file(file_path)
            [sub, ses, anat_file, file_path]
        }
        .set { anat_t2w_with_t1w_jobs }
    
    // T2w-only files (no T1w in session - process normally)
    anat_branched.t2w_only
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_paths = item[2]
            def file_path = file_paths instanceof List ? file_paths[0] : file_paths
            def anat_file = file(file_path)
            [sub, ses, anat_file, file_path]
        }
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
    
    // Anatomical processing steps
    // Note: The dependency is correctly enforced:
    // - Files requiring synthesis wait for ANAT_SYNTHESIS to complete
    // - Single files (no synthesis) proceed immediately
    
    // REORIENT step (conditionally enabled) - processes normal anatomical files
    def anat_after_reorient_normal = anat_input_ch
    if (anat_reorient_enabled) {
        ANAT_REORIENT(anat_input_ch, config_file)
        anat_after_reorient_normal = ANAT_REORIENT.out.output
    } else {
        // Pass through: create channel with same structure
        anat_after_reorient_normal = anat_input_ch
            .map { sub, ses, file, bids_template ->
                [sub, ses, file, bids_template]
            }
    }
    
    // CONFORM step (conditionally enabled) - only for normal processing (not T2w-with-T1w)
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
    
    // BIAS_CORRECTION step (conditionally enabled)
    def anat_after_bias = anat_after_conform
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION(anat_after_conform, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION.out.output
    } else {
        // Use pass-through process
        ANAT_BIAS_CORRECTION_PASSTHROUGH(anat_after_conform, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION_PASSTHROUGH.out.output
    }
    
    // SKULLSTRIPPING step (conditionally enabled)
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
        anat_after_skull = anat_after_bias
            .map { sub, ses, file, bids_template ->
                [sub, ses, file, bids_template]
            }
    }
    
    // REGISTRATION step (conditionally enabled)
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
    
    // QC for individual steps (conditionally enabled)
    // QC_CONFORM: needs conformed file + resampled template (same space as conformed image)
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
    
    // QC_REGISTRATION: needs registered file + transforms
    if (anat_registration_enabled) {
        anat_after_reg
            .join(anat_reg_transforms, by: [0, 1])
            .map { sub, ses, reg_file, trans -> 
                [sub, ses, reg_file, trans]
            }
            .set { anat_reg_for_qc }
        QC_REGISTRATION(anat_reg_for_qc, config_file)
    }    
    
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
    
    // Step 1: REORIENT T2w files (using aliased process)
    def t2w_after_reorient = anat_t2w_with_t1w_jobs
    if (anat_reorient_enabled) {
        ANAT_REORIENT_T2W(anat_t2w_with_t1w_jobs, config_file)
        t2w_after_reorient = ANAT_REORIENT_T2W.out.output
    } else {
        // Pass through: create channel with same structure
        t2w_after_reorient = anat_t2w_with_t1w_jobs
            .map { sub, ses, file, bids_template ->
                [sub, ses, file, bids_template]
            }
    }
    
    // Step 2: Get T1w bias-corrected output to use as reference
    // Filter T1w files from the main pipeline
    def t1w_bias_corrected = anat_after_bias
        .filter { sub, ses, file, bids_template ->
            // Check if this is a T1w file by examining the bids_template
            bids_template.toString().contains('T1w')
        }
    
    // Step 3: Join reoriented T2w with T1w bias-corrected output
    // T1w bias-corrected: [sub, ses, file, bids_template]
    // T2w reoriented: [sub, ses, file, bids_template]
    def t2w_reg_joined = t2w_after_reorient
        .join(t1w_bias_corrected, by: [0, 1])  // Join by subject and session
        .map { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            // Create tuple for process: [sub, ses, t2w_file, bids_template, t1w_file]
            [sub, ses, t2w_file, t2w_bids_template, t1w_file]
        }
    
    // Split into tuple channel and T1w reference channel
    def t2w_reg_input = t2w_reg_joined
        .map { sub, ses, t2w_file, t2w_bids_template, t1w_file ->
            [sub, ses, t2w_file, t2w_bids_template]
        }
    
    def t1w_ref_for_t2w = t2w_reg_joined
        .map { sub, ses, t2w_file, t2w_bids_template, t1w_file ->
            t1w_file
        }
    
    // Step 4: Run T2w→T1w registration
    // Process signature: (tuple, t1w_reference, config_file)
    ANAT_T2W_TO_T1W_REGISTRATION(t2w_reg_input, t1w_ref_for_t2w, config_file)
    def t2w_after_reg_to_t1w = ANAT_T2W_TO_T1W_REGISTRATION.out.output
    
    // Step 5: BIAS_CORRECTION for registered T2w (using aliased process)
    def t2w_after_bias_final = t2w_after_reg_to_t1w
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION_T2W(t2w_after_reg_to_t1w, config_file)
        t2w_after_bias_final = ANAT_BIAS_CORRECTION_T2W.out.output
    } else {
        // Pass through: create channel with same structure
        t2w_after_bias_final = t2w_after_reg_to_t1w
            .map { sub, ses, file, bids_template ->
                [sub, ses, file, bids_template]
            }
    }
    
    // QC for T2w→T1w registration
    // Join registered T2w output with skull-stripped T1w brain reference (for overlaid contour)
    // Process expects: tuple [sub, ses, registered_t2w_file, t1w_reference_file], bids_naming_template, config_file
    // Get skull-stripped T1w brain files from the main pipeline
    def t1w_skullstripped = anat_after_skull
        .filter { sub, ses, file, bids_template ->
            // Check if this is a T1w file by examining the bids_template
            bids_template.toString().contains('T1w')
        }
    
    def t2w_qc_input = t2w_after_reg_to_t1w
        .join(t1w_skullstripped, by: [0, 1])
        .map { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            // Create tuple for process: [sub, ses, t2w_file, t1w_file, t2w_bids_template]
            [sub, ses, t2w_file, t1w_file, t2w_bids_template]
        }
    
    // Split into tuple channel and bids_template channel
    def t2w_qc_tuple = t2w_qc_input
        .map { sub, ses, t2w_file, t1w_file, t2w_bids_template ->
            [sub, ses, t2w_file, t1w_file]
        }
    
    def t2w_qc_bids_template = t2w_qc_input
        .map { sub, ses, t2w_file, t1w_file, t2w_bids_template ->
            t2w_bids_template
        }
    
    // QC_T2W_TO_T1W_REGISTRATION
    QC_T2W_TO_T1W_REGISTRATION(t2w_qc_tuple, t2w_qc_bids_template, config_file)

    
    // ============================================
    // FUNCTIONAL PIPELINE
    // ============================================
    if (!anat_only) {
        // Functional processing steps (conditionally enabled)
        
        // REORIENT step
        def func_after_reorient = func_jobs_ch
        if (func_reorient_enabled) {
            FUNC_REORIENT(func_jobs_ch, config_file)
            func_after_reorient = FUNC_REORIENT.out.output
        } else {
            // Pass through: create channel with same structure
            func_after_reorient = func_jobs_ch
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // SLICE_TIMING step
        def func_after_slice = func_after_reorient
        if (func_slice_timing_enabled) {
            FUNC_SLICE_TIMING(func_after_reorient, config_file)
            func_after_slice = FUNC_SLICE_TIMING.out.output
        } else {
            func_after_slice = func_after_reorient
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // MOTION_CORRECTION step
        def func_after_motion = func_after_slice
        def func_motion_params = Channel.empty()
        if (func_motion_correction_enabled) {
            FUNC_MOTION_CORRECTION(func_after_slice, config_file)
            func_after_motion = FUNC_MOTION_CORRECTION.out.output
            func_motion_params = FUNC_MOTION_CORRECTION.out.motion_params
        } else {
            func_after_motion = func_after_slice
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // DESPIKE step
        def func_after_despike = func_after_motion
        if (func_despike_enabled) {
            FUNC_DESPIKE(func_after_motion, config_file)
            func_after_despike = FUNC_DESPIKE.out.output
        } else {
            func_after_despike = func_after_motion
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // BIAS_CORRECTION step
        def func_after_bias = func_after_despike
        if (func_bias_correction_enabled) {
            FUNC_BIAS_CORRECTION(func_after_despike, config_file)
            func_after_bias = FUNC_BIAS_CORRECTION.out.output
        } else {
            func_after_bias = func_after_despike
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // CONFORM step (conditionally enabled - needs pass-through for transforms)
        def func_after_conform = func_after_bias
        def func_conform_transforms = Channel.empty()
        if (func_conform_enabled) {
            FUNC_CONFORM(func_after_bias, config_file)
            func_after_conform = FUNC_CONFORM.out.output
            func_conform_transforms = FUNC_CONFORM.out.transforms
        } else {
            // Pass through: create channel with same structure (no transforms)
            func_after_conform = func_after_bias
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // SKULLSTRIPPING step
        def func_after_skull = func_after_conform
        def func_skull_mask = Channel.empty()
        if (func_skullstripping_enabled) {
            FUNC_SKULLSTRIPPING(func_after_conform, config_file)
            func_after_skull = FUNC_SKULLSTRIPPING.out.output
            func_skull_mask = FUNC_SKULLSTRIPPING.out.brain_mask
        } else {
            func_after_skull = func_after_conform
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // Functional registration (depends on anatomical if available)
        // Strategy: Join by subject AND session first, then fallback to first available anatomical session for same subject
        // Prepare anatomical channel: [sub, ses, anat_file, trans]
        def anat_reg_ch = anat_after_reg
            .join(anat_reg_transforms, by: [0, 1])
            .map { sub, ses, anat_file, trans -> 
                [sub, ses, anat_file, trans]
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
        
        // REGISTRATION step (conditionally enabled)
        def func_after_reg = func_after_skull
        def func_reg_transforms = Channel.empty()
        if (anat_registration_enabled) {
            // Join functional data with anatomical data by subject AND session (exact match)
            // func_after_skull: [sub, ses, task, run, processed_file, bids_naming_template]
            // anat_reg_ch: [sub, ses, anat_reg_file, anat_trans]
            def func_anat_exact = func_after_skull
                .join(anat_reg_ch, by: [0, 1])  // Join by [subject_id, session_id]
                .map { sub, ses, task, run, processed_file, bids_naming_template, anat_reg, anat_trans ->
                    // Exact match - same subject and session
                    [sub, ses, task, run, processed_file, bids_naming_template, anat_reg, anat_trans, ses, false]  // Last two: anat_ses, is_fallback
                }
            
            // For functional sessions without exact anatomical match, use first available anatomical for same subject
            // Combine all functional with first anatomical per subject, then filter to only unmatched cases
            def func_anat_fallback = func_after_skull
                .combine(anat_by_subject, by: 0)  // Combine by subject_id only
                .filter { sub, ses_func, task, run, processed_file, bids_naming_template, ses_anat, anat_reg, anat_trans ->
                    // Only keep if functional session doesn't match anatomical session (fallback case)
                    ses_func != ses_anat
                }
                .map { sub, ses_func, task, run, processed_file, bids_naming_template, ses_anat, anat_reg, anat_trans ->
                    // Using anatomical from different session - add warning flag
                    [sub, ses_func, task, run, processed_file, bids_naming_template, anat_reg, anat_trans, ses_anat, true]  // Last two: anat_ses, is_fallback
                }
            
            // Combine exact matches and fallbacks
            def func_anat_joined = func_anat_exact
                .mix(func_anat_fallback)
            
            FUNC_REGISTRATION(func_anat_joined, config_file)
            func_after_reg = FUNC_REGISTRATION.out.output
            func_reg_transforms = FUNC_REGISTRATION.out.transforms
        } else {
            // Pass through: create channel with same structure (no transforms)
            func_after_reg = func_after_skull
                .map { sub, ses, task, run, file, bids_template ->
                    [sub, ses, task, run, file, bids_template]
                }
        }
        
        // APPLY_TRANSFORMS step (only if registration was enabled)
        def func_final_output = func_after_reg
        if (anat_registration_enabled) {
            // Join registration outputs (tmean_registered and transforms) for apply_transforms
            // Join by subject_id (0), session_id (1), task_name (2), run (3)
            def func_reg_tuple_ch = func_after_reg
                .join(func_reg_transforms, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, processed_file, bids_naming_template, trans -> 
                    [sub, ses, task, run, processed_file, bids_naming_template, trans]
                }
            
            // Join with 4D file from DESPIKE (last step that processes 4D)
            // Match by subject/session/task/run to ensure correct pairing
            // func_reg_tuple_ch: [sub, ses, task, run, tmean_reg, bids_naming_template, trans]
            // func_after_despike: [sub, ses, task, run, processed_file, bids_naming_template]
            // After join by [0,1,2,3]: [sub, ses, task, run, tmean_reg, bids_naming_template_reg, trans, func_4d, bids_naming_template_despike]
            def func_joined_ch = func_reg_tuple_ch
                .join(func_after_despike, by: [0, 1, 2, 3])
            
            // Create the two input channels from the joined channel
            // Channel 1: tuple with registration info (use bids_naming_template from registration)
            def func_reg_input = func_joined_ch.map { sub, ses, task, run, tmean_reg, bids_naming_template_reg, trans, func_4d, bids_naming_template_despike ->
                [sub, ses, task, run, tmean_reg, trans, bids_naming_template_reg]
            }
            
            // Channel 2: 4D file path
            def func_4d_input = func_joined_ch.map { sub, ses, task, run, tmean_reg, bids_naming_template_reg, trans, func_4d, bids_naming_template_despike ->
                func_4d
            }
            
            // FUNC_APPLY_TRANSFORMS expects: (tuple with reg info), (4D file path), (config file)
            FUNC_APPLY_TRANSFORMS(func_reg_input, func_4d_input, config_file)
            func_final_output = FUNC_APPLY_TRANSFORMS.out.output
        }
        
        // QC for functional - individual steps (conditionally enabled)
        // QC_MOTION_CORRECTION: needs motion params + input file
        if (func_motion_correction_enabled) {
            func_after_motion
                .join(func_motion_params, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, processed_file, bids_naming_template, motion_file ->
                    [sub, ses, task, run, motion_file, processed_file, bids_naming_template]
                }
                .set { motion_qc_input }
            QC_MOTION_CORRECTION(motion_qc_input, config_file)
        }
        
        // QC_BIAS_CORRECTION_FUNC: needs original (from DESPIKE) + corrected (from BIAS_CORRECTION)
        if (func_bias_correction_enabled) {
            func_after_despike
                .join(func_after_bias, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, processed_file1, bids_naming_template1, processed_file2, bids_naming_template2 ->
                    // Both bids_naming_template values are the same, use the second one
                    [sub, ses, task, run, processed_file1, processed_file2, bids_naming_template2]
                }
                .set { func_bias_qc_input }
            QC_BIAS_CORRECTION_FUNC(func_bias_qc_input, config_file)
        }
        
        // QC_SKULLSTRIPPING_FUNC: needs brain file + mask file
        if (func_skullstripping_enabled) {
            func_after_skull
                .join(func_skull_mask, by: [0, 1, 2, 3])
                .map { sub, ses, task, run, processed_file, bids_naming_template, mask_file ->
                    [sub, ses, task, run, processed_file, mask_file, bids_naming_template]
                }
                .set { func_skull_qc_input }
            QC_SKULLSTRIPPING_FUNC(func_skull_qc_input, config_file)
        }
        
        // QC_REGISTRATION_FUNC: needs registered file
        if (anat_registration_enabled) {
            QC_REGISTRATION_FUNC(func_final_output, config_file)
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
        if (func_bias_correction_enabled) {
            func_qc_channels = func_qc_channels.mix(QC_BIAS_CORRECTION_FUNC.out.metadata)
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
