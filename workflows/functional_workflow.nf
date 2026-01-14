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

workflow FUNC_WF {
    take:
    anat_after_skull  // channel from anatomical workflow
    anat_reg_transforms  // channel from anatomical workflow
    anat_reg_reference  // channel from anatomical workflow (target_final.nii.gz from ANAT_REGISTRATION)
    anat_only_ch  // channel with anat_only boolean value (kept for API compatibility)
    
    main:
    // Read anat_only directly from config/params instead of trying to extract from async channel
    // Nextflow channels are asynchronous, so extracting values in workflow definition blocks
    // returns DataflowVariable objects, not the actual values
    def config_file_path = params.config_file ?: "${projectDir}/macacaMRIprep/config/defaults.yaml"
    def batch_script = "${projectDir}/macacaMRIprep/nextflow_scripts/read_yaml_config.py"
    
    // Read anat_only from config
    def anat_only_from_config = false
    try {
        def cmd = ["python3", batch_script, config_file_path, "general.anat_only", "--defaults=false"]
        def proc = cmd.execute()
        def output = new StringBuffer()
        proc.consumeProcessOutput(output, new StringBuffer())
        proc.waitFor()
        if (proc.exitValue() == 0) {
            anat_only_from_config = output.toString().trim() == "true"
        }
    } catch (Exception e) {
        // Use default if config read fails
    }
    
    // params.anat_only takes precedence over config file
    def anat_only = (params.anat_only != null && params.anat_only == true) ? true : anat_only_from_config
    
    // Read config file to get functional flags (reuse config_file_path and batch_script from above)
    def func_config_keys = [
        "func.reorient.enabled",
        "func.slice_timing_correction.enabled",
        "func.motion_correction.enabled",
        "func.despike.enabled",
        "func.bias_correction.enabled",
        "func.conform.enabled",
        "func.skullstripping.enabled",
        "func.coreg_runs_within_session",
        "registration.enabled"
    ]
    def func_config_defaults = ["true", "true", "true", "true", "true", "true", "true", "false", "true"]
    
    def func_config_values = [:]
    try {
        def cmd = ["python3", batch_script, config_file_path] + func_config_keys + ["--defaults=" + func_config_defaults.join(",")]
        def proc = cmd.execute()
        def output = new StringBuffer()
        proc.consumeProcessOutput(output, new StringBuffer())
        proc.waitFor()
        if (proc.exitValue() == 0) {
            def results = output.toString().trim().split('\t')
            func_config_keys.eachWithIndex { key, idx ->
                func_config_values[key] = results[idx] == "true"
            }
        } else {
            func_config_keys.eachWithIndex { key, idx ->
                func_config_values[key] = func_config_defaults[idx] == "true"
            }
        }
    } catch (Exception e) {
        func_config_keys.eachWithIndex { key, idx ->
            func_config_values[key] = func_config_defaults[idx] == "true"
        }
    }
    
    def readYamlBool = { key_path, default_bool ->
        return func_config_values.get(key_path, default_bool) as Boolean
    }
    
    def func_reorient_enabled = readYamlBool("func.reorient.enabled", true)
    def func_slice_timing_enabled = readYamlBool("func.slice_timing_correction.enabled", true)
    def func_motion_correction_enabled = readYamlBool("func.motion_correction.enabled", true)
    def func_despike_enabled = readYamlBool("func.despike.enabled", true)
    def func_bias_correction_enabled = readYamlBool("func.bias_correction.enabled", true)
    def func_conform_enabled = readYamlBool("func.conform.enabled", true)
    def func_skullstripping_enabled = readYamlBool("func.skullstripping.enabled", true)
    def func_coreg_runs_within_session = readYamlBool("func.coreg_runs_within_session", false)
    def registration_enabled = readYamlBool("registration.enabled", true)
    
    // Load config file (config_file_path already defined above)
    def config_file = file(config_file_path)
    
    // Helper functions
    def isT1wFile = channelHelpers.isT1wFile
    def passThroughFunc = channelHelpers.passThroughFunc
    def findUnmatched = channelHelpers.findUnmatched
    
    // Parse functional jobs JSON into channel
    def func_jobs_ch
    if (!anat_only) {
        def func_jobs_file = file("${params.output_dir}/nextflow_reports/functional_jobs.json")
        if (!new File(func_jobs_file.toString()).exists()) {
            error "Discovery file not found: ${func_jobs_file}\n" +
                  "Please run the discovery script before starting Nextflow."
        }
        
        func_jobs_ch = Channel.fromPath(func_jobs_file)
            .splitJson()
            .map { job ->
                def sub = job.subject_id.toString()
                def ses = job.session_id ? job.session_id.toString() : null
                def file_obj = file(job.file_path as String)
                def bids_naming_template = file_obj.toString()
                def run_identifier = channelHelpers.extractRunIdentifier(bids_naming_template)
                [sub, ses, run_identifier, file_obj, bids_naming_template]
            }
    } else {
        func_jobs_ch = Channel.empty()
    }
    
    def func_coreg_success = false
    
    if (!anat_only) {
        // SLICE_TIMING
        def func_after_slice = func_jobs_ch
        if (func_slice_timing_enabled) {
            FUNC_SLICE_TIMING(func_jobs_ch, config_file)
            func_after_slice = FUNC_SLICE_TIMING.out.output
        } else {
            func_after_slice = func_jobs_ch.map(passThroughFunc)
        }

        // REORIENT
        def func_after_reorient = func_after_slice
        if (func_reorient_enabled) {
            FUNC_REORIENT(func_after_slice, config_file)
            func_after_reorient = FUNC_REORIENT.out.output
        } else {
            func_after_reorient = func_after_slice.map(passThroughFunc)
        }
        
        // MOTION_CORRECTION
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
        
        // BIAS_CORRECTION
        def func_after_bias = func_after_despike
        if (func_bias_correction_enabled) {
            FUNC_BIAS_CORRECTION(func_after_despike, config_file)
            func_after_bias = FUNC_BIAS_CORRECTION.out.output
        } else {
            func_after_bias = func_after_despike
        }
        
        // WITHIN-SESSION COREGISTRATION
        def func_after_coreg = func_after_bias
        def func_coreg_transforms_ch = Channel.empty()
        def func_tmean_averaged_ch = Channel.empty()
        
        if (func_coreg_runs_within_session) {
            def coregChannels = funcChannels.prepareWithinSessionCoregChannels(func_after_bias, Channel)
            
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
        def dummy_anat = file("${workDir}/dummy_anat.dummy")
        def func_anat_selection = funcChannels.performAnatomicalSelection(
            func_after_coreg,
            anat_after_skull,
            isT1wFile,
            findUnmatched,
            dummy_anat
        )

        // COMPUTE PHASE
        def func_compute_conform_output = Channel.empty()
        def func_compute_conform_transforms = Channel.empty()
        def func_compute_mask_output = Channel.empty()
        def func_compute_reg_output = Channel.empty()
        
        if (func_coreg_runs_within_session && func_coreg_success) {
            // SESSION-LEVEL COMPUTE PHASE
            def func_compute_input = func_tmean_averaged_ch
                .map { sub, ses, tmean, bids ->
                    def dummy_bold = file("${workDir}/dummy_bold_${sub}_${ses}.dummy")
                    [sub, ses, "", dummy_bold, tmean, bids]
                }
            
            if (func_conform_enabled) {

                def func_conform_with_anat = func_compute_input
                    .join(func_anat_selection, by: [0, 1])
                    .map { sub, ses, run_id, bold, tmean, bids, run_id2, anat_file, anat_ses, is_cross_ses ->
                        [sub, ses, run_id, bold, tmean, bids, anat_file]
                    }
                
                func_conform_with_anat
                    .multiMap { sub, ses, run_id, bold, tmean, bids, anat_file ->
                        combined: [sub, ses, run_id, bold, tmean, bids]
                        reference: anat_file
                    }
                    .set { func_compute_conform_multi }

                FUNC_COMPUTE_CONFORM(func_compute_conform_multi.combined, func_compute_conform_multi.reference, config_file)
                func_compute_conform_output = FUNC_COMPUTE_CONFORM.out.output
                func_compute_conform_transforms = FUNC_COMPUTE_CONFORM.out.transforms
            } else {
                func_compute_conform_output = func_compute_input
                    .map { sub, ses, run_id, bold, tmean, bids ->
                        [sub, ses, run_id, tmean, bids]
                    }
                def dummy_forward_transform = file("${workDir}/dummy_conform_forward_transform.dummy")
                def dummy_inverse_transform = file("${workDir}/dummy_conform_inverse_transform.dummy")
                func_compute_conform_transforms = func_compute_input
                    .map { sub, ses, run_id, bold, tmean, bids ->
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
            // PER-RUN COMPUTE PHASE
            def func_compute_input = func_after_coreg
            
            if (func_conform_enabled) {
                def func_conform_with_anat = func_compute_input
                    .join(func_anat_selection, by: [0, 1, 2])
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
                func_compute_conform_output = FUNC_COMPUTE_CONFORM.out.output
                func_compute_conform_transforms = FUNC_COMPUTE_CONFORM.out.transforms
            } else {
                func_compute_conform_output = func_compute_input
                    .map { sub, ses, run_id, bold, tmean, bids ->
                        [sub, ses, run_id, tmean, bids]
                    }
                def dummy_forward_transform = file("${workDir}/dummy_conform_forward_transform.dummy")
                def dummy_inverse_transform = file("${workDir}/dummy_conform_inverse_transform.dummy")
                func_compute_conform_transforms = func_compute_input
                    .map { sub, ses, run_id, bold, tmean, bids ->
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
        def func_apply_bold_input = func_coreg_runs_within_session && func_coreg_success ? func_after_coreg : func_after_coreg
        
        // APPLY CONFORM
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
                    .map { sub, ses, run_id, bold, tmean, bids, conformed_tmean, func2target_xfm ->
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
        def func_apply_reg = func_apply_conform_output
        def func_apply_reg_reference = Channel.empty()
        if (registration_enabled) {
            def dummy_anat2template_xfm = file("${workDir}/dummy_anat2template_xfm.dummy")
            def dummy_anat_reg_ref = file("${workDir}/dummy_anat_reg_ref.dummy")
            
            // Create real anat_reg_all from anatomical workflow (session-level: [sub, ses, xfm, ref])
            // anat_reg_transforms is now: [sub, ses, anat2template_xfm, inverse_transform]
            // anat_reg_reference is now: [sub, ses, ref_from_anat_reg]
            def anat_reg_transforms_forward = anat_reg_transforms
                .map { sub, ses, anat2template_xfm, inverse_transform ->
                    [sub, ses, anat2template_xfm]
                }
            
            def anat_reg_all_real = anat_reg_transforms_forward
                .join(anat_reg_reference, by: [0, 1])
                .map { sub, ses, anat2template_xfm, ref_from_anat_reg -> 
                [sub, ses, anat2template_xfm, ref_from_anat_reg] }
            
            // Create dummy anat_reg_all for all subjects/sessions (session-level: [sub, ses, dummy_xfm, dummy_ref])
            def subjects_sessions = func_compute_reg_output
                .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses ->
                    [sub, ses]
                }
                .unique()

            def anat_reg_all_dummy = subjects_sessions
                .map { sub, ses -> [sub, ses, dummy_anat2template_xfm, dummy_anat_reg_ref] }

            // Mix channels and group by [sub, ses], then select real over dummy
            // Add debug logging to show which subjects get real vs dummy data
            def anat_reg_all = anat_reg_all_real
                .mix(anat_reg_all_dummy)
                .groupTuple(by: [0, 1])
                .map { sub, ses, entries ->
                    // entries is a list of [xfm, ref] tuples
                    // Prefer first non-dummy entry, or first entry if all are dummy
                    def selected = entries.find { xfm, ref ->
                        !(xfm.toString().contains('.dummy') || ref.toString().contains('.dummy'))
                    } ?: entries[0]
                    [sub, ses] + selected
                }
                .map { sub, ses, xfm, ref ->
                    def is_dummy = (xfm.toString().contains('.dummy') || ref.toString().contains('.dummy'))
                    [sub, ses, xfm, ref]
                }
            
            // debug print 
            anat_reg_all.view { tuple ->
                "DEBUG [FUNC_APPLY_TRANSFORMS: anat_reg_all]: ${tuple}"
            }
            
            // def func_apply_reg_input
            // if (func_coreg_runs_within_session && func_coreg_success) {
            //     // Session-level compute outputs (run_id == "") joined with transforms and reference
            //     // FUNC_COMPUTE_REGISTRATION.out.transforms is now: [sub, ses, run_id, func2target_xfm, inverse_transform]
            //     // FUNC_COMPUTE_REGISTRATION.out.reference is now: [sub, ses, run_id, ref_from_anat_reg]
            //     def func_reg_transforms_forward = FUNC_COMPUTE_REGISTRATION.out.transforms
            //         .map { sub, ses, run_id, func2target_xfm, inverse_transform ->
            //             [sub, ses, run_id, func2target_xfm]
            //         }
                
            //     def func_reg_with_ref = func_compute_reg_output
            //         .join(func_reg_transforms_forward, by: [0, 1])
            //         .join(FUNC_COMPUTE_REGISTRATION.out.reference, by: [0, 1])
            //         .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses, func2target_xfm, ref_from_func_reg ->
            //             [sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg]
            //         }

            //     // debug print
            //     func_reg_with_ref.first().view { tuple ->
            //         "DEBUG [FUNC_COMPUTE_REGISTRATION: func_reg_with_ref]: ${tuple}"
            //     }

            //     // Single combine with anat_reg_all (replaces two separate joins)
            //     def all_reg_with_ref = func_reg_with_ref
            //         .combine(anat_reg_all, by: [0, 1])
            //         .map { sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg ->
            //             [sub, ses, run_id, registered_tmean, func2target_xfm, anat2template_xfm, ref_from_func_reg, ref_from_anat_reg]
            //         }
                
            //     // debug print
            //     all_reg_with_ref.first().view { tuple ->
            //         "DEBUG [FUNC_COMPUTE_REGISTRATION: all_reg_with_ref]: ${tuple}"
            //     }

            //     def func_apply_reg_with_bold = func_apply_conform_output
            //         .combine(
            //             all_reg_with_ref,
            //             by: [0, 1]
            //         )
            //         .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids, registered_tmean, func2target_xfm, anat2template_xfm, ref_from_func_reg, ref_from_anat_reg, anat_ses, is_cross_ses ->
            //             def target_type = 'anat'
            //             def target2template = true
            //             // Keep conformed_bold for multiMap extraction
            //             [sub, ses, run_id, conformed_bold, bids, target_type, target2template, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
            //         }
                
            //     func_apply_reg_with_bold
            //         .multiMap { sub, ses, run_id, conformed_bold, bids, target_type, target2template, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg ->
            //             reg_combined: [sub, ses, run_id, bids, target_type, target2template, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
            //             func_4d_file: conformed_bold
            //         }
            //         .set { func_apply_reg_multi }
                
            //     // debug print
            //     func_apply_reg_multi.reg_combined.first().view { tuple ->
            //         "DEBUG [FUNC_COMPUTE_REGISTRATION: func_apply_reg_input]: ${tuple}"
            //     }
                
            // } else {
            //     // FUNC_COMPUTE_REGISTRATION.out.transforms is now: [sub, ses, run_id, func2target_xfm, inverse_transform]
            //     // FUNC_COMPUTE_REGISTRATION.out.reference is now: [sub, ses, run_id, ref_from_anat_reg]
            //     def func_reg_transforms_forward = FUNC_COMPUTE_REGISTRATION.out.transforms
            //         .map { sub, ses, run_id, func2target_xfm, inverse_transform ->
            //             [sub, ses, run_id, func2target_xfm]
            //         }
                
            //     def func_reg_with_ref = func_compute_reg_output
            //         .join(func_reg_transforms_forward, by: [0, 1, 2])
            //         .join(FUNC_COMPUTE_REGISTRATION.out.reference, by: [0, 1, 2])
            //         .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses, func2target_xfm, ref_from_func_reg ->
            //             [sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat_ses, is_cross_ses]
            //         }
                
            //     // Single combine with anat_reg_all (replaces two separate joins)
            //     def func_reg_with_anat = func_reg_with_ref
            //         .combine(anat_reg_all, by: [0, 1])
            //         .map { sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat_ses, is_cross_ses, anat2template_xfm, ref_from_anat_reg ->
            //             [sub, ses, run_id, registered_tmean, func2target_xfm, anat2template_xfm, ref_from_func_reg, ref_from_anat_reg, anat_ses, is_cross_ses]
            //         }
                
            //     def func_apply_reg_with_bold = func_apply_conform_output
            //         .join(func_reg_with_anat, by: [0, 1, 2])
            //         .map { sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids, registered_tmean, func2target_xfm, anat2template_xfm, ref_from_func_reg, ref_from_anat_reg, anat_ses, is_cross_ses ->
            //             def target_type = 'anat'
            //             def target2template = true
            //             // Keep conformed_bold for multiMap extraction
            //             [sub, ses, run_id, conformed_bold, bids, target_type, target2template, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
            //         }
                
            //     func_apply_reg_with_bold
            //         .multiMap { sub, ses, run_id, conformed_bold, bids, target_type, target2template, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg ->
            //             reg_combined: [sub, ses, run_id, bids, target_type, target2template, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
            //             func_4d_file: conformed_bold
            //         }
            //         .set { func_apply_reg_multi }
            // }
            
            // FUNC_APPLY_TRANSFORMS(func_apply_reg_multi.reg_combined, func_apply_reg_multi.func_4d_file, config_file)
            // func_apply_reg = FUNC_APPLY_TRANSFORMS.out.output
            // func_apply_reg_reference = FUNC_APPLY_TRANSFORMS.out.reference
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
            def func_skull_qc_input = func_apply_conform_output
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
            QC_SKULLSTRIPPING_FUNC(func_skull_qc_input, config_file)
        }

        // if (registration_enabled) {
        //     func_apply_reg
        //         .join(func_apply_reg_reference, by: [0, 1, 2])
        //         .map { sub, ses, run_identifier, bold_file, registered_boldref, bids_template, reference_file ->
        //             [sub, ses, run_identifier, registered_boldref, reference_file]
        //         }
        //         .set { func_reg_qc_input }
        //     QC_REGISTRATION_FUNC(func_reg_qc_input, config_file)
        // }
    }
    
    // Collect functional QC channels
    func_qc_channels = Channel.empty()
    func_jobs_ch_out = Channel.empty()
    
    // if (!anat_only) {
    //     func_jobs_ch_out = func_jobs_ch
    //     if (func_motion_correction_enabled) {
    //         func_qc_channels = func_qc_channels.mix(QC_MOTION_CORRECTION.out.metadata)
    //     }
    //     if (func_conform_enabled) {
    //         func_qc_channels = func_qc_channels.mix(QC_CONFORM_FUNC.out.metadata)
    //     }
    //     if (func_skullstripping_enabled) {
    //         func_qc_channels = func_qc_channels.mix(QC_SKULLSTRIPPING_FUNC.out.metadata)
    //     }
    //     if (func_coreg_runs_within_session) {
    //         func_qc_channels = func_qc_channels.mix(QC_WITHIN_SES_COREG.out.metadata)
    //     }
    //     if (registration_enabled) {
    //         func_qc_channels = func_qc_channels.mix(QC_REGISTRATION_FUNC.out.metadata)
    //     }
    // }
    
    emit:
    func_qc_channels
    func_jobs_ch_out
}
