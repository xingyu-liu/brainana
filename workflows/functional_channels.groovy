/*
 * Functional channel operations
 * Load this file in main.nf with: def funcChannels = evaluate(new File("${projectDir}/workflows/functional_channels.groovy").text)
 * 
 * NOTE: These functions only prepare channels. Process calls must be done in main.nf workflow context.
 */

/**
 * Prepare channels for within-session coregistration
 * Returns a map with prepared channels for process calls
 */
def prepareWithinSessionCoregChannels = { func_after_bias, Channel ->
    // Group by [sub, ses] to identify sessions and find first run
    // func_after_bias: [sub, ses, run_identifier, bold, tmean, bids_template]
    def func_by_ses_flat = func_after_bias
        .groupTuple(by: [0, 1])  // Group by [sub, ses]
        .flatMap { sub, ses, run_identifier_list, bold_list, tmean_list, bids_list ->
            // Create tuples with run_identifier as key for sorting
            def runs_data = [run_identifier_list, bold_list, tmean_list, bids_list].transpose()
            def sorted_runs = runs_data.sort { a, b -> (a[0] ?: '') <=> (b[0] ?: '') }  // Sort by run_identifier (lexicographic)
            
            if (sorted_runs.size() == 0) {
                return []
            }
            
            def first = sorted_runs[0]
            def first_run_identifier = first[0]
            def first_bold = first[1]
            def first_tmean = first[2]
            def first_bids = first[3]
            
            // Emit first run with marker, then later runs
            def result = []
            result.add([sub, ses, first_run_identifier, first_bold, first_tmean, first_bids, true, false])  // [sub, ses, run_identifier, bold, tmean, bids, is_first, is_single]
            
            if (sorted_runs.size() == 1) {
                // Single run session - mark as single
                result[0][7] = true  // is_single = true
            } else {
                // Multi-run session - emit later runs (skip first element)
                def later = sorted_runs.subList(1, sorted_runs.size())
                later.each { run_data ->
                    def run_identifier = run_data[0]
                    def bold = run_data[1]
                    def tmean = run_data[2]
                    def bids = run_data[3]
                    result.add([sub, ses, run_identifier, bold, tmean, bids, false, false, first_tmean, first_run_identifier])  // [sub, ses, run_identifier, bold, tmean, bids, is_first, is_single, ref_tmean, ref_run_identifier]
                }
            }
            
            return result
        }
    
    // Split: single run sessions vs multi-run sessions
    def func_single_run_ses = func_by_ses_flat
        .filter { item ->
            item.size() >= 8 && item[7] == true  // is_single == true
        }
        .map { sub, ses, run_identifier, bold, tmean, bids, is_first, is_single ->
            // Pass through unchanged (no coreg needed)
            [sub, ses, run_identifier, bold, tmean, bids]
        }
    
    // Multi-run sessions: separate first runs and later runs
    def func_first_runs = func_by_ses_flat
        .filter { item ->
            item.size() >= 8 && item[6] == true && item[7] == false  // is_first == true, is_single == false
        }
        .map { sub, ses, run_identifier, bold, tmean, bids, is_first, is_single ->
            [sub, ses, run_identifier, bold, tmean, bids]
        }
    
    // Later runs for coregistration
    def func_later_runs = func_by_ses_flat
        .filter { item ->
            item.size() >= 10 && item[6] == false  // is_first == false (has ref_tmean and ref_run_identifier)
        }
        .map { sub, ses, run_identifier, bold, tmean, bids, is_first, is_single, ref_tmean, ref_run_identifier ->
            [sub, ses, run_identifier, bold, tmean, bids, ref_tmean, ref_run_identifier]
        }
    
    // Prepare channels for coregistration (return the channel that will be multiMapped)
    // Note: multiMap must be called in workflow context, not here
    
    // Prepare channels for averaging
    def func_all_coreg_prep = func_first_runs
        .mix(func_single_run_ses.map { sub, ses, run_identifier, bold, tmean, bids ->
            [sub, ses, run_identifier, bold, tmean, bids]
        })
    
    // Prepare channel for file list (return the channel that will be multiMapped)
    def func_for_file_list_ch = func_all_coreg_prep
        .groupTuple(by: [0, 1])
    
    def func_grouped_with_bids = func_all_coreg_prep
        .groupTuple(by: [0, 1])
        .map { sub, ses, run_identifier_list, bold_list, tmean_list, bids_list ->
            def bids_template = bids_list[0]
            [sub, ses, bids_template]
        }
    
    return [
        func_later_runs: func_later_runs,
        func_first_runs: func_first_runs,
        func_single_run_ses: func_single_run_ses,
        func_all_coreg_prep: func_all_coreg_prep,
        func_for_file_list_ch: func_for_file_list_ch,
        func_grouped_with_bids: func_grouped_with_bids
    ]
}

