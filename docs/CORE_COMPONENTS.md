# macacaMRIprep Core Components

## Overview

This document describes the core architectural components of macacaMRIprep and their relationships, focusing on the main processing pipeline components.

## Core Components

### 1. BIDS Dataset Processor

**Location**: `macacaMRIprep/workflow/bids_processor.py`

**Purpose**: The central orchestrator that processes entire BIDS datasets with automatic file discovery and dependency management.

**Key Responsibilities**:
- Discovers and validates BIDS dataset structure
- Handles cross-session dependencies (anatomical data in one session, functional in another)
- Creates processing jobs for anatomical and functional data
- Manages multi-run T1w synthesis (automatic coregistration and averaging)
- Maintains BIDS derivatives structure for outputs

**Components**:
- `BIDSDatasetProcessor` - Main processor class
- `BaseJob` - Base class for all processing jobs
- `AnatomicalJob` - Handles anatomical MRI processing
- `FunctionalJob` - Handles functional MRI processing

### 2. Pipeline Management

**Location**: `macacaMRIprep/operations/pipeline.py`

**Purpose**: Manages the execution flow and state of processing pipelines.

**Key Responsibilities**:
- Executes processing operations in the correct order
- Manages pipeline state and execution flow
- Handles error recovery and cleanup
- Coordinates between different processing stages

**Components**:
- `Pipeline` - Main pipeline execution engine
- `PipelineState` - Manages pipeline state and execution flow

### 3. Workflow Processors

**Location**: `macacaMRIprep/workflow/`

**Purpose**: Implements the specific processing workflows for different data types.

**Key Responsibilities**:
- Defines the processing steps for each data type
- Coordinates with operations modules to execute processing
- Manages workflow-specific configurations and parameters

**Components**:
- `BasePreprocessingWorkflow` - Base workflow class
- `FunctionalProcessor` - Processes functional MRI data
- `AnatomicalProcessor` - Processes anatomical MRI data

#### Functional Processor
**Processing Steps**:
1. Slice timing correction
2. Motion correction
3. Despiking
4. Bias field correction
5. Skullstripping
6. Registration to target (anatomical or template)

#### Anatomical Processor
**Processing Steps**:
1. Bias field correction
2. Skullstripping
3. Registration to template space

### 4. Processing Operations

**Location**: `macacaMRIprep/operations/`

**Purpose**: Provides the actual implementation of processing algorithms and operations.

**Key Responsibilities**:
- Implements individual processing steps
- Interfaces with external tools (AFNI, ANTs, FSL)
- Provides validation and error checking
- Generates quality control metrics

**Core Operations**:
- **Preprocessing**: `preprocessing.py` - slice timing, motion correction, despiking, bias correction
- **Registration**: `registration.py` - ANTs-based registration and transform application
- **Skullstripping**: `skullstripping/` - UNet-based brain extraction
- **Validation**: `validation.py` - input/output validation and working directory management

## Component Relationships

### Data Flow Architecture

```
BIDS Dataset Processor
         ↓
    Creates Jobs
         ↓
    Workflow Processors
         ↓
    Pipeline Management
         ↓
    Processing Operations
         ↓
    Quality Control
```

### Detailed Relationships

#### 1. BIDS Processor → Workflow Processors
- **Relationship**: Creates and manages
- **Flow**: BIDS processor discovers data and creates appropriate workflow instances
- **Dependency**: BIDS processor depends on workflow processors for job execution

#### 2. Workflow Processors → Pipeline Management
- **Relationship**: Uses
- **Flow**: Workflow processors use pipeline management to execute their processing steps
- **Dependency**: Workflow processors depend on pipeline management for execution control

#### 3. Pipeline Management → Processing Operations
- **Relationship**: Executes
- **Flow**: Pipeline management calls individual processing operations in sequence
- **Dependency**: Pipeline management depends on processing operations for actual computation

#### 4. Processing Operations → Quality Control
- **Relationship**: Generates
- **Flow**: Processing operations generate quality control metrics and snapshots
- **Dependency**: Quality control depends on processing operations for data

### Execution Flow

1. **Initialization**: BIDS processor scans dataset and creates processing jobs
2. **Job Creation**: For each dataset, appropriate workflow processor is instantiated
3. **Workflow Execution**: Workflow processor defines processing steps and hands off to pipeline
4. **Pipeline Execution**: Pipeline management executes operations in sequence
5. **Operation Processing**: Individual operations perform their specific tasks
6. **Quality Control**: QC metrics are generated throughout the process
7. **Output**: Processed data is saved in BIDS derivatives format

### Dependency Management

- **Anatomical First**: Anatomical data is processed before functional data
- **Cross-session Handling**: BIDS processor manages dependencies across sessions
- **Template Registration**: Anatomical data is registered to template before functional registration
- **Error Recovery**: Pipeline management handles failures and cleanup

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

This architecture ensures that macacaMRIprep can process complex BIDS datasets with proper dependency management while maintaining robust error handling and quality control throughout the pipeline. 