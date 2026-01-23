/*
 * Helper closures for channel operations
 * 
 * Provides utility functions for channel manipulation in Nextflow workflows:
 * - File path extraction and mapping
 * - BIDS entity extraction
 * - Channel filtering and pass-through operations
 * 
 * Load this file in main.nf with: def channelHelpers = evaluate(new File("${projectDir}/workflows/channel_helpers.groovy").text)
 */

/**
 * Extract single file path from file_paths (handles both List and single value)
 * 
 * @param file_paths Either a List of file paths or a single file path
 * @return Single file path (first element if List, otherwise the value itself)
 */
def getSingleFilePath = { file_paths ->
    file_paths instanceof List ? file_paths[0] : file_paths
}

/**
 * Map single-file job tuple to [sub, ses, file, bids_name] format
 * 
 * @param item Job tuple: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg]
 * @return Mapped tuple: [sub, ses, anat_file, bids_name]
 */
def mapSingleFileJob = { item ->
    def sub = item[0]
    def ses = item[1]
    def file_objects = item[2]  // Already file objects from anat_jobs_ch
    // For single files, file_objects is a list with one element, extract it
    def anat_file = file_objects instanceof List ? file_objects[0] : file_objects
    // Get bids_name from the original file path (for single files, use the file itself)
    def bids_name = anat_file.toString()
    [sub, ses, anat_file, bids_name]
}

/**
 * Normalize session ID from Nextflow.
 * Handles None, empty string, whitespace, and string "null".
 * 
 * @param ses Session ID to normalize
 * @return Normalized session ID string, or null if empty/null
 */
def normalizeSessionId = { ses ->
    if (ses == null || ses == "") {
        return null
    }
    if (ses instanceof String) {
        def trimmed = ses.trim()
        if (trimmed == "" || trimmed.toLowerCase() == 'null') {
            return null
        }
        return trimmed
    }
    return ses
}

/**
 * Match two session IDs, handling subject-level case (null/empty/"null").
 * 
 * @param ses1 First session ID
 * @param ses2 Second session ID
 * @return true if sessions match (including both being subject-level)
 */
def matchSessions = { ses1, ses2 ->
    def ses1_norm = normalizeSessionId(ses1)
    def ses2_norm = normalizeSessionId(ses2)
    return ses1_norm == ses2_norm
}

/**
 * Filter predicate for T1w files (checks bids_name)
 * 
 * @param sub Subject ID
 * @param ses Session ID
 * @param file File object
 * @param bids_name BIDS naming template string
 * @return true if file is T1w, false otherwise
 */
def isT1wFile = { sub, ses, file, bids_name ->
    bids_name.toString().contains('T1w')
}

/**
 * Pass-through mapping helper for anatomical (preserves channel structure when step is disabled)
 * 
 * @param sub Subject ID
 * @param ses Session ID
 * @param file File object
 * @param bids_name BIDS naming template string
 * @return Same tuple structure: [sub, ses, file, bids_name]
 */
def passThroughAnat = { sub, ses, file, bids_name ->
    [sub, ses, file, bids_name]
}

/**
 * Pass-through mapping helper for functional (preserves channel structure when step is disabled)
 * 
 * @param sub Subject ID
 * @param ses Session ID
 * @param run_identifier Run identifier (all non-sub/ses BIDS entities)
 * @param file File object
 * @param bids_name BIDS naming template string
 * @return Same tuple structure: [sub, ses, run_identifier, file, bids_name]
 */
def passThroughFunc = { sub, ses, run_identifier, file, bids_name ->
    [sub, ses, run_identifier, file, bids_name]
}

/**
 * Extract run_identifier from BIDS filename (all non-sub/ses entities)
 * 
 * Returns sorted string like "acq-RevPol_task-rest_run-1" or "rec-realigned_task-rest_run-1"
 * 
 * @param bids_filename Full BIDS filename or path
 * @return Sorted string of all BIDS entities except sub and ses, joined with underscores
 */
