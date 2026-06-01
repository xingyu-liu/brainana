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
# Pin FireANTs for reproducibility. v1.5.0 provides the API brainana imports
# (fireants.io.{Image,BatchedImages,FakeBatchedImages}, AffineRegistration,
# GreedyRegistration, utils.globals.MIN_IMG_SIZE).
FIREANTS_VERSION="${FIREANTS_VERSION:-v1.5.0}"
FIREANTS_REPO="https://github.com/rohitrango/FireANTs.git"

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
# SimpleITK powers the FSL-free rigid conform (rigid_method="sitk"), so no FLIRT needed.
echo "Installing Python dependencies ..."
pip install antspyx SimpleITK nibabel nilearn matplotlib torch torchvision \
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

# ── 5. System tools check (none needed beyond ANTs) ──────────────────────────
# The lite T1w pipeline (rigid_method="sitk") needs NO FSL and NO AFNI: rigid conform +
# template resampling use SimpleITK, masking uses nibabel, registration/bias use ANTs
# (bundled with antspyx, wired into PATH above). So the only required binaries are ANTs.
MISSING=""
for bin in antsRegistration N4BiasFieldCorrection; do
    command -v "${bin}" >/dev/null 2>&1 || MISSING="${MISSING} ${bin}"
done
if [ -n "${MISSING}" ]; then
    echo "WARNING: missing ANTs binaries:${MISSING} (expected from antspyx; check step 4)."
else
    echo "ANTs binaries found on PATH (no FSL, no AFNI needed)."
fi

# ── 6. FireANTs (optional GPU SyN) ────────────────────────────────────────────
if python - <<'PY' 2>/dev/null
import torch
raise SystemExit(0 if torch.cuda.is_available() else 1)
PY
then
    if [ -d "${INSTALL_DIR}/fireants/.git" ]; then
        echo "Updating FireANTs to ${FIREANTS_VERSION} ..."
        git -C "${INSTALL_DIR}/fireants" fetch --tags --depth 1 origin
        git -C "${INSTALL_DIR}/fireants" checkout "${FIREANTS_VERSION}"
    else
        echo "Installing FireANTs ${FIREANTS_VERSION} ..."
        git clone --quiet --branch "${FIREANTS_VERSION}" --depth 1 "${FIREANTS_REPO}" "${INSTALL_DIR}/fireants"
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
WORKING_DIR_HINT="$(dirname "${INSTALL_DIR}")"
echo "Next steps:"
echo "  The notebook expects this env under <WORKING_DIR>/brainana_lite_env."
echo "  If you installed there (recommended), set WORKING_DIR=${WORKING_DIR_HINT}"
echo "  in scripts/brainana_lite.ipynb, put your T1w file(s) in"
echo "  ${WORKING_DIR_HINT}/input_T1w/, then Run All. (env.sh is auto-loaded by the notebook.)"
