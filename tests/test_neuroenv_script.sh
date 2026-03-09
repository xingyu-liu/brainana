#!/usr/bin/env bash
# Tests the neuroenv.sh welcome script generation logic from the Dockerfile,
# without needing to rebuild the image. Generates the script locally using the
# same printf template, checks for syntax errors, and validates that command
# substitutions run rather than printing literally.

set -euo pipefail

PASS=0
FAIL=0
TMPDIR_TEST=$(mktemp -d)
SCRIPT="$TMPDIR_TEST/neuroenv.sh"
OUTPUT="$TMPDIR_TEST/output.txt"

cleanup() { rm -rf "$TMPDIR_TEST"; }
trap cleanup EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "========================================"
echo "  neuroenv.sh generation & syntax tests"
echo "========================================"

# ---------------------------------------------------------------------------
# 1. Generate the script with the same printf used in the Dockerfile.
#    Use dummy paths so the export lines are populated.
# ---------------------------------------------------------------------------
FSLDIR=/usr/local/fsl
AFNI_HOME=/usr/local/afni
AFNIPATH=/usr/local/afni
ANTSPATH=/opt/ants/bin/
FREESURFER_HOME=/usr/local/freesurfer
FS_LICENSE=/fs_license.txt

printf '#!/bin/bash\n\
# Neuroimaging tools environment\n\
export FSLDIR=%s\n\
export AFNI_HOME=%s\n\
export AFNIPATH=%s\n\
export ANTSPATH=%s\n\
export FREESURFER_HOME=%s\n\
export FS_LICENSE=%s\n\
export FSLOUTPUTTYPE=NIFTI_GZ\n\
export PATH=$FSLDIR/bin:$AFNI_HOME:$ANTSPATH:$FREESURFER_HOME/bin:${JAVA_HOME}/bin:/usr/local/bin:$PATH\n\
\n\
# License check\n\
if [ ! -f "$FS_LICENSE" ]; then\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "WARNING: FreeSurfer license not found at $FS_LICENSE"\n\
    echo "To run FreeSurfer tools, please mount your license file:"\n\
    echo "  docker run ... -v /path/to/license.txt:/fs_license.txt ..."\n\
    echo "--------------------------------------------------------------------------------"\n\
fi\n\
\n\
# Welcome Message\n\
if [ "$PS1" ]; then\n\
    echo "================================================================================"\n\
    echo "Welcome to brainana Interactive Environment"\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "Installed Tools:"\n\
    echo "  - FSL:        $(flirt -version 2>&1 | head -n 1 || echo "Installed")"\n\
    echo "  - ANTs:       $(antsRegistration --version 2>&1 | grep -i version | head -n 1 || echo "Installed")"\n\
    echo "  - FireANTs:   $(python3 -c "import fireants; print(fireants.__version__)" 2>/dev/null || echo "Installed")"\n\
    echo "  - AFNI:       $(afni -version | head -n 1 || echo "Installed")"\n\
    echo "  - FreeSurfer: $(cat $FREESURFER_HOME/build-stamp.txt 2>/dev/null || echo "Installed")"\n\
    echo "  - Python:     $(python3 --version)"\n\
    echo "  - Java:       $(java -version 2>&1 | head -n 1)"\n\
    echo "  - uv:         $(uv --version)"\n\
    echo "  - Nextflow:   $(nextflow -version 2>/dev/null | head -n 1 || echo "Installed")"\n\
    echo "  - Workbench:  $(wb_command -version 2>/dev/null | head -n 1 || echo "Installed")"\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "Usage Examples:"\n\
    echo "  ./run_brainana.sh run main.nf --bids_dir /data --output_dir /output"\n\
    echo "  (Config generator: open docs/_static/config_generator.html in a browser)"\n\
    echo "================================================================================"\n\
fi\n' \
    "$FSLDIR" "$AFNI_HOME" "$AFNIPATH" "$ANTSPATH" "$FREESURFER_HOME" "$FS_LICENSE" \
    > "$SCRIPT"
chmod +x "$SCRIPT"

echo
echo "--- Test 1: Script generation ---"
if [[ -s "$SCRIPT" ]]; then
    pass "Script file generated ($(wc -l < "$SCRIPT") lines)"
else
    fail "Script file is empty or missing"
fi

# ---------------------------------------------------------------------------
# 2. Syntax check
# ---------------------------------------------------------------------------
echo
echo "--- Test 2: Bash syntax check ---"
if bash -n "$SCRIPT" 2>&1; then
    pass "No syntax errors"