/**
 * Prepare channels for averaging tmean after coregistration
 * Returns the channel before multiMap (multiMap must be done in workflow context)
 */
def prepareAveragingChannels = { FUNC_WRITE_TMEAN_LIST, func_grouped_with_bids, Channel ->
    // FUNC_WRITE_TMEAN_LIST outputs:
    // - file_list: path (tmean_files_list.txt)
    // - tmean_files: path (list of tmean files for staging) - this is a path input that may contain multiple files
    // - subject_id: val
    // - session_id: val
    //
    // We need to combine all outputs and join with func_grouped_with_bids
    // Final structure should be: [file_list, tmean_files, subject_id, session_id, bids_template]
    // FUNC_AVERAGE_TMEAN expects: [tmean_files_list, tmean_files, subject_id, session_id, bids_naming_template]
    
    // Combine all outputs from FUNC_WRITE_TMEAN_LIST
    // The combine operations will create: [file_list, tmean_files, subject_id, session_id]
    def func_write_outputs_combined = FUNC_WRITE_TMEAN_LIST.out.file_list
        .combine(FUNC_WRITE_TMEAN_LIST.out.tmean_files)
        .combine(FUNC_WRITE_TMEAN_LIST.out.subject_id)
        .combine(FUNC_WRITE_TMEAN_LIST.out.session_id)
    
    // Join with func_grouped_with_bids [sub, ses, bids_template] by matching subject_id/session_id with sub/ses
    // func_write_outputs_combined structure: [file_list, tmean_files, subject_id, session_id]
    // func_grouped_with_bids structure: [sub, ses, bids_template]
    // We need to join by matching [subject_id, session_id] with [sub, ses]
    // IMPORTANT: Nextflow join concatenates left tuple + right tuple (excluding join keys from right)
    // So if left is [file_list, tmean_files, subject_id, session_id] and right is [sub, ses, bids_template]
    // Join by [2,3] (indices of subject_id, session_id) produces: [file_list, tmean_files, subject_id, session_id, bids_template]
    def func_for_averaging_ch = func_write_outputs_combined
        .join(func_grouped_with_bids, by: [2, 3])  // Join by [subject_id/sub, session_id/ses] at indices 2,3
        .map { file_list, tmean_files, subject_id, session_id, bids_template ->
            // After join: [file_list, tmean_files, subject_id, session_id, bids_template]
            // FUNC_AVERAGE_TMEAN expects: [file_list, tmean_files, subject_id, session_id, bids_template]
            // This is already in the correct order!
            [file_list, tmean_files, subject_id, session_id, bids_template]
        }
    
    return func_for_averaging_ch
}

/**
 * Prepare QC channels for within-session coregistration
 */
