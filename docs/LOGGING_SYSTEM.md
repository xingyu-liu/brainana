# Logging System Walkthrough

This document explains the multi-layered logging system in macacaMRIprep, especially in the Nextflow context.

## Overview

The logging system has **three main layers**:

1. **Python Standard Logging** - Application-level logging (INFO, DEBUG, ERROR, etc.)
2. **Command Logging** - Dedicated file tracking all shell commands executed
3. **Nextflow Process Logging** - Nextflow's built-in process execution logs

---

## 1. Python Standard Logging

### Architecture

The Python logging system uses a centralized logger hierarchy:

```
macacaMRIprep (root logger)
├── macacaMRIprep.step.{step_name} (step-specific loggers)
└── macacaMRIprep.{workflow_name} (workflow loggers)
```

### Key Components

**Location**: `macacaMRIprep/utils/logger.py`

#### Main Functions

1. **`setup_logging()`** - Sets up main application logging
   - Creates console and optional file handlers
   - Used for standalone scripts

2. **`setup_step_logging()`** - Creates step-specific loggers
   - Creates `{step_name}.log` in specified logs directory
   - Used for individual processing steps
   - Format: `%(asctime)s | %(levelname)-8s | %(message)s`

3. **`setup_workflow_logging()`** - Creates workflow loggers
   - Creates `workflow.log` in workflow directory
   - Used for entire workflow execution

4. **`get_logger(name)`** - Gets a logger instance
   - Returns child logger of root logger
   - Automatically inherits parent configuration

### Usage in Nextflow

In Nextflow processes, Python logging goes to:
- **Console** (stdout/stderr) - captured by Nextflow
- **Nextflow work directories** - each process has its own stdout/stderr files

**Example**:
```python
from macacaMRIprep.utils import get_logger

logger = get_logger(__name__)
logger.info("Processing started")
logger.debug("Detailed debug information")
```

---

## 2. Command Logging (NEW)

### Purpose

Tracks **all shell commands** executed via `run_command()` in a single file, similar to FreeSurfer's `.cmd` files.

### Automatic Log Rotation

To prevent log files from consuming excessive storage on large datasets, **automatic log rotation** is enabled by default:

- **Size limit**: 20 MB (configurable, default: 20 MB)
- **Rotation**: When limit is reached, log is rotated to `commands.log.1`, `commands.log.2`, etc.
- **Compression**: Old logs are automatically compressed with gzip (`.gz` extension)
- **Retention**: Keeps up to 5 rotated log files (oldest are automatically deleted)

**Example log files** (standard logrotate convention):
```
reports/
├── commands.log          # Current active log (newest, actively being written)
├── commands.log.1.gz    # Most recent rotated log (compressed) - newest after current
├── commands.log.2.gz    # Older rotated log (compressed)
├── commands.log.3.gz    # Even older rotated log (compressed)
└── commands.log.4.gz    # Oldest kept log (compressed) - highest number = oldest
```

**Numbering Convention**: Follows standard log rotation (same as `logrotate`):
- `.1` = most recently rotated log (newest)
- Higher numbers = older logs
- When rotation occurs: existing logs shift (`.1` → `.2`, `.2` → `.3`, etc.), and current log becomes `.1`

**Configuration**:
```python
from macacaMRIprep.utils import set_cmd_log_rotation_config

# Customize rotation settings (before initializing log file)
set_cmd_log_rotation_config(
    max_size_mb=50.0,   # Rotate at 50 MB instead of 20 MB
    max_files=10,       # Keep 10 rotated files instead of 5
    compress=False      # Don't compress (saves CPU, uses more disk)
)
```

### Architecture

**Location**: `macacaMRIprep/utils/system.py`

#### Key Functions

1. **`init_cmd_log_file(output_dir)`** - Initialize command log file
   - Creates `output_dir/reports/commands.log`
   - Sets global command log file path
   - Called automatically in Nextflow processes

2. **`set_cmd_log_file(path)`** - Manually set command log file
   - Override default location if needed

3. **`get_cmd_log_file()`** - Get current command log file path

4. **`run_command()`** - Executes commands and logs them
   - Logs to Python logger (INFO level)
   - **Also writes to command log file** if enabled