else
    fail "Syntax errors detected"
fi

# ---------------------------------------------------------------------------
# 3. Source the script with PS1 set so the welcome block runs
# ---------------------------------------------------------------------------
echo
echo "--- Test 3: Script executes without errors ---"
if ( export PS1="test\$ "; . "$SCRIPT" ) > "$OUTPUT" 2>&1; then
    pass "Script sourced without errors"
else
    fail "Script sourced with errors (exit $?)"
    echo "    Output:"
    sed 's/^/      /' "$OUTPUT"
fi

# ---------------------------------------------------------------------------
# 4. No literal $(...) in output (command substitutions ran)
# ---------------------------------------------------------------------------
echo
echo "--- Test 4: No un-expanded command substitutions in output ---"
if grep -q '\$(' "$OUTPUT"; then
    fail "Found literal \$(...) in output — command substitutions did not run"
    grep '\$(' "$OUTPUT" | sed 's/^/      /'
else
    pass "All \$(...) were evaluated"
fi

# ---------------------------------------------------------------------------
# 5. No literal backslash-dollar in output
# ---------------------------------------------------------------------------
echo
echo "--- Test 5: No escaped \\\$(...) in output ---"
if grep -q '\\\$' "$OUTPUT"; then
    fail "Found \\\\\\$(...) in output — backslash-escaped substitution printed literally"
    grep '\\\$' "$OUTPUT" | sed 's/^/      /'
else
    pass "No backslash-escaped substitutions in output"
fi

# ---------------------------------------------------------------------------
# 6. Welcome header present
# ---------------------------------------------------------------------------
echo
echo "--- Test 6: Welcome header present ---"
if grep -q "Welcome to brainana" "$OUTPUT"; then
    pass "Welcome header found"
else
    fail "Welcome header missing"
fi

# ---------------------------------------------------------------------------
# 7. All tool lines present
# ---------------------------------------------------------------------------
echo
echo "--- Test 7: All tool lines present ---"
TOOLS=(FSL ANTs FireANTs AFNI FreeSurfer Python Java uv Nextflow Workbench)
for tool in "${TOOLS[@]}"; do
    if grep -qF -- "- $tool:" "$OUTPUT"; then
        pass "$tool line present"
    else
        fail "$tool line missing"
    fi
done

# ---------------------------------------------------------------------------
# 8. No tool line is completely empty (each has a version or "Installed")
# ---------------------------------------------------------------------------
echo
echo "--- Test 8: No tool line has empty value ---"
while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*-[[:space:]]([A-Za-z]+): ]]; then
        tool="${BASH_REMATCH[1]}"
        value="${line#*: }"
        if [[ -z "${value// }" ]]; then
            fail "$tool has no version value"
        else
            pass "$tool has value: $value"
        fi
    fi
done < "$OUTPUT"

# ---------------------------------------------------------------------------
# 9. License warning shown (since /fs_license.txt doesn't exist locally)
# ---------------------------------------------------------------------------
echo
echo "--- Test 9: License warning shown when license file absent ---"
if grep -q "FreeSurfer license not found" "$OUTPUT"; then
    pass "License warning displayed correctly"
else
    fail "License warning missing"
fi

# ---------------------------------------------------------------------------
# 10. No license warning when license file exists
# ---------------------------------------------------------------------------
echo
echo "--- Test 10: No license warning when license file exists ---"
FAKE_LICENSE="$TMPDIR_TEST/license.txt"
touch "$FAKE_LICENSE"
sed "s|export FS_LICENSE=.*|export FS_LICENSE=$FAKE_LICENSE|" "$SCRIPT" > "$TMPDIR_TEST/neuroenv_lic.sh"
( export PS1="test\$ "; . "$TMPDIR_TEST/neuroenv_lic.sh" ) > "$TMPDIR_TEST/output_lic.txt" 2>&1
if grep -q "FreeSurfer license not found" "$TMPDIR_TEST/output_lic.txt"; then
    fail "License warning shown even though license file exists"
else
    pass "No spurious license warning when file exists"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "========================================"
TOTAL=$((PASS + FAIL))
echo "  Results: $PASS/$TOTAL passed"
if [[ $FAIL -gt 0 ]]; then
    echo "  $FAIL test(s) FAILED"
    echo "========================================"
    exit 1
else
    echo "  All tests passed!"
    echo "========================================"
fi