def extractRunIdentifier = { bids_filename ->
    // Extract just the filename if a full path was provided
    def filename = bids_filename.toString()
    if (filename.contains('/') || filename.contains('\\')) {
        filename = new File(filename).getName()
    }
    
    // Remove extensions
    filename = filename.replaceAll('\\.nii\\.gz$', '').replaceAll('\\.nii$', '').replaceAll('\\.gz$', '')
    
    // Extract all BIDS entities using regex: key-value pairs
    def pattern = ~/([a-zA-Z]+)-([a-zA-Z0-9-]+)/
    def entities = [:]
    def matcher = pattern.matcher(filename)
    
    while (matcher.find()) {
        def entity = matcher.group(1)
        def value = matcher.group(2)
        entities[entity] = value
    }
    
    // Remove sub and ses entities
    entities.remove('sub')
    entities.remove('ses')
    
    // Sort by entity name and create identifier string
    def sortedEntities = entities.sort { it.key }
    def identifierParts = sortedEntities.collect { "${it.key}-${it.value}" }
    
    return identifierParts.join('_')
}

/**
 * Find unmatched functional jobs (jobs not in matched_keys)
 * 
 * Used for anatomical selection logic to find functional jobs without matching anatomical data
 * 
 * @param func_channel Functional channel: [sub, ses, run_identifier, bold_file, tmean_file, bids_name]
 * @param matched_keys Channel of matched keys: [sub, ses, run_identifier]
 * @return Channel of unmatched keys: [sub, ses, run_identifier]
 */
def findUnmatchedFunc = { func_channel, matched_keys ->
    def all_keys = func_channel.map { sub, ses, run_identifier, bold_file, tmean_file, bids_name ->
        [sub, ses, run_identifier]
    }.unique()
    
    matched_keys.map { key -> [key, 'matched'] }
        .mix(all_keys.map { key -> [key, 'all'] })
        .groupTuple()
        .filter { key, flags -> flags.size() == 1 && flags[0] == 'all' }
        .map { key, flags -> key }
}

/**
 * Find unmatched T2w jobs (jobs not in matched_keys)
 * 
 * Used for T2w anatomical selection logic to find T2w jobs without matching T1w data
 * 
 * @param t2w_channel T2w channel: [sub, ses, t2w_file, t2w_bids_name]
 * @param matched_keys Channel of matched keys: [sub, ses]
 * @return Channel of unmatched keys: [sub, ses]
 */
def findUnmatchedT2w = { t2w_channel, matched_keys ->
    def all_keys = t2w_channel.map { sub, ses, t2w_file, t2w_bids_name ->
        [sub, ses]
    }.unique()
    
    matched_keys.map { key -> [key, 'matched'] }
        .mix(all_keys.map { key -> [key, 'all'] })
        .groupTuple()
        .filter { key, flags -> flags.size() == 1 && flags[0] == 'all' }
        .map { key, flags -> key }
}

/**
 * Perform anatomical selection for T2w jobs
 * Returns: [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
 * If no T1w found, t1w_file will be null, anat_ses will be t2w session
 */
