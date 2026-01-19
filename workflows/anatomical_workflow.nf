/*
 * Anatomical Processing Workflow
 * 
 * Handles all anatomical processing steps including:
 * - Input validation and config reading
 * - Anatomical job parsing
 * - Anatomical processing pipeline (synthesis, reorient, conform, bias correction, skull stripping, registration)
 * - Surface reconstruction
 * - T2w special processing
 * - Anatomical QC steps
 */

nextflow.enable.dsl=2

// Include anatomical processing modules
include { ANAT_SYNTHESIS } from '../modules/anatomical.nf'
include { ANAT_SYNTHESIS as ANAT_SYNTHESIS_T2W } from '../modules/anatomical.nf'
include { ANAT_REORIENT } from '../modules/anatomical.nf'
include { ANAT_REORIENT as ANAT_REORIENT_T2W } from '../modules/anatomical.nf'
include { ANAT_CONFORM } from '../modules/anatomical.nf'
include { ANAT_CONFORM as ANAT_CONFORM_T2W } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION as ANAT_BIAS_CORRECTION_T2W } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION as ANAT_BIAS_CORRECTION_T2W_NO_T1W } from '../modules/anatomical.nf'
include { ANAT_SKULLSTRIPPING } from '../modules/anatomical.nf'
include { ANAT_SKULLSTRIPPING as ANAT_SKULLSTRIPPING_T2W } from '../modules/anatomical.nf'
include { ANAT_SURFACE_RECONSTRUCTION } from '../modules/anatomical.nf'
include { ANAT_REGISTRATION } from '../modules/anatomical.nf'
include { ANAT_REGISTRATION as ANAT_REGISTRATION_T2W } from '../modules/anatomical.nf'
include { ANAT_T2W_TO_T1W_REGISTRATION } from '../modules/anatomical.nf'
include { ANAT_CONFORM_PASSTHROUGH } from '../modules/anatomical.nf'
include { ANAT_CONFORM_PASSTHROUGH as ANAT_CONFORM_PASSTHROUGH_T2W } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION_PASSTHROUGH } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION_PASSTHROUGH as ANAT_BIAS_CORRECTION_PASSTHROUGH_T2W } from '../modules/anatomical.nf'
include { ANAT_REGISTRATION_PASSTHROUGH } from '../modules/anatomical.nf'
include { ANAT_REGISTRATION_PASSTHROUGH as ANAT_REGISTRATION_PASSTHROUGH_T2W } from '../modules/anatomical.nf'
include { ANAT_APPLY_CONFORM } from '../modules/anatomical.nf'
include { ANAT_APPLY_TRANSFORMATION } from '../modules/anatomical.nf'
include { ANAT_APPLY_TRANSFORM_MASK } from '../modules/anatomical.nf'

// Include anatomical QC modules
include { QC_CONFORM } from '../modules/qc.nf'
include { QC_BIAS_CORRECTION } from '../modules/qc.nf'
include { QC_SKULLSTRIPPING } from '../modules/qc.nf'
include { QC_ATLAS_SEGMENTATION } from '../modules/qc.nf'
include { QC_SURF_RECON_TISSUE_SEG } from '../modules/qc.nf'
include { QC_CORTICAL_SURF_AND_MEASURES } from '../modules/qc.nf'
include { QC_REGISTRATION } from '../modules/qc.nf'
include { QC_T2W_TO_T1W_REGISTRATION } from '../modules/qc.nf'
include { QC_T2W_TEMPLATE_SPACE } from '../modules/qc.nf'

// Load external Groovy files for channel operations
def channelHelpers = evaluate(new File("${projectDir}/workflows/channel_helpers.groovy").text)

// Load parameter resolver
def paramResolver = evaluate(new File("${projectDir}/workflows/param_resolver.groovy").text)

// Load config helpers
def configHelpers = evaluate(new File("${projectDir}/workflows/config_helpers.groovy").text)

