# Parameter Management System

## Overview

The banana Nextflow pipeline uses a centralized parameter management system with clear priority ordering. All parameters are resolved through `workflows/param_resolver.groovy`, which ensures consistency across all workflows and modules.

## Parameter Priority

Parameters are resolved with the following priority (highest to lowest):

1. **Command-line arguments** (`--param value`) - highest priority
2. **YAML config file** (user-provided or `defaults.yaml`) - medium priority
3. **defaults.yaml** (`macacaMRIprep/config/defaults.yaml`) - lowest priority

## Parameter Types

### CLI Parameters

These parameters can be set via command-line and have corresponding YAML keys:

| CLI Parameter | YAML Key | Description |
|-------------|----------|-------------|
| `--output_space` | `template.output_space` | Template space (e.g., "NMT2Sym:res-05") |
| `--anat_only` | `general.anat_only` | Process only anatomical data |
| `--overwrite` | `general.overwrite` | Overwrite existing outputs |
| `--subjects` | `bids_filtering.subjects` | Filter by subject IDs |
| `--sessions` | `bids_filtering.sessions` | Filter by session IDs |
| `--tasks` | `bids_filtering.tasks` | Filter by task names |
| `--runs` | `bids_filtering.runs` | Filter by run numbers |

**Example:**
```bash
nextflow run main.nf \
  --bids_dir /data/bids \
  --output_dir /data/output \
  --output_space "NMT2Sym:res-1" \
  --anat_only true \
  --config_file /path/to/config.yaml
```

### YAML-Only Parameters

These parameters are read only from YAML config files (not available via CLI):

- `func.reorient.enabled`
- `func.slice_timing_correction.enabled`
- `func.motion_correction.enabled`
- `anat.conform.enabled`
- `anat.bias_correction.enabled`
- `registration.enabled`
- ... and all other parameters in `defaults.yaml`

**Example YAML config:**
```yaml
func:
  reorient:
    enabled: false
  motion_correction:
    enabled: true
    dof: 6
```

### Workflow-Specific Parameters

These parameters are not in YAML and are only set via CLI:

- `--bids_dir` - Path to BIDS dataset (required)
- `--output_dir` - Path to output directory (required)
- `--config_file` - Path to YAML config file (optional)
- `--work_dir` - Nextflow work directory
- `--skip_bids_validation` - Skip BIDS validation
- `--max_cpus`, `--max_memory` - Resource limits
- `--gpu_enabled`, `--gpu_queue` - GPU settings

## Usage in Workflows

### Initialization

The parameter resolver must be initialized before use:

```groovy
def paramResolver = load('workflows/param_resolver.groovy')

workflow {
    // Initialize resolver
    paramResolver.initialize(params, projectDir)
    
    // Use resolved parameters
    def output_space = paramResolver.getParamOutputSpace(params, 'output_space', 'NMT2Sym:res-05')
    def anat_only = paramResolver.getParamBool(params, 'anat_only', false)
}
```

### Getting CLI Parameters

```groovy
// Get output_space with validation
def output_space = paramResolver.getParamOutputSpace(params, 'output_space', 'NMT2Sym:res-05')

// Get boolean parameter
def anat_only = paramResolver.getParamBool(params, 'anat_only', false)

// Get list parameter
def subjects = paramResolver.getParamList(params, 'subjects', null)
```

### Getting YAML-Only Parameters

```groovy
// Get boolean from YAML
def func_reorient_enabled = paramResolver.getYamlBool("func.reorient.enabled", true)

// Get string from YAML
def registration_type = paramResolver.getYamlString("registration.anat2template_xfm_type", "syn")

// Get integer from YAML
def shrink_factor = paramResolver.getYamlInt("anat.bias_correction.shrink_factor", 2, 1, null)
```

## Validation

The parameter resolver includes validation for all parameter types:

- **output_space**: Validates format (e.g., "native", "NMT2Sym:res-05")
- **Boolean**: Validates true/false, 1/0, yes/no, on/off
- **Integer**: Validates numeric value and optional range
- **Float**: Validates numeric value and optional range
- **List**: Validates list, array, or comma-separated string

Invalid values will cause the workflow to error and stop execution.

## Default Values

All default values are defined in `macacaMRIprep/config/defaults.yaml`. The `nextflow.config` file no longer contains default values for parameters that can be set via YAML.

## Migration Notes

### For Developers

1. **Remove Python script calls**: Replace calls to `read_yaml_config.py` with `paramResolver` functions
2. **Use centralized resolution**: All parameter resolution goes through `param_resolver.groovy`
3. **Update process scripts**: Processes now receive `effective_output_space` as a parameter from workflows (no Python function needed)

### For Users

1. **CLI parameters**: Use `--param value` format (unchanged)
2. **YAML config**: Create config files with same structure as `defaults.yaml`
3. **Priority**: CLI always overrides YAML, which overrides defaults

## Examples

### Example 1: Using CLI to override YAML

```bash
# config.yaml
template:
  output_space: "NMT2Sym:res-1"

# Command line
nextflow run main.nf --output_space "NMT2Sym:res-05" --config_file config.yaml

# Result: Uses "NMT2Sym:res-05" (CLI overrides YAML)
```

### Example 2: Using YAML to override defaults

```bash
# config.yaml
general:
  anat_only: true
func:
  motion_correction:
    enabled: false

# Command line
nextflow run main.nf --config_file config.yaml

# Result: Uses values from config.yaml (overrides defaults.yaml)
```

### Example 3: Mixing CLI and YAML

```bash
# config.yaml
func:
  reorient:
    enabled: false
  motion_correction:
    enabled: true

# Command line
nextflow run main.nf --output_space "native" --config_file config.yaml

# Result:
# - output_space = "native" (from CLI)
# - func.reorient.enabled = false (from YAML)
# - func.motion_correction.enabled = true (from YAML)
```

## Implementation Details

The parameter resolver (`workflows/param_resolver.groovy`) provides:

- **Type conversion**: Automatic conversion between string, boolean, integer, float, list
- **Validation**: Format and range validation with error messages
- **Caching**: YAML configs are loaded once and cached
- **Idempotent initialization**: Safe to call `initialize()` multiple times

## Troubleshooting

### Parameter not found

If a parameter is not found in CLI, YAML, or defaults, the resolver will use the provided default value. Check:
1. CLI parameter name is correct
2. YAML key path matches the expected structure
3. Default value is provided in the function call

### Invalid parameter value

If validation fails, the workflow will error with a descriptive message. Check:
1. Parameter format matches expected type
2. Value is within valid ranges (for integers/floats)
3. Boolean values use supported formats

### Config file not found

If the config file cannot be loaded, the resolver will:
1. Warn and use defaults.yaml only
2. Continue execution (non-fatal)
3. CLI parameters will still work
