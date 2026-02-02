# brainana Docker Usage Guide

This Docker image provides a complete environment for `brainana`, including neuroimaging toolkits (FSL, ANTs, AFNI, FreeSurfer) and a pre-configured Python environment. It supports GUI interaction, GPU acceleration, and automatic permission management.

## 1. Build the Image

Build the image from the project root. We recommend passing your local `USER_ID` and `GROUP_ID` as build arguments to ensure that files created by the container are owned by you on the host machine.

```bash
docker build \
    --build-arg USER_ID=$(id -u) \
    --build-arg GROUP_ID=$(id -g) \
    -t brainana:latest .
```

The build process uses `uv` for extremely fast installation of Python dependencies.

---

## 2. Prerequisites (FreeSurfer License)

To use FreeSurfer-based features (e.g., `fastsurfer_surfrecon`), a valid license file is required.
Ensure you have a `license.txt` file on your host machine. 

If you do not have a FreeSurfer license yet, you can request one for free at the [FreeSurfer Website](https://surfer.nmr.mgh.harvard.edu/fswiki/License).

---

## 3. Running the Container

### A. Interactive Development Mode (Recommended, with GUI)
Use this mode if you need to run the `config_generator` or use GUI tools like `fslview`, `afni`, or `freeview`.

**1. Enable X11 access on your host:**
```bash
xhost +local:root
```

**2. Start the container:**
```bash
docker run -it --rm \
    --gpus all \
    --network host \
    --name macaca_dev \
    --user $(id -u):$(id -g) \
    --env="DISPLAY=$DISPLAY" \
    --env="QT_X11_NO_MITSHM=1" \
    --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
    --volume="$(pwd):/opt/brainana" \
    --volume="$HOME/.cache/uv:/home/neuro/.cache/uv" \
    --volume="/home/yinzi/dataset/testing_dataset:/data" \
    --volume="/nvmessd/yinzi/brainana/license.txt:/opt/freesurfer/license.txt" \
    --workdir="/opt/brainana" \
    brainana:latest
```

**Parameter Breakdown:**
- `--gpus all`: Enables GPU acceleration (requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)).
- `--network host`: Uses the host's network stack. This is required for the GUI config generator to be easily accessible via localhost and for optimal network performance.
- `--user $(id -u):$(id -g)`: Ensures files created inside the container are owned by your host user.
- `--volume="$(pwd):/opt/brainana"`: Mounts the current source code. Since it's installed in `editable` mode (`-e`), any changes you make locally are reflected immediately inside the container.
- `--volume="$HOME/.cache/uv:/home/neuro/.cache/uv"`: Shares the `uv` package cache between the host and container. This prevents `uv` from re-downloading large packages (like PyTorch) when you run `uv add` or `uv sync` inside the container.
- `--env="DISPLAY"` & `--volume="/tmp/.X11-unix"`: Forwards the GUI from the container to your host display.

---

### B. Production/Batch Mode
Run the Nextflow preprocessing pipeline directly without entering an interactive shell:

```bash
docker run --rm \
    --gpus all \
    --network host \
    --user $(id -u):$(id -g) \
    --volume="$HOME/.cache/uv:/home/neuro/.cache/uv" \
    --volume="/home/yinzi/dataset/testing_dataset:/data" \
    --volume="/path/to/output_dir:/output" \
    --volume="/nvmessd/yinzi/brainana/license.txt:/opt/freesurfer/license.txt" \
    --workdir="/opt/brainana" \
    brainana:latest \
    ./run_nextflow.sh run main.nf --bids_dir /data --output_dir /output --output_space "NMT2Sym:res-1" --config_file /data/my_config.yaml
```

---

## 4. Common Operations inside the Container

Upon entry, a welcome message will display the versions of installed tools.

*   **Launch Config Generator (GUI)**:
    ```bash
    python3 -m nhp_mri_prep.config.config_generator_cli --dataset-dir /data
    ```
    *Then access the URL (usually http://localhost:8050) from your host browser.*

*   **Run Preprocessing Pipeline (Nextflow)**:
    ```bash
    ./run_nextflow.sh run main.nf --bids_dir /data --output_dir /output --output_space "NMT2Sym:res-1"
    ```

*   **Access Neuroimaging Tools**:
    Commands like `fsl`, `afni`, `antsRegistration`, and `freeview` are available directly in the shell.

---

## 5. Troubleshooting (FAQ)

**Q: I get "cannot connect to X server" when running GUI tools.**
A: Run `xhost +local:root` on your host machine. If you are using SSH, ensure X11 forwarding is enabled (`ssh -X` or `-Y`).

**Q: How do I enable GPU acceleration?**
A: If you have the NVIDIA Container Toolkit installed, add `--gpus all` to your `docker run` command.

**Q: Do I need to rebuild the image after editing code?**
A: No. Because we use `--volume="$(pwd):/opt/brainana"` and the package is installed in `editable` mode, your local changes are applied instantly.