def prepareCoregQCChannels = { func_first_runs, func_tmean_averaged_ch ->
    def func_first_run_tmean = func_first_runs
        .map { sub, ses, run_identifier, bold, tmean, bids ->
            [sub, ses, tmean]
        }
        .unique { sub, ses, tmean -> [sub, ses] }  // One per session
    
    def func_coreg_qc_input = func_first_run_tmean
        .join(func_tmean_averaged_ch, by: [0, 1])
        .map { sub, ses, tmean_run1, tmean_avg, bids_template ->
            [sub, ses, tmean_run1, tmean_avg, bids_template]
        }
    
    return func_coreg_qc_input
}

/**
 * Perform anatomical selection for functional jobs
 * Returns: [sub, ses, run_identifier, anat_file, anat_ses, is_cross_ses]
 */
def performAnatomicalSelection = { func_after_coreg, anat_after_skull, isT1wFile, findUnmatched, dummy_anat ->
    // Select anatomical reference for each functional job with priority:
    // 1. Same session (exact match by [sub, ses])
    // 2. Different session (same subject, first available session)
    // 3. No anatomical data (dummy file, Python will fallback to template)
    
    def anat_for_func = anat_after_skull.filter(isT1wFile)
    
    // Build lookup: same-session anatomical data [sub, ses, anat_file]
    def anat_same_ses = anat_for_func
        .map { sub, ses, anat_file, bids_template -> [sub, ses, anat_file] }
        .unique { sub, ses, anat_file -> [sub, ses] }  // Deduplicate by [sub, ses]
    
    // Build lookup: across-session anatomical data [sub, ses, anat_file] (first session per subject)
    def anat_across_ses = anat_for_func
        .map { sub, ses, anat_file, bids_template -> [sub, ses, anat_file] }
        .groupTuple(by: 0)
        .map { sub, ses_list, file_list ->
            def first = [ses_list, file_list].transpose().sort { a, b -> (a[0] ?: '') <=> (b[0] ?: '') }[0]
            [sub, first[0], first[1]]
        }
    
    // Case 1: Same-session match
    def func_same_ses = func_after_coreg
        .combine(anat_same_ses, by: [0, 1])
        .map { sub, ses, run_identifier, bold_file, tmean_file, bids_template, anat_file ->
            [sub, ses, run_identifier, anat_file, ses, false]  // [sub, ses, run_identifier, anat_file, anat_ses, is_cross_ses]
        }
    
    def matched_same_ses = func_same_ses.map { sub, ses, run_identifier, anat_file, anat_ses, is_cross_ses ->
        [sub, ses, run_identifier]
    }.unique()
    
    // Case 2: Across-session match (for unmatched jobs)
    def unmatched_for_case2 = findUnmatched(func_after_coreg, matched_same_ses)
    def func_across_ses = func_after_coreg
        .map { sub, ses, run_identifier, bold_file, tmean_file, bids_template ->
            [[sub, ses, run_identifier], [sub, ses, run_identifier, bold_file, tmean_file, bids_template]]
        }
        .combine(unmatched_for_case2.map { key -> [key, true] }.groupTuple(), by: 0)
        .map { key, func_data, flags -> func_data }
        .combine(anat_across_ses, by: 0)
        .map { sub, ses_func, run_identifier, bold_file, tmean_file, bids_template, ses_anat, anat_file ->
            [sub, ses_func, run_identifier, anat_file, ses_anat, true]
        }
    
    def matched_across_ses = func_across_ses.map { sub, ses, run_identifier, anat_file, anat_ses, is_cross_ses ->
        [sub, ses, run_identifier]
    }.unique()
    
    // Case 3: No anatomical data (for remaining unmatched jobs)
    def unmatched_for_case3 = findUnmatched(func_after_coreg, matched_same_ses.mix(matched_across_ses).unique())
    def func_no_anat = func_after_coreg
        .map { sub, ses, run_identifier, bold_file, tmean_file, bids_template ->
            [[sub, ses, run_identifier], [sub, ses, run_identifier, bold_file, tmean_file, bids_template]]
        }
        .combine(unmatched_for_case3.map { key -> [key, true] }.groupTuple(), by: 0)
        .map { key, func_data, flags -> func_data }
        .map { sub, ses, run_identifier, bold_file, tmean_file, bids_template ->
            [sub, ses, run_identifier, dummy_anat, ses, false]
        }
    
    // Combine all cases: [sub, ses, run_identifier, anat_file, anat_ses, is_cross_ses]
    return func_same_ses.mix(func_across_ses).mix(func_no_anat)
}

