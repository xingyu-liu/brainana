# Changelog

All notable changes to banana will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Project renamed**: Project renamed from macacaMRIprep to banana
- **Architecture migration**: Migrated from CLI-based workflow to Nextflow-based pipeline for maximum parallelization
- **Docker image**: Docker image name changed from `macacamriprep:latest` to `banana:latest`
- **Removed CLI**: Removed command-line interface (`macacaMRIprep-preproc`); use Nextflow pipeline instead
- **Step-based architecture**: Processing now uses individual step functions orchestrated by Nextflow modules

### Added
- **Nextflow pipeline**: Complete Nextflow implementation with per-step parallelization
- **Nextflow modules**: Modular Nextflow components for BIDS discovery, anatomical, functional, and QC processing
- **Step functions**: Individual processing step functions in `macacaMRIprep/steps/` for use by Nextflow
- **Nextflow wrapper script**: `run_nextflow.sh` for clean project directory management
- **Automatic resumption**: Nextflow automatically handles resumption from any failed step
- **Per-step parallelization**: Each processing step runs in parallel across all subjects/sessions/runs

### Removed
- **CLI command**: `macacaMRIprep-preproc` command removed (use Nextflow instead)
- **Workflow classes**: Old workflow classes (`BIDSDatasetProcessor`, `AnatomicalProcessor`, `FunctionalProcessor`) removed
- **Pipeline management**: Old pipeline management system removed (Nextflow handles orchestration)

## [1.0.0] - 2024-01-01

### Added
- Initial release of banana (formerly macacaMRIprep)
- BIDS dataset processing support
- Anatomical and functional preprocessing workflows
- Template registration capabilities
- Quality control reporting
- Parallel processing support 