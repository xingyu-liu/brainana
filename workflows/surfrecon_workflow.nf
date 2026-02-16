/*
 * Surface Reconstruction Workflow
 *
 * Generates cortical surfaces and measurements from anatomical data.
 * Requires skullstripping and optionally uses T1wT2w combined images.
 *
 * Inputs from ANAT_WF: anat_for_surf_recon, anat_skull_seg, anat_skull_mask
 */

nextflow.enable.dsl=2

// Include surface reconstruction modules
include { ANAT_SURFACE_RECONSTRUCTION } from '../modules/anatomical.nf'
include { QC_SURF_RECON_TISSUE_SEG } from '../modules/qc.nf'
include { QC_CORTICAL_SURF_AND_MEASURES } from '../modules/qc.nf'

// Load parameter resolver and config helpers
def paramResolver = evaluate(new File("${projectDir}/workflows/param_resolver.groovy").text)
def configHelpers = evaluate(new File("${projectDir}/workflows/config_helpers.groovy").text)

workflow SURF_RECON_WF {
    take:
    anat_for_surf_recon    // [sub, ses, anat_file, bids_name]
    anat_skull_seg         // [sub, ses, seg_file]
    anat_skull_mask        // [sub, ses, mask_file]
    gpu_queue

    main:
    // ============================================
    // INITIALIZATION
    // ============================================
    configHelpers.ensureParamResolverInitialized(paramResolver, params, projectDir)
    def config_file_path = configHelpers.getEffectiveConfigPath(params, projectDir)
    def config_file = config_file_path

    // ============================================
    // RESOLVE PARAMETERS
    // ============================================
    def surf_recon_enabled = paramResolver.getYamlBool("anat.surface_reconstruction.enabled")
    def anat_skullstripping_enabled = paramResolver.getYamlBool("anat.skullstripping_segmentation.enabled")

    // ============================================
    // SURFACE RECONSTRUCTION
    // ============================================
    surf_qc_channels = Channel.empty()
    if (surf_recon_enabled && anat_skullstripping_enabled) {
        // Step 0: Calculate session count per subject (for surface reconstruction naming)
        def anat_sessions_per_subject = anat_for_surf_recon
            .map { sub, ses, anat_file, bids_name ->
                [sub, ses]
            }
            .unique()
            .groupTuple(by: 0)
            .map { sub, ses_list ->
                def unique_sessions = ses_list.findAll { it && it != '' }.unique()
                def session_count = unique_sessions.size()
                [sub, session_count]
            }

        // Step 1: Join anatomical image with segmentation
        def surf_recon_input_base = anat_for_surf_recon
            .join(anat_skull_seg.map { sub, ses, seg_file -> [sub, ses, seg_file] }, by: [0, 1], remainder: true)
            .map { sub, ses, anat_file, bids_name, seg_file ->
                [sub, ses, anat_file, bids_name, seg_file]
            }

        // Step 2: Join with brain mask
        def surf_recon_input_with_mask = surf_recon_input_base
            .join(anat_skull_mask.map { sub, ses, mask_file -> [sub, ses, mask_file] }, by: [0, 1], remainder: true)
            .map { sub, ses, anat_file, bids_name, seg_file, mask_file ->
                def final_mask = mask_file ?: file("${workDir}/dummy_brain_mask.dummy")
                [sub, ses, anat_file, bids_name, seg_file, final_mask]
            }

        // Step 3: Join with session count
        def anat_sessions_clean = anat_sessions_per_subject
            .unique { sub, session_count -> sub }
            .map { sub, session_count -> [sub, session_count] }

        def surf_recon_input = surf_recon_input_with_mask
            .combine(anat_sessions_clean, by: 0)
            .map { sub, ses, anat_file, bids_name, seg_file, mask_file, session_count ->
                def count = session_count instanceof List ? session_count[0] : session_count
                [sub, ses, anat_file, bids_name, seg_file, mask_file, count]
            }

        ANAT_SURFACE_RECONSTRUCTION(surf_recon_input, config_file)

        // Step 4: Prepare QC input channels
        def surf_qc_bids_lookup = anat_for_surf_recon
            .map { sub, ses, anat_file, bids_name ->
                [sub, ses, bids_name]
            }

        def surf_qc_input = ANAT_SURFACE_RECONSTRUCTION.out.subject_dir
            .join(ANAT_SURFACE_RECONSTRUCTION.out.actual_subject_id, by: [0, 1])
            .join(ANAT_SURFACE_RECONSTRUCTION.out.metadata, by: [0, 1])
            .join(surf_qc_bids_lookup, by: [0, 1])
            .map { sub, ses, subject_dir, actual_subject_id_file, metadata_file, bids_name ->
                def atlas_name = "ARM2"
                try {
                    def metadata = new groovy.json.JsonSlurper().parse(metadata_file)
                    atlas_name = metadata.atlas_name ?: "ARM2"
                } catch (Exception e) {
                    println "Warning: Could not read atlas_name from metadata, using default: ${e.message}"
                }
                def actual_subject_id = actual_subject_id_file.text.trim()
                [sub, ses, actual_subject_id, bids_name, atlas_name]
            }

        // Step 5: Run QC processes
        def surf_tissue_seg_qc_input = surf_qc_input
            .map { sub, ses, actual_subject_id, bids_name, atlas_name ->
                [sub, ses, actual_subject_id, bids_name]
            }
        QC_SURF_RECON_TISSUE_SEG(surf_tissue_seg_qc_input, config_file)
        QC_CORTICAL_SURF_AND_MEASURES(surf_qc_input, config_file)

        // Collect QC channels for completion signal
        surf_qc_channels = QC_SURF_RECON_TISSUE_SEG.out.metadata
            .mix(QC_CORTICAL_SURF_AND_MEASURES.out.metadata)
    } else {
        if (surf_recon_enabled && !anat_skullstripping_enabled) {
            println "Warning: Surface reconstruction is enabled but skullstripping is disabled. Skipping surface reconstruction."
        }
        // Emit single value so main.nf QC completion doesn't hang when surf recon is skipped
        surf_qc_channels = Channel.value('skipped')
    }

    // ============================================
    // EMIT OUTPUT CHANNELS
    // ============================================
    // Explicit name required for sub-workflow output access (Nextflow 25.x)
    emit:
    surf_qc_channels
}
