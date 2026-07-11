# shellcheck shell=bash
#
# Shared CLI-flag helpers for brainana's bash entry layers (entrypoint.sh, run_brainana.sh).
# Lives at the repo root (NOT under lib/, which the standard Python .gitignore excludes).
#
# Provides, from a SINGLE source of truth (known_flags.txt):
#   KNOWN_FLAGS      space-padded string of accepted bare flag names
#   normalize_flag   canonicalize one token's connector (hyphen -> underscore for known flags)
#   validate_flags   collect any unrecognized --flags from a list of args (into UNKNOWN_FLAGS)
#   print_usage      print the argument listing (USAGE.txt, with a fallback)
#
# Fail-open: if known_flags.txt is missing/empty, KNOWN_FLAGS is empty, normalization and
# validation become no-ops (with a warning) rather than breaking otherwise-valid runs.

# Self-locate so paths resolve regardless of the caller's working directory. flags.sh sits
# next to known_flags.txt and USAGE.txt at the repo root (/opt/brainana in the image).
_FLAGS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_FLAGS_FILE="$_FLAGS_DIR/known_flags.txt"
_FLAGS_USAGE_FILE="$_FLAGS_DIR/USAGE.txt"

# Load KNOWN_FLAGS as " name1 name2 ... " (leading/trailing space => whole-word matching).
if [ -f "$_FLAGS_FILE" ]; then
    KNOWN_FLAGS=" $(grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$_FLAGS_FILE" \
                    | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//') "
else
    KNOWN_FLAGS=" "
    echo "WARNING: known_flags.txt not found at $_FLAGS_FILE; flag normalization and" >&2
    echo "         unknown-argument validation are disabled for this run." >&2
fi

# Print the canonical form of a single argument token (hyphen->underscore in the NAME part,
# only for known flags). Non-"--" tokens and unknown flags are echoed unchanged. Values
# (after "=") are never touched.
normalize_flag() {
    local tok="$1"
    case "$tok" in
        --*)
            local name value has_value=0
            if [[ "$tok" == *=* ]]; then
                name="${tok%%=*}"
                value="${tok#*=}"
                has_value=1
            else
                name="$tok"
            fi
            local bare="${name#--}"      # strip leading -- : work-dir
            local under="${bare//-/_}"   # hyphen -> underscore : work_dir
            if [[ "$KNOWN_FLAGS" == *" $under "* ]]; then
                name="--$under"
            fi
            if [ "$has_value" -eq 1 ]; then
                printf '%s=%s' "$name" "$value"
            else
                printf '%s' "$name"
            fi
            ;;
        *)
            printf '%s' "$tok"
            ;;
    esac
}

# Populate the global array UNKNOWN_FLAGS with any unrecognized "--flag" among the args.
# Skips single-dash Nextflow natives (-w, -resume, -profile, ...), the bare "--" marker,
# and non-flag values. Returns 0 if all recognized, 1 otherwise. No-op (returns 0) when the
# allowlist is empty (fail-open).
validate_flags() {
    UNKNOWN_FLAGS=()
    [ -z "${KNOWN_FLAGS// /}" ] && return 0   # allowlist empty => fail-open
    local tok name bare
    for tok in "$@"; do
        case "$tok" in
            --) ;;                              # end-of-options marker
            --*)
                name="${tok%%=*}"               # drop =value
                bare="${name#--}"               # drop leading --
                bare="${bare//-/_}"             # hyphen -> underscore
                if [[ "$KNOWN_FLAGS" != *" $bare "* ]]; then
                    UNKNOWN_FLAGS+=("$name")
                fi
                ;;
            *) ;;                               # values / single-dash options -> skip
        esac
    done
    [ ${#UNKNOWN_FLAGS[@]} -eq 0 ]
}

# Print the full argument listing (USAGE.txt) or a short fallback synopsis.
print_usage() {
    if [ -f "$_FLAGS_USAGE_FILE" ]; then
        cat "$_FLAGS_USAGE_FILE"
    else
        echo "brainana — usage: docker run ... <image> [bids_dir] [output_dir] [OPTIONS]"
        echo "(USAGE.txt not found; see docs/usage_notes.rst)"
    fi
}