workflow ANAT_WF {
    main:
    // ============================================
    // INPUT VALIDATION
    // ============================================
    if (!params.bids_dir) {
        error "Missing required parameter: --bids_dir"
    }
    if (!params.output_dir) {
        error "Missing required parameter: --output_dir"
    }
    
    // Validate paths exist
    def bids_dir_path = file(params.bids_dir)
    def bids_dir_str = params.bids_dir.toString()
    if (!new File(bids_dir_str).exists()) {
        error "BIDS directory not found: ${params.bids_dir}"
    }
    
    // ============================================
    // INITIALIZATION
    // ============================================
    // Initialize parameter resolver (if not already initialized in main.nf)
    // This is safe to call multiple times - it will only load configs once
    configHelpers.ensureParamResolverInitialized(paramResolver, params, projectDir)
    
    // Use effective config file (generated in main.nf)
    // This contains all resolved parameters: CLI params → YAML config → defaults.yaml
    // Get path as string - Nextflow processes can accept string paths for 'path' inputs
    def config_file_path = configHelpers.getEffectiveConfigPath(params, projectDir)
    // Pass string path directly - Nextflow will convert to file object when process executes
    // This avoids early validation issues with file() in workflow blocks
    def config_file = config_file_path
    
    // ============================================
    // RESOLVE PARAMETERS (for workflow logic)
    // ============================================
    // Priority: CLI params → YAML config → defaults.yaml
    // All defaults come from defaults.yaml - no hardcoded values
    
    // Resolve YAML-only boolean parameters
    // All defaults come from defaults.yaml
    def surf_recon_enabled = paramResolver.getYamlBool("anat.surface_reconstruction.enabled")
    def anat_reorient_enabled = paramResolver.getYamlBool("anat.reorient.enabled")
    def anat_conform_enabled = paramResolver.getYamlBool("anat.conform.enabled")
    def anat_bias_correction_enabled = paramResolver.getYamlBool("anat.bias_correction.enabled")
    def anat_skullstripping_enabled = paramResolver.getYamlBool("anat.skullstripping_segmentation.enabled")
    def registration_enabled = paramResolver.getYamlBool("registration.enabled")
    
    // Resolve BIDS filtering parameters (CLI parameters)
    // Defaults come from defaults.yaml (bids_filtering.*)
    def subjects_list = paramResolver.getParamList(params, 'subjects', null)
    def sessions_list = paramResolver.getParamList(params, 'sessions', null)
    def tasks_list = paramResolver.getParamList(params, 'tasks', null)
    def runs_list = paramResolver.getParamList(params, 'runs', null)
    
    // Convert lists to strings for display (backward compatibility with existing code)
    def subjects_str = subjects_list ? subjects_list.join(' ') : ''
    def sessions_str = sessions_list ? sessions_list.join(' ') : ''
    def tasks_str = tasks_list ? tasks_list.join(' ') : ''
    def runs_str = runs_list ? runs_list.join(' ') : ''
    
    // Get output_space for display (from effective config)
    def effective_output_space = paramResolver.getParamOutputSpace(params, 'output_space')
    
    println "Processing mode: surface_reconstruction = ${surf_recon_enabled}"
    println "Step enabled flags:"
    println "  ANAT: reorient=${anat_reorient_enabled}, conform=${anat_conform_enabled}, bias_correction=${anat_bias_correction_enabled}, skullstripping=${anat_skullstripping_enabled}, registration=${registration_enabled}"
    
    println "============================================"
    println "banana Nextflow Pipeline - Anatomical"
    println "============================================"
    println "BIDS directory: ${params.bids_dir}"
    println "Output directory: ${params.output_dir}"
    println "Output space: ${effective_output_space}"
    println "Effective config: ${config_file_path}"
    if (subjects_str) println "Subjects filter: ${subjects_str}"
    if (sessions_str) println "Sessions filter: ${sessions_str}"
    if (tasks_str) println "Tasks filter: ${tasks_str}"
    if (runs_str) println "Runs filter: ${runs_str}"
    println "============================================"
    
    // ============================================
    // PARSE ANATOMICAL JOBS
    // ============================================
    // Load pre-discovered job lists from discovery script
    // Channel structure: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg]
    def anat_jobs_file = file("${params.output_dir}/nextflow_reports/anatomical_jobs.json")
    
    if (!new File(anat_jobs_file.toString()).exists()) {
        error "Discovery file not found: ${anat_jobs_file}\n" +
              "Please run the discovery script before starting Nextflow."
    }
    
    Channel.fromPath(anat_jobs_file)
        .splitJson()
        .map { job ->
            def sub = job.subject_id.toString()
            def ses = job.session_id ? job.session_id.toString() : null
            def needs_synth = job.needs_synthesis ?: false
            def file_paths_raw = job.file_paths ?: [job.file_path]
            def file_paths_list = file_paths_raw instanceof List ? file_paths_raw : [file_paths_raw]
            def file_objects = file_paths_list.collect { path_val ->
                file(path_val as String)
            }
            def suffix = job.suffix.toString()
            def needs_t1w_reg = job.needs_t1w_registration ?: false
            def synthesis_type = job.synthesis_type ?: null
            
            [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg, synthesis_type]
        }
        .set { anat_jobs_ch }
    
    // ============================================
    // PREPARE CHANNEL HELPERS
    // ============================================
    def getSingleFilePath = channelHelpers.getSingleFilePath
    def mapSingleFileJob = channelHelpers.mapSingleFileJob
    def isT1wFile = channelHelpers.isT1wFile
    def passThroughAnat = channelHelpers.passThroughAnat
    
    // Extract all subjects from anat_jobs_ch for later use
    anat_jobs_ch
        .map { it[0] }
        .unique()
        .set { anat_subjects_ch }
    
    // ============================================
    // BRANCH JOBS BY TYPE
    // ============================================
    // Split jobs into categories: T1w synthesis, T2w synthesis, T1w single, T2w single
    // Input: anat_jobs_ch: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg, synthesis_type]
    // ============================================
    anat_jobs_ch.branch {
        t1w_synthesis: it[3] == true && it[6] == "t1w"
        t2w_synthesis: it[3] == true && it[6] == "t2w"
        t1w_single: it[3] == false && it[4] == "T1w"
        t2w_single: it[3] == false && it[4] == "T2w"
    }.set { anat_branched }
    
    // ============================================
    // PROCESS T1W SYNTHESIS JOBS
    // ============================================
    // Synthesize multiple T1w runs into single T1w
    // Input: anat_branched.t1w_synthesis: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg, synthesis_type]
    // Output: anat_t1w_synthesis_output: [sub, ses, anat_file, bids_name]
    // ============================================
    def anat_t1w_synthesis_input = anat_branched.t1w_synthesis
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_objects = item[2]
            [sub, ses, file_objects]
        }
    
    def anat_t1w_synthesis_output = Channel.empty()
    ANAT_SYNTHESIS(anat_t1w_synthesis_input, config_file)
    anat_t1w_synthesis_output = ANAT_SYNTHESIS.out.synthesized
        .map { sub, ses, anat_file, bids_naming_template_file ->
            def bids_name = bids_naming_template_file.text.trim()
            [sub, ses, anat_file, bids_name]
        }
    
    // ============================================
    // PROCESS T2W SYNTHESIS JOBS
    // ============================================
    // Synthesize multiple T2w runs into single T2w
    // Input: anat_branched.t2w_synthesis: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg, synthesis_type]
    // Output: anat_t2w_synthesis_output: [sub, ses, anat_file, bids_name, needs_t1w_reg]
    // ============================================
    // Store needs_t1w_reg before synthesis
    def t2w_synthesis_needs_t1w_reg = anat_branched.t2w_synthesis
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def needs_t1w_reg = item[5]
            [sub, ses, needs_t1w_reg]
        }
    
    def anat_t2w_synthesis_input = anat_branched.t2w_synthesis
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_objects = item[2]
            [sub, ses, file_objects]
        }
    
    def anat_t2w_synthesis_output = Channel.empty()
    ANAT_SYNTHESIS_T2W(anat_t2w_synthesis_input, config_file)
    anat_t2w_synthesis_output = ANAT_SYNTHESIS_T2W.out.synthesized
        .map { sub, ses, anat_file, bids_naming_template_file ->
            def bids_name = bids_naming_template_file.text.trim()
            [sub, ses, anat_file, bids_name]
        }
        .join(t2w_synthesis_needs_t1w_reg, by: [0, 1])
        .map { sub, ses, anat_file, bids_name, needs_t1w_reg ->
            [sub, ses, anat_file, bids_name, needs_t1w_reg]
        }
    
    // ============================================
    // PROCESS SINGLE FILE JOBS
    // ============================================
    // Process T1w single files
    // Input: anat_branched.t1w_single: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg, synthesis_type]
    // Output: anat_t1w_jobs: [sub, ses, anat_file, bids_name]
    // ============================================
    anat_branched.t1w_single
        .map(mapSingleFileJob)
        .set { anat_t1w_jobs }
    
    // ============================================
    // COMBINE ALL T1W INPUTS
    // ============================================
    // Merge synthesized and single T1w file jobs for normal processing pipeline
    // Input: anat_t1w_synthesis_output, anat_t1w_jobs: [sub, ses, anat_file, bids_name]
    // Output: anat_input_ch: [sub, ses, anat_file, bids_name]
    // ============================================
    def anat_input_ch = anat_t1w_synthesis_output
        .mix(anat_t1w_jobs)
    
    // ============================================
    // ANATOMICAL PROCESSING PIPELINE
    // ============================================
    // Sequential processing: reorient → conform → bias correction → skull stripping → registration
    // Channel structure maintained: [sub, ses, anat_file, bids_name]
    // ============================================
    
    // ============================================
    // REORIENT
    // ============================================
    // Reorient anatomical images to standard orientation
    // Input: anat_input_ch: [sub, ses, anat_file, bids_name]
    // Output: anat_after_reorient_normal: [sub, ses, anat_file, bids_name]
    // ============================================
    anat_after_reorient_normal = anat_input_ch
    if (anat_reorient_enabled) {
        ANAT_REORIENT(anat_input_ch, config_file)
        anat_after_reorient_normal = ANAT_REORIENT.out.output
    } else {
        anat_after_reorient_normal = anat_input_ch.map(passThroughAnat)
    }
    
    // ============================================
    // BIAS CORRECTION
    // ============================================
    // Correct intensity non-uniformity (bias field)
    // Input: anat_after_reorient_normal: [sub, ses, anat_file, bids_name]
    // Output: anat_after_bias: [sub, ses, anat_file, bids_name]
    // ============================================
    anat_after_bias = anat_after_reorient_normal
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION(anat_after_reorient_normal, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION.out.output
    } else {
        ANAT_BIAS_CORRECTION_PASSTHROUGH(anat_after_reorient_normal, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION_PASSTHROUGH.out.output
    }
    
    // ============================================
    // CONFORM
    // ============================================
    // Conform anatomical images to template space
    // Input: anat_after_bias: [sub, ses, anat_file, bids_name]
    // Output: anat_after_conform: [sub, ses, anat_file, bids_name]
    //         anat_conform_transforms: [sub, ses, forward_xfm, inverse_xfm]
    //         anat_conform_reference: [sub, ses, reference_file]
    // ============================================
    anat_after_conform = anat_after_bias
    anat_conform_transforms = Channel.empty()
    anat_conform_reference = Channel.empty()
    if (anat_conform_enabled) {
        ANAT_CONFORM(anat_after_bias, config_file)
        anat_after_conform = ANAT_CONFORM.out.output
        anat_conform_transforms = ANAT_CONFORM.out.transforms
        anat_conform_reference = ANAT_CONFORM.out.reference
    } else {
        ANAT_CONFORM_PASSTHROUGH(anat_after_bias, config_file)
        anat_after_conform = ANAT_CONFORM_PASSTHROUGH.out.output
        anat_conform_transforms = ANAT_CONFORM_PASSTHROUGH.out.transforms
        anat_conform_reference = ANAT_CONFORM_PASSTHROUGH.out.reference
    }
    
    // ============================================
    // SKULLSTRIPPING
    // ============================================
    // Remove non-brain tissue using deep learning segmentation
    // Input: anat_after_conform: [sub, ses, anat_file, bids_name]
    // Output: anat_after_skull: [sub, ses, anat_file, bids_name]
    //         anat_skull_mask: [sub, ses, brain_mask]
    //         anat_skull_seg: [sub, ses, brain_segmentation]
    // ============================================
    anat_skull_mask = Channel.empty()
    anat_skull_seg = Channel.empty()
    anat_after_skull = Channel.empty()
    if (anat_skullstripping_enabled) {
        ANAT_SKULLSTRIPPING(anat_after_conform, config_file)
        anat_after_skull = ANAT_SKULLSTRIPPING.out.output
        anat_skull_mask = ANAT_SKULLSTRIPPING.out.brain_mask
        anat_skull_seg = ANAT_SKULLSTRIPPING.out.brain_segmentation
    } else {
        anat_after_skull = anat_after_conform.map(passThroughAnat)
    }
    
    // ============================================
    // REGISTRATION
    // ============================================
    // Register anatomical images to template space
    // Compute transform on skullstripped version (for better registration)
    // Apply transform to unskullstripped version (to get full head in template space)
    // Input: anat_after_skull: [sub, ses, anat_file, bids_name] (for computing transform)
    //        anat_after_conform: [sub, ses, anat_file, bids_name] (for applying transform)
    // Output: anat_after_reg: [sub, ses, registered_file, bids_name] (unskullstripped registered)
    //         anat_reg_transforms: [sub, ses, forward_xfm, inverse_xfm]
    //         anat_reg_reference: [sub, ses, reference_file]
    // ============================================
    anat_after_reg = Channel.empty()
    anat_reg_transforms = Channel.empty()
    anat_reg_reference = Channel.empty()
    if (registration_enabled) {
        // Join skullstripped version (for computing transform) with unskullstripped version (for applying transform)
        // ANAT_REGISTRATION expects: [sub, ses, skull_file, bids_name, unskull_file]
        def registration_input = anat_after_skull
            .join(anat_after_conform, by: [0, 1])
            .map { sub, ses, skull_file, skull_bids, unskull_file, unskull_bids ->
                [sub, ses, skull_file, skull_bids, unskull_file]
            }
        
        ANAT_REGISTRATION(registration_input, config_file)
        anat_after_reg = ANAT_REGISTRATION.out.output
        anat_reg_transforms = ANAT_REGISTRATION.out.transforms
        anat_reg_reference = ANAT_REGISTRATION.out.reference
    } else {
        ANAT_REGISTRATION_PASSTHROUGH(anat_after_skull, config_file)
        anat_after_reg = ANAT_REGISTRATION_PASSTHROUGH.out.output
        anat_reg_transforms = ANAT_REGISTRATION_PASSTHROUGH.out.transforms
        anat_reg_reference = ANAT_REGISTRATION_PASSTHROUGH.out.reference
    }
    
    // ============================================
    // MASK TRANSFORMATION
    // ============================================
    // Transform brain mask to template space using registration transform
    // Input: anat_skull_mask: [sub, ses, brain_mask] (in conformed space)
    //        anat_reg_transforms: [sub, ses, forward_xfm, inverse_xfm]
    //        anat_reg_reference: [sub, ses, reference_file]
    // Output: anat_skull_mask_registered: [sub, ses, transformed_mask] (in template space)
    // ============================================
    anat_skull_mask_registered = Channel.empty()
    if (registration_enabled && anat_skullstripping_enabled) {
        // Join mask with registration transform and reference
        def mask_transform_input = anat_skull_mask
            .join(anat_reg_transforms.map { sub, ses, forward_xfm, inverse_xfm -> [sub, ses, forward_xfm] }, by: [0, 1])
            .join(anat_reg_reference, by: [0, 1])
            .map { sub, ses, mask_file, forward_xfm, reference ->
                [sub, ses, mask_file, forward_xfm, reference]
            }
        
        ANAT_APPLY_TRANSFORM_MASK(mask_transform_input, config_file)
        anat_skull_mask_registered = ANAT_APPLY_TRANSFORM_MASK.out.output
    }
    
    // ============================================
    // QUALITY CONTROL
    // ============================================
    // Generate QC reports for anatomical processing steps
    // ============================================
    if (anat_conform_enabled) {
        anat_after_conform
            .join(anat_conform_reference, by: [0, 1])
            .map { sub, ses, anat_file, bids_name, reference ->
                [sub, ses, anat_file, bids_name, reference]
            }
            .set { conform_qc_input }
        QC_CONFORM(conform_qc_input, config_file)
    }
    
    if (anat_bias_correction_enabled) {
        anat_after_reorient_normal
            .join(anat_after_bias, by: [0, 1])
            .map { sub, ses, reoriented_file, bids_name1, bias_corrected_file, bids_name2 ->
                [sub, ses, reoriented_file, bias_corrected_file, bids_name2]
            }
            .set { bias_qc_input }
        QC_BIAS_CORRECTION(bias_qc_input, config_file)
    }
    
    if (anat_skullstripping_enabled) {
        anat_after_conform
            .join(anat_skull_mask, by: [0, 1])
            .map { sub, ses, anat_file, bids_name, mask_file ->
                [sub, ses, anat_file, mask_file, bids_name]
            }
            .set { skull_qc_input }
        QC_SKULLSTRIPPING(skull_qc_input, config_file)
        
        anat_after_skull
            .join(anat_skull_seg, by: [0, 1])
            .map { sub, ses, anat_file, bids_name, seg_file ->
                [sub, ses, anat_file, seg_file, bids_name]
            }
            .set { atlas_qc_input }
        QC_ATLAS_SEGMENTATION(atlas_qc_input, config_file)
    }
    
    if (registration_enabled) {
        anat_after_reg
            .join(anat_reg_reference, by: [0, 1])
            .map { sub, ses, registered_file, bids_name, reference_file ->
                [sub, ses, registered_file, reference_file, bids_name]
            }
            .set { registration_qc_input }

        QC_REGISTRATION(registration_qc_input, config_file)
    }
    
    // ============================================
    // SURFACE RECONSTRUCTION
    // ============================================
    // Generate cortical surfaces and measurements (requires skullstripping)
    // Input: anat_after_conform, anat_skull_seg, anat_skull_mask: [sub, ses, ...]
    // Output: Surface reconstruction outputs and QC
    // ============================================
    def surf_recon_input = Channel.empty()
    def surf_qc_input = Channel.empty()
    if (surf_recon_enabled && anat_skullstripping_enabled) {
        // Step 1: Join conformed image with segmentation
        def surf_recon_input_base = anat_after_conform
            .join(anat_skull_seg, by: [0, 1])
            .map { sub, ses, anat_file, bids_name, seg_file ->
                [sub, ses, anat_file, bids_name, seg_file]
            }
        
        // Step 2: Join with brain mask
        surf_recon_input = surf_recon_input_base
            .join(anat_skull_mask, by: [0, 1])
            .map { sub, ses, anat_file, bids_name, seg_file, mask_file ->
                [sub, ses, anat_file, bids_name, seg_file, mask_file ?: file("")]
            }
        
        ANAT_SURFACE_RECONSTRUCTION(surf_recon_input, config_file)
        
        // Step 3: Prepare QC input channels
        surf_qc_input = ANAT_SURFACE_RECONSTRUCTION.out.subject_dir
            .join(ANAT_SURFACE_RECONSTRUCTION.out.metadata, by: [0, 1])
            .join(surf_recon_input, by: [0, 1])
            .map { sub, ses, subject_dir, metadata_file, anat_file, bids_name, seg_file, mask_file ->
                def atlas_name = "ARM2"
                try {
                    def metadata = new groovy.json.JsonSlurper().parse(metadata_file)
                    atlas_name = metadata.atlas_name ?: "ARM2"
                } catch (Exception e) {
                    println "Warning: Could not read atlas_name from metadata, using default: ${e.message}"
                }
                [sub, ses, subject_dir, bids_name, atlas_name]
            }
        
        // Step 4: Run QC processes
        def surf_tissue_seg_qc_input = surf_qc_input
            .map { sub, ses, subject_dir, bids_name, atlas_name ->
                [sub, ses, subject_dir, bids_name]
            }
        QC_SURF_RECON_TISSUE_SEG(surf_tissue_seg_qc_input, config_file)
        
        QC_CORTICAL_SURF_AND_MEASURES(surf_qc_input, config_file)
    } else {
        if (surf_recon_enabled && !anat_skullstripping_enabled) {
            println "Warning: Surface reconstruction is enabled but skullstripping is disabled. Skipping surface reconstruction."
        }
    }
    
    // ============================================
    // T2W PROCESSING
    // ============================================
    // Process all T2w files (both synthesized and single files)
    // Flow: synthesis → reorient → bias correction → T2w→T1w registration → APPLY phase (for T2w with T1w)
    //       OR: synthesis → reorient → bias correction → STOP (for T2w without T1w)
    // ============================================
    // Step 1: Combine T2w synthesis output with single T2w files
    // anat_t2w_synthesis_output: [sub, ses, anat_file, bids_name, needs_t1w_reg]
    // anat_branched.t2w_single: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg, synthesis_type]
    def anat_t2w_single_jobs = anat_branched.t2w_single
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_objects = item[2]
            def needs_t1w_reg = item[5]
            def anat_file = file_objects instanceof List ? file_objects[0] : file_objects
            def bids_name = anat_file.toString()
            [sub, ses, anat_file, bids_name, needs_t1w_reg]
        }
    
    def anat_t2w_all_jobs = anat_t2w_synthesis_output
        .mix(anat_t2w_single_jobs)
    
    // Step 2: Reorient T2w files
    // Input: anat_t2w_all_jobs: [sub, ses, anat_file, bids_name, needs_t1w_reg]
    // Output: t2w_after_reorient: [sub, ses, anat_file, bids_name, needs_t1w_reg]
    def t2w_after_reorient = anat_t2w_all_jobs
    if (anat_reorient_enabled) {
        anat_t2w_all_jobs
            .map { sub, ses, anat_file, bids_name, needs_t1w_reg ->
                [sub, ses, anat_file, bids_name]
            }
            .set { t2w_for_reorient }
        ANAT_REORIENT_T2W(t2w_for_reorient, config_file)
        t2w_after_reorient = ANAT_REORIENT_T2W.out.output
            .join(anat_t2w_all_jobs.map { sub, ses, anat_file, bids_name, needs_t1w_reg -> [sub, ses, needs_t1w_reg] }, by: [0, 1])
            .map { sub, ses, anat_file, bids_name, needs_t1w_reg ->
                [sub, ses, anat_file, bids_name, needs_t1w_reg]
            }
    } else {
        t2w_after_reorient = anat_t2w_all_jobs
    }
    
    // Step 3: Bias correct T2w files
    // Input: t2w_after_reorient: [sub, ses, anat_file, bids_name, needs_t1w_reg]
    // Output: t2w_after_bias: [sub, ses, anat_file, bids_name, needs_t1w_reg]
    def t2w_after_bias = t2w_after_reorient
    if (anat_bias_correction_enabled) {
        t2w_after_reorient
            .map { sub, ses, anat_file, bids_name, needs_t1w_reg ->
                [sub, ses, anat_file, bids_name]
            }
            .set { t2w_for_bias }
        ANAT_BIAS_CORRECTION_T2W(t2w_for_bias, config_file)
        t2w_after_bias = ANAT_BIAS_CORRECTION_T2W.out.output
            .join(t2w_after_reorient.map { sub, ses, anat_file, bids_name, needs_t1w_reg -> [sub, ses, needs_t1w_reg] }, by: [0, 1])
            .map { sub, ses, anat_file, bids_name, needs_t1w_reg ->
                [sub, ses, anat_file, bids_name, needs_t1w_reg]
            }
    } else {
        t2w_after_bias = t2w_after_reorient
    }
    
    // Step 4: Perform anatomical selection for ALL T2w files
    // Check for T1w matches (same-session or cross-session) for all T2w files
    // Priority: 1) Same session T1w, 2) Cross-session T1w, 3) No T1w (stop processing)
    // Output: [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
    def t2w_all_after_bias = t2w_after_bias
        .map { sub, ses, anat_file, bids_name, needs_t1w_reg ->
            [sub, ses, anat_file, bids_name]
        }
    
    def findUnmatchedT2w = channelHelpers.findUnmatchedT2w
    def t2w_anat_selection = channelHelpers.performT2wAnatomicalSelection(
        t2w_all_after_bias,
        anat_after_bias,
        isT1wFile,
        findUnmatchedT2w
    )
    
    // Step 4b: Split T2w into two paths based on T1w availability
    // Path 1: T2w with T1w (same-session or cross-session) - register to T1w space, then APPLY T1w's transforms
    // Path 2: T2w without T1w - stop after bias correction
    t2w_anat_selection
        .branch {
            with_t1w: it[4] != null  // t1w_file != null
            without_t1w: it[4] == null  // t1w_file == null
        }
        .set { t2w_branched_by_t1w }
    
    // Path 1: T2w with T1w - register to T1w space
    // Input: t2w_branched_by_t1w.with_t1w: [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
    // Output: t2w_after_reg_to_t1w: [sub, ses, t2w_file, t2w_bids_name, anat_ses]
    def t2w_with_t1w_for_reg = t2w_branched_by_t1w.with_t1w
        .map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses ->
            [sub, ses, t2w_file, t2w_bids_name, t1w_file]
        }
        .multiMap { sub, ses, t2w_file, t2w_bids_name, t1w_file ->
            combined: [sub, ses, t2w_file, t2w_bids_name]
            reference: t1w_file
        }
        .set { t2w_reg_multi }
    
    ANAT_T2W_TO_T1W_REGISTRATION(t2w_reg_multi.combined, t2w_reg_multi.reference, config_file)
    def t2w_after_reg_to_t1w = ANAT_T2W_TO_T1W_REGISTRATION.out.output
        .join(t2w_branched_by_t1w.with_t1w
            .map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses -> [sub, ses, anat_ses] }, 
            by: [0, 1])
        .map { sub, ses, t2w_file, t2w_bids_name, anat_ses ->
            [sub, ses, t2w_file, t2w_bids_name, anat_ses]
        }
    
    // Path 2: T2w without T1w - stop after bias correction
    // Input: t2w_branched_by_t1w.without_t1w: [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
    // Output: t2w_without_t1w_final: [sub, ses, t2w_file, t2w_bids_name]
    // (No further processing - stops here)
    def t2w_without_t1w_final = t2w_branched_by_t1w.without_t1w
        .map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses ->
            [sub, ses, t2w_file, t2w_bids_name]
        }
    
    // ============================================
    // T2W APPLY PHASE (only for T2w with T1w)
    // ============================================
    // Apply T1w's computed transforms to T2w
    // Flow: Apply conform → Apply registration
    // ============================================
    
    // Step 5: Apply T1w's conform transform to T2w
    // Input: t2w_after_reg_to_t1w: [sub, ses, t2w_file, t2w_bids_name, anat_ses]
    //        anat_conform_transforms: [sub, ses, forward_xfm, inverse_xfm] (keyed by T1w session)
    //        anat_conform_reference: [sub, ses, reference] (keyed by T1w session)
    // Output: t2w_after_apply_conform: [sub, ses, t2w_file, t2w_bids_name, anat_ses]
    def t2w_after_apply_conform = t2w_after_reg_to_t1w
    if (anat_conform_enabled) {
        // Join T2w with T1w's conform transform by anatomical session
        // IMPORTANT: Use combine() + filter() instead of join() because multiple T2w sessions
        // may reference the SAME T1w session. join() causes race condition, combine() creates
        // all subject-level combinations, then filter keeps only matching anat_ses.
        def anat_conform_data = anat_conform_transforms
            .map { sub, ses, forward_xfm, inverse_xfm -> [sub, ses, forward_xfm] }
            .join(anat_conform_reference, by: [0, 1])
        
        def t2w_for_apply_conform = t2w_after_reg_to_t1w
            .map { sub, ses, t2w_file, t2w_bids_name, anat_ses ->
                [sub, ses, t2w_file, t2w_bids_name, anat_ses]
            }
            .combine(anat_conform_data, by: 0)  // Combine by subject only
            .filter { sub, ses, t2w_file, t2w_bids_name, anat_ses, conform_ses, forward_xfm, reference ->
                anat_ses == conform_ses  // Keep only where T2w's anat_ses matches conform session
            }
            .map { sub, ses, t2w_file, t2w_bids_name, anat_ses, conform_ses, forward_xfm, reference ->
                [sub, ses, t2w_file, t2w_bids_name, forward_xfm, reference, anat_ses]
            }
        
        ANAT_APPLY_CONFORM(t2w_for_apply_conform, config_file)
        t2w_after_apply_conform = ANAT_APPLY_CONFORM.out.output
    } else {
        t2w_after_apply_conform = t2w_after_reg_to_t1w
    }
    
    // Step 6: Apply T1w's registration transform to T2w
    // Input: t2w_after_apply_conform: [sub, ses, t2w_file, t2w_bids_name, anat_ses]
    //        anat_reg_transforms: [sub, ses, forward_xfm, inverse_xfm] (keyed by T1w session)
    //        anat_reg_reference: [sub, ses, reference] (keyed by T1w session)
    // Output: t2w_after_apply_reg: [sub, ses, t2w_file, t2w_bids_name]
    def t2w_after_apply_reg = t2w_after_apply_conform
    if (registration_enabled) {
        // IMPORTANT: Use combine() + filter() instead of join() because multiple T2w sessions
        // may reference the SAME T1w session. join() causes race condition.
        def anat_reg_data = anat_reg_transforms
            .map { sub, ses, forward_xfm, inverse_xfm -> [sub, ses, forward_xfm] }
            .join(anat_reg_reference, by: [0, 1])
        
        def t2w_for_apply_reg = t2w_after_apply_conform
            .map { sub, ses, conformed_t2w, t2w_bids_name, anat_ses ->
                [sub, ses, conformed_t2w, t2w_bids_name, anat_ses]
            }
            .combine(anat_reg_data, by: 0)  // Combine by subject only
            .filter { sub, ses, conformed_t2w, t2w_bids_name, anat_ses, reg_ses, forward_xfm, reference ->
                anat_ses == reg_ses  // Keep only where T2w's anat_ses matches registration session
            }
            .map { sub, ses, conformed_t2w, t2w_bids_name, anat_ses, reg_ses, forward_xfm, reference ->
                [sub, ses, conformed_t2w, t2w_bids_name, forward_xfm, reference]
            }
        
        ANAT_APPLY_TRANSFORMATION(t2w_for_apply_reg, config_file)
        t2w_after_apply_reg = ANAT_APPLY_TRANSFORMATION.out.output
    } else {
        t2w_after_apply_reg = t2w_after_apply_conform
            .map { sub, ses, conformed_t2w, t2w_bids_name, anat_ses ->
                [sub, ses, conformed_t2w, t2w_bids_name]
            }
    }
    
    // Combine T2w outputs (with and without T1w)
    def t2w_final_output = t2w_after_apply_reg
        .mix(t2w_without_t1w_final)
    
    // ============================================
    // T2W QUALITY CONTROL
    // ============================================
    // Two QC snaps for T2w with T1w:
    // 1. T2w→T1w registration QC: T2w in T1w space (after T2w→T1w reg) with T1w brain contours
    // 2. T2w in template space QC: T2w in template space (after all transforms) with template contours
    // ============================================
    
    // Filter T1w skullstripped images for QC
    def t1w_skullstripped = anat_after_skull
        .filter(isT1wFile)
    
    // ============================================
    // QC SNAP 1: T2w→T1w Registration
    // ============================================
    // Underlay: Conformed T2w (after applying conform transform)
    // Overlay: T1w brain (skullstripped T1w) - contours will be generated
    // Input: t2w_after_apply_conform: [sub, ses, t2w_file, t2w_bids_name, anat_ses]
    //        t1w_skullstripped: [sub, ses, t1w_file, t1w_bids_name] (keyed by anatomical session)
    // ============================================
    // IMPORTANT: Use combine() + filter() instead of join() because multiple T2w sessions
    // may reference the SAME T1w session. join() causes race condition.
    def t2w_qc1_input = t2w_after_apply_conform
        .map { sub, ses, t2w_file, t2w_bids_name, anat_ses ->
            [sub, ses, t2w_file, t2w_bids_name, anat_ses]
        }
        .combine(t1w_skullstripped, by: 0)  // Combine by subject only
        .filter { sub, ses, t2w_file, t2w_bids_name, anat_ses, t1w_ses, t1w_file, t1w_bids_name ->
            anat_ses == t1w_ses  // Keep only where T2w's anat_ses matches T1w session
        }
        .map { sub, ses, t2w_file, t2w_bids_name, anat_ses, t1w_ses, t1w_file, t1w_bids_name ->
            [sub, ses, t2w_file, t1w_file, t2w_bids_name]
        }
    
    t2w_qc1_input
        .multiMap { sub, ses, t2w_file, t1w_file, t2w_bids_name ->
            combined: [sub, ses, t2w_file, t1w_file]
            bids_name: t2w_bids_name
        }
        .set { t2w_qc1_channels }
    
    // Call QC process - it will handle empty channels gracefully
    QC_T2W_TO_T1W_REGISTRATION(t2w_qc1_channels.combined, t2w_qc1_channels.bids_name, config_file)
    
    // ============================================
    // QC SNAP 2: T2w in Template Space
    // ============================================
    // Underlay: T2w after all transforms (in template space)
    // Overlay: Template reference - contours will be generated
    // Input: t2w_after_apply_reg: [sub, ses, t2w_file, t2w_bids_name]
    //        t2w_anat_selection: [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses] (to get anat_ses)
    //        anat_reg_reference: [sub, ses, reference] (keyed by anatomical session)
    // ============================================
    // IMPORTANT: Use combine() + filter() instead of join() for the anat_reg_reference join
    // because multiple T2w sessions may reference the SAME T1w session. join() causes race condition.
    def t2w_qc2_input = t2w_after_apply_reg
        .join(t2w_anat_selection
            .filter { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses -> t1w_file != null }
            .map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses -> [sub, ses, anat_ses] },
            by: [0, 1])
        .map { sub, ses, registered_t2w_file, t2w_bids_name, anat_ses ->
            [sub, ses, registered_t2w_file, t2w_bids_name, anat_ses]
        }
        .combine(anat_reg_reference, by: 0)  // Combine by subject only
        .filter { sub, ses, registered_t2w_file, t2w_bids_name, anat_ses, ref_ses, template_ref ->
            anat_ses == ref_ses  // Keep only where T2w's anat_ses matches reference session
        }
        .map { sub, ses, registered_t2w_file, t2w_bids_name, anat_ses, ref_ses, template_ref ->
            [sub, ses, registered_t2w_file, template_ref, t2w_bids_name]
        }
    
    t2w_qc2_input
        .multiMap { sub, ses, t2w_file, template_ref, t2w_bids_name ->
            combined: [sub, ses, t2w_file, template_ref]
            bids_name: t2w_bids_name
        }
        .set { t2w_qc2_channels }
    
    // Call QC process - it will handle empty channels gracefully
    QC_T2W_TEMPLATE_SPACE(t2w_qc2_channels.combined, t2w_qc2_channels.bids_name, config_file)
    
    // ============================================
    // COLLECT QC CHANNELS
    // ============================================
    // Aggregate all QC metadata channels for output
    // ============================================
    anat_qc_channels = Channel.empty()
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
    anat_qc_channels = anat_qc_channels.mix(QC_T2W_TO_T1W_REGISTRATION.out.metadata)
    anat_qc_channels = anat_qc_channels.mix(QC_T2W_TEMPLATE_SPACE.out.metadata)
    
    // ============================================
    // EMIT OUTPUT CHANNELS
    // ============================================
    emit:
    anat_after_skull
    anat_reg_transforms
    anat_reg_reference
    anat_subjects_ch
    anat_qc_channels
}
