# banana Core Components

## Overview

This document describes the core architectural components of banana and their relationships, focusing on the Nextflow-based processing pipeline.

## Core Components

### 1. Nextflow Pipeline

**Location**: `main.nf`, `modules/`

**Purpose**: The central orchestrator that processes entire BIDS datasets with maximum parallelization through per-step processing.

**Key Responsibilities**:
- Orchestrates preprocessing workflow with Nextflow
- Manages parallel execution of processing steps
- Handles automatic resumption from failures
- Coordinates resource allocation (CPU, GPU, memory)

**Components**:
- `main.nf` - Main Nextflow workflow
- `modules/anatomical.nf` - Anatomical processing modules
- `modules/functional.nf` - Functional processing modules
- `modules/qc.nf` - Quality control modules

### 2. Step Functions

**Location**: `macacaMRIprep/steps/`

**Purpose**: Individual processing step functions used by Nextflow modules.

**Key Responsibilities**:
- Implements individual processing steps
- Provides clean input/output interfaces
- Handles step-specific validation and error checking

**Components**:
- `bids_discovery.py` - BIDS dataset discovery and job creation
- `anatomical.py` - Anatomical processing steps (reorient, conform, bias correction, skull stripping, registration)
- `functional.py` - Functional processing steps (slice timing, motion correction, despike, bias correction, skull stripping, registration)
- `qc.py` - Quality control step functions
- `types.py` - Type definitions for step inputs/outputs

#### Anatomical Steps
**Processing Steps**:
1. T1w synthesis (if multiple runs)
2. Reorient to template/RAS
3. Conform to template space
4. Bias field correction
5. Skullstripping (GPU)
6. Registration to template

#### Functional Steps
**Processing Steps**:
1. Reorient + generate temporal mean
2. Slice timing correction
3. Motion correction
4. Despiking
5. Bias field correction (on temporal mean)
6. Conform temporal mean to target
7. Skullstripping on temporal mean (GPU)
8. Register temporal mean to target
9. Apply transforms to full 4D BOLD

### 3. Processing Operations

**Location**: `macacaMRIprep/operations/`

**Purpose**: Provides the actual implementation of processing algorithms and operations used by step functions.

**Key Responsibilities**:
- Implements core processing algorithms
- Interfaces with external tools (AFNI, ANTs, FSL)
- Provides validation and error checking
- Generates quality control metrics

**Core Operations**:
- **Preprocessing**: `preprocessing.py` - slice timing, motion correction, despiking, bias correction
- **Registration**: `registration.py` - ANTs-based registration and transform application
- **Synthesis**: `synthesis_multiple_anat.py` - T1w synthesis for multiple runs
- **Validation**: `validation.py` - input/output validation and working directory management

## Component Relationships

### Data Flow Architecture

```
Python Discovery Script (discover_bids_for_nextflow.py)
         ↓
    Creates Processing Jobs (JSON files)
         ↓
Nextflow Pipeline (main.nf)
         ↓
    Parallel Step Execution
         ├─→ Anatomical Modules
         │      ↓
         │   Step Functions
         │      ↓
         │   Processing Operations
         │
         └─→ Functional Modules
                ↓
             Step Functions
                ↓
             Processing Operations
         ↓
    Quality Control Modules
         ↓
    BIDS Derivatives Output
```

### Detailed Relationships

#### 1. Python Discovery Script → Nextflow Pipeline
- **Relationship**: Prepares
- **Flow**: Python script runs before Nextflow to scan dataset and create job JSON files
- **Dependency**: Nextflow depends on pre-generated job JSON files from discovery script

#### 2. Nextflow Modules → Step Functions
- **Relationship**: Calls
- **Flow**: Nextflow modules call Python step functions for each processing step
- **Dependency**: Nextflow modules depend on step functions for processing logic

#### 3. Step Functions → Processing Operations
- **Relationship**: Uses
- **Flow**: Step functions call processing operations to perform actual computation
- **Dependency**: Step functions depend on processing operations for algorithm implementation

#### 4. Processing Operations → Quality Control
- **Relationship**: Generates
- **Flow**: Processing operations generate quality control metrics and snapshots
- **Dependency**: Quality control depends on processing operations for data

### Execution Flow

1. **BIDS Discovery**: Python discovery script runs before Nextflow to scan dataset and create job JSON files
2. **Initialization**: Nextflow pipeline starts and loads configuration
3. **Parallel Execution**: Nextflow executes all steps in parallel across subjects/sessions/runs
4. **Step Processing**: Each step function performs its specific task
5. **Operation Execution**: Processing operations interface with external tools (AFNI, ANTs, FSL)
6. **Quality Control**: QC modules generate metrics and snapshots
7. **Output**: Processed data is saved in BIDS derivatives format

### Dependency Management

- **Nextflow Dependencies**: Nextflow automatically manages step dependencies
- **Anatomical First**: Anatomical steps complete before functional steps that depend on them
- **Cross-session Handling**: BIDS discovery identifies cross-session dependencies
- **Automatic Resumption**: Nextflow can resume from any failed step
- **Resource Management**: Nextflow manages CPU, GPU, and memory allocation per step

## Key Design Principles

1. **Modularity**: Each component has a single, well-defined responsibility
2. **Dependency Safety**: Two-phase processing ensures proper data dependencies
3. **BIDS Compliance**: All inputs and outputs maintain BIDS structure
4. **Error Handling**: Robust error handling with cleanup and recovery
5. **Quality Control**: Integrated QC throughout the processing pipeline
6. **Configuration**: Flexible configuration system for different processing needs

## External Dependencies

The core components interface with external tools through the processing operations:

- **AFNI**: Slice timing correction, motion correction, despiking
- **ANTs**: Registration and transform application
- **FSL**: Additional preprocessing operations
- **PyTorch**: UNet models for skullstripping
- **Nibabel**: Neuroimaging file I/O

This architecture ensures that banana can process complex BIDS datasets with maximum parallelization through Nextflow while maintaining robust error handling and quality control throughout the pipeline. 