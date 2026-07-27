"""Unit tests for copy_atlas_sidecars (steps/anatomical.py).

Covers copying an atlas's associated sidecars — atlas-{name}.tsv / .md verbatim and
references.bib renamed to atlas-{name}.bib — next to the backprojected label image,
for both an explicit source dir and re-discovery from the bundled template zoo.
"""

from pathlib import Path

import pytest

from nhp_mri_prep.steps.anatomical import copy_atlas_sidecars
from nhp_mri_prep.utils.templates import get_template_manager


def _make_family(dir_path: Path, name: str, with_bib=True, with_md=True, with_tsv=True):
    """Create a fake template-zoo atlas family dir for `name`."""
    dir_path.mkdir(parents=True, exist_ok=True)
    # Label image (must NOT be copied) — note the '_space-' right after the name.
    (dir_path / f"atlas-{name}_space-NMT2Sym_res-05.nii.gz").write_bytes(b"img")
    if with_tsv:
        (dir_path / f"atlas-{name}.tsv").write_text("index\tname\n1\tregionA\n")
    if with_md:
        (dir_path / f"atlas-{name}.md").write_text("# docs\n")
    if with_bib:
        (dir_path / "references.bib").write_text("@article{x, title={y}}\n")


# --------------------------------------------------------------------------- #
# explicit source_dir
# --------------------------------------------------------------------------- #
def test_copies_sidecars_and_renames_bib(tmp_path):
    src = tmp_path / "FOO"
    _make_family(src, "FOO")
    dest = tmp_path / "out"

    copied = copy_atlas_sidecars("FOO", dest, source_dir=src)

    assert (dest / "atlas-FOO.tsv").read_text().startswith("index")
    assert (dest / "atlas-FOO.md").exists()
    # references.bib renamed to carry the atlas- prefix.
    assert (dest / "atlas-FOO.bib").exists()
    assert not (dest / "references.bib").exists()
    # The label image is never copied.
    assert not (dest / "atlas-FOO_space-NMT2Sym_res-05.nii.gz").exists()
    assert {p.name for p in copied} == {
        "atlas-FOO.tsv",
        "atlas-FOO.md",
        "atlas-FOO.bib",
    }


def test_no_bib_copies_only_prefixed_sidecars(tmp_path):
    src = tmp_path / "BAR"
    _make_family(src, "BAR", with_bib=False)
    dest = tmp_path / "out"

    copied = copy_atlas_sidecars("BAR", dest, source_dir=src)

    assert {p.name for p in copied} == {"atlas-BAR.tsv", "atlas-BAR.md"}
    assert not (dest / "atlas-BAR.bib").exists()


def test_existing_dest_not_overwritten(tmp_path):
    src = tmp_path / "FOO"
    _make_family(src, "FOO")
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "atlas-FOO.tsv").write_text("SENTINEL")

    copied = copy_atlas_sidecars("FOO", dest, source_dir=src)

    # Pre-existing file left untouched and excluded from the returned list.
    assert (dest / "atlas-FOO.tsv").read_text() == "SENTINEL"
    assert all(p.name != "atlas-FOO.tsv" for p in copied)
    # Others still copied.
    assert (dest / "atlas-FOO.md").exists()
    assert (dest / "atlas-FOO.bib").exists()


def test_name_prefix_does_not_leak_across_atlases(tmp_path):
    # Family dir holding two atlases; asking for FOO must not copy FOO2's sidecar.
    src = tmp_path / "fam"
    _make_family(src, "FOO", with_bib=False, with_md=False)
    (src / "atlas-FOO2.tsv").write_text("other\n")
    dest = tmp_path / "out"

    copied = copy_atlas_sidecars("FOO", dest, source_dir=src)

    assert {p.name for p in copied} == {"atlas-FOO.tsv"}
    assert not (dest / "atlas-FOO2.tsv").exists()


# --------------------------------------------------------------------------- #
# re-discovery from the bundled template zoo (source_dir=None)
# --------------------------------------------------------------------------- #
def _zoo_has(name: str) -> bool:
    root = get_template_manager().template_dir / "atlas"
    return any(root.glob(f"**/atlas-{name}_space-*.nii.gz"))


@pytest.mark.skipif(not _zoo_has("ARM1"), reason="ARM1 atlas not in template zoo")
def test_rediscovers_arm_from_zoo(tmp_path):
    copied = copy_atlas_sidecars("ARM1", tmp_path)
    names = {p.name for p in copied}
    # ARM ships a per-atlas LUT and a family references.bib.
    assert "atlas-ARM1.tsv" in names
    assert "atlas-ARM1.bib" in names


@pytest.mark.skipif(
    not _zoo_has("CortHierarchy"), reason="CortHierarchy atlas not in template zoo"
)
def test_rediscovers_bib_only_atlas_from_zoo(tmp_path):
    # CortHierarchy has no .tsv/.md sidecar, only the family references.bib.
    # (This test used to point at D99, which gained an atlas-D99.tsv in v2.0.0.)
    copied = copy_atlas_sidecars("CortHierarchy", tmp_path)
    assert {p.name for p in copied} == {"atlas-CortHierarchy.bib"}


def test_unknown_atlas_returns_empty(tmp_path):
    assert copy_atlas_sidecars("NoSuchAtlasXYZ", tmp_path) == []