def performT2wAnatomicalSelection = { t2w_after_reorient, anat_after_bias, isT1wFileForT2w, findUnmatched ->
    // Select T1w reference for each T2w job with priority:
    // 1. Subject-level (cross-session synthesized T1w, ses == "") - HIGHEST PRIORITY
    // 2. Same session (exact match by [sub, ses])
    // 3. Different session (same subject, first available session)
    // 4. No T1w data (null files, skip T2w→T1w registration)
    
    def t1w_for_t2w = anat_after_bias.filter(isT1wFileForT2w)
    
    // Build lookup: subject-level T1w data [sub, t1w_file] (ses == "" or "null")
    // Note: Nextflow may pass "null" as a string when session_id is empty/null in Groovy
    def t1w_subject_level = t1w_for_t2w
        .filter { sub, ses, t1w_file, t1w_bids_name -> 
            normalizeSessionId(ses) == null
        }
        .map { sub, ses, t1w_file, t1w_bids_name -> [sub, t1w_file] }
        .unique { sub, t1w_file -> sub }  // Deduplicate by subject
    
    // Build lookup: same-session T1w data [sub, ses, t1w_file]
    // Exclude subject-level (ses == "" or "null") from same-session lookup
    def t1w_same_ses = t1w_for_t2w
        .filter { sub, ses, t1w_file, t1w_bids_name -> 
            normalizeSessionId(ses) != null
        }
        .map { sub, ses, t1w_file, t1w_bids_name -> [sub, ses, t1w_file] }
        .unique { sub, ses, t1w_file -> [sub, ses] }  // Deduplicate by [sub, ses]
    
    // Build lookup: across-session T1w data [sub, t1w_file, anat_ses] (first session per subject)
    // Exclude subject-level (ses == "" or "null") from across-session lookup
    def t1w_across_ses = t1w_for_t2w
        .filter { sub, ses, t1w_file, t1w_bids_name -> 
            normalizeSessionId(ses) != null
        }
        .map { sub, ses, t1w_file, t1w_bids_name -> [sub, ses, t1w_file] }
        .groupTuple(by: 0)
        .map { sub, ses_list, file_list ->
            def first = [ses_list, file_list].transpose().sort { a, b -> (a[0] ?: '') <=> (b[0] ?: '') }[0]
            [sub, first[1], first[0]]  // [sub, t1w_file, anat_ses]
        }
    
    // Case 1: Subject-level match (HIGHEST PRIORITY)
    // Match by subject only - subject-level T1w available to ALL T2w sessions
    def t2w_subject_level = t2w_after_reorient
        .combine(t1w_subject_level, by: 0)  // combine by subject
        .map { sub, ses, t2w_file, t2w_bids_name, t1w_file ->
            [sub, ses, t2w_file, t2w_bids_name, t1w_file, ""]  // [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses] with anat_ses = ""
        }
    
    def matched_subject_level = t2w_subject_level.map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses ->
        [sub, ses]
    }.unique()
    
    // Case 2: Same-session match (for T2w NOT matched in Case 1)
    def unmatched_for_case2 = findUnmatched(t2w_after_reorient, matched_subject_level)
    def t2w_same_ses = unmatched_for_case2
        .map { key -> [key[0], key[1]] }  // [sub, ses]
        .combine(t2w_after_reorient.map { sub, ses, t2w_file, t2w_bids_name -> [sub, ses, t2w_file, t2w_bids_name] }, by: [0, 1])
        .map { sub, ses, t2w_file, t2w_bids_name ->
            [sub, ses, t2w_file, t2w_bids_name]
        }
        .combine(t1w_same_ses, by: [0, 1])
        .map { sub, ses, t2w_file, t2w_bids_name, t1w_file ->
            [sub, ses, t2w_file, t2w_bids_name, t1w_file, ses]  // [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
        }
    
    def matched_same_ses = t2w_same_ses.map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses ->
        [sub, ses]
    }.unique()
    
    // Case 3: Across-session match (for T2w NOT matched in Case 1 OR Case 2)
    def all_matched_case3 = matched_subject_level.mix(matched_same_ses).unique()
    def unmatched_for_case3 = findUnmatched(t2w_after_reorient, all_matched_case3)
    def t2w_across_ses = unmatched_for_case3
        .map { key -> [key[0], key[1]] }  // [sub, ses]
        .combine(t2w_after_reorient.map { sub, ses, t2w_file, t2w_bids_name -> [sub, ses, t2w_file, t2w_bids_name] }, by: [0, 1])
        .map { sub, ses, t2w_file, t2w_bids_name ->
            [sub, ses, t2w_file, t2w_bids_name]
        }
        .combine(t1w_across_ses, by: 0)
        .map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses ->
            [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
        }
    
    def matched_across_ses = t2w_across_ses.map { sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses ->
        [sub, ses]
    }.unique()
    
    // Case 4: No T1w data (for remaining unmatched T2w - skip T2w→T1w registration)
    def all_matched = matched_subject_level.mix(matched_same_ses).mix(matched_across_ses).unique()
    def unmatched_for_case4 = findUnmatched(t2w_after_reorient, all_matched)
    def t2w_no_t1w = unmatched_for_case4
        .map { key -> [key[0], key[1]] }  // [sub, ses]
        .combine(t2w_after_reorient.map { sub, ses, t2w_file, t2w_bids_name -> [sub, ses, t2w_file, t2w_bids_name] }, by: [0, 1])
        .map { sub, ses, t2w_file, t2w_bids_name ->
            [sub, ses, t2w_file, t2w_bids_name, null, ses]  // null T1w file, anat_ses = t2w session
        }
    
    // Combine all cases: [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
    return t2w_subject_level.mix(t2w_same_ses).mix(t2w_across_ses).mix(t2w_no_t1w)
}

