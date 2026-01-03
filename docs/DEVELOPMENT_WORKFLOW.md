# Development Workflow Guide: Docker + Nextflow

## Understanding the Relationship

### How Docker and Nextflow Work Together

1. **Nextflow (Orchestrator)**: Runs on your host machine (or in a container)
   - Manages workflow execution
   - Handles parallelization, scheduling, and resumability
   - Creates and manages process execution

2. **Docker (Process Execution)**: Each Nextflow process runs inside a Docker container
   - Every process in `modules/*.nf` executes inside `banana:latest` container
   - Container provides isolated environment with all dependencies (FSL, ANTs, AFNI, FreeSurfer, Python packages)
   - Ensures reproducibility across different systems

### Current Configuration

From `nextflow.config`:
```nextflow
docker {
    enabled = true
    runOptions = '--user $(id -u):$(id -g)'
}

process {
    container = 'banana:latest'  // Every process uses this image
}
```

**Key Point**: When Docker is enabled, Nextflow executes each process command inside a fresh container instance. Your code changes won't be visible unless:
- The Docker image is rebuilt, OR
- You use volume mounts (development mode)

---

## Recommended Development Workflow

### Phase 1: Fast Iteration (Test Without Docker)

**Goal**: Quickly test Nextflow workflow logic and catch syntax/logic errors

**Steps**:

1. **Disable Docker temporarily** in `nextflow.config`:
   ```nextflow
   docker {
       enabled = false  // Change to false
   }
   ```

2. **Ensure local environment has dependencies**:
   ```bash
   # Install Python package in editable mode
   pip install -e .
   
   # Set up neuroimaging tools (if available locally)
   export FSLDIR=/path/to/fsl
   export ANTSPATH=/path/to/ants/bin
   export AFNI_HOME=/path/to/afni
   export FREESURFER_HOME=/path/to/freesurfer
   export PATH=$FSLDIR/bin:$AFNI_HOME:$ANTSPATH:$FREESURFER_HOME/bin:$PATH
   ```

3. **Test with minimal dataset**:
   ```bash
   ./run_nextflow.sh run main.nf \
       --bids_dir /path/to/small_test_dataset \
       --output_dir /tmp/test_output \
       --output_space "NMT2Sym:res-1" \
       --subjects "01"  # Test with one subject
   ```

4. **Iterate quickly**:
   - Fix Nextflow syntax errors
   - Fix Python import errors
   - Fix workflow logic issues
   - No Docker rebuild needed!

**Pros**:
- ✅ Fast iteration (no Docker rebuild)
- ✅ Easy debugging (direct access to logs)
- ✅ Can use debugger/print statements easily

**Cons**:
- ❌ Requires all dependencies installed locally
- ❌ Environment may differ from production
- ❌ Some tools (FreeSurfer) may not be available

---

### Phase 2: Docker Validation (Test With Docker)

**Goal**: Validate that everything works in the production-like Docker environment

**Steps**:

1. **Re-enable Docker** in `nextflow.config`:
   ```nextflow
   docker {
       enabled = true
   }
   ```

2. **Build Docker image**:
   ```bash
   docker build \
       --build-arg USER_ID=$(id -u) \
       --build-arg GROUP_ID=$(id -g) \
       -t banana:latest .
   ```

3. **Test with Docker**:
   ```bash
   ./run_nextflow.sh run main.nf \
       --bids_dir /path/to/test_dataset \
       --output_dir /tmp/test_output \
       --output_space "NMT2Sym:res-1"
   ```

4. **If code changes are needed**:
   - Option A: Rebuild Docker image (slower but clean)
   - Option B: Use development Docker setup (see below)

---

### Phase 3: Development Docker Setup (Optional, for Frequent Changes)

**Goal**: Test Docker execution while still allowing code changes without rebuilds

**Approach**: Run Nextflow itself inside Docker, with volume mounts for code

**Steps**:

