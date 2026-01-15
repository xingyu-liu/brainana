/*
 * Functional Processing Workflow
 * 
 * Handles all functional processing steps including:
 * - Functional job parsing
 * - Functional processing pipeline (slice timing, reorient, motion correction, despike, bias correction, conform, skull stripping, registration)
 * - Within-session coregistration
 * - Functional QC steps
 */

nextflow.enable.dsl=2

// Include functional processing modules
include { FUNC_REORIENT } from '../modules/functional.nf'
include { FUNC_SLICE_TIMING } from '../modules/functional.nf'
include { FUNC_MOTION_CORRECTION } from '../modules/functional.nf'
include { FUNC_GENERATE_TMEAN } from '../modules/functional.nf'
include { FUNC_DESPIKE } from '../modules/functional.nf'
include { FUNC_BIAS_CORRECTION } from '../modules/functional.nf'
include { FUNC_COMPUTE_CONFORM } from '../modules/functional.nf'
include { FUNC_COMPUTE_BRAIN_MASK } from '../modules/functional.nf'
include { FUNC_COMPUTE_REGISTRATION } from '../modules/functional.nf'
include { FUNC_APPLY_CONFORM } from '../modules/functional.nf'
include { FUNC_APPLY_BRAIN_MASK } from '../modules/functional.nf'
include { FUNC_APPLY_TRANSFORMS } from '../modules/functional.nf'
include { FUNC_WITHIN_SES_COREG } from '../modules/functional.nf'
include { FUNC_AVERAGE_TMEAN } from '../modules/functional.nf'

// Include functional QC modules
include { QC_MOTION_CORRECTION } from '../modules/qc.nf'
include { QC_CONFORM_FUNC } from '../modules/qc.nf'
include { QC_SKULLSTRIPPING_FUNC } from '../modules/qc.nf'
include { QC_REGISTRATION_FUNC } from '../modules/qc.nf'
include { QC_WITHIN_SES_COREG } from '../modules/qc.nf'

// Load external Groovy files
def channelHelpers = evaluate(new File("${projectDir}/workflows/channel_helpers.groovy").text)
def funcChannels = evaluate(new File("${projectDir}/workflows/functional_channels.groovy").text)

// Load parameter resolver
def paramResolver = evaluate(new File("${projectDir}/workflows/param_resolver.groovy").text)

// Load config helpers
def configHelpers = evaluate(new File("${projectDir}/workflows/config_helpers.groovy").text)

