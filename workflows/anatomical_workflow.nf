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
include { ANAT_REORIENT } from '../modules/anatomical.nf'
include { ANAT_REORIENT as ANAT_REORIENT_T2W } from '../modules/anatomical.nf'
include { ANAT_CONFORM } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION as ANAT_BIAS_CORRECTION_T2W } from '../modules/anatomical.nf'
include { ANAT_SKULLSTRIPPING } from '../modules/anatomical.nf'
include { ANAT_SURFACE_RECONSTRUCTION } from '../modules/anatomical.nf'
include { ANAT_REGISTRATION } from '../modules/anatomical.nf'
include { ANAT_T2W_TO_T1W_REGISTRATION } from '../modules/anatomical.nf'
include { ANAT_CONFORM_PASSTHROUGH } from '../modules/anatomical.nf'
include { ANAT_BIAS_CORRECTION_PASSTHROUGH } from '../modules/anatomical.nf'
include { ANAT_REGISTRATION_PASSTHROUGH } from '../modules/anatomical.nf'

// Include anatomical QC modules
include { QC_CONFORM } from '../modules/qc.nf'
include { QC_BIAS_CORRECTION } from '../modules/qc.nf'
include { QC_SKULLSTRIPPING } from '../modules/qc.nf'
include { QC_ATLAS_SEGMENTATION } from '../modules/qc.nf'
include { QC_SURF_RECON_TISSUE_SEG } from '../modules/qc.nf'
include { QC_CORTICAL_SURF_AND_MEASURES } from '../modules/qc.nf'
include { QC_REGISTRATION } from '../modules/qc.nf'
include { QC_T2W_TO_T1W_REGISTRATION } from '../modules/qc.nf'

// Load external Groovy files for channel operations
def channelHelpers = evaluate(new File("${projectDir}/workflows/channel_helpers.groovy").text)

// Load parameter resolver
def paramResolver = evaluate(new File("${projectDir}/workflows/param_resolver.groovy").text)

