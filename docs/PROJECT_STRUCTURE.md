# banana Project Structure

## Overview

**banana** is a comprehensive Python package for preprocessing and registration of macaque neuroimaging data. It provides robust, reproducible preprocessing workflows specifically designed for non-human primate neuroimaging research with BIDS dataset support and sophisticated dependency management.

## Key Features

- **🧠 BIDS-First Approach**: Complete BIDS dataset processing with automatic file discovery
- **⚡ Advanced Processing**: Complete preprocessing pipeline including slice timing correction, motion correction, despiking, skullstripping, and bias field correction
- **🔧 Nextflow-Based Architecture**: Maximum parallelization through per-step processing
- **🖥️ Nextflow Pipeline**: User-friendly Nextflow workflow with automatic resumption and resource management

## Project Architecture

### Core Components

The project follows a modular architecture with the following main components:

#### 1. **Nextflow Pipeline**
- **Location**: `main.nf`, `modules/`
- **Main Components**:
  - `main.nf` - Main Nextflow workflow orchestrator
  - `modules/anatomical.nf` - Anatomical processing modules
  - `modules/functional.nf` - Functional processing modules
  - `modules/qc.nf` - Quality control modules
- **Discovery Script**:
  - `macacaMRIprep/nextflow_scripts/discover_bids_for_nextflow.py` - BIDS dataset discovery (runs before Nextflow)
  - `macacaMRIprep/nextflow_scripts/read_yaml_config.py` - YAML config reader utility for Nextflow workflow
- **Purpose**: Orchestrates preprocessing with maximum parallelization through per-step processing

#### 2. **Step Functions**
- **Location**: `macacaMRIprep/steps/`
- **Main Modules**:
  - `bids_discovery.py` - BIDS dataset discovery and job creation
  - `anatomical.py` - Anatomical processing step functions
  - `functional.py` - Functional processing step functions
  - `qc.py` - Quality control step functions
  - `types.py` - Type definitions for step inputs/outputs
- **Purpose**: Individual processing steps used by Nextflow modules for maximum parallelization

#### 3. **Processing Operations**
- **Location**: `macacaMRIprep/operations/`


##### Preprocessing Operations
- `preprocessing.py` - Core preprocessing functions:
  - `slice_timing_correction` - Slice timing correction
  - `motion_correction` - Motion correction
  - `despike` - Despiking
  - `bias_correction` - Bias field correction
  - `precheck` - Preprocessing checks

##### Registration Operations
- `registration.py` - Registration functions:
  - `ants_register` - ANTs registration
  - `ants_apply_transforms` - Apply ANTs transforms
  - `compose_ants_registration_cmd` - Compose ANTs commands

##### Skullstripping Operations
- **Location**: `macacaMRIprep/operations/skullstripping/`
- **Components**:
  - `skullstripping_api.py` - Main skullstripping API
  - `function.py` - Skullstripping functions
  - `dataset.py` - Dataset handling for skullstripping
  - `model.py` - UNet model implementation
- **Models**: 
  - `skullstripping_anat.model` - Anatomical skullstripping model
  - `skullstripping_func.model` - Functional skullstripping model

##### Validation Operations
- `validation.py` - Validation functions:
  - `validate_input_file` - Input file validation
  - `validate_output_file` - Output file validation
  - `ensure_working_directory` - Working directory validation

#### 6. **Quality Control**
- **Location**: `macacaMRIprep/quality_control/`
- **Components**:
  - `reports.py` - Quality control report generation
  - `snapshots.py` - Snapshot processing for QC
- **Functions**:
  - `create_motion_correction_qc` - Motion correction QC
  - `create_skullstripping_qc` - Skullstripping QC
  - `create_registration_qc` - Registration QC
  - `create_bias_correction_qc` - Bias correction QC
  - `generate_qc_report` - Generate comprehensive QC reports

#### 7. **Configuration Management**
- **Location**: `macacaMRIprep/config/`
- **Components**:
  - `config.py` - Main configuration management
  - `validation.py` - Configuration validation
  - `defaults.json` - Default configuration settings
- **Functions**:
  - `load_config` - Load configuration
  - `validate_config` - Validate configuration
  - `validate_paths` - Validate file paths

#### 8. **Utilities**
- **Location**: `macacaMRIprep/utils/`

##### System Utilities
- `system.py` - System-level utilities:
  - `run_command` - Command execution
  - `check_dependency` - Dependency checking

##### MRI Utilities
- `mri.py` - MRI-specific utilities:
  - `calculate_func_tmean` - Calculate functional temporal mean
  - `reorient_image_to_target` - Reorient image to match target file orientation
  - `reorient_image_to_orientation` - Reorient image to specific orientation (e.g., RAS)
  - `get_image_shape` - Get image shape
  - `get_image_resolution` - Get image resolution
  - `get_image_orientation` - Get image orientation

##### Template Utilities
- `templates.py` - Template management:
  - `resolve_template` - Template resolution
  - `resolve_template_file` - Template file resolution
  - `list_available_templates` - List available templates
  - `validate_template_spec` - Template specification validation
  - `get_template_manager` - Template manager access

##### BIDS Utilities
- `bids.py` - BIDS-specific utilities:
  - `parse_bids_entities` - Parse BIDS entities
  - `create_bids_filename` - Create BIDS filenames
  - `get_filename_stem` - Get filename stem
  - `find_bids_metadata` - Find BIDS metadata