/**
 * Prepare channels for applying transforms (session-level)
 */
def prepareSessionLevelTransforms = { func_after_reg, func_reg_transforms, func_reg_metadata, func_reg_reference, func_reg_anat_session, func_after_coreg, anat_reg_transforms, dummy_anat2template, Channel ->
    def func_reg_metadata_parsed = func_reg_metadata
        .map { sub, ses, metadata_file ->
            def metadata_text = metadata_file.text.trim()
            def parts = metadata_text.split('\t')
            def target_type = parts[0]
            def target2template = parts.length > 1 ? parts[1].toBoolean() : false
            [sub, ses, target_type, target2template]
        }
    
    def func_reg_session_complete = func_after_reg
        .join(func_reg_transforms, by: [0, 1])
        .join(func_reg_metadata_parsed, by: [0, 1])
        .join(func_reg_reference, by: [0, 1])
        .join(func_reg_anat_session, by: [0, 1])
        .map { sub, ses, registered_tmean, bids, transform, target_type, target2template, ref, anat_ses ->
            [sub, ses, registered_tmean, bids, transform, target_type, target2template, ref, anat_ses]
        }
    
    def func_all_runs_for_apply = func_after_coreg
        .join(func_reg_session_complete, by: [0, 1])
        .map { sub, ses, run_identifier, bold, tmean, bids, registered_tmean, transform, target_type, target2template, ref, anat_ses ->
            [sub, ses, run_identifier, registered_tmean, transform, target_type, target2template, ref, anat_ses, bold, bids]
        }
    
    def func_sequential = func_all_runs_for_apply
        .filter { sub, ses, run_identifier, registered_tmean, transform, target_type, target2template, ref, anat_ses, bold, bids ->
            target2template && target_type == 'anat'
        }
    
    def func_single = func_all_runs_for_apply
        .filter { sub, ses, run_identifier, registered_tmean, transform, target_type, target2template, ref, anat_ses, bold, bids ->
            !(target2template && target_type == 'anat')
        }
    
    def anat_reg_transforms_for_join = anat_reg_transforms
        .map { sub, ses, transform_file -> [sub, ses, transform_file] }
    
    def func_sequential_joined = func_sequential
        .map { sub, ses, run_identifier, registered_tmean, transform, target_type, target2template, ref, anat_ses, bold, bids ->
            [sub, anat_ses, ses, run_identifier, registered_tmean, transform, target_type, target2template, ref, bold, bids]
        }
        .combine(anat_reg_transforms_for_join, by: [0, 1])
        .map { sub, anat_ses, ses, run_identifier, registered_tmean, transform, target_type, target2template, ref, bold, bids, anat2template_transform ->
            [sub, ses, run_identifier, registered_tmean, transform, anat2template_transform, bids, target_type, target2template, ref, bold]
        }
    
    def func_sequential_final = func_sequential_joined
        .map { sub, ses, run_identifier, registered_tmean, transform, anat2template_transform, bids, target_type, target2template, ref, bold ->
            [sub, ses, run_identifier, registered_tmean, transform, anat2template_transform, bids, target_type, target2template, ref, bold]
        }
    
    def func_single_final = func_single
        .map { sub, ses, run_identifier, registered_tmean, transform, target_type, target2template, ref, anat_ses, bold, bids ->
            [sub, ses, run_identifier, registered_tmean, transform, dummy_anat2template, bids, target_type, target2template, ref, bold]
        }
    
    def func_all_for_apply = func_sequential_final.mix(func_single_final)
        .map { sub, ses, run_identifier, registered_tmean, transform, anat2template_transform, bids, target_type, target2template, ref, bold ->
            // Keep bold file for multiMap, but reg_combined tuple (for FUNC_APPLY_TRANSFORMS) doesn't include it
            // Structure: [sub, ses, run_identifier, registered_tmean, transform, anat2template_transform, bids, target_type, target2template, ref, bold]
            [sub, ses, run_identifier, registered_tmean, transform, anat2template_transform, bids, target_type, target2template, ref, bold]
        }
    
    // Return channel before multiMap (multiMap must be done in workflow context)
    return func_all_for_apply
}

