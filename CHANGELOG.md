# Changelog

All notable changes to macacaMRIprep will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Immediate job completion caching**: Jobs are now stamped as completed immediately when they finish processing, rather than waiting for all jobs in a batch to complete
- **Robust resumption support**: Processing can now be safely resumed even if interrupted mid-batch, with completed jobs properly recognized
- **Enhanced cache validation**: Added optional output file verification for cached completion status
- **Streamlined cache management**: Consolidated cache operations into a single `_stamp_job_completion` method

### Changed
- **Improved cache reliability**: Fixed issue where job completion status was not updated in cache when processing was interrupted
- **Reduced code duplication**: Added `_handle_job_completion` helper function to eliminate duplicate completion handling code
- **Simplified cache architecture**: Removed redundant `_update_job_cache` method in favor of unified `_stamp_job_completion`

### Fixed
- **Cache persistence bug**: Jobs that completed successfully but were interrupted before batch completion are now properly cached
- **Resumption reliability**: Processing can now be safely resumed from any point without losing progress
- **Cross-session dependency handling**: Improved handling of functional jobs that depend on anatomical jobs from different sessions

### Technical Details
- **Cache key generation**: Uses MD5 hash of job identity (inputs + template) for reliable job identification
- **Generated file tracking**: Tracks actual output files generated during processing for validation
- **Immediate persistence**: Cache is saved to disk immediately after each job completion
- **Backward compatibility**: Existing cache files are automatically migrated to new format

## [1.0.0] - 2024-01-01

### Added
- Initial release of macacaMRIprep
- BIDS dataset processing support
- Anatomical and functional preprocessing workflows
- Template registration capabilities
- Quality control reporting
- Parallel processing support 