##### Logging Utilities
- `logger.py` - Logging utilities:
  - `setup_logging` - Setup logging
  - `get_logger` - Get logger instance
  - `setup_workflow_logging` - Setup workflow logging
  - `setup_step_logging` - Setup step-specific logging

#### 9. **Environment Management**
- **Location**: `macacaMRIprep/`
- **Main Module**: `environment.py`
- **Functions**:
  - `check_environment` - Environment checking
  - `check_dependencies` - Dependency management

#### 10. **Templates**
- **Location**: `templatezoo/`
- **Content**: NMT2Sym template files at various resolutions (0.25mm, 0.5mm, 1mm, 2mm)
- **Types**: T1w, brain masks, segmentation files, gray matter masks

## External Dependencies

The project relies on several external tools and libraries:

### Required External Tools
- **FSL** (≥6.0) - FMRIB Software Library
- **ANTs** (≥2.3) - Advanced Normalization Tools
- **AFNI** (≥20.0) - Analysis of Functional NeuroImages

### Python Libraries
- **PyTorch** - Deep learning framework for UNet models
- **Nibabel** - Neuroimaging file I/O
- **BIDS** - BIDS specification support
- **Matplotlib** - Quality control visualization
- **NumPy** - Numerical computing
- **Pandas** - Data manipulation

## Directory Structure

```
macacaMRIprep/
├── macacaMRIprep/                    # Main package directory
│   ├── __init__.py                   # Package initialization
│   ├── info.py                       # Package information
│   ├── environment.py                # Environment management
│   ├── cli/                          # Command line interface
│   │   ├── __init__.py
│   │   └── preproc.py                # Main CLI entry point
│   ├── workflow/                     # Workflow processing
│   │   ├── __init__.py
│   │   ├── base.py                   # Base workflow classes
│   │   ├── bids_processor.py         # BIDS dataset processor
│   │   ├── anat2template.py          # Anatomical to template workflow
│   │   └── func2target.py            # Functional to target workflow
│   ├── operations/                   # Processing operations
│   │   ├── __init__.py
│   │   ├── pipeline.py               # Pipeline management
│   │   ├── preprocessing.py          # Preprocessing operations
│   │   ├── registration.py           # Registration operations
│   │   ├── validation.py             # Validation operations
│   │   └── skullstripping/           # Skullstripping operations
│   │       ├── __init__.py
│   │       ├── skullstripping_api.py # Main skullstripping API
│   │       ├── function.py           # Skullstripping functions
│   │       ├── dataset.py            # Dataset handling
│   │       └── model.py              # UNet model implementation
│   ├── quality_control/              # Quality control
│   │   ├── __init__.py
│   │   ├── reports.py                # QC report generation
│   │   └── snapshots.py              # QC snapshot processing
│   ├── utils/                        # Utility functions
│   │   ├── __init__.py
│   │   ├── system.py                 # System utilities
│   │   ├── mri.py                    # MRI utilities
│   │   ├── templates.py              # Template utilities
│   │   ├── bids.py                   # BIDS utilities
│   │   └── logger.py                 # Logging utilities
│   ├── config/                       # Configuration management
│   │   ├── __init__.py
│   │   ├── config.py                 # Configuration management
│   │   ├── validation.py             # Configuration validation
│   │   └── defaults.json             # Default configuration
│   └── unet_model/                   # UNet models
│       ├── skullstripping_anat.model # Anatomical skullstripping model
│       └── skullstripping_func.model # Functional skullstripping model
├── modules/                          # Nextflow modules
│   ├── anatomical.nf                # Anatomical processing modules
│   ├── functional.nf               # Functional processing modules
│   └── qc.nf                        # Quality control modules
├── main.nf                           # Main Nextflow workflow
├── nextflow.config                   # Nextflow configuration
├── run_nextflow.sh                   # Nextflow wrapper script
├── templatezoo/                      # Template files
│   └── *.nii.gz                     # NMT2Sym template files
├── tests/                            # Test suite
├── docs/                             # Documentation
├── README_for_inz.rst               # Main documentation
├── README_NEXTFLOW.md               # Nextflow documentation
├── README_Docker.md                  # Docker documentation
├── CHANGELOG.md                      # Change log
├── CONTRIBUTING.md                   # Contribution guidelines
├── LICENSE                           # License file
├── pyproject.toml                    # Project configuration
├── setup.cfg                         # Setup configuration
└── uv.lock                           # Dependency lock file
```

## Data Flow

1. **Input**: BIDS-formatted dataset with anatomical and functional MRI data
2. **Processing**: Two-phase approach (anatomical first, then functional)
3. **Output**: Processed data in BIDS derivatives format with quality control reports

## Key Workflows

### Anatomical Processing
1. Bias field correction
2. Skullstripping using UNet model
3. Registration to template space using ANTs

### Functional Processing
1. Slice timing correction
2. Motion correction
3. Despiking
4. Bias field correction
5. Skullstripping using UNet model
6. Registration to anatomical or template space

## Configuration

The system uses YAML-based configuration with validation:
- Default settings in `macacaMRIprep/config/defaults.yaml`
- User-specific overrides via Nextflow parameters or config files
- Environment variable support for external tool paths

## Quality Control

Comprehensive quality control includes:
- Motion correction quality assessment
- Skullstripping quality evaluation
- Registration quality verification
- Bias correction quality assessment
- Automated report generation with visualizations

## Development

- **Testing**: Comprehensive test suite in `tests/`
- **Documentation**: RST-based documentation with examples
- **Contributing**: Guidelines in `CONTRIBUTING.md`
- **License**: MIT License 