/**
 * Prepare channels for applying transforms (per-run)
 */
def preparePerRunTransforms = { func_after_reg, func_reg_transforms, func_reg_metadata, func_reg_reference, func_reg_anat_session, anat_reg_transforms, dummy_anat2template, Channel ->
    def func_reg_metadata_parsed = func_reg_metadata
        .map { sub, ses, run_identifier, metadata_file ->
            def metadata_text = metadata_file.text.trim()
            def parts = metadata_text.split('\t')
            def target_type = parts[0]
            def target2template = parts.length > 1 ? parts[1].toBoolean() : false
            [sub, ses, run_identifier, target_type, target2template]
        }
    
    def func_reg_complete = func_after_reg
        .join(func_reg_transforms, by: [0, 1, 2])
        .join(func_reg_metadata_parsed, by: [0, 1, 2])
        .join(func_reg_reference, by: [0, 1, 2])
        .join(func_reg_anat_session, by: [0, 1, 2])
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses]
        }
    
    def func_sequential = func_reg_complete
        .filter { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            target2template && target_type == 'anat'
        }
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses]
        }
    
    def func_single = func_reg_complete
        .filter { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            !(target2template && target_type == 'anat')
        }
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses]
        }
    
    def anat_reg_transforms_for_join = anat_reg_transforms
        .map { sub, ses, transform_file -> [sub, ses, transform_file] }
    
    def func_sequential_joined = func_sequential
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            [sub, anat_ses, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file]
        }
        .combine(anat_reg_transforms_for_join, by: [0, 1])
        .map { sub, anat_ses, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, transform_file ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, transform_file, target_type, target2template, reference_file]
        }
    
    def func_sequential_joined_keys = func_sequential_joined
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
            [sub, ses, run_identifier]
        }
        .unique()
    
    def func_sequential_no_match = func_sequential
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file]
        }
        .combine(func_sequential_joined_keys.groupTuple(), by: [0, 1, 2])
        .filter { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, matched_keys ->
            !matched_keys || matched_keys.isEmpty()
        }
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, dummy_anat2template, target_type, target2template, reference_file]
        }
    
    def func_sequential_final = func_sequential_joined.mix(func_sequential_no_match)
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file]
        }
    
    def func_single_final = func_single
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, target_type, target2template, reference_file, anat_ses ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, dummy_anat2template, target_type, target2template, reference_file]
        }
    
    def func_all_for_apply = func_sequential_final.mix(func_single_final)
        .map { sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file ->
            [sub, ses, run_identifier, bold_file, registered_tmean, bids_template, forward_transform, anat2template_transform, target_type, target2template, reference_file]
        }
    
    // Return channel before multiMap (multiMap must be done in workflow context)
    return func_all_for_apply
}

return [
    performAnatomicalSelection: performAnatomicalSelection,
    prepareWithinSessionCoregChannels: prepareWithinSessionCoregChannels,
    prepareAveragingChannels: prepareAveragingChannels,
    prepareCoregQCChannels: prepareCoregQCChannels,
    prepareSessionLevelTransforms: prepareSessionLevelTransforms,
    preparePerRunTransforms: preparePerRunTransforms
]
