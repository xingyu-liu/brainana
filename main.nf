/*
 * Main Nextflow workflow for brainana
 * 
 * This workflow processes BIDS datasets using per-step parallelization
 * for maximum efficiency.
 * 
 * BIDS discovery is performed by a Python script BEFORE this workflow runs.
 * The discovery script validates the BIDS dataset, discovers all jobs, and
 * saves JSON files that this workflow reads to create channels.
 * 
 */

nextflow.enable.dsl=2

import groovyx.gpars.dataflow.DataflowQueue

// Include sub-workflows
include { ANAT_WF } from './workflows/anatomical_workflow.nf'
include { FUNC_WF } from './workflows/functional_workflow.nf'

// QC reports are generated in workflow.onComplete (below) so that a report is
// always produced, even when the run aborts early on an upstream failure.

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
    // Must be generated before workflows are invoked
    def effective_config_path = paramResolver.generateEffectiveConfig(params, projectDir, params.output_dir)
    
    // Verify the file was created successfully
    def effective_config_file_check = new File(effective_config_path)
    if (!effective_config_file_check.exists()) {
        error "Failed to generate effective config file at: ${effective_config_path}"
    }
    
    def effective_config_file = file(effective_config_path)
    
    // ============================================
    // RESOLVE PARAMETERS (for workflow logic)
    // ============================================
    // Get anat_only parameter with priority: CLI → YAML → defaults.yaml
    def anat_only = paramResolver.getParamBool(params, 'anat_only')
    
    // Resolve GPU usage policy from config + runtime hardware detection.
    // general.gpu_device controls whether GPU scheduling should be enabled.
    // -1 / "cpu" => force CPU-only scheduling (no GPU tokens consumed by workflows).
    def general_gpu_device = paramResolver.getYamlParam('general.gpu_device', 'auto')
    def general_gpu_device_str = general_gpu_device == null ? 'auto' : general_gpu_device.toString().trim().toLowerCase()
    def gpu_forced_cpu = (general_gpu_device_str == 'cpu' || general_gpu_device_str == '-1')
    params.use_gpu = !gpu_forced_cpu && ((params.gpu_count ?: 0) > 0)

    // ============================================
    // GLOBAL GPU TOKEN POOL
    // ============================================
    // Create a shared GPU token queue so ALL GPU processes draw from the same pool
    // This enforces max_jobs_per_gpu across anatomical + functional GPU steps.
    def gpu_queue = new DataflowQueue()
    def gpu_count = params.use_gpu ? (params.gpu_count ?: 0) : 0
    def max_jobs_per_gpu = params.max_jobs_per_gpu ?: 1
    def token_gpu_count = gpu_count > 0 ? gpu_count : 1
    def token_jobs_per_gpu = max_jobs_per_gpu > 0 ? max_jobs_per_gpu : 1
    (0..<token_gpu_count).each { gpu_id ->
        (0..<token_jobs_per_gpu).each { gpu_queue << gpu_id }
    }
    
    // ============================================
    // RUN ANATOMICAL WORKFLOW
    // ============================================
    ANAT_WF(gpu_queue)

    // ============================================
    // RUN FUNCTIONAL WORKFLOW (conditionally)
    // ============================================
    if (!anat_only) {
        FUNC_WF(
            ANAT_WF.out.anat_after_bias_brain,  // Use brain version for functional registration
            ANAT_WF.out.anat_reg_transforms,
            ANAT_WF.out.anat_reg_reference,
            ANAT_WF.out.surf_actual_subject_id,
            ANAT_WF.out.anat_skull_seg,       // T1w-space segmentation (for confounds tissue regressors)
            ANAT_WF.out.anat_skull_seg_lut,   // atlas LUT (tissue classification)
            gpu_queue
        )
    }
    
    // ============================================
    // QC REPORT GENERATION
    // ============================================
    // Reports are generated in workflow.onComplete (below) instead of as a DAG
    // node, so they are produced on both success and early abort. See main.nf
    // bottom for the handler.
}

// ============================================
// WORKFLOW COMPLETION HANDLER
// ============================================
// Always runs (success OR early abort). Generates the per-subject QC reports so
// the user gets a report even when the run aborts, and prints a failure summary.
workflow.onComplete {
    def failedCount = workflow.stats.failedCount
    def ignoredCount = workflow.stats.ignoredCount

    // --- Always (re)generate QC reports, embedding the run status -------------
    // QC snapshots are published incrementally, so a report built here contains
    // whatever completed. Wrapped so report generation can never crash the run.
    if (params.output_dir != null) {
        try {
            def traceFile = "${params.output_dir}/nextflow_reports/nextflow_trace.txt"
            def status = [
                success        : workflow.success,
                exit_status    : workflow.exitStatus,
                error_message  : workflow.errorMessage,
                error_report   : workflow.errorReport,
                duration       : workflow.duration?.toString(),
                succeeded_count: workflow.stats.succeededCount,
                failed_count   : failedCount,
                ignored_count  : ignoredCount,
                trace_file     : traceFile,
            ]

            def reportsDir = new File("${params.output_dir}/nextflow_reports")
            reportsDir.mkdirs()
            def statusFile = new File(reportsDir, "run_status.json")
            statusFile.text = groovy.json.JsonOutput.toJson(status)

            def config_file_path = params.config_file ?: "${projectDir}/src/nhp_mri_prep/config/defaults.yaml"
            def python = System.getenv('PYTHON') ?: 'python3'
            def gen_script = "${projectDir}/src/nhp_mri_prep/nextflow_scripts/generate_reports.py"
            def cmd = [
                python, gen_script,
                "--output-dir", "${params.output_dir}",
                "--config-file", config_file_path,
                "--status-file", statusFile.toString(),
            ]
            def out = new StringBuffer()
            def err = new StringBuffer()
            def proc = cmd.execute()
            proc.consumeProcessOutput(out, err)
            proc.waitFor()
            if (out.length() > 0) print out.toString()
            if (proc.exitValue() != 0) {
                println "WARNING: QC report generation exited with ${proc.exitValue()}."
                if (err.length() > 0) println err.toString()
            }
        } catch (Exception e) {
            println "WARNING: Could not generate QC report - ${e.message}"
            println "  Check the trace file: ${params.output_dir}/nextflow_reports/nextflow_trace.txt"
        }
    }

    // --- Failure summary ------------------------------------------------------
    // Report on failed/ignored tasks (typically surface reconstruction failures)
    if (ignoredCount > 0 || failedCount > 0) {
        println ""
        println "WARNING: Some tasks failed (${failedCount + ignoredCount} total)."
        println "This may include surface reconstruction jobs that failed due to image quality issues."
        println ""
        println "To see details, check the trace file:"
        println "  ${params.output_dir}/nextflow_reports/nextflow_trace.txt"
        println ""
        println "Filter for failed tasks with:"
        println "  grep -E 'FAILED|ABORTED' ${params.output_dir}/nextflow_reports/nextflow_trace.txt"
    }

    if (!workflow.success) {
        println ""
        println "Pipeline aborted early. A partial QC report (with the error in the"
        println "Run status section) was written to: ${params.output_dir}/sub-*.html"
    }

    println ""
}
