# brainana Docker Usage Guide

This Docker image provides a complete environment for `brainana`, including neuroimaging toolkits (FSL, ANTs, AFNI, FreeSurfer, Connectome Workbench), Nextflow, and a pre-configured Python environment. It supports a simple production interface, GUI interaction for config generation, and GPU acceleration.

---

## System Requirements

| Tier | RAM | CPUs | Disk | GPU |
|------|-----|------|------|-----|
| **Minimal** | 16 GB | 4 | 20 GB | Optional (skullstrip slower on CPU) |
| **Recommended** | 20 GB | 8 | 50 GB | 1× with ≥6 GB VRAM |
| **Production** | 32 GB | 8+ | 100 GB+ | 1× with ≥10 GB VRAM |

The container defaults to 8 CPUs and 20 GB for Nextflow scheduling (no `-e` flags needed). To hard-cap the container on a shared host, pass `--memory` and `--cpus` and optionally `-e NXF_MAX_CPUS` / `-e NXF_MAX_MEMORY` to match. See [docs/RESOURCE_CALIBRATION.md](docs/RESOURCE_CALIBRATION.md) for details.

---

## 1. Build the Image

Build the image from the project root:

```bash
docker build \
    --build-arg USER_ID=$(id -u) \
    --build-arg GROUP_ID=$(id -g) \
    -t xxxlab/brainana:latest .
```

---

## 2. Prerequisites (FreeSurfer License)

To use FreeSurfer-based features (e.g., surface reconstruction), a valid license file is required.
Ensure you have a `license.txt` file on your host machine.

If you do not have a FreeSurfer license yet, you can request one for free at the [FreeSurfer Website](https://surfer.nmr.mgh.harvard.edu/fswiki/License).

---

## 3. Production Mode (Recommended)

**Default** (Nextflow uses 8 CPUs, 20 GB inside the container):

```bash
docker run -it --rm --gpus all \
    -v <bids_dir>:/input \
    -v <output_dir>:/output \
    -v <path/to/license.txt>:/fs_license.txt \
    xxxlab/brainana:latest
```

**Example:**
```bash
docker run -it --rm --gpus all \
    -v /data/my_bids_dataset:/input \
    -v /data/preprocessed:/output \
    -v /home/user/license.txt:/fs_license.txt \
    xxxlab/brainana:latest
```

**Optional: hard-cap the container** (e.g. on a shared host):
```bash
docker run -it --rm --gpus all \
    --memory 20g --cpus 8 \
    -v <bids_dir>:/input \
    -v <output_dir>:/output \
    -v <path/to/license.txt>:/fs_license.txt \
    xxxlab/brainana:latest
```

**Optional: minimal resources** (anat-only, 1–2 subjects) – pass `-profile minimal` and limit the container:
```bash
docker run -it --rm --gpus all \
    --memory 16g --cpus 4 \
    -e NXF_MAX_CPUS=4 -e NXF_MAX_MEMORY=16g \
    -v <bids_dir>:/input \
    -v <output_dir>:/output \
    -v <path/to/license.txt>:/fs_license.txt \
    xxxlab/brainana:latest /input /output -profile minimal
```

**With optional arguments** (e.g., anat-only mode, custom output space, or resource profile):
```bash
docker run -it --rm --gpus all \
    -v /data/bids:/input \
    -v /data/output:/output \
    -v /path/to/license.txt:/fs_license.txt \
    xxxlab/brainana:latest /input /output --anat_only --output_space "NMT2Sym:res-1"
# Or use a resource profile: ... /input /output -profile recommended
```

---

## 4. Running as Host User (File Permissions)

To ensure output files are owned by your host user, use `--user` and set writable Nextflow directories:

```bash
docker run -it --rm --gpus all \
    --user $(id -u):$(id -g) \
    -e NXF_WORK=/tmp/nextflow-work \
    -e NXF_HOME=/tmp/nextflow-home \
    -v <bids_dir>:/input \
    -v <output_dir>:/output \
    -v <path/to/license.txt>:/fs_license.txt \
    xxxlab/brainana:latest
```

**Why:** When using `--user $(id -u):$(id -g)`, the container runs as your host user. Nextflow's default work directory (`~/.nextflow/work`) may not be writable. Setting `NXF_WORK` and `NXF_HOME` to `/tmp/...` ensures Nextflow can write its cache and work files.

---

## 5. Interactive Development Mode (with GUI)

**1. Enable X11 access on your host:**
```bash
xhost +local:root
```

**2. Start an interactive shell:**
```bash
docker run -it --rm \
    --gpus all \
    --network host \
    --user $(id -u):$(id -g) \
    -e NXF_WORK=/tmp/nextflow-work \
    -e NXF_HOME=/tmp/nextflow-home \
    --env="DISPLAY=$DISPLAY" \
    --env="QT_X11_NO_MITSHM=1" \
    --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
    --volume="$(pwd):/opt/brainana" \
    --volume="$HOME/.cache/uv:/home/neuro/.cache/uv" \
    --volume="/path/to/your/data:/data" \
    --volume="/path/to/license.txt:/fs_license.txt" \
    --workdir="/opt/brainana" \
    xxxlab/brainana:latest bash
```

**Inside the container:**
- **Launch Config Generator (GUI):** `python3 -m nhp_mri_prep.config.config_generator_cli --dataset-dir /data`
- **Run pipeline manually:** `./run_brainana.sh run main.nf --bids_dir /data --output_dir /output --config_file /opt/brainana/src/nhp_mri_prep/config/defaults.yaml`
- **Neuroimaging tools:** `fsl`, `afni`, `antsRegistration`, `freeview`, `wb_view` are available.

---

## 6. Troubleshooting (FAQ)

**Q: I get "cannot connect to X server" when running GUI tools.**
A: Run `xhost +local:root` on your host machine. If using SSH, ensure X11 forwarding is enabled (`ssh -X` or `-Y`).

**Q: How do I enable GPU acceleration?**
A: Add `--gpus all` to your `docker run` command (requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)).

**Q: Do I need to provide a config file?**
A: No. Production mode uses built-in defaults. For custom settings, generate a config via the config generator (GUI), save it, and mount it with `-v /path/to/config.yaml:/config.yaml`, then pass `--config_file /config.yaml` as an extra argument.

**Q: Can I run without a FreeSurfer license?**
A: Anatomical and functional preprocessing will work, but surface reconstruction will fail. The container will warn if the license is missing.

**Q: How do I align Docker limits with Nextflow?**
A: Nextflow defaults to 8 CPUs and 20 GB (set in the container). To cap the container to match, pass `--memory 20g --cpus 8`. To change Nextflow’s scheduling (e.g. for a bigger run), pass `-e NXF_MAX_CPUS=16 -e NXF_MAX_MEMORY=32g` or use `-profile recommended` (32 GB).
