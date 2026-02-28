# brainana Input Arguments Reference

This document lists **all** input arguments for running brainana: Docker entrypoint, local/CLI (run_brainana.sh + Nextflow), BIDS discovery script, and environment variables. It is the canonical reference for "what the user can pass"; for how parameters are resolved inside the pipeline (CLI vs YAML vs defaults), see `PARAMETER_MANAGEMENT.md`.

---

## 1. Invocation layers (summary)

| Layer | When | What user passes |
|-------|------|-------------------|
| **Docker entrypoint** | `docker run ... image [args]` | Positionals + entrypoint-only flags + pipeline args |
| **run_brainana.sh** | Local: `./run_brainana.sh run main.nf [args]` | Named args only (no positionals); forwards to discovery + Nextflow |
| **BIDS discovery** | Invoked by run_brainana.sh before Nextflow | Same as pipeline args (bids_dir, output_dir, config_file, filtering, skip_bids_validation) |
| **Nextflow** | Receives args from entrypoint or run_brainana.sh | `params.*` (bids_dir, output_dir, config_file, work_dir, pipeline options) |

Docker: the entrypoint turns positionals + entrypoint flags into a call to `run_brainana.sh run main.nf --bids_dir <input> --output_dir <output> --config_file <config> [extra]`. So the **pipeline** always sees named `--bids_dir`, `--output_dir`, `--config_file` plus the rest.

---

## 2. Docker (entrypoint.sh)

Used when running the container: `docker run ... xxxlab/brainana:latest [input_dir] [output_dir] [extra...]`

### 2.1 Positional (optional)

| Argument | Default | Description |
|----------|---------|-------------|
| **input_dir** | `/input` | BIDS dataset directory (container path). Must be mounted (e.g. `-v <host_bids>:/input`) if using default. |
| **output_dir** | `/output` | Output directory (container path). Must be mounted (e.g. `-v <host_out>:/output`) if using default. |

If omitted, the entrypoint uses `/input` and `/output`; those paths must exist and be writable (e.g. via `-v` mounts).

### 2.2 Entrypoint-only (parsed by entrypoint, not passed to Nextflow)

| Argument | Default | Description |
|----------|---------|-------------|
| **--config** *path* | `/opt/brainana/src/nhp_mri_prep/config/defaults.yaml` | Path inside container to YAML config. Overrides the default config used when calling run_brainana.sh (maps to `--config_file` for the pipeline). |
| **--config=**path | (same) | Same as `--config path`. |
| **--freesurfer-license** *path* | (none) | Path inside container to FreeSurfer license file. Sets `FS_LICENSE`; required when surface reconstruction is enabled. Typical: mount license with `-v <host>/license.txt:/fs_license.txt` and pass `--freesurfer-license /fs_license.txt`. |
| **--freesurfer-license=**path | (same) | Same as `--freesurfer-license path`. |
| **-w** *path* / **--work-dir** *path* | `<output_dir>_wd` | Nextflow work directory (container path). Used for `NXF_HOME` / `NXF_WORK` so resume and cache persist. |
| **--no-resume** | (resume on) | Do not add `-resume` to the Nextflow command; run from scratch. |
| **bash** / **sh** / **-bash** / **-sh** | — | If the first argument is one of these, the entrypoint runs an interactive shell instead of the pipeline; no other logic runs. |

All other arguments (e.g. `--anat_only`, `--output_space`, `-profile minimal`) are passed through as **extra args** to `run_brainana.sh run main.nf`.

---

## 3. Local / CLI (run_brainana.sh + Nextflow)

Used when running from source: `./run_brainana.sh run main.nf --bids_dir <path> --output_dir <path> [--config_file <path>] [options...]`

There are **no positionals**; everything is named. **Aliases:** `--config` = `--config_file`; `--work-dir` = `--work_dir`.

### 3.1 Required (pipeline + discovery)

| Argument | Default | Description |
|----------|---------|-------------|
| **--bids_dir** | (none) | Path to BIDS dataset root. |
| **--output_dir** | (none) | Path to output directory. |

### 3.1b Optional – config and work dir (aliases supported)

| Argument | Default | Description |
|----------|---------|-------------|
| **--config_file** / **--config** | `src/nhp_mri_prep/config/defaults.yaml` (relative to project) | Path to YAML config. When omitted, built-in defaults are used. **--config** is an alias for **--config_file** (same as Docker entrypoint). |
| **--work_dir** / **--work-dir** | (script dir when local; entrypoint sets in Docker) | Nextflow launch/work directory. **--work-dir** is an alias for **--work_dir**. |

### 3.2 Optional – filtering (passed to discovery + Nextflow)

| Argument | Default | Description | YAML key |
|----------|---------|-------------|----------|
| **--subjects** | (all) | Restrict to subject ID(s). Comma- or space-separated depending on config. | `bids_filtering.subjects` |
| **--sessions** | (all) | Restrict to session ID(s). | `bids_filtering.sessions` |
| **--tasks** | (all) | Restrict to task name(s) (functional). | `bids_filtering.tasks` |
| **--runs** | (all) | Restrict to run number(s). | `bids_filtering.runs` |

### 3.3 Optional – workflow / pipeline (CLI overrides YAML)

| Argument | Default | Description | YAML key |
|----------|---------|-------------|----------|
| **--anat_only** | (from config) | Run only anatomical pipeline (no functional). Boolean-like: true/false, 1/0, yes/no. | `general.anat_only` |
| **--output_space** | (from config) | Template space for outputs, e.g. `NMT2Sym:res-1`, `NMT2Sym:res-05`, `T1w`. | `template.output_space` |
| **--skip_bids_validation** | `false` | Skip BIDS validation in discovery. | (workflow-only) |

### 3.4 Optional – Nextflow / runner

| Argument | Default | Description |
|----------|---------|-------------|
| **--no-docker** | — | Set `NXF_NO_DOCKER=1` so Nextflow does not use Docker (local dev). Filtered out before passing to Nextflow. |
| **-resume** | (added by Docker entrypoint by default) | Nextflow resume. Not required from run_brainana.sh; entrypoint adds it unless `--no-resume` is passed. |
| **-profile** *name* | (default) | Nextflow profile: `minimal` (4 CPUs, 16 GB), `recommended` (8 CPUs, 32 GB), etc. See `nextflow.config` profiles. |

---

## 4. BIDS discovery script (discover_bids_for_nextflow.py)

Invoked by run_brainana.sh **before** Nextflow. It accepts the same paths and filtering as the pipeline; it does **not** accept `--anat_only`, `--output_space`, or Nextflow-only options.

| Argument | Required | Description |
|----------|----------|-------------|
| **--bids_dir** | Yes | Path to BIDS dataset. |
| **--output_dir** | Yes | Output directory (writes job JSONs under `nextflow_reports/`). |
| **--config_file** | No (default: built-in defaults.yaml) | Path to YAML config (used for discovery logic). run_brainana.sh always passes a path (user’s or default). |
| **--skip_bids_validation** | No | Skip BIDS validator. |
| **--subjects** | No | Comma-separated subject IDs. |
| **--sessions** | No | Comma-separated session IDs. |
| **--tasks** | No | Comma-separated task names. |
| **--runs** | No | Comma-separated run numbers. |

---

## 5. Nextflow params (main.nf / nextflow.config)

These are the `params.*` used by the workflow. They are set from the command line (when using run_brainana.sh or Docker extra args) or from defaults in `nextflow.config`.

### 5.1 Input/output and workflow (not in YAML)

| Param | Default | Description |
|-------|---------|-------------|
| **bids_dir** | `null` | Set by `--bids_dir`. |
| **output_dir** | `null` | Set by `--output_dir`. |
| **config_file** | `null` (then resolved to defaults.yaml) | Set by `--config_file` (or Docker `--config` → entrypoint passes as `--config_file`). |
| **work_dir** | `NXF_WORK` env or `~/.nextflow/work` | Set by `--work_dir` (local) or entrypoint’s `-w` (Docker). |
| **skip_bids_validation** | `false` | Set by `--skip_bids_validation`. |

### 5.2 Pipeline options (CLI maps to YAML)

| Param | Default | Description | YAML key |
|-------|---------|-------------|----------|
| **output_space** | (from YAML) | Template space. | `template.output_space` |
| **subjects** | (from YAML) | Subject filter. | `bids_filtering.subjects` |
| **sessions** | (from YAML) | Session filter. | `bids_filtering.sessions` |
| **tasks** | (from YAML) | Task filter. | `bids_filtering.tasks` |
| **runs** | (from YAML) | Run filter. | `bids_filtering.runs` |
| **anat_only** | (from YAML) | Anatomical-only run. | `general.anat_only` |

### 5.3 GPU / executor (workflow-specific)

| Param | Default | Description |
|-------|---------|-------------|
| **gpu_enabled** | `false` | Whether to use GPU queue. |
| **gpu_queue** | `'gpu'` | Queue name for GPU processes. |
| **gpu_count** | (auto from nvidia-smi) | Set at config parse from host. |
| **max_jobs_per_gpu** | (auto from VRAM) | Set at config parse. |