### Command Log File Format

The command log file uses a format similar to FreeSurfer:

```
# Command log file for macacaMRIprep
# Created: 2024-01-15 10:30:45
# Output directory: /path/to/output
#--------------------------------------------

#--------------------------------------------
#@# 3dTshift Mon Jan 15 10:31:12 PST 2024
cd /work/dir
3dTshift -prefix output.nii.gz -TR 2.0s -tzero 0 -tpattern alt+z input.nii.gz

#--------------------------------------------
#@# mcflirt Mon Jan 15 10:31:45 PST 2024
mcflirt -in input.nii.gz -out output -dof 6 -reffile ref.nii.gz -mats -plots
```

### Automatic Initialization in Nextflow

In each Nextflow process, command logging is automatically initialized:

```python
from macacaMRIprep.utils import init_cmd_log_file

# Initialize command log file (saves to output_dir/reports/commands.log)
init_cmd_log_file('${params.output_dir}')
```

This happens at the start of each Python script block in Nextflow modules.

### Where Commands Are Logged

When `run_command()` is called:

1. **Python Logger** (INFO level):
   ```
   System: executing command - 3dTshift -prefix output.nii.gz ...
   System: command completed - exit code 0, duration 12.34s
   ```

2. **Command Log File** (`output_dir/reports/commands.log`):
   ```
   #@# 3dTshift Mon Jan 15 10:31:12 PST 2024
   cd /work/dir
   3dTshift -prefix output.nii.gz ...
   ```

3. **Nextflow Process Logs** (via stdout/stderr capture)

---

## 3. Nextflow Process Logging

### Built-in Logging

Nextflow automatically captures:
- **stdout** - Standard output from processes
- **stderr** - Standard error from processes
- **command.log** - The exact shell command executed

### Log Locations

1. **Process Work Directories**: `~/.nextflow/work/{hash}/`
   - `command.log` - Shell command executed
   - `.command.out` - stdout
   - `.command.err` - stderr
   - `.command.sh` - Shell script

2. **Nextflow Main Log**: `~/.nextflow/logs/nextflow.log`
   - Overall workflow execution
   - Process status and errors

3. **Reports Directory**: `output_dir/reports/`
   - `nextflow_report.html` - Execution report
   - `nextflow_timeline.html` - Timeline visualization
   - `nextflow_trace.txt` - Execution trace
   - `commands.log` - **Our command log file** (NEW)

---

## Log Flow in Nextflow Processes

Here's how logging flows through a typical Nextflow process:

```
┌─────────────────────────────────────────────────────────┐
│ Nextflow Process (e.g., ANAT_REORIENT)                  │
├─────────────────────────────────────────────────────────┤
│                                                           │
│ 1. Process starts                                         │
│    └─> Nextflow creates work directory                   │
│                                                           │
│ 2. Python script begins                                  │
│    └─> init_cmd_log_file('${params.output_dir}')         │
│        └─> Creates output_dir/reports/commands.log       │
│                                                           │
│ 3. Processing operations                                  │
│    └─> run_command(['3dTshift', ...])                    │
│        ├─> Logs to Python logger (INFO)                  │
│        │   └─> Goes to stdout → Nextflow captures        │
│        └─> Writes to commands.log                        │
│            └─> output_dir/reports/commands.log           │
│                                                           │
│ 4. Process completes                                      │
│    └─> Nextflow saves stdout/stderr to work directory    │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Finding Logs

### Command Log File (All Commands)
```bash
# Single file with all commands
cat output_dir/reports/commands.log
```

### Nextflow Process Logs
```bash
# Find all process work directories
find ~/.nextflow/work -name "command.log"