workflow FUNC_WF {
    take:
    anat_after_skull  // channel from anatomical workflow
    anat_reg_transforms  // channel from anatomical workflow
    anat_reg_reference  // channel from anatomical workflow (target_final.nii.gz from ANAT_REGISTRATION)
    
    main:
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
    // Priority: CLI params → YAML config → defaults.yaml
    // All defaults come from defaults.yaml - no hardcoded values
    // ============================================
    
    // Resolve YAML-only boolean parameters
    // All defaults come from defaults.yaml
    def func_reorient_enabled = paramResolver.getYamlBool("func.reorient.enabled")
    def func_slice_timing_enabled = paramResolver.getYamlBool("func.slice_timing_correction.enabled")
    def func_motion_correction_enabled = paramResolver.getYamlBool("func.motion_correction.enabled")
    def func_despike_enabled = paramResolver.getYamlBool("func.despike.enabled")
    def func_bias_correction_enabled = paramResolver.getYamlBool("func.bias_correction.enabled")
    def func_conform_enabled = paramResolver.getYamlBool("func.conform.enabled")
    def func_skullstripping_enabled = paramResolver.getYamlBool("func.skullstripping.enabled")
    def func_coreg_runs_within_session = paramResolver.getYamlBool("func.coreg_runs_within_session")
    def registration_enabled = paramResolver.getYamlBool("registration.enabled")
    
    // Helper functions
    def isT1wFile = channelHelpers.isT1wFile
    def passThroughFunc = channelHelpers.passThroughFunc
    def findUnmatched = channelHelpers.findUnmatched
    
    // Parse functional jobs JSON into channel
    // Channel structure: [sub, ses, run_identifier, file_obj, bids_naming_template]
    def func_jobs_file = file("${params.output_dir}/nextflow_reports/functional_jobs.json")
    if (!new File(func_jobs_file.toString()).exists()) {
        error "Discovery file not found: ${func_jobs_file}\n" +
              "Please run the discovery script before starting Nextflow."
    }
    
    def func_jobs_ch = Channel.fromPath(func_jobs_file)
        .splitJson()
        .map { job ->
            def sub = job.subject_id.toString()
            def ses = job.session_id ? job.session_id.toString() : null
            def file_obj = file(job.file_path as String)
            def bids_naming_template = file_obj.toString()
            def run_identifier = channelHelpers.extractRunIdentifier(bids_naming_template)
            [sub, ses, run_identifier, file_obj, bids_naming_template]
        }
    
    def func_coreg_success = false
    
        // SLICE_TIMING
        // Channel structure: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
        def func_after_slice = func_jobs_ch
        if (func_slice_timing_enabled) {
            FUNC_SLICE_TIMING(func_jobs_ch, config_file)
            func_after_slice = FUNC_SLICE_TIMING.out.output
        } else {
            func_after_slice = func_jobs_ch.map(passThroughFunc)
        }

        // REORIENT
        // Channel structure: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
        def func_after_reorient = func_after_slice
        if (func_reorient_enabled) {
            FUNC_REORIENT(func_after_slice, config_file)
            func_after_reorient = FUNC_REORIENT.out.output
        } else {
            func_after_reorient = func_after_slice.map(passThroughFunc)
        }
        
        // MOTION_CORRECTION
        // Channel structure: [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
        def func_after_motion = func_after_reorient
        def func_motion_params = Channel.empty()
        if (func_motion_correction_enabled) {
            FUNC_MOTION_CORRECTION(func_after_reorient, config_file)
            func_after_motion = FUNC_MOTION_CORRECTION.out.output
            func_motion_params = FUNC_MOTION_CORRECTION.out.motion_params
        } else {
            FUNC_GENERATE_TMEAN(func_after_reorient, config_file)
            func_after_motion = FUNC_GENERATE_TMEAN.out.output
        }
        
        // DESPIKE
        def func_after_despike = func_after_motion
        if (func_despike_enabled) {
            FUNC_DESPIKE(func_after_motion, config_file)
            func_after_despike = FUNC_DESPIKE.out.output
        } else {
            func_after_despike = func_after_motion
        }
        
        // WITHIN-SESSION COREGISTRATION
        // ============================================
        // Coregister multiple runs within the same session to a reference run
        // Input: func_after_despike: [sub, ses, run_id, bold_file, tmean_file, bids_template]
        // Output: func_after_coreg: [sub, ses, run_id, bold_file, tmean_file, bids_template]
        // ============================================
        def func_after_coreg = func_after_despike
        def func_coreg_transforms_ch = Channel.empty()
        def func_tmean_averaged_ch = Channel.empty()
        
        if (func_coreg_runs_within_session) {
            def coregChannels = funcChannels.prepareWithinSessionCoregChannels(func_after_despike, Channel)
            
            coregChannels.func_later_runs
                .multiMap { sub, ses, run_identifier, bold, tmean, bids, ref_tmean, ref_run_identifier ->
                    combined: [sub, ses, run_identifier, bold, tmean, bids]
                    reference: ref_tmean
                    ref_run_identifier_val: ref_run_identifier
                }
                .set { func_coreg_multi }
            
            FUNC_WITHIN_SES_COREG(func_coreg_multi.combined, func_coreg_multi.reference, func_coreg_multi.ref_run_identifier_val, config_file)
            func_coreg_transforms_ch = FUNC_WITHIN_SES_COREG.out.transforms
            
            def func_all_coreg = coregChannels.func_first_runs
                .mix(FUNC_WITHIN_SES_COREG.out.output)
                .mix(coregChannels.func_single_run_ses)
            
            def func_for_averaging_ch = func_all_coreg
                .groupTuple(by: [0, 1])
                .map { sub, ses, run_identifier_list, bold_list, tmean_list, bids_list ->
                    def tmean_paths = tmean_list.collect { file -> file.toString() }
                    def tmean_paths_json = groovy.json.JsonOutput.toJson(tmean_paths)
                    def bids_template = bids_list[0]
                    [sub, ses, tmean_paths_json, bids_template]
                }
            
            func_for_averaging_ch
                .multiMap { sub, ses, tmean_paths, bids_template ->
                    tmean_files_input: tmean_paths
                    subject_id_input: sub
                    session_id_input: ses
                    bids_template_input: bids_template
                }
                .set { averagingChannels }
            
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
            
            def func_coreg_qc_input = funcChannels.prepareCoregQCChannels(coregChannels.func_first_runs, func_tmean_averaged_ch)
            QC_WITHIN_SES_COREG(func_coreg_qc_input, config_file)
        }
        
        // ANATOMICAL SELECTION
        // ============================================
        // Select appropriate anatomical reference for each functional job
        // Priority: 1) Same session, 2) Different session (same subject), 3) Dummy (no anatomical)
        // Input: func_after_coreg: [sub, ses, run_id, bold_file, tmean_file, bids_template]
        //        anat_after_skull: [sub, ses, anat_file, bids_template]
        // Output: [sub, ses, run_id, anat_file, anat_ses, is_cross_ses]
        // ============================================
        def dummy_anat = file("${workDir}/dummy_anat.dummy")
        def func_anat_selection = funcChannels.performAnatomicalSelection(
            func_after_coreg,
            anat_after_skull,
            isT1wFile,
            findUnmatched,
            dummy_anat
        )

        // COMPUTE PHASE
        // ============================================
        // Compute transforms and masks on tmean (session-level or per-run)
        // Two paths: session-level (when coreg enabled) vs per-run processing
        // ============================================
        def func_compute_conform_output = Channel.empty()
        def func_compute_conform_transforms = Channel.empty()
        def func_compute_mask_output = Channel.empty()
        def func_compute_reg_output = Channel.empty()
        
        if (func_coreg_runs_within_session && func_coreg_success) {
            // ============================================
            // SESSION-LEVEL COMPUTE PHASE
            // ============================================
            // Process session-level averaged tmean (run_id == "")
            // Input: func_tmean_averaged_ch: [sub, ses, tmean, bids]
            // Output channels maintain structure: [sub, ses, "", ...] (empty run_id)
            // ============================================
            def func_compute_input = func_tmean_averaged_ch
                .map { sub, ses, tmean, bids ->
                    [sub, ses, "", tmean, bids]
                }

            // BIAS_CORRECTION
            def func_after_bias = func_compute_input
            if (func_bias_correction_enabled) {
                FUNC_BIAS_CORRECTION(func_compute_input, config_file)
                func_after_bias = FUNC_BIAS_CORRECTION.out.output
            } else {
                func_after_bias = func_compute_input
            }
            
            if (func_conform_enabled) {

                def func_conform_with_anat = func_after_bias
                    .join(func_anat_selection, by: [0, 1])
                    .map { sub, ses, run_id, tmean, bids, run_id2, anat_file, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, tmean, bids, anat_file]
                    }
                
                func_conform_with_anat
                    .multiMap { sub, ses, run_id, tmean, bids, anat_file ->
                        combined: [sub, ses, run_id, tmean, bids]
                        reference: anat_file
                    }
                    .set { func_compute_conform_multi }

                FUNC_COMPUTE_CONFORM(func_compute_conform_multi.combined, func_compute_conform_multi.reference, config_file)
                func_compute_conform_output = FUNC_COMPUTE_CONFORM.out.output
                func_compute_conform_transforms = FUNC_COMPUTE_CONFORM.out.transforms
            } else {
                func_compute_conform_output = func_after_bias
                    .map { sub, ses, run_id, tmean, bids ->
                        [sub, ses, run_id, tmean, bids]
                    }
                def dummy_forward_transform = file("${workDir}/dummy_conform_forward_transform.dummy")
                def dummy_inverse_transform = file("${workDir}/dummy_conform_inverse_transform.dummy")
                func_compute_conform_transforms = func_after_bias
                    .map { sub, ses, run_id, tmean, bids ->
                        [sub, ses, run_id, dummy_forward_transform, dummy_inverse_transform]
                    }
            }
            
            if (func_skullstripping_enabled) {
                def func_compute_mask_input = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids ->
                        [sub, ses, run_id, conformed_tmean, bids]
                    }
                
                FUNC_COMPUTE_BRAIN_MASK(func_compute_mask_input, config_file)
                func_compute_mask_output = FUNC_COMPUTE_BRAIN_MASK.out.output
            } else {
                func_compute_mask_output = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids ->
                        def dummy_mask = file("${workDir}/dummy_brain_mask.dummy")
                        [sub, ses, run_id, conformed_tmean, bids, dummy_mask]
                    }
            }
            
            if (registration_enabled) {

                def func_compute_reg_input = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        [sub, ses, run_id, masked_tmean, bids]
                    }
                    .join(func_anat_selection, by: [0, 1])
                    .map { sub, ses, run_id, masked_tmean, bids, run_id2, anat_file, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses]
                    }

                func_compute_reg_input
                    .multiMap { sub, ses, run_id, masked_tmean, bids, anat_file, anat_ses, is_cross_ses ->
                        combined: [sub, ses, run_id, masked_tmean, bids, anat_ses, is_cross_ses]
                        reference: anat_file
                    }
                    .set { func_compute_reg_multi }

                FUNC_COMPUTE_REGISTRATION(func_compute_reg_multi.combined, func_compute_reg_multi.reference, config_file)
                func_compute_reg_output = FUNC_COMPUTE_REGISTRATION.out.output
            } else {
                func_compute_reg_output = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        def dummy_transform = file("${workDir}/dummy_reg_transform.dummy")
                        [sub, ses, run_id, masked_tmean, bids, dummy_transform, "", false]
                    }
            }
            
        } else {
            // ============================================
            // PER-RUN COMPUTE PHASE
            // ============================================
            // Process each run's tmean separately
            // Input: func_after_coreg: [sub, ses, run_id, bold_file, tmean_file, bids_template]
            // Output channels maintain structure: [sub, ses, run_id, ...]
            // ============================================
            def func_compute_input = func_after_coreg
                .map { sub, ses, run_id, bold, tmean, bids ->
                    [sub, ses, run_id, tmean, bids]
                }

            // BIAS_CORRECTION
            def func_after_bias = func_compute_input
            if (func_bias_correction_enabled) {
                FUNC_BIAS_CORRECTION(func_compute_input, config_file)
                func_after_bias = FUNC_BIAS_CORRECTION.out.output
            } else {
                func_after_bias = func_compute_input
            }
            
            if (func_conform_enabled) {
                def func_conform_with_anat = func_after_bias
                    .join(func_anat_selection, by: [0, 1, 2])
                    .map { sub, ses, run_id, tmean, bids, anat_file, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, tmean, bids, anat_file]
                    }
                
                func_conform_with_anat
                    .multiMap { sub, ses, run_id, tmean, bids, anat_file ->
                        combined: [sub, ses, run_id, tmean, bids]
                        reference: anat_file
                    }
                    .set { func_compute_conform_multi }
                
                FUNC_COMPUTE_CONFORM(func_compute_conform_multi.combined, func_compute_conform_multi.reference, config_file)
                func_compute_conform_output = FUNC_COMPUTE_CONFORM.out.output
                func_compute_conform_transforms = FUNC_COMPUTE_CONFORM.out.transforms
            } else {
                func_compute_conform_output = func_after_bias
                    .map { sub, ses, run_id, tmean, bids ->
                        [sub, ses, run_id, tmean, bids]
                    }
                def dummy_forward_transform = file("${workDir}/dummy_conform_forward_transform.dummy")
                def dummy_inverse_transform = file("${workDir}/dummy_conform_inverse_transform.dummy")
                func_compute_conform_transforms = func_after_bias
                    .map { sub, ses, run_id, tmean, bids ->
                        [sub, ses, run_id, dummy_forward_transform, dummy_inverse_transform]
                    }
            }
            
            if (func_skullstripping_enabled) {
                def func_compute_mask_input = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids ->
                        [sub, ses, run_id, conformed_tmean, bids]
                    }
                
                FUNC_COMPUTE_BRAIN_MASK(func_compute_mask_input, config_file)
                func_compute_mask_output = FUNC_COMPUTE_BRAIN_MASK.out.output
            } else {
                func_compute_mask_output = func_compute_conform_output
                    .map { sub, ses, run_id, conformed_tmean, bids ->
                        def dummy_mask = file("${workDir}/dummy_brain_mask.dummy")
                        [sub, ses, run_id, conformed_tmean, bids, dummy_mask]
                    }
            }
            
            if (registration_enabled) {
                def func_compute_reg_input = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        [sub, ses, run_id, masked_tmean, bids]
                    }
                    .join(func_anat_selection, by: [0, 1, 2])
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
                func_compute_reg_output = FUNC_COMPUTE_REGISTRATION.out.output
            } else {
                func_compute_reg_output = func_compute_mask_output
                    .map { sub, ses, run_id, masked_tmean, bids, mask ->
                        def dummy_transform = file("${workDir}/dummy_reg_transform.dummy")
                        [sub, ses, run_id, masked_tmean, bids, dummy_transform, "", false]
                    }
            }
        }
        
        // APPLY PHASE
        // ============================================
        // Apply computed transforms to full BOLD 4D data
        // Input: func_after_coreg: [sub, ses, run_id, bold_file, tmean_file, bids_template]
        // Output: func_apply_reg: [sub, ses, run_id, registered_bold, registered_boldref, bids]
        // ============================================
        def func_apply_bold_input = func_after_coreg
        
        // APPLY CONFORM
        // ============================================
        // Apply conform transform to BOLD data
        // Input: func_apply_bold_input: [sub, ses, run_id, bold_file, tmean_file, bids_template]
        //        func_compute_conform_output: [sub, ses, run_id, conformed_tmean, bids]
        //        func_compute_conform_transforms: [sub, ses, run_id, forward_xfm, inverse_xfm]
        // Output: [sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids]
        // ============================================
        def func_apply_conform_output = Channel.empty()
        if (func_conform_enabled) {
            def func_apply_conform_input
            if (func_coreg_runs_within_session && func_coreg_success) {
                func_apply_conform_input = func_apply_bold_input
                    .combine(
                        func_compute_conform_output,
                        by: [0, 1]
                    )
                    .combine(
                        func_compute_conform_transforms
                            .map { sub, ses, run_id, func2target_xfm, inverse_transform ->
                                [sub, ses, func2target_xfm]
                            },
                        by: [0, 1]
                    )
                    .map { sub, ses, run_id, bold, tmean, bids, run_id2, conformed_tmean, bids2, func2target_xfm ->
                        [sub, ses, run_id, bold, func2target_xfm, conformed_tmean, bids]
                    }

            } else {
                func_apply_conform_input = func_apply_bold_input
                    .join(
                        func_compute_conform_output,
                        by: [0, 1, 2]
                    )
                    .join(
                        func_compute_conform_transforms
                            .map { sub, ses, run_id, func2target_xfm, inverse_transform ->
                                [sub, ses, run_id, func2target_xfm]
                            },
                        by: [0, 1, 2]
                    )
                    .map { sub, ses, run_id, bold, tmean, bids, conformed_tmean, bids2,func2target_xfm ->
                        [sub, ses, run_id, bold, func2target_xfm, conformed_tmean, bids]
                    }
            }
            
            FUNC_APPLY_CONFORM(func_apply_conform_input, config_file)
            func_apply_conform_output = FUNC_APPLY_CONFORM.out.output
        } else {
            func_apply_conform_output = func_apply_bold_input
                .map { sub, ses, run_id, bold, tmean, bids ->
                    def dummy_tmean_ref = file("${workDir}/dummy_tmean_ref.dummy")
                    [sub, ses, run_id, bold, dummy_tmean_ref, bids]
                }
        }
        
        // APPLY REG
        // ============================================
        // Registration application phase: Apply computed transforms to BOLD data
        // Input: func_apply_conform_output: [sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids]
        // Output: func_apply_reg: [sub, ses, run_id, registered_bold, registered_boldref, bids]
        // ============================================
        def func_apply_reg = func_apply_conform_output
        def func_apply_reg_reference = Channel.empty()
        if (registration_enabled) {

            // ============================================
            // PREPARE ANATOMICAL REGISTRATION DATA
            // ============================================
            // Combine anatomical registration transforms and reference into single channel
            // Input channels:
            //   - anat_reg_transforms: [sub, ses, anat2template_xfm, inverse_transform]
            //   - anat_reg_reference: [sub, ses, ref_from_anat_reg]
            // Output: anat_reg_all_real: [sub, ses, anat2template_xfm, ref_from_anat_reg]
            def anat_reg_transforms_forward = anat_reg_transforms
                .map { sub, ses, anat2template_xfm, inverse_transform ->
                    [sub, ses, anat2template_xfm]
                }
            
            def anat_reg_all_real = anat_reg_transforms_forward
                .join(anat_reg_reference, by: [0, 1])
                .map { sub, ses, anat2template_xfm, ref_from_anat_reg -> 
                    [sub, ses, anat2template_xfm, ref_from_anat_reg]
                }
            
            // ============================================
            // MAP FUNCTIONAL TO ANATOMICAL SESSIONS
            // ============================================
            // Extract session mapping from func_compute_reg_output
            // Structure: [sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses]
            // Output: [sub, ses_func, anat_ses, is_cross_ses] unique by [sub, ses_func]
            def func_ses_mapping = func_compute_reg_output
                .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses ->
                    [sub, ses, anat_ses, is_cross_ses]
                }
                .unique { sub, ses, anat_ses, is_cross_ses -> [sub, ses] }

            // Split into same-session and cross-session cases
            // Same-session: functional and anatomical data in same session
            def func_ses_same = func_ses_mapping
                .filter { sub, ses, anat_ses, is_cross_ses -> !is_cross_ses }
                .map { sub, ses, anat_ses, is_cross_ses -> [sub, ses] }
            
            // Cross-session: functional data uses anatomical from different session
            def func_ses_cross = func_ses_mapping
                .filter { sub, ses, anat_ses, is_cross_ses -> is_cross_ses }
                .map { sub, ses, anat_ses, is_cross_ses -> [sub, ses, anat_ses] }

            // ============================================
            // JOIN ANATOMICAL REGISTRATION BY SESSION
            // ============================================
            // Case 1: Same-session - join anat_reg_all_real by [sub, ses]
            // Output: [sub, ses, xfm, ref]
            def anat_reg_same_ses = func_ses_same
                .join(anat_reg_all_real, by: [0, 1])
                .map { sub, ses, xfm, ref -> [sub, ses, xfm, ref] }

            // Case 2: Cross-session - join anat_reg_all_real by [sub, anat_ses], then map back to func ses
            // Output: [sub, ses_func, xfm, ref]
            def anat_reg_cross_ses = func_ses_cross
                .map { sub, ses_func, anat_ses -> [sub, anat_ses, ses_func] }  // Reorder for joining
                .join(anat_reg_all_real, by: [0, 1])
                .map { sub, anat_ses, ses_func, xfm, ref -> [sub, ses_func, xfm, ref] }  // Map back to func session

            // ============================================
            // CREATE DUMMY REGISTRATION FOR MISSING DATA
            // ============================================
            // Create dummy anat_reg_all for functional subjects/sessions without anatomical data
            def subjects_sessions = func_compute_reg_output
                .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses ->
                    [sub, ses]
                }
                .unique()

            def dummy_anat2template_xfm = file("${workDir}/dummy_anat2template_xfm.dummy")
            def dummy_anat_reg_ref = file("${workDir}/dummy_anat_reg_ref.dummy")
            def anat_reg_all_dummy = subjects_sessions
                .map { sub, ses -> [sub, ses, dummy_anat2template_xfm, dummy_anat_reg_ref] }

            // ============================================
            // COMBINE ALL ANATOMICAL REGISTRATION DATA
            // ============================================
            // Mix all channels (same-session real, cross-session real, and dummy), then group by [sub, ses]
            // and select real over dummy
            // Output: [sub, ses, xfm, ref] where xfm/ref are real files if available, dummy otherwise
            def anat_reg_all = anat_reg_same_ses
                .mix(anat_reg_cross_ses)
                .mix(anat_reg_all_dummy)
                .map { sub, ses, xfm, ref ->
                    // Wrap xfm and ref into nested tuple so groupTuple preserves the pairing
                    [sub, ses, [xfm, ref]]
                }
                .groupTuple(by: [0, 1])
                .map { sub, ses, entries ->
                    // entries is now a list of [xfm, ref] tuples
                    // Prefer first non-dummy entry, or first entry if all are dummy
                    def selected = entries.find { xfm, ref ->
                        !(xfm.toString().contains('.dummy') || ref.toString().contains('.dummy'))
                    } ?: entries[0]
                    [sub, ses] + selected
                }
                .map { sub, ses, xfm, ref ->
                    [sub, ses, xfm, ref]
                }
            
            // // debug print 
            // anat_reg_all.view { tuple ->
            //     "DEBUG [FUNC_APPLY_TRANSFORMS: anat_reg_all]: ${tuple}"
            // }
            
            def func_apply_reg_input
            def func_apply_reg_with_bold
            if (func_coreg_runs_within_session && func_coreg_success) {
                // Session-level compute outputs (run_id == "") joined with transforms and reference
                // FUNC_COMPUTE_REGISTRATION.out.transforms is now: [sub, ses, run_id, func2target_xfm, inverse_transform]
                // FUNC_COMPUTE_REGISTRATION.out.reference is now: [sub, ses, run_id, ref_from_anat_reg]                
                def func_reg_with_ref = func_compute_reg_output
                    .combine(FUNC_COMPUTE_REGISTRATION.out.transforms, by: [0, 1])
                    .combine(FUNC_COMPUTE_REGISTRATION.out.reference, by: [0, 1])
                    .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses, run_id2, func2target_xfm, inverse_xfm, run_id3, ref_from_func_reg ->
                        [sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg]
                    }

                // Single combine with anat_reg_all (replaces two separate joins)
                def all_reg_with_ref = func_reg_with_ref
                    .combine(anat_reg_all, by: [0, 1])
                    .map { sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg ->
                        [sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
                    }

                func_apply_reg_with_bold = func_apply_conform_output
                    .combine(all_reg_with_ref, by: [0, 1])
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids, run_id2, registered_tmean, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg ->
                        [sub, ses, run_id, conformed_bold, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
                    }

            } else {
                // ============================================
                // PER-RUN PROCESSING PATH
                // ============================================
                // Per-run compute outputs joined with transforms and reference
                // Input channels:
                //   - func_compute_reg_output: [sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses]
                //   - FUNC_COMPUTE_REGISTRATION.out.transforms: [sub, ses, run_id, func2target_xfm, inverse_transform]
                //   - FUNC_COMPUTE_REGISTRATION.out.reference: [sub, ses, run_id, ref_from_anat_reg]
                // Output: [sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat_ses, is_cross_ses]
                def func_reg_with_ref = func_compute_reg_output
                    .join(FUNC_COMPUTE_REGISTRATION.out.transforms, by: [0, 1, 2])
                    .join(FUNC_COMPUTE_REGISTRATION.out.reference, by: [0, 1, 2])
                    .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses, func2target_xfm, inverse_xfm, ref_from_func_reg ->
                        [sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat_ses, is_cross_ses]
                    }
                
                // Combine with anatomical registration data
                // Output: [sub, ses, run_id, registered_tmean, func2target_xfm, anat2template_xfm, ref_from_func_reg, ref_from_anat_reg, anat_ses, is_cross_ses]
                def func_reg_with_anat = func_reg_with_ref
                    .combine(anat_reg_all, by: [0, 1])
                    .map { sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat_ses, is_cross_ses, anat2template_xfm, ref_from_anat_reg ->
                        [sub, ses, run_id, registered_tmean, func2target_xfm, anat2template_xfm, ref_from_func_reg, ref_from_anat_reg, anat_ses, is_cross_ses]
                    }
                
                // Join with conformed BOLD data for application
                // Input: func_apply_conform_output: [sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids]
                // Output: [sub, ses, run_id, conformed_bold, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
                func_apply_reg_with_bold = func_apply_conform_output
                    .join(func_reg_with_anat, by: [0, 1, 2])
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids, registered_tmean, func2target_xfm, anat2template_xfm, ref_from_func_reg, ref_from_anat_reg, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, conformed_bold, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
                    }
                // // debug print
                // func_apply_reg_with_bold.first().view { tuple ->
                //     "DEBUG [FUNC_APPLY_TRANSFORMS: func_apply_reg_with_bold]: ${tuple}"
                // }
            }

            // ============================================
            // SPLIT CHANNELS FOR FUNC_APPLY_TRANSFORMS
            // ============================================
            // Split into registration parameters and BOLD file for process input
            // Input: func_apply_reg_with_bold: [sub, ses, run_id, conformed_bold, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
            // Output channels:
            //   - reg_combined: [sub, ses, run_id, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
            //   - func_4d_file: conformed_bold (separate channel for 4D file)
            func_apply_reg_with_bold
                .multiMap { sub, ses, run_id, conformed_bold, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg ->
                    reg_combined: [sub, ses, run_id, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
                    func_4d_file: conformed_bold
                }
                .set { func_apply_reg_multi }
            
            // Apply transforms to BOLD data
            // Output: func_apply_reg: [sub, ses, run_id, registered_bold, registered_boldref, bids]
            //         func_apply_reg_reference: [sub, ses, run_id, target_final] (for QC)
            FUNC_APPLY_TRANSFORMS(func_apply_reg_multi.reg_combined, func_apply_reg_multi.func_4d_file, config_file)
            func_apply_reg = FUNC_APPLY_TRANSFORMS.out.output
            func_apply_reg_reference = FUNC_APPLY_TRANSFORMS.out.reference
        }

        // ================================
        // QC for functional
        // ================================
        if (func_motion_correction_enabled) {
            func_after_motion
                .join(func_motion_params, by: [0, 1, 2])
                .map { sub, ses, run_identifier, bold_file, tmean_file, bids_template, motion_file ->
                    [sub, ses, run_identifier, motion_file, tmean_file, bids_template]
                }
                .set { motion_qc_input }
            QC_MOTION_CORRECTION(motion_qc_input, config_file)
        }
        
        if (func_conform_enabled) {
            // Join conform output with reference
            // func_apply_conform_output: [sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids_template]
            // FUNC_COMPUTE_CONFORM.out.reference: [sub, ses, run_id, reference.nii.gz]
            // When coreg is enabled, compute phase is session-level (run_id == ""), so combine by [0, 1] instead of [0, 1, 2]
            if (func_coreg_runs_within_session && func_coreg_success) {
                func_apply_conform_output
                    .combine(FUNC_COMPUTE_CONFORM.out.reference, by: [0, 1])
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids_template, run_id2, reference ->
                        // QC expects: [sub, ses, run_id, conformed_file, bids_template, reference_file]
                        [sub, ses, run_id, conformed_tmean_ref, bids_template, reference]
                    }
                    .set { func_conform_qc_input }
            } else {
                func_apply_conform_output
                    .join(FUNC_COMPUTE_CONFORM.out.reference, by: [0, 1, 2])
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids_template, reference ->
                        // QC expects: [sub, ses, run_id, conformed_file, bids_template, reference_file]
                        [sub, ses, run_id, conformed_tmean_ref, bids_template, reference]
                    }
                    .set { func_conform_qc_input }
            }
            QC_CONFORM_FUNC(func_conform_qc_input, config_file)
        }
        
        if (func_skullstripping_enabled) {
            def func_skull_qc_input
            if (func_coreg_runs_within_session && func_coreg_success) {
                // Session-level compute phase: FUNC_COMPUTE_BRAIN_MASK.out.output has run_id == ""
                func_skull_qc_input = func_apply_conform_output
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids ->
                        [sub, ses, run_id, conformed_tmean_ref, bids]
                    }
                    .combine(
                        FUNC_COMPUTE_BRAIN_MASK.out.output
                            .map { sub, ses, run_id, masked_tmean, bids, brain_mask ->
                                [sub, ses, brain_mask]
                            },
                        by: [0, 1]
                    )
                    .map { sub, ses, run_id, conformed_tmean_ref, bids, brain_mask ->
                        [sub, ses, run_id, conformed_tmean_ref, brain_mask, bids]
                    }
            } else {
                // Per-run compute phase: FUNC_COMPUTE_BRAIN_MASK.out.output has run-level items
                func_skull_qc_input = func_apply_conform_output
                    .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids ->
                        [sub, ses, run_id, conformed_tmean_ref, bids]
                    }
                    .join(
                        FUNC_COMPUTE_BRAIN_MASK.out.output
                            .map { sub, ses, run_id, masked_tmean, bids, brain_mask ->
                                [sub, ses, run_id, brain_mask]
                            },
                        by: [0, 1, 2]
                    )
                    .map { sub, ses, run_id, conformed_tmean_ref, bids, brain_mask ->
                        [sub, ses, run_id, conformed_tmean_ref, brain_mask, bids]
                    }
            }
            QC_SKULLSTRIPPING_FUNC(func_skull_qc_input, config_file)
        }

        if (registration_enabled) {
            func_apply_reg
                .join(func_apply_reg_reference, by: [0, 1, 2])
                .map { sub, ses, run_identifier, registered_bold, registered_boldref, bids_template, reference_file ->
                    [sub, ses, run_identifier, registered_boldref, reference_file]
                }
                .set { func_reg_qc_input }
            QC_REGISTRATION_FUNC(func_reg_qc_input, config_file)
        }
    
    // Collect functional QC channels
    func_qc_channels = Channel.empty()
    func_jobs_ch_out = Channel.empty()
    
    func_jobs_ch_out = func_jobs_ch
    if (func_motion_correction_enabled) {
        func_qc_channels = func_qc_channels.mix(QC_MOTION_CORRECTION.out.metadata)
    }
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

    emit:
    func_qc_channels
    func_jobs_ch_out
}
