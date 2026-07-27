"""Ingest-normalization findings for QC reports.

Anything ingest repaired or could not repair is recorded in the derivative JSON
sidecars by ``ANAT_SYNTHESIS``. A log line scrolls past and a sidecar is opened by
nobody, so this module lifts those records into the per-subject HTML report.

Follows the same collect -> render split as :mod:`.run_status`, and renders nothing
at all when there is nothing to report, so a clean dataset produces an unchanged
report.
"""

import html
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Sidecar keys written by ANAT_SYNTHESIS for repairs that were applied, in the order
# they should appear. The note is what the reader actually needs to know about the
# consequence -- for orientation, that means the left/right caveat, which is the one
# finding here that can silently invalidate a result.
_REPAIRS = (
    (
        "Input4DCollapsed",
        "4D input collapsed to 3D",
        "The input carried a frame axis. A trailing singleton was dropped losslessly; "
        "a genuine multi-volume anatomical was averaged over its last axis.",
    ),
    (
        "OrientationRecovered",
        "Orientation recovered",
        "The input stored no orientation (qform_code = 0 and sform_code = 0), so a "
        "convention was assumed: LAS with a centred origin, what nibabel and FSL "
        "already fall back to. This is a convention, not ground truth — if the "
        "acquisition ran the other way the result is a left/right mirror that no "
        "registration can undo and that is invisible on inspection. Confirm handedness "
        "against an external record before trusting hemisphere-wise results.",
    ),
    (
        "QformSformReconciled",
        "qform/sform disagreement resolved",
        "The header stored its geometry twice with two different answers. Both were set "
        "to the sform, which nibabel, FSL and the rest of this pipeline already read; "
        "left alone, FastSurfer would have resolved toward the qform and segmented "
        "against a different grid than registration used.",
    ),
)

_UNREPAIRED_KEY = "InputHeaderWarnings"


def _sidecar_sources(sidecar: Dict[str, Any], fallback: str) -> List[str]:
    """Name the input files a finding applies to, preferring BIDS ``Sources``."""
    sources = sidecar.get("Sources")
    if isinstance(sources, list) and sources:
        return [Path(str(s)).name for s in sources]
    return [fallback]


def collect_ingest_findings(
    subject_dir: Union[str, Path],
    logger: Optional[logging.Logger] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Gather ingest-normalization findings from a subject's derivative sidecars.

    Args:
        subject_dir: Published subject directory (``<output_dir>/sub-XXX``).
        logger: Logger instance (optional).

    Returns:
        ``{"repaired": [...], "unrepaired": [...]}``. Both lists are empty when the
        subject's inputs were well-formed. Findings are grouped so one defect
        affecting several runs reads as one entry naming each file.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    subject_dir = Path(subject_dir)
    repaired: Dict[str, Dict[str, Any]] = {}
    unrepaired: Dict[str, Dict[str, Any]] = {}

    if not subject_dir.is_dir():
        return {"repaired": [], "unrepaired": []}

    for sidecar_path in sorted(subject_dir.glob("**/*.json")):
        try:
            with open(sidecar_path, encoding="utf-8") as f:
                sidecar = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            # A malformed sidecar must not take the whole report down with it.
            logger.debug("QC: skipping unreadable sidecar %s (%s)", sidecar_path, e)
            continue
        if not isinstance(sidecar, dict):
            continue

        sources = _sidecar_sources(sidecar, sidecar_path.name)

        for key, label, note in _REPAIRS:
            actions = sidecar.get(key)
            if not actions:
                continue
            entry = repaired.setdefault(
                key, {"key": key, "label": label, "note": note, "files": []}
            )
            for name in sources:
                if name not in entry["files"]:
                    entry["files"].append(name)

        for message in sidecar.get(_UNREPAIRED_KEY) or []:
            entry = unrepaired.setdefault(
                str(message), {"message": str(message), "files": []}
            )
            for name in sources:
                if name not in entry["files"]:
                    entry["files"].append(name)

    # Preserve the declared repair order rather than sidecar discovery order.
    ordered_repairs = [repaired[key] for key, _, _ in _REPAIRS if key in repaired]
    return {
        "repaired": ordered_repairs,
        "unrepaired": list(unrepaired.values()),
    }


def has_findings(findings: Optional[Dict[str, List[Dict[str, Any]]]]) -> bool:
    """True when there is anything worth rendering."""
    if not findings:
        return False
    return bool(findings.get("repaired") or findings.get("unrepaired"))


def _render_files(files: List[str]) -> str:
    if not files:
        return ""
    listed = ", ".join(f"<code>{html.escape(n)}</code>" for n in files)
    return f'<div class="ffiles">{listed}</div>'


def render_data_findings_content(
    findings: Optional[Dict[str, List[Dict[str, Any]]]],
) -> str:
    """Render the inner HTML block for the data-findings section.

    Returns ``""`` when there is nothing to report, so the section disappears
    entirely for a well-formed dataset rather than rendering an empty box.
    """
    if not has_findings(findings):
        return ""

    repaired = findings.get("repaired") or []
    unrepaired = findings.get("unrepaired") or []

    # Unrepaired findings set the tone: those need a decision from the user, whereas
    # a repair is informational (with the notable exception of the L/R caveat, which
    # the note spells out).
    css_class = "warn" if unrepaired else "ok"
    badge = "Action needed" if unrepaired else "Repaired"
    if unrepaired and repaired:
        headline = "Input headers were repaired, and some issues need your attention"
    elif unrepaired:
        headline = "Input headers have issues that need your attention"
    else:
        headline = "Input headers were repaired before processing"

    blocks = []

    if repaired:
        items = "".join(
            f"<li><b>{html.escape(entry['label'])}</b>"
            f"<div class=\"fnote\">{html.escape(entry['note'])}</div>"
            f"{_render_files(entry['files'])}</li>"
            for entry in repaired
        )
        blocks.append(
            '<p class="fgroup">Repaired automatically</p>'
            f'<ul class="findings">{items}</ul>'
        )

    if unrepaired:
        items = "".join(
            f"<li><b>{html.escape(entry['message'])}</b>"
            f"{_render_files(entry['files'])}</li>"
            for entry in unrepaired
        )
        blocks.append(
            '<p class="fgroup">Not repaired — no safe automatic fix</p>'
            f'<ul class="findings">{items}</ul>'
        )

    return f"""<div class="status {css_class}">
<p class="headline"><span class="badge">{badge}</span>{headline}</p>
{"".join(blocks)}
</div>"""
