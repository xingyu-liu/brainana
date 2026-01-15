/*
 * Main Nextflow workflow for banana
 * 
 * This workflow processes BIDS datasets using per-step parallelization
 * for maximum efficiency.
 * 
 * BIDS discovery is performed by a Python script BEFORE this workflow runs.
 * The discovery script validates the BIDS dataset, discovers all jobs, and
 * saves JSON files that this workflow reads to create channels.
 * 
 * ============================================
 * CHANNEL STRUCTURE DOCUMENTATION
 * ============================================
 * 
 * Standard channel structures used throughout the workflow:
 * 
 * Anatomical channels:
 *   - [sub, ses, file, bids_template] (4 elements) - standard anatomical tuple
 *   - [sub, ses, file_paths, needs_synth, suffix, needs_t1w_reg] (6 elements) - from discovery
 * 
 * Functional channels:
 *   - [sub, ses, run_identifier, file, bids_template] (5 elements) - initial functional tuple
 *   - [sub, ses, run_identifier, bold_file, tmean_file, bids_template] (6 elements) - after MOTION_CORRECTION
 *   - [sub, ses, run_identifier, anat_file, anat_ses, is_cross_ses] (6 elements) - anatomical selection result
 * 
 * Transform channels:
 *   - [sub, ses, transform_file] (3 elements) - anatomical transforms
 *   - [sub, ses, run_identifier, transform_file] (4 elements) - functional transforms
 * 
 * QC channels:
 *   - [sub, ses, metadata_file] (3 elements) - QC metadata
 *   - [sub, ses, run_identifier, metadata_file] (4 elements) - functional QC metadata
 * 
 * Note: run_identifier contains all non-sub/ses BIDS entities as a sorted string
 *       e.g., "acq-RevPol_task-rest_run-1" or "rec-realigned_task-rest_run-1"
 */

nextflow.enable.dsl=2

// Include sub-workflows
include { ANAT_WF } from './workflows/anatomical_workflow.nf'
include { FUNC_WF } from './workflows/functional_workflow.nf'

// Include QC report generation
include { QC_GENERATE_REPORT } from './modules/qc.nf'

// Load parameter resolver
def paramResolver = evaluate(new File("${projectDir}/workflows/param_resolver.groovy").text)

workflow {
    // ============================================
    // INITIALIZE PARAMETER RESOLVER
    // ============================================
    // Initialize parameter resolver with priority: CLI params → YAML config → defaults.yaml
    paramResolver.initialize(params, projectDir)
    
    // ============================================
    // GENERATE EFFECTIVE CONFIG FILE
    // ============================================
    // Generate effective config.yaml that merges: CLI params → YAML config → defaults.yaml
    // This file will be used by all processes instead of passing individual parameters
    def effective_config_path = paramResolver.generateEffectiveConfig(params, projectDir, params.output_dir)
    def effective_config_file = file(effective_config_path)
    
    // ============================================
    // RESOLVE PARAMETERS (for workflow logic)
    // ============================================
    // Get anat_only parameter with priority: CLI → YAML → defaults.yaml
    // No hardcoded default - must come from defaults.yaml
    def anat_only = paramResolver.getParamBool(params, 'anat_only')
    
    // ============================================
    // RUN ANATOMICAL WORKFLOW
    // ============================================
    ANAT_WF()
    
    // ============================================
    // RUN FUNCTIONAL WORKFLOW (conditionally)
    // ============================================
    if (!anat_only) {
        FUNC_WF(
            ANAT_WF.out.anat_after_skull,
            ANAT_WF.out.anat_reg_transforms,
            ANAT_WF.out.anat_reg_reference
        )
    }
    
    // // ============================================
    // // QC REPORT GENERATION (per subject)
    // // ============================================
    // // Read anat_only directly from config/params (cannot extract from async channel in workflow block)
    // def config_file_path = params.config_file ?: "${projectDir}/macacaMRIprep/config/defaults.yaml"
    // def batch_script = "${projectDir}/macacaMRIprep/nextflow_scripts/read_yaml_config.py"
    // def anat_only_from_config = false
    // try {
    //     def cmd = ["python3", batch_script, config_file_path, "general.anat_only", "--defaults=false"]
    //     def proc = cmd.execute()
    //     def output = new StringBuffer()
    //     proc.consumeProcessOutput(output, new StringBuffer())
    //     proc.waitFor()
    //     if (proc.exitValue() == 0) {
    //         anat_only_from_config = output.toString().trim() == "true"
    //     }
    // } catch (Exception e) {
    //     // Use default if config read fails
    // }
    // def anat_only = (params.anat_only != null && params.anat_only == true) ? true : anat_only_from_config
    
    // // Wait for anatomical QC to complete
    // def anat_qc_completion = ANAT_WF.out.anat_qc_channels
    //     .last()
    
    // // Create completion signal
    // def qc_completion_signal = anat_qc_completion
    // if (!anat_only) {
    //     def func_qc_completion = FUNC_WF.out.func_qc_channels
    //         .last()
        
    //     qc_completion_signal = anat_qc_completion
    //         .combine(func_qc_completion)
    //         .map { anat_meta, func_meta -> true }
    // }
    
    // // Get unique subjects
    // def all_subjects = ANAT_WF.out.anat_subjects_ch
    // if (!anat_only) {
    //     all_subjects = all_subjects.mix(
    //         FUNC_WF.out.func_jobs_ch_out
    //             .map { sub, ses, run_identifier, file_path, bids_naming_template -> sub }
    //             .unique()
    //     )
    // }
    
    // // Load config file (reuse config_file_path from above)
    // def config_file = file(config_file_path)
    
    // // Create snapshot directory path for each subject
    // def qc_report_input = all_subjects
    //     .unique()
    //     .combine(qc_completion_signal)
    //     .map { sub, completion_signal ->
    //         def snapshot_dir = file("${params.output_dir}/sub-${sub}/figures")
    //         [sub, snapshot_dir, config_file]
    //     }
    
    // QC_GENERATE_REPORT(qc_report_input)
}
