Outputs
=======

brainana writes all results under the **output directory** you specify (e.g. ``/output`` when using Docker).

Directory layout (typical)
--------------------------

- **output_dir/** — Root of all outputs.
- **output_dir/sub-<subject_id>/** — Per-subject outputs (e.g. figures, subject-specific derivatives).
- **output_dir/sub-<subject_id>/figures/** — QC figures and snapshots.
- **output_dir/nextflow_reports/** — Nextflow reports and logs (e.g. ``nextflow_trace.txt``).
- **output_dir/fastsurfer/** — FastSurfer/surface reconstruction outputs when enabled.

Exact layout may depend on the pipeline configuration (anat-only vs full, template space, and QC options). Check the pipeline configuration and Nextflow ``publishDir`` directives in the repository for the authoritative list.

Logs and debugging
------------------

- Nextflow log: ``output_dir/nextflow_reports/nextflow_trace.txt``
- To inspect failed or aborted jobs: ``grep -E 'FAILED|ABORTED' output_dir/nextflow_reports/nextflow_trace.txt``

For pipeline step-by-step details, see :doc:`processing`. For design and architecture, see the repository (e.g. ``docs/paper/``).
