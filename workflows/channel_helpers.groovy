/*
 * Helper closures for channel operations
 * Load this file in main.nf with: def channelHelpers = load('workflows/channel_helpers.groovy')
 */

// Extract single file path from file_paths (handles both List and single value)
def getSingleFilePath = { file_paths ->
    file_paths instanceof List ? file_paths[0] : file_paths
}

// Map single-file job tuple to [sub, ses, file, bids_template] format
def mapSingleFileJob = { item ->
    def sub = item[0]
    def ses = item[1]
    def file_objects = item[2]  // Already file objects from anat_jobs_ch
    // For single files, file_objects is a list with one element, extract it
    def anat_file = file_objects instanceof List ? file_objects[0] : file_objects
    // Get bids_template from the original file path (for single files, use the file itself)
    def bids_template = anat_file.toString()
    [sub, ses, anat_file, bids_template]
}

// Filter predicate for T1w files (checks bids_template)
def isT1wFile = { sub, ses, file, bids_template ->
    bids_template.toString().contains('T1w')
}

// Pass-through mapping helper (preserves channel structure when step is disabled)
def passThroughAnat = { sub, ses, file, bids_template ->
    [sub, ses, file, bids_template]
}

// Pass-through mapping helper for functional (preserves channel structure when step is disabled)
// Updated to use run_identifier: [sub, ses, run_identifier, file, bids_template]
def passThroughFunc = { sub, ses, run_identifier, file, bids_template ->
    [sub, ses, run_identifier, file, bids_template]
}

// Extract run_identifier from BIDS filename (all non-sub/ses entities)
// Returns sorted string like "acq-RevPol_task-rest_run-1" or "rec-realigned_task-rest_run-1"
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

// Helper: find unmatched functional jobs (jobs not in matched_keys)
// Updated to use run_identifier instead of task/run
def findUnmatched = { func_channel, matched_keys ->
    def all_keys = func_channel.map { sub, ses, run_identifier, bold_file, tmean_file, bids_template ->
        [sub, ses, run_identifier]
    }.unique()
    
    matched_keys.map { key -> [key, 'matched'] }
        .mix(all_keys.map { key -> [key, 'all'] })
        .groupTuple()
        .filter { key, flags -> flags.size() == 1 && flags[0] == 'all' }
        .map { key, flags -> key }
}

// Return a map with all helpers
return [
    getSingleFilePath: getSingleFilePath,
    mapSingleFileJob: mapSingleFileJob,
    isT1wFile: isT1wFile,
    passThroughAnat: passThroughAnat,
    passThroughFunc: passThroughFunc,
    findUnmatched: findUnmatched,
    extractRunIdentifier: extractRunIdentifier
]
