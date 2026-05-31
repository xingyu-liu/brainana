#!/usr/bin/env bash
# Build a minimal brainana environment for brainana_lite.ipynb.
# Clones brainana from GitHub at a pinned tag, installs Python deps, and wires ANTs into PATH.
#
# Usage:
#   ./setup_brainana_lite.sh [version] [install_dir]
#     version     Git tag (default: v1.0.0)
#     install_dir Install root (default: ./brainana_lite_env)

set -euo pipefail

BRAINANA_VERSION="${1:-v1.0.0}"
INSTALL_DIR="${2:-$(pwd)/brainana_lite_env}"
BRAINANA_REPO="https://github.com/xingyu-liu/brainana.git"

echo "Brainana lite setup"
echo "  version:     ${BRAINANA_VERSION}"
echo "  install dir: ${INSTALL_DIR}"
echo ""

mkdir -p "${INSTALL_DIR}"

# ── 1. Clone brainana ─────────────────────────────────────────────────────────
if [ -d "${INSTALL_DIR}/brainana/.git" ]; then
    echo "Updating existing clone in ${INSTALL_DIR}/brainana ..."
    git -C "${INSTALL_DIR}/brainana" fetch --tags --depth 1 origin
    git -C "${INSTALL_DIR}/brainana" checkout "${BRAINANA_VERSION}"
else
    echo "Cloning ${BRAINANA_REPO} @ ${BRAINANA_VERSION} ..."
    git clone --branch "${BRAINANA_VERSION}" --depth 1 "${BRAINANA_REPO}" "${INSTALL_DIR}/brainana"
fi

# ── 2. Editable install (keeps template_zoo at the correct relative path) ───
echo "Installing brainana (editable) ..."
pip install -e "${INSTALL_DIR}/brainana"

# ── 3. Python dependencies ───────────────────────────────────────────────────
echo "Installing Python dependencies ..."
pip install antspyx nibabel nilearn matplotlib torch torchvision \
    pyyaml yacs h5py pandas scipy scikit-image scikit-learn Pillow \
    pybids packaging psutil requests torchio tqdm seaborn

# ── 4. ANTs binaries in PATH (bundled with antspyx) ───────────────────────────
ENV_FILE="${INSTALL_DIR}/env.sh"
: > "${ENV_FILE}"
echo "# Source this file before running brainana_lite.ipynb locally:" >> "${ENV_FILE}"
echo "#   source ${ENV_FILE}" >> "${ENV_FILE}"

ANTS_BIN="$(python - <<'PY' 2>/dev/null || true
import os
try:
    import ants
    print(os.path.join(ants.get_ants_path(), "bin"))
except Exception:
    pass
PY
)"
if [ -n "${ANTS_BIN}" ] && [ -d "${ANTS_BIN}" ]; then
    echo "export PATH=\"${ANTS_BIN}:\${PATH}\"" >> "${ENV_FILE}"
    echo "ANTs binaries: ${ANTS_BIN}"
else
    echo "WARNING: could not locate antspyx ANTs binaries; ensure ANTs is on PATH."
fi

# ── 5. System tools check (FSL + AFNI must be pre-installed) ──────────────────
MISSING=""
for bin in flirt fslmaths fslstats 3dresample; do
    command -v "${bin}" >/dev/null 2>&1 || MISSING="${MISSING} ${bin}"
done
if [ -n "${MISSING}" ]; then
    echo "WARNING: missing system tools:${MISSING}"
    echo "  FSL:  https://fsl.fmrib.ox.ac.uk/fsl/docs/#/install/index"
    echo "  AFNI: https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/background_install/install_instructs/index.html"
else
    echo "FSL/AFNI binaries found on PATH."
fi

# ── 6. FireANTs (optional GPU SyN) ────────────────────────────────────────────
if python - <<'PY' 2>/dev/null
import torch
raise SystemExit(0 if torch.cuda.is_available() else 1)
PY
then
    if [ ! -d "${INSTALL_DIR}/fireants/.git" ]; then
        echo "Installing FireANTs ..."
        git clone --quiet https://github.com/rohitrango/fireants "${INSTALL_DIR}/fireants"
    fi
    pip install -q "${INSTALL_DIR}/fireants"
    if [ -d "${INSTALL_DIR}/fireants/fused_ops" ]; then
        python "${INSTALL_DIR}/fireants/fused_ops/setup.py" build_ext install 2>/dev/null || true
    fi
    echo "FireANTs installed (CUDA available)."
else
    echo "No CUDA GPU detected — FireANTs skipped (CPU antsRegistration will be used)."
fi

echo ""
echo "Setup complete."
echo "  brainana: ${INSTALL_DIR}/brainana"
echo "  env file: ${ENV_FILE}"
echo ""
echo "Next steps:"
echo "  1. source ${ENV_FILE}"
echo "  2. Open scripts/brainana_lite.ipynb and set BRAINANA_ENV_DIR=${INSTALL_DIR}"