# View a specific process's logs
cat ~/.nextflow/work/*/command.log
cat ~/.nextflow/work/*/.command.out
cat ~/.nextflow/work/*/.command.err
```

### Nextflow Main Log
```bash
cat ~/.nextflow/logs/nextflow.log
```

### Nextflow Reports
```bash
# HTML reports
open output_dir/reports/nextflow_report.html
open output_dir/reports/nextflow_timeline.html

# Text trace
cat output_dir/reports/nextflow_trace.txt
```

---

## Log Levels

### Python Logging Levels

- **DEBUG** - Detailed diagnostic information
- **INFO** - General informational messages
- **WARNING** - Warning messages
- **ERROR** - Error messages
- **CRITICAL** - Critical errors

### Verbose Levels

The system uses a 0-2 verbose scale:
- **0 (Quiet)** - Only errors
- **1 (Normal)** - INFO level (default)
- **2 (Verbose)** - DEBUG level

---

## Example: Tracing a Command

Let's trace what happens when `run_command(['3dTshift', ...])` is called:

1. **Function Call**: `run_command(['3dTshift', '-prefix', 'out.nii.gz', 'in.nii.gz'])`

2. **Python Logger** writes:
   ```
   2024-01-15 10:31:12 | INFO     | System: executing command - 3dTshift -prefix out.nii.gz in.nii.gz
   ```

3. **Command Log File** writes:
   ```
   #--------------------------------------------
   #@# 3dTshift Mon Jan 15 10:31:12 PST 2024
   3dTshift -prefix out.nii.gz in.nii.gz
   ```

4. **Command Executes** (subprocess.run)

5. **Python Logger** writes:
   ```
   2024-01-15 10:31:24 | INFO     | System: command completed - exit code 0, duration 12.34s
   ```

6. **Nextflow Captures** all stdout/stderr to work directory

---

## Configuration

### Disable Command Logging

If you want to disable command logging:

```python
from macacaMRIprep.utils import set_cmd_log_file

# Disable command logging
set_cmd_log_file(None)
```

### Custom Command Log Location

```python
from macacaMRIprep.utils import set_cmd_log_file
from pathlib import Path

# Use custom location
set_cmd_log_file(Path("/custom/path/commands.log"))
```

### Change Python Log Level

In Nextflow processes, Python logging level is controlled by:
- Default: INFO level
- Can be changed via logger configuration in each step

---

## Best Practices

1. **Always initialize command logging** in Nextflow processes:
   ```python
   init_cmd_log_file('${params.output_dir}')
   ```

2. **Use appropriate log levels**:
   - INFO for normal operations
   - DEBUG for detailed diagnostics
   - ERROR for failures

3. **Check command log file** for debugging:
   ```bash
   tail -f output_dir/reports/commands.log
   ```

4. **Use Nextflow reports** for workflow overview:
   ```bash
   open output_dir/reports/nextflow_report.html
   ```

---

## Troubleshooting

### Command log file not created?

- Check that `output_dir` is set correctly
- Verify `reports/` directory is writable
- Check Python logger for initialization messages

### Missing commands in log file?

- Ensure `init_cmd_log_file()` was called
- Verify `run_command()` is being used (not direct subprocess calls)
- Check file permissions

### Too much logging?

- Adjust log levels in configuration
- Use DEBUG only when needed
- Command log file is always written (if enabled)

### Log file too large?

- **Automatic rotation is enabled by default** (100 MB limit)
- Check for rotated log files: `ls -lh output_dir/reports/commands.log*`
- Adjust rotation settings if needed:
  ```python
  set_cmd_log_rotation_config(max_size_mb=50.0, max_files=3)
  ```
- To disable rotation (not recommended for large datasets):
  ```python
  set_cmd_log_rotation_config(max_size_mb=float('inf'))
  ```

### Viewing compressed log files?

```bash
# View compressed log file
zcat output_dir/reports/commands.log.1.gz | less

# Or decompress first
gunzip output_dir/reports/commands.log.1.gz
cat output_dir/reports/commands.log.1
```

---

## Summary

The logging system provides:

✅ **Python logging** - Application-level messages (INFO, DEBUG, etc.)  
✅ **Command logging** - All shell commands in one file (`commands.log`)  
✅ **Nextflow logging** - Process execution logs and reports  

All three work together to give you complete visibility into:
- What the workflow is doing (Python logs)
- What commands are being run (command log)
- How Nextflow is executing (Nextflow logs)

The command log file (`output_dir/reports/commands.log`) is the **single source of truth** for all commands executed during processing.