workflow ANAT_WF {
    main:
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
    
    // Initialize parameter resolver (if not already initialized in main.nf)
    // This is safe to call multiple times - it will only load configs once
    try {
        paramResolver.initialize(params, projectDir)
    } catch (Exception e) {
        error "Failed to initialize parameter resolver: ${e.message}"
    }
    
    // Use effective config file (generated in main.nf)
    // This contains all resolved parameters: CLI params → YAML config → defaults.yaml
    def effective_config_path = "${params.output_dir}/nextflow_reports/config.yaml"
    def config_file = file(effective_config_path)
    if (!new File(effective_config_path).exists()) {
        error "Effective config file not found: ${effective_config_path}. Make sure parameter resolver is initialized in main.nf"
    }
    
    // ============================================
    // RESOLVE PARAMETERS (for workflow logic)
    // Priority: CLI params → YAML config → defaults.yaml
    // All defaults come from defaults.yaml - no hardcoded values
    // ============================================
    
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
    println "Effective config: ${effective_config_path}"
    if (subjects_str) println "Subjects filter: ${subjects_str}"
    if (sessions_str) println "Sessions filter: ${sessions_str}"
    if (tasks_str) println "Tasks filter: ${tasks_str}"
    if (runs_str) println "Runs filter: ${runs_str}"
    println "============================================"
    
    println "============================================"
    println "banana Nextflow Pipeline - Anatomical"
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
    def anat_jobs_file = file("${params.output_dir}/nextflow_reports/anatomical_jobs.json")
    
    if (!new File(anat_jobs_file.toString()).exists()) {
        error "Discovery file not found: ${anat_jobs_file}\n" +
              "Please run the discovery script before starting Nextflow."
    }
    
    // ============================================
    // PARSE DISCOVERY RESULTS INTO CHANNELS
    // ============================================
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
            
            [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg]
        }
        .set { anat_jobs_ch }
    
    // ============================================
    // ANATOMICAL PIPELINE
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
    
    // Use branch operator to split jobs into categories
    anat_jobs_ch.branch {
        synthesis: it[3] == true
        t1w_single: it[3] == false && it[4] == "T1w"
        t2w_with_t1w: it[3] == false && it[4] == "T2w" && it[5] == true
        t2w_only: it[3] == false && it[4] == "T2w" && it[5] == false
    }.set { anat_branched }
    
    // Process synthesis jobs
    anat_branched.synthesis
        .map { item ->
            def sub = item[0]
            def ses = item[1]
            def file_objects = item[2]
            [sub, ses, file_objects]
        }
        .set { anat_synthesis_input }
    
    // ANAT_SYNTHESIS
    ANAT_SYNTHESIS(anat_synthesis_input, config_file)
    
    // Process T1w single files
    anat_branched.t1w_single
        .map(mapSingleFileJob)
        .set { anat_t1w_jobs }
    
    // T2w files that need special processing
    anat_branched.t2w_with_t1w
        .map(mapSingleFileJob)
        .set { anat_t2w_with_t1w_jobs }
    
    // T2w-only files
    anat_branched.t2w_only
        .map(mapSingleFileJob)
        .set { anat_t2w_only_jobs }
    
    // Combine T1w and T2w-only jobs for normal processing
    def anat_single_jobs = anat_t1w_jobs
        .mix(anat_t2w_only_jobs)
    
    // Create synthesis output channel
    def anat_synthesis_output = ANAT_SYNTHESIS.out.synthesized
        .map { sub, ses, anat_file, bids_naming_template_file ->
            def bids_naming_template = bids_naming_template_file.text.trim()
            [sub, ses, anat_file, bids_naming_template]
        }
    
    // Combine synthesized and single jobs
    def anat_input_ch = anat_synthesis_output
        .mix(anat_single_jobs)
    
    // ANAT_REORIENT
    anat_after_reorient_normal = anat_input_ch
    if (anat_reorient_enabled) {
        ANAT_REORIENT(anat_input_ch, config_file)
        anat_after_reorient_normal = ANAT_REORIENT.out.output
    } else {
        anat_after_reorient_normal = anat_input_ch.map(passThroughAnat)
    }
    
    // ANAT_CONFORM
    anat_after_conform = anat_after_reorient_normal
    anat_conform_transforms = Channel.empty()
    anat_conform_reference = Channel.empty()
    if (anat_conform_enabled) {
        ANAT_CONFORM(anat_after_reorient_normal, config_file)
        anat_after_conform = ANAT_CONFORM.out.output
        anat_conform_transforms = ANAT_CONFORM.out.transforms
        anat_conform_reference = ANAT_CONFORM.out.reference
    } else {
        ANAT_CONFORM_PASSTHROUGH(anat_after_reorient_normal, config_file)
        anat_after_conform = ANAT_CONFORM_PASSTHROUGH.out.output
        anat_conform_transforms = ANAT_CONFORM_PASSTHROUGH.out.transforms
        anat_conform_reference = ANAT_CONFORM_PASSTHROUGH.out.reference
    }
    
    // ANAT_BIAS_CORRECTION
    anat_after_bias = anat_after_conform
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION(anat_after_conform, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION.out.output
    } else {
        ANAT_BIAS_CORRECTION_PASSTHROUGH(anat_after_conform, config_file)
        anat_after_bias = ANAT_BIAS_CORRECTION_PASSTHROUGH.out.output
    }
    
    // ANAT_SKULLSTRIPPING
    anat_skull_mask = Channel.empty()
    anat_skull_seg = Channel.empty()
    anat_after_skull = Channel.empty()
    if (anat_skullstripping_enabled) {
        ANAT_SKULLSTRIPPING(anat_after_bias, config_file)
        anat_after_skull = ANAT_SKULLSTRIPPING.out.output
        anat_skull_mask = ANAT_SKULLSTRIPPING.out.brain_mask
        anat_skull_seg = ANAT_SKULLSTRIPPING.out.brain_segmentation
    } else {
        anat_after_skull = anat_after_bias.map(passThroughAnat)
    }
    
    // ANAT_REGISTRATION
    anat_after_reg = Channel.empty()
    anat_reg_transforms = Channel.empty()
    anat_reg_reference = Channel.empty()
    if (registration_enabled) {
        ANAT_REGISTRATION(anat_after_skull, config_file)
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
    // QC for anatomical pipeline
    // ============================================
    if (anat_conform_enabled) {
        anat_after_conform
            .join(anat_conform_reference, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, reference ->
                [sub, ses, anat_file, bids_naming_template, reference]
            }
            .set { conform_qc_input }
        QC_CONFORM(conform_qc_input, config_file)
    }
    
    if (anat_bias_correction_enabled) {
        anat_after_conform
            .join(anat_after_bias, by: [0, 1])
            .map { sub, ses, conformed_file, bids_naming_template1, bias_corrected_file, bids_naming_template2 ->
                [sub, ses, conformed_file, bias_corrected_file, bids_naming_template2]
            }
            .set { bias_qc_input }
        QC_BIAS_CORRECTION(bias_qc_input, config_file)
    }
    
    if (anat_skullstripping_enabled) {
        anat_after_bias
            .join(anat_skull_mask, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, mask_file ->
                [sub, ses, anat_file, mask_file, bids_naming_template]
            }
            .set { skull_qc_input }
        QC_SKULLSTRIPPING(skull_qc_input, config_file)
        
        anat_after_skull
            .join(anat_skull_seg, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, seg_file ->
                [sub, ses, anat_file, seg_file, bids_naming_template]
            }
            .set { atlas_qc_input }
        QC_ATLAS_SEGMENTATION(atlas_qc_input, config_file)
    }
    
    if (registration_enabled) {
        anat_after_reg
            .join(anat_reg_reference, by: [0, 1])
            .map { sub, ses, registered_file, bids_template, reference_file ->
                [sub, ses, registered_file, reference_file, bids_template]
            }
            .set { registration_qc_input }

        QC_REGISTRATION(registration_qc_input, config_file)
    }
    
    // ============================================
    // SURFACE RECONSTRUCTION
    // ============================================
    def surf_recon_input = Channel.empty()
    def surf_qc_input = Channel.empty()
    if (surf_recon_enabled && anat_skullstripping_enabled) {
        def surf_recon_input_base = anat_after_bias
            .join(anat_skull_seg, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, seg_file ->
                [sub, ses, anat_file, bids_naming_template, seg_file]
            }
        
        surf_recon_input = surf_recon_input_base
            .join(anat_skull_mask, by: [0, 1])
            .map { sub, ses, anat_file, bids_naming_template, seg_file, mask_file ->
                [sub, ses, anat_file, bids_naming_template, seg_file, mask_file ?: file("")]
            }
        
        ANAT_SURFACE_RECONSTRUCTION(surf_recon_input, config_file)
        
        surf_qc_input = ANAT_SURFACE_RECONSTRUCTION.out.subject_dir
            .join(ANAT_SURFACE_RECONSTRUCTION.out.metadata, by: [0, 1])
            .join(surf_recon_input, by: [0, 1])
            .map { sub, ses, subject_dir, metadata_file, anat_file, bids_naming_template, seg_file, mask_file ->
                def atlas_name = "ARM2"
                try {
                    def metadata = new groovy.json.JsonSlurper().parse(metadata_file)
                    atlas_name = metadata.atlas_name ?: "ARM2"
                } catch (Exception e) {
                    println "Warning: Could not read atlas_name from metadata, using default: ${e.message}"
                }
                [sub, ses, subject_dir, bids_naming_template, atlas_name]
            }
        
        def surf_tissue_seg_qc_input = surf_qc_input
            .map { sub, ses, subject_dir, bids_naming_template, atlas_name ->
                [sub, ses, subject_dir, bids_naming_template]
            }
        QC_SURF_RECON_TISSUE_SEG(surf_tissue_seg_qc_input, config_file)
        
        QC_CORTICAL_SURF_AND_MEASURES(surf_qc_input, config_file)
    } else {
        if (surf_recon_enabled && !anat_skullstripping_enabled) {
            println "Warning: Surface reconstruction is enabled but skullstripping is disabled. Skipping surface reconstruction."
        }
    }
    
    // ============================================
    // T2W SPECIAL PROCESSING (with T1w in same session)
    // ============================================
    def t2w_after_reorient = anat_t2w_with_t1w_jobs
    if (anat_reorient_enabled) {
        ANAT_REORIENT_T2W(anat_t2w_with_t1w_jobs, config_file)
        t2w_after_reorient = ANAT_REORIENT_T2W.out.output
    } else {
        t2w_after_reorient = anat_t2w_with_t1w_jobs.map(passThroughAnat)
    }
    
    def t1w_bias_corrected = anat_after_bias
        .filter(isT1wFile)
    
    def t2w_t1w_joined = t2w_after_reorient
        .join(t1w_bias_corrected, by: [0, 1])
        .map { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            [sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template]
        }
    
    t2w_t1w_joined
        .multiMap { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            combined: [sub, ses, t2w_file, t2w_bids_template]
            reference: t1w_file
        }
        .set { t2w_reg_multi }
    
    ANAT_T2W_TO_T1W_REGISTRATION(t2w_reg_multi.combined, t2w_reg_multi.reference, config_file)
    def t2w_after_reg_to_t1w = ANAT_T2W_TO_T1W_REGISTRATION.out.output
    
    def t2w_after_bias_final = t2w_after_reg_to_t1w
    if (anat_bias_correction_enabled) {
        ANAT_BIAS_CORRECTION_T2W(t2w_after_reg_to_t1w, config_file)
        t2w_after_bias_final = ANAT_BIAS_CORRECTION_T2W.out.output
    } else {
        t2w_after_bias_final = t2w_after_reg_to_t1w.map(passThroughAnat)
    }
    
    // QC for T2w→T1w registration
    def t1w_skullstripped = anat_after_skull
        .filter(isT1wFile)
    
    t2w_after_bias_final
        .join(t1w_skullstripped, by: [0, 1])
        .multiMap { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
            combined: [sub, ses, t2w_file, t1w_file]
            bids_template: t2w_bids_template
        }
        .set { t2w_qc_channels }
    
    QC_T2W_TO_T1W_REGISTRATION(t2w_qc_channels.combined, t2w_qc_channels.bids_template, config_file)
    
    // ============================================
    // COLLECT QC CHANNELS
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