1. **Create a development Docker run script** (`dev_docker_run.sh`):
   ```bash
   #!/bin/bash
   docker run -it --rm \
       --gpus all \
       --network host \
       --user $(id -u):$(id -g) \
       --volume="$(pwd):/opt/banana" \
       --volume="$HOME/.cache/uv:/home/neuro/.cache/uv" \
       --volume="/path/to/test_data:/data" \
       --volume="/path/to/output:/output" \
       --volume="/path/to/license.txt:/opt/freesurfer/license.txt" \
       --workdir="/opt/banana" \
       banana:latest \
       ./run_nextflow.sh run main.nf \
           --bids_dir /data \
           --output_dir /output \
           --output_space "NMT2Sym:res-1"
   ```

2. **Modify Dockerfile to support editable install** (already done):
   - Your Dockerfile already installs with `-e` (editable mode)
   - With volume mount `$(pwd):/opt/banana`, code changes are reflected immediately

3. **However, there's a catch**: 
   - Nextflow processes still run in containers
   - Each process uses `container = 'banana:latest'` from config
   - The container image needs your code, OR you need to modify the process to use volumes

**Better approach for development**: Use the `--no-docker` flag:

```bash
./run_nextflow.sh run main.nf --no-docker --bids_dir ... --output_dir ...
```

The `--no-docker` flag automatically sets `NXF_NO_DOCKER=1` environment variable, which is read by `nextflow.config` to disable Docker. This is cleaner than manually setting environment variables.

---

## Recommended Workflow Summary

### For Initial Development (After Refactoring)

1. **Start without Docker** (Phase 1):
   ```bash
   # Use --no-docker flag to test locally
   ./run_nextflow.sh run main.nf --no-docker --bids_dir ... --output_dir ...
   ```

2. **Fix issues iteratively**:
   - Nextflow syntax errors → fix immediately
   - Python import errors → fix immediately
   - Logic errors → fix immediately
   - No Docker rebuild needed!

3. **Once workflow runs locally**, **switch to Docker** (Phase 2):
   ```bash
   # Edit nextflow.config: docker.enabled = true
   # Build Docker image
   docker build -t banana:latest .
   # Test with Docker
   ./run_nextflow.sh run main.nf ...
   ```

4. **Fix Docker-specific issues**:
   - Path issues
   - Permission issues
   - Missing dependencies in image

### For Ongoing Development

- **Small Python changes**: Test locally first (no Docker), then rebuild Docker
- **Nextflow workflow changes**: Test locally first, then validate with Docker
- **Dockerfile changes**: Must rebuild and test

---

## Quick Reference Commands

### Test Without Docker
```bash
# Use --no-docker flag
./run_nextflow.sh run main.nf \
    --no-docker \
    --bids_dir /path/to/bids \
    --output_dir /tmp/output \
    --config_file /path/to/config.yaml
```

### Test With Docker
```bash
# 1. Enable Docker in nextflow.config
# 2. Build image
docker build -t banana:latest .
# 3. Run
./run_nextflow.sh run main.nf \
    --bids_dir /path/to/bids \
    --output_dir /tmp/output \
    --output_space "NMT2Sym:res-1"
```

### Debug Failed Process
```bash
# Check Nextflow logs
cat ~/.nextflow/logs/nextflow.log

# Check process work directory
ls -la ~/.nextflow/work/*/command.log

# Re-run with resume
./run_nextflow.sh run main.nf -resume ...
```

---

## Common Issues and Solutions

### Issue: "Docker image banana:latest not found"
**Solution**: Build the image first
```bash
docker build -t banana:latest .
```

### Issue: Code changes not reflected in Docker
**Solution**: Rebuild Docker image after code changes
```bash
docker build -t banana:latest .
```

### Issue: Permission errors in Docker
**Solution**: Ensure `--user $(id -u):$(id -g)` is set (already in config)

### Issue: GPU not available in Docker
**Solution**: 
```bash
# Test GPU access
docker run --rm --gpus all banana:latest nvidia-smi

# If that works, Nextflow should work too
```

---

## Best Practices

1. **Always test locally first** (faster iteration)
2. **Validate with Docker before committing** (ensures production readiness)
3. **Use small test datasets** during development
4. **Check Nextflow logs** for detailed error messages
5. **Use `-resume` flag** to continue from failures
6. **Tag Docker images** with versions for reproducibility:
   ```bash
   docker build -t banana:v0.1.0 -t banana:latest .
   ```