/**
 * Perform anatomical selection for functional jobs
 * Returns: [sub, ses, anat_file, anat_ses]
 * 
 * Note: All runs in the same session use the same anatomical reference,
 * so this function returns session-level results only (no run_identifier).
 * Use combine() to match with run-level functional data.
 */
def performFuncAnatomicalSelection = { func_after_coreg, anat_after_bias_brain, isT1wFileForFunc, findUnmatched, dummy_anat ->
    // Select anatomical reference for each functional session with priority:
    // 1. Subject-level (cross-session synthesized anat, ses == "") - HIGHEST PRIORITY
    // 2. Same session (exact match by [sub, ses])
    // 3. Different session (same subject, first available session)
    // 4. No anatomical data (dummy file, Python will fallback to template)
    //
    // CRITICAL: This function MUST return entries for ALL functional sessions
    // to prevent jobs from being dropped in the compute phase.
    //
    // NOTE: We use a "left anti-join" pattern with mix() + groupTuple() instead of
    // combine() because combine() only emits when BOTH channels have matching keys,
    // which would silently drop sessions that need to go to Case 2, 3, or 4.
    //
    // NOTE: Uses anat_after_bias_brain (Phase 1 final output - brain version) for functional registration
    //
    // Extract unique [sub, ses] pairs from functional jobs
    // All runs in the same session will use the same anatomical reference
    def func_sessions = func_after_coreg.map { sub, ses, run_identifier, bold_file, tmean_file, bids_name ->
        [sub, ses]
    }.unique()
    
    def anat_for_func = anat_after_bias_brain.filter(isT1wFileForFunc)
    
    // Build lookup: subject-level anatomical data [sub, anat_file] (ses == "" or "null")
    // Note: anat_after_bias_brain structure is [sub, ses, brain_file, bids_name]
    // Note: Nextflow may pass "null" as a string when session_id is empty/null in Groovy
    def anat_subject_level = anat_for_func
        .filter { sub, ses, brain_file, bids_name -> 
            normalizeSessionId(ses) == null
        }
        .map { sub, ses, brain_file, bids_name -> [sub, brain_file] }
        .unique { sub, brain_file -> sub }  // Deduplicate by subject
    
    // Build lookup: same-session anatomical data [sub, ses, anat_file]
    // Exclude subject-level (ses == "" or "null") from same-session lookup
    def anat_same_ses = anat_for_func
        .filter { sub, ses, brain_file, bids_name -> 
            normalizeSessionId(ses) != null
        }
        .map { sub, ses, brain_file, bids_name -> [sub, ses, brain_file] }
        .unique { sub, ses, brain_file -> [sub, ses] }  // Deduplicate by [sub, ses]
    
    // Build lookup: across-session anatomical data [sub, anat_file, anat_ses] (first session per subject)
    // Exclude subject-level (ses == "" or "null") from across-session lookup
    def anat_across_ses = anat_for_func
        .filter { sub, ses, brain_file, bids_name -> 
            normalizeSessionId(ses) != null
        }
        .map { sub, ses, brain_file, bids_name -> [sub, ses, brain_file] }
        .groupTuple(by: 0)
        .map { sub, ses_list, file_list ->
            def first = [ses_list, file_list].transpose().sort { a, b -> (a[0] ?: '') <=> (b[0] ?: '') }[0]
            [sub, first[1], first[0]]  // [sub, anat_file, anat_ses]
        }
    
    // Case 1: Subject-level match (HIGHEST PRIORITY)
    // Match by subject only - subject-level anat available to ALL functional sessions
    def func_subject_level = func_sessions
        .combine(anat_subject_level, by: 0)  // combine by subject
        .map { sub, ses, anat_file ->
            [sub, ses, anat_file, ""]  // [sub, ses, anat_file, anat_ses] with anat_ses = ""
        }
    
    def matched_subject_level_keys = func_subject_level.map { sub, ses, anat_file, anat_ses ->
        [sub, ses]
    }.unique()
    
    // Case 2: Same-session match (for sessions NOT matched in Case 1)
    // Use left anti-join pattern: mix with marker tags, group, filter for unmatched
    def unmatched_for_case2 = func_sessions
        .map { sub, ses -> [[sub, ses], 'func'] }
        .mix(matched_subject_level_keys.map { sub, ses -> [[sub, ses], 'matched'] })
        .groupTuple(by: 0)
        .filter { key, tags -> !tags.contains('matched') }
        .map { key, tags -> key }  // key is [sub, ses]
    
    // Match with same-session anatomical data
    def func_same_ses = unmatched_for_case2
        .map { key -> [key[0], key[1]] }  // [sub, ses]
        .combine(anat_same_ses, by: [0, 1])
        .map { sub, ses, anat_file ->
            [sub, ses, anat_file, ses]  // [sub, ses, anat_file, anat_ses]
        }
    
    def matched_same_ses_keys = func_same_ses.map { sub, ses, anat_file, anat_ses ->
        [sub, ses]
    }.unique()
    
    // Case 3: Across-session match (for sessions NOT matched in Case 1 OR Case 2)
    def all_matched_keys_case3 = matched_subject_level_keys.mix(matched_same_ses_keys).unique()
    def unmatched_for_case3 = func_sessions
        .map { sub, ses -> [[sub, ses], 'func'] }
        .mix(all_matched_keys_case3.map { sub, ses -> [[sub, ses], 'matched'] })
        .groupTuple(by: 0)
        .filter { key, tags -> !tags.contains('matched') }
        .map { key, tags -> key }  // key is [sub, ses]
    
    // Match with cross-session anatomical data (by subject only)
    def func_across_ses = unmatched_for_case3
        .map { key -> [key[0], key[1]] }  // [sub, ses]
        .combine(anat_across_ses, by: 0)  // combine by subject
        .map { sub, ses_func, anat_file, anat_ses ->
            [sub, ses_func, anat_file, anat_ses]
        }
    
    def matched_across_ses_keys = func_across_ses.map { sub, ses, anat_file, anat_ses ->
        [sub, ses]
    }.unique()
    
    // Case 4: No anatomical data (sessions NOT matched in Case 1, 2, OR 3)
    def all_matched_keys = matched_subject_level_keys.mix(matched_same_ses_keys).mix(matched_across_ses_keys).unique()
    def unmatched_for_case4 = func_sessions
        .map { sub, ses -> [[sub, ses], 'func'] }
        .mix(all_matched_keys.map { sub, ses -> [[sub, ses], 'matched'] })
        .groupTuple(by: 0)
        .filter { key, tags -> !tags.contains('matched') }
        .map { key, tags -> key }  // key is [sub, ses]
    
    def func_no_anat = unmatched_for_case4
        .map { key ->
            def sub = key[0]
            def ses = key[1]
            [sub, ses, dummy_anat, ses]  // [sub, ses, anat_file, anat_ses] with dummy file
        }
    
    // Combine all cases: [sub, ses, anat_file, anat_ses]
    // This MUST include entries for ALL functional sessions to prevent job loss
    def result = func_subject_level.mix(func_same_ses).mix(func_across_ses).mix(func_no_anat)
    
    return result
}

// Return a map with all helpers
return [
    getSingleFilePath: getSingleFilePath,
    mapSingleFileJob: mapSingleFileJob,
    isT1wFile: isT1wFile,
    passThroughAnat: passThroughAnat,
    passThroughFunc: passThroughFunc,
    findUnmatchedFunc: findUnmatchedFunc,
    findUnmatchedT2w: findUnmatchedT2w,
    extractRunIdentifier: extractRunIdentifier,
    performT2wAnatomicalSelection: performT2wAnatomicalSelection,
    performFuncAnatomicalSelection: performFuncAnatomicalSelection,
    normalizeSessionId: normalizeSessionId,
    matchSessions: matchSessions
]