---

## 6. Environment variables

Relevant for both Docker and local runs.

| Variable | Typical use | Description |
|----------|-------------|-------------|
| **NXF_WORK** | Docker / local | Nextflow work directory (process scratch). Entrypoint sets it when using `-w`/`--work-dir`. |
| **NXF_HOME** | Docker / local | Nextflow home (cache, history). Entrypoint sets to same as work dir when `-w` is used. |
| **NXF_LAUNCH_DIR** | Set by entrypoint or run_brainana.sh | Directory from which Nextflow is launched (where `.nextflow/` is created). |
| **NXF_MAX_CPUS** | Docker: `-e NXF_MAX_CPUS=8` | Max CPUs for executor (default in container: 8). |
| **NXF_MAX_MEMORY** | Docker: `-e NXF_MAX_MEMORY=20g` | Max memory for executor (default in container: 20 GB). |
| **NXF_NO_DOCKER** | Local: `--no-docker` sets it | Disable Docker for Nextflow (run processes on host). |
| **NXF_ANSI_LOG** | Optional | Set to `false` to disable colored log (e.g. when piping). |
| **FS_LICENSE** | Docker / local | FreeSurfer license path. Set by entrypoint when `--freesurfer-license` is passed; image may set default `/fs_license.txt`. |

---

## 7. Master table (all user-facing arguments)

| Argument / option | Where | Default | Description |
|-------------------|--------|---------|-------------|
| *input_dir* (positional) | Docker only | `/input` | BIDS directory (container path). |
| *output_dir* (positional) | Docker only | `/output` | Output directory (container path). |
| **--config** | Docker entrypoint | built-in defaults.yaml | Config file path in container. |
| **--freesurfer-license** | Docker entrypoint | (none) | FreeSurfer license path in container. |
| **-w** / **--work-dir** | Docker entrypoint | `<output_dir>_wd` | Nextflow work dir (container). |
| **--no-resume** | Docker entrypoint | (resume on) | Do not add `-resume`. |
| **bash** / **sh** | Docker entrypoint | — | Run shell instead of pipeline. |
| **--bids_dir** | CLI + discovery + Nextflow | (required) | BIDS root path. |
| **--output_dir** | CLI + discovery + Nextflow | (required) | Output path. |
| **--config_file** / **--config** | CLI + discovery + Nextflow | (built-in defaults) | Config YAML path; optional. |
| **--subjects** | CLI + discovery + Nextflow | (all) | Subject filter. |
| **--sessions** | CLI + discovery + Nextflow | (all) | Session filter. |
| **--tasks** | CLI + discovery + Nextflow | (all) | Task filter. |
| **--runs** | CLI + discovery + Nextflow | (all) | Run filter. |
| **--anat_only** | CLI + Nextflow | (from config) | Anatomical-only. |
| **--output_space** | CLI + Nextflow | (from config) | Template space. |
| **--skip_bids_validation** | CLI + discovery + Nextflow | `false` | Skip BIDS validation. |
| **--work_dir** / **--work-dir** | run_brainana.sh (local); Docker uses -w/--work-dir | (script dir / \<output_dir\>_wd) | Nextflow launch dir. |
| **--no-docker** | run_brainana.sh | — | Set NXF_NO_DOCKER=1. |
| **-profile** | Nextflow | (default) | minimal \| recommended \| … |
| **-resume** | Nextflow | (Docker adds by default) | Resume previous run. |

---

## 8. Where arguments are defined in code

| Layer | File(s) |
|-------|---------|
| Docker entrypoint | `entrypoint.sh` (positionals, --config, --freesurfer-license, -w, --no-resume; then exec run_brainana.sh with --bids_dir, --output_dir, --config_file + extra) |
| run_brainana.sh | `run_brainana.sh` (extract_param for bids_dir, output_dir, config_file, subjects, sessions, tasks, runs; --work_dir → NXF_LAUNCH_DIR; --no-docker → NXF_NO_DOCKER; forwards rest to Nextflow) |
| BIDS discovery | `src/nhp_mri_prep/nextflow_scripts/discover_bids_for_nextflow.py` (argparse: bids_dir, output_dir, config_file, skip_bids_validation, subjects, sessions, tasks, runs) |
| Nextflow params | `nextflow.config` (`params { ... }`), `workflows/param_resolver.groovy` (CLI ↔ YAML mapping) |

User-facing docs that mirror this reference: `docs/usage_local.rst` (includes command-line reference section).
