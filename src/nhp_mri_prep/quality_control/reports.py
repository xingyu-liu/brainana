"""
Quality Control Report Generation

This module generates comprehensive HTML reports summarizing preprocessing results,
including embedded snapshots, processing parameters, and quality metrics.
"""

import os
import logging
import html
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Union, List, Optional
import re

from ..utils.bids import parse_bids_entities, BIDS_ENTITY_ORDER
from ..config.config_io import get_nested_config_value


# Configuration constants
SNAPSHOT_MAPPINGS = {
    'conform': {'key': 'conform_overlay', 'description': 'Conform to template space'},
    'biascorrect': {'key': 'bias_correction_comparison', 'description': 'Bias field correction'},
    'atlasSegmentation': {'key': 'atlas_segmentation_overlay', 'description': 'Atlas segmentation'},
    'anat2template': {'key': 'anat2template_registration_overlay', 'description': 'Structural to template registration'},
    'func2anat': {'key': 'func2anat_registration_overlay', 'description': 'Functional to anatomical registration'},
    'func2target': {'key': 'func2target_registration_overlay', 'description': 'Functional to target registration'},
    'T2w2T1w': {'key': 'T2w2T1w_registration_overlay', 'description': 'T2w to T1w coregistration'},
    'T2w2template': {'key': 'T2w2template_registration_overlay', 'description': 'T2w to template registration'},
    'T1wT2wCombined': {'key': 't1wt2w_combined_comparison', 'description': 'T1wT2wCombined comparison'},
    'func_coreg': {'key': 'func_coreg_overlay', 'description': 'Within-session functional coregistration'},
    'motion': {'key': 'motion_parameters', 'description': 'Motion parameters'},
    'surfReconTissueSeg': {'key': 'surf_recon_tissue_seg_overlay', 'description': 'Surface reconstruction tissue segmentation'},
    'corticalSurfAndMeasures': {'key': 'cortical_surf_and_measures_overlay', 'description': 'Cortical surface and measures'},
    'skullstrip': {'key': 'skullstrip_overlay', 'description': 'Skullstripping'},
}

# Figure descriptions shown above the figure (same font style as "Get figure file"); first letter auto-capitalized.
# Key by desc; for 'conform' use (desc, modality) because anatomical vs functional differ.
FIGURE_DESCRIPTIONS = {
    'conform': {
        'anatomical': 'rigid registered T1w (underlaid); template space (contour)',
        'functional': 'rigid registered BOLD (underlaid); target space (contour)',
    },
    'anat2template': 'registered T1w (underlaid); template space (contour)',
    'atlasSegmentation': 'ARM2: CHARM level 2 parcellation in cortex and SARM level 2 parcellation in subcortex',
    'surfReconTissueSeg': 'White surface (blue contour); pial surface (red contour)',
    'T2w2T1w': 'rigid registered T2w (underlaid); T1w space (contour)',
    'T2w2template': 'registered T2w (underlaid); template space (contour)',
    'func2anat': 'registered BOLD (underlaid); T1w space (contour)',
    'func2target': 'registered BOLD (underlaid); target space (contour)',
}

SNAPSHOT_ORDER = [
    'conform_overlay', 
    'skullstrip_overlay', 'atlas_segmentation_overlay', 
    'bias_correction_comparison', 
    'anat2template_registration_overlay', 
    'T2w2T1w_registration_overlay', 
    't1wt2w_combined_comparison',
    'T2w2template_registration_overlay',
    'surf_recon_tissue_seg_overlay', 'cortical_surf_and_measures_overlay',
    'func_coreg_overlay',  # Within-session coregistration (appears before run-specific snapshots)
    'func2anat_registration_overlay',  # Functional to anatomical (intermediate step in sequential transforms)
    'func2target_registration_overlay', 
    'motion_parameters'
]

SNAPSHOT_ORDER_INDEX = {key: index for index, key in enumerate(SNAPSHOT_ORDER)}

# Full sequential stage labels used in anat-to-template normalization sentences.
_XFM_STAGE_LABELS: Dict[str, str] = {
    "translation": "translation-only",
    "rigid": "rigid",
    "affine": "translation, rigid, and affine",
    "syn": "translation, rigid, affine, and non-linear (SyN)",
}

# Abbreviated transform labels used in parenthetical func coregistration sentences.
_XFM_COREG_LABELS: Dict[str, str] = {
    "translation": "translation",
    "rigid": "rigid",
    "affine": "rigid and affine",
    "syn": "rigid, affine, and SyN",
}

# APA 7 references for the Methods section. Key = exact in-text citation (Author et al., YEAR).
# Only references whose key appears in the methods body are included in the report.
# Full reference: docs_temp/paper/methods_reference.md
_METHODS_REFERENCE_MAP = {
    "Avants et al., 2008": (
        "Avants, B. B., Epstein, C. L., Grossman, M., & Gee, J. C. (2008). Symmetric diffeomorphic "
        "image registration with cross-correlation: Evaluating automated labeling of elderly and "
        "neurodegenerative brain. Medical Image Analysis, 12(1), 26–41. "
        "https://doi.org/10.1016/j.media.2007.06.004"
    ),
    "Cox, 1996": (
        "Cox, R. W. (1996). AFNI: Software for analysis and visualization of functional magnetic "
        "resonance neuroimages. Computers and Biomedical Research, 29(3), 162–173. "
        "https://doi.org/10.1006/cbmr.1996.0014"
    ),
    "Cox & Hyde, 1997": (
        "Cox, R. W., & Hyde, J. S. (1997). Software tools for analysis and visualization of fMRI "
        "data. NMR in Biomedicine, 10(4–5), 171–178. "
        "https://doi.org/10.1002/(SICI)1099-1492(199706/08)10:4/5<171::AID-NBM453>3.0.CO;2-L"
    ),
    "Dale et al., 1999": (
        "Dale, A. M., Fischl, B., & Sereno, M. I. (1999). Cortical surface-based analysis: "
        "Segmentation and surface reconstruction. NeuroImage, 9(2), 179–194. "
        "https://doi.org/10.1006/nimg.1998.0395"
    ),
    "Henschel et al., 2020": (
        "Henschel, L., Conjeti, S., Estrada, S., Diers, K., Fischl, B., & Reuter, M. (2020). "
        "FastSurfer: A fast and accurate deep learning based neuroimaging pipeline. "
        "NeuroImage, 219, 117012. https://doi.org/10.1016/j.neuroimage.2020.117012"
    ),
    "Jenkinson et al., 2002": (
        "Jenkinson, M., Bannister, P., Brady, M., & Smith, S. (2002). Improved optimization for the "
        "robust and accurate linear registration and motion correction of brain images. "
        "NeuroImage, 17(2), 825–841. https://doi.org/10.1006/nimg.2002.1132"
    ),
    "Jena et al., 2024": (
        "Jena, R., Chaudhari, P., & Gee, J. C. (2024). FireANTs: Adaptive Riemannian optimization "
        "for multi-scale diffeomorphic matching. arXiv preprint arXiv:2404.01249. "
        "https://arxiv.org/abs/2404.01249"
    ),
    "Jung et al., 2021": (
        "Jung, B., Taylor, P. A., Seidlitz, J., Suber, A., Donahue, C. J., Coalson, T., Glasser, "
        "M. F., Shafer, A. T., Van Essen, D. C., Dienes, T., Earl, E., Feczko, E., Fair, D. A., & "
        "Donahue, J. N. (2021). A comprehensive macaque fMRI pipeline and hierarchical atlas. "
        "NeuroImage, 235, 117997. https://doi.org/10.1016/j.neuroimage.2021.117997"
    ),
    "Tustison et al., 2010": (
        "Tustison, N. J., Avants, B. B., Cook, P. A., Zheng, Y., Egan, A., Yushkevich, P. A., & "
        "Gee, J. C. (2010). N4ITK: Improved N3 bias correction. IEEE Transactions on Medical "
        "Imaging, 29(6), 1310–1320. https://doi.org/10.1109/TMI.2010.2046908"
    ),
    "Wang et al., 2021": (
        "Wang, X., Li, X., & Xu, T. (2021). U-net model for brain extraction: Trained on humans for "
        "transfer to non-human primates. NeuroImage, 235, 118001. "
        "https://doi.org/10.1016/j.neuroimage.2021.118001"
    ),
}


def _cited_references(methods_body: str) -> List[str]:
    """Return full reference strings for all citation keys that appear in methods_body, sorted alphabetically by first author."""
    seen: set = set()
    for match in re.findall(r"\(([^)]+)\)", methods_body):
        for part in match.split(";"):
            key = part.strip()
            if key in _METHODS_REFERENCE_MAP:
                seen.add(key)
    refs = [_METHODS_REFERENCE_MAP[k] for k in seen]
    return sorted(refs)


class BidsEntityProcessor:
    """Handles all BIDS entity processing operations."""
    
    @staticmethod
    def extract_entities_from_snapshots(data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract all unique BIDS entity combinations from snapshot hierarchy."""
        entities_list = []
        
        def collect_entities(level_data: Dict[str, Any]) -> None:
            for value in level_data.values():
                if isinstance(value, dict):
                    if 'entities' in value:
                        entities = {k: v for k, v in value['entities'].items() if k not in ['sub', 'desc', 'space']}
                        if entities and entities not in entities_list:
                            entities_list.append(entities)
                    else:
                        collect_entities(value)
        
        collect_entities(data)
        return sorted(entities_list, key=lambda x: [x.get(k, '') for k in BIDS_ENTITY_ORDER])
    
    @staticmethod
    def create_display_text(entities: Dict[str, str]) -> str:
        """Create human-readable display text from BIDS entities."""
        parts = []
        for entity in BIDS_ENTITY_ORDER:
            if entity in entities:
                if entity == 'ses':
                    parts.append(f'session <span class="bids-entity">{entities[entity]}</span>')
                elif entity == 'task':
                    parts.append(f'task <span class="bids-entity">{entities[entity]}</span>')
                elif entity == 'run':
                    parts.append(f'run <span class="bids-entity">{entities[entity]}</span>')
                else:
                    parts.append(f'{entity} <span class="bids-entity">{entities[entity]}</span>')
        
        return f"{', '.join(parts)}" if parts else None
    
    @staticmethod
    def clean_header_id(text: str) -> str:
        """Clean text to create valid HTML ID."""
        clean_text = re.sub(r'<[^>]+>', '', text)
        clean_text = re.sub(r'[^a-zA-Z0-9-]', '-', clean_text.lower())
        return re.sub(r'-+', '-', clean_text).strip('-')


class SnapshotProcessor:
    """Handles snapshot discovery, parsing, and organization."""
    
    @staticmethod
    def discover_and_parse(snapshot_dir: Path, logger: logging.Logger, 
                          provided_paths: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Discover and parse all snapshots in one pass."""
        if provided_paths:
            snapshot_files = {name: Path(path) for name, path in provided_paths.items()}
            logger.info(f"QC: using {len(snapshot_files)} provided snapshot paths")
        else:
            png_files = list(snapshot_dir.glob("*.png"))
            logger.info(f"QC: auto-discovered {len(png_files)} PNG files")
            snapshot_files = {SnapshotProcessor._create_key(f.name): f for f in png_files}
        
        snapshots = {}
        available_entities = {key: set() for key in BIDS_ENTITY_ORDER if key != 'sub'}
        
        for name, path in snapshot_files.items():
            entities = parse_bids_entities(path.name)
            
            # Collect available entities
            for entity_key in BIDS_ENTITY_ORDER:
                if entity_key != 'sub' and entity_key in entities:
                    available_entities[entity_key].add(entities[entity_key])
            
            desc = entities.get('desc', '')
            mapping = SNAPSHOT_MAPPINGS.get(desc, {})
            snapshot_type = mapping.get('key', desc)
            
            # Determine modality first
            modality = SnapshotProcessor._determine_modality(path.name)
            
            # Customize description based on modality for conform snapshots
            description = mapping.get('description', '')
            if desc == 'conform' and modality == 'functional':
                description = 'Conform to target space'
            
            # Figure description (underlaid/contour text) for QC report
            figure_desc_entry = FIGURE_DESCRIPTIONS.get(desc)
            if isinstance(figure_desc_entry, dict):
                figure_description = figure_desc_entry.get(modality, '')
            else:
                figure_description = figure_desc_entry if isinstance(figure_desc_entry, str) else ''
            
            # Store the filename separately for reliable path construction
            snapshots[name] = {
                'path': str(path),
                'filename': path.name,
                'entities': entities,
                'modality': modality,
                'description': description,
                'snapshot_type': snapshot_type,
                'figure_description': figure_description,
            }
        
        # Convert sets to sorted lists
        for key in available_entities:
            available_entities[key] = sorted(available_entities[key])
        
        logger.info(f"QC: parsed {len(snapshots)} snapshots")
        return {'snapshots': snapshots, 'available_entities': available_entities}
    
    @staticmethod
    def _create_key(filename: str) -> str:
        """Create snapshot key from filename."""
        entities = parse_bids_entities(filename)
        desc = entities.get('desc', '')
        mapping = SNAPSHOT_MAPPINGS.get(desc, {})
        base_name = mapping.get('key', desc)
        
        key_parts = [base_name]
        for entity_key in BIDS_ENTITY_ORDER:
            if entity_key != 'sub' and entity_key in entities:
                key_parts.append(f"{entity_key}-{entities[entity_key]}")
        
        # Add modality suffix to avoid key collisions between T1w/T2w
        if filename.endswith('_T1w.png'):
            key_parts.append('T1w')
        elif filename.endswith('_T2w.png'):
            key_parts.append('T2w')
        elif filename.endswith('_bold.png') or filename.endswith('_boldref.png'):
            key_parts.append('bold')
        
        return "_".join(key_parts)
    
    @staticmethod
    def _determine_modality(name: str) -> str:
        """Determine modality from filename."""
        # Check for functional first (bold or boldref suffix), as functional files can contain
        # space-T1w or space-T2w entities which would otherwise be misclassified
        if (name.lower().endswith('_bold.png') or '_bold.png' in name.lower() or
            name.lower().endswith('_boldref.png') or '_boldref.png' in name.lower()):
            return "functional"
        # Check for anatomical in suffix position (e.g., _T1w.png, _T2w.png)
        # This avoids false positives from space-T1w or space-T2w entities
        elif name.endswith('_T1w.png') or name.endswith('_T2w.png'):
            return "anatomical"
        # Fallback: check if T1w/T2w appears as a suffix pattern (before extension)
        elif '_T1w.' in name or '_T2w.' in name:
            return "anatomical"
        elif 'fmap' in name.lower():
            return "field_mapping"
        else:
            return "summary"
    
    @staticmethod
    def organize_by_hierarchy(snapshots: Dict[str, Any], snapshot_dir: Path, 
                            report_path: Path, logger: logging.Logger) -> Dict[str, Any]:
        """Organize snapshots by BIDS hierarchy."""
        organized = {"anatomical": {}, "functional": {}, "field_mapping": {}, "summary": {}}
        
        # Calculate relative path from report parent to snapshot directory
        # snapshot_dir is the published path: /full/path/to/output/sub-XXX/figures
        # report_path might be relative (work directory) or absolute (published)
        # We need the published report path for correct relative path calculation
        # Derive it from snapshot_dir: if snapshot_dir is /path/to/output/sub-XXX/figures,
        # then published report is /path/to/output/sub-XXX.html
        
        snapshot_dir_str = str(snapshot_dir)
        report_path_str = str(report_path)
        
        # If report_path is relative, derive published path from snapshot_dir
        if not os.path.isabs(report_path_str):
            # snapshot_dir is like: /path/to/output/sub-XXX/figures
            # published report is: /path/to/output/sub-XXX.html
            snapshot_dir_path = Path(snapshot_dir_str)
            # Get parent (sub-XXX) and then parent again (output directory)
            output_dir = snapshot_dir_path.parent.parent
            report_filename = Path(report_path_str).name  # e.g., "sub-XXX.html"
            published_report_path = output_dir / report_filename
            report_parent = str(published_report_path.parent)
        else:
            # report_path is already absolute (published path)
            report_parent = str(Path(report_path_str).parent)
        
        # Calculate relative path using string paths (don't resolve to avoid work directory issues)
        try:
            report_to_snapshot_dir = os.path.relpath(snapshot_dir_str, report_parent)
        except ValueError:
            # If paths are on different drives (Windows) or can't be made relative,
            # extract the relative portion manually
            # Both paths should share a common prefix up to the output directory
            report_parent_parts = Path(report_parent).parts
            snapshot_dir_parts = Path(snapshot_dir_str).parts
            
            # Find common prefix
            common_parts = []
            for r_part, s_part in zip(report_parent_parts, snapshot_dir_parts):
                if r_part == s_part:
                    common_parts.append(r_part)
                else:
                    break
            
            # Calculate relative path: go up from report_parent, then down to snapshot_dir
            up_levels = len(report_parent_parts) - len(common_parts)
            down_parts = snapshot_dir_parts[len(common_parts):]
            
            if up_levels > 0 and down_parts:
                report_to_snapshot_dir = os.path.join(*(['..'] * up_levels + list(down_parts)))
            elif down_parts:
                report_to_snapshot_dir = os.path.join(*down_parts)
            else:
                report_to_snapshot_dir = '.'
        
        for name, snapshot_info in snapshots.items():
            # Get filename (stored separately for reliability, or extract from path)
            filename = snapshot_info.get('filename', Path(snapshot_info['path']).name)
            
            # Construct relative path: from report_parent to snapshot_dir, then filename
            if report_to_snapshot_dir == '.':
                relative_path = filename
            else:
                relative_path = os.path.join(report_to_snapshot_dir, filename)
            
            snapshot_data = {
                "path": relative_path,
                "entities": snapshot_info['entities'],
                "description": snapshot_info['description'],
                "snapshot_type": snapshot_info['snapshot_type'],
                "figure_description": snapshot_info.get('figure_description', ''),
            }
            
            modality = snapshot_info['modality']
            SnapshotProcessor._add_to_hierarchy(organized[modality], snapshot_data, 
                                              snapshot_info['entities'], name)
        
        SnapshotProcessor._sort_hierarchy(organized)
        logger.info("QC: organized snapshots by BIDS hierarchy with relative paths")
        return organized
    
    @staticmethod
    def _add_to_hierarchy(root: Dict, snapshot_data: Dict, entities: Dict, name: str):
        """Add snapshot to hierarchical structure."""
        current = root
        for entity_key in BIDS_ENTITY_ORDER:
            if entity_key != 'sub' and entity_key in entities:
                value = entities[entity_key]
                if value not in current:
                    current[value] = {}
                current = current[value]
        current[name] = snapshot_data
    
    @staticmethod
    def _sort_hierarchy(data: Dict):
        """Sort hierarchical structure recursively."""
        for key, value in data.items():
            if isinstance(value, dict) and 'path' not in value:
                if any(isinstance(v, dict) and 'snapshot_type' in v for v in value.values()):
                    # Sort by snapshot order, with special handling for T1w/T2w modality order
                    def sort_key(item):
                        name, snapshot_info = item
                        base_order = SNAPSHOT_ORDER_INDEX.get(snapshot_info.get('snapshot_type', ''), 999)
                        
                        # For anatomical snapshots, ensure T1w comes before T2w
                        # Also ensure that within the same snapshot type, T1w comes before T2w
                        modality_order = 0
                        # Use more specific logic - check file ending for modality
                        if name.endswith('_T1w.png') or (snapshot_info.get('entities', {}).get('suffix') == 'T1w'):
                            modality_order = 0  # T1w first
                        elif name.endswith('_T2w.png') or (snapshot_info.get('entities', {}).get('suffix') == 'T2w'):
                            modality_order = 1  # T2w second
                        
                        return (base_order, modality_order, name)
                    
                    sorted_items = sorted(value.items(), key=sort_key)
                else:
                    # For non-snapshot items, ensure T1w comes before T2w
                    def sort_key(item):
                        name, _ = item
                        # Use more specific logic - check file ending for modality
                        if name.endswith('_T1w.png') or '_T1w' in name:
                            return (0, name)
                        elif name.endswith('_T2w.png') or '_T2w' in name:
                            return (1, name)
                        else:
                            return (2, name)
                    
                    sorted_items = sorted(value.items(), key=sort_key)
                    
                data[key] = dict(sorted_items)
                SnapshotProcessor._sort_hierarchy(data[key])


class HtmlGenerator:
    """Handles all HTML generation operations."""
    
    @staticmethod
    def create_navigation_menu(organized_snapshots: Dict[str, Any]) -> str:
        """Create navigation menu."""
        nav_items = ['<li class="nav-item"><a class="nav-link" href="#Summary">Summary</a></li>']
        
        # Add modality sections with dropdowns if they have content
        for modality, title in [("anatomical", "Structural"), ("functional", "Functional"),
                               ("field_mapping", "B₀ field mapping")]:
            if organized_snapshots[modality]:
                section_prefix = modality
                groups = HtmlGenerator._group_snapshots_by_entities(organized_snapshots[modality], section_prefix)
                # Anatomical returns two-level dict (ses/run -> modality -> list); nav uses top-level keys
                group_keys = list(groups.keys())
                if len(group_keys) > 1:
                    dropdown_items = []
                    for group_key in group_keys:
                        nav_id = f"{section_prefix}-{BidsEntityProcessor.clean_header_id(group_key)}"
                        dropdown_items.append(f'<a class="dropdown-item" href="#{nav_id}">{group_key}</a>')
                    dropdown_content = '\n'.join(dropdown_items)
                    nav_items.append(f'''<li class="nav-item dropdown">
<a class="nav-link dropdown-toggle" id="navbar{modality.title()}" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false" href="#">{title}</a>
<div class="dropdown-menu" aria-labelledby="navbar{modality.title()}">
{dropdown_content}
</div>
</li>''')
                else:
                    nav_items.append(f'<li class="nav-item"><a class="nav-link" href="#{modality.title()}">{title}</a></li>')
        
        nav_items.extend([
            '<li class="nav-item"><a class="nav-link" href="#About">About</a></li>',
            '<li class="nav-item"><a class="nav-link" href="#Methods">Methods</a></li>'
        ])
        
        return '\n'.join(nav_items)
    
    @staticmethod
    def create_section(section_id: str, title: str, content: str) -> str:
        """Create a section with header and content."""
        return f'<div id="{section_id}"><h1 class="sub-report-title">{title}</h1>{content}</div>'
    
    @staticmethod
    def create_summary_section(report_data: Dict[str, Any], config: Dict[str, Any]) -> str:
        """Create summary section."""
        subject_id = report_data["metadata"]["subject_id"]
        organized = report_data["organized_snapshots"]

        # Use original counts from dataset_context if available; otherwise derive from snapshots
        dataset_context = report_data.get("dataset_context", {})
        if "subject_file_counts" in dataset_context:
            # Use detailed subject counts if available (preferred)
            t1w_count = dataset_context["subject_file_counts"].get("t1w", 0)
            t2w_count = dataset_context["subject_file_counts"].get("t2w", 0)
            func_count = dataset_context["subject_file_counts"]["functional"]
        elif "job_file_counts" in dataset_context:
            # Fall back to job counts (no T1w/T2w breakdown available)
            t1w_count = dataset_context["job_file_counts"]["anatomical"]
            t2w_count = 0  # Cannot determine T2w count from legacy data
            func_count = dataset_context["job_file_counts"]["functional"]
        else:
            # Derive counts from organized snapshots (what actually has QC in this report)
            anat_counts = HtmlGenerator._count_anatomical_by_modality(organized["anatomical"])
            t1w_count = anat_counts["t1w"]
            t2w_count = anat_counts["t2w"]
            func_count = HtmlGenerator._count_unique_images(organized["functional"])

        # Build structural images description: always show both T1w and T2w
        if t1w_count == "N/A" or t2w_count == "N/A":
            structural_text = "N/A"
        else:
            t1w = int(t1w_count) if t1w_count is not None else 0
            t2w = int(t2w_count) if t2w_count is not None else 0
            structural_text = f"{t1w} T1w, {t2w} T2w"

        # Standard output space: template.output_space (e.g. "NMT2Sym:res-05") -> display template name
        output_space_raw = (
            config.get("template", {}).get("output_space")
            or config.get("output_spaces")
            or "NMT2Sym"
        )
        output_space_display = str(output_space_raw).split(":")[0] if output_space_raw else "NMT2Sym"

        # Surface reconstruction: show "Run by Brainana" if this report includes surface reconstruction QC
        has_surf = HtmlGenerator._has_surface_recon_snapshots(organized["anatomical"])
        freesurfer_text = "Run by Brainana" if has_surf else "Not applicable"

        content = f'''<div class="boiler-html">
<p><strong>Configuration:</strong> For detailed processing parameters and configuration settings,
please refer to the brainana configuration files in your preprocessing directory.</p>
</div>
<ul class="elem-desc">
<li>Subject ID: {subject_id}</li>
<li>Structural images: {structural_text}</li>
<li>Functional images: {func_count}</li>
<li>Output spaces: {output_space_display}</li>
<li>Surface reconstruction: {freesurfer_text}</li>
</ul>'''

        return HtmlGenerator.create_section("Summary", "Summary", content)
    
    @staticmethod
    def create_modality_section(section_id: str, data: Dict[str, Any], title: str = None) -> str:
        """Create modality section with snapshots."""
        if not data:
            return ""
        
        if title is None:
            title = section_id
        
        content = HtmlGenerator._render_snapshots(data, section_id.lower())
        return HtmlGenerator.create_section(section_id, title, content)
    
    @staticmethod
    def _render_snapshots(data: Dict[str, Any], section_prefix: str) -> str:
        """Render snapshots with grouping."""
        html_parts = []
        
        # Group snapshots by BIDS entities (two-level for anatomical: ses/run then T1w/T2w)
        snapshot_groups = HtmlGenerator._group_snapshots_by_entities(data, section_prefix)
        
        def render_snapshot_blocks(snapshots: List[Dict[str, Any]]) -> None:
            for snapshot_data in snapshots:
                snapshot_id = f"{section_prefix}-{snapshot_data['filename'].replace('.', '-')}"
                title = snapshot_data.get('description', snapshot_data['filename'])
                fig_desc = snapshot_data.get('figure_description', '')
                if fig_desc:
                    fig_desc = fig_desc[0].upper() + fig_desc[1:]
                fig_desc_block = f'\n<div class="elem-filename">\n    {fig_desc}\n</div>' if fig_desc else ''
                html_parts.append(f'''<div id="{snapshot_id}">
<h3 class="run-title">{title}</h3>{fig_desc_block}
<img class="svg-reportlet" src="{snapshot_data["path"]}" style="width: 100%" />
</div>
<div class="elem-filename">
    Get figure file: <a href="{snapshot_data["path"]}" target="_blank">{snapshot_data["filename"]}</a>
</div>''')

        # Two-level structure (anatomical): ses/run -> T1w/T2w -> snapshots
        first_val = next(iter(snapshot_groups.values()), None) if snapshot_groups else None
        two_level = isinstance(first_val, dict)
        if two_level:
            for group_key, modality_dict in snapshot_groups.items():
                if group_key:
                    header_id = f"{section_prefix}-{BidsEntityProcessor.clean_header_id(group_key)}"
                    html_parts.append(f'<h2 class="sub-report-group" id="{header_id}">{group_key}</h2>')
                for modality in ('T1w', 'T2w'):
                    if modality in modality_dict:
                        html_parts.append(f'<h3 class="sub-report-group">{modality}</h3>')
                        render_snapshot_blocks(modality_dict[modality])
        else:
            for group_key, snapshots in snapshot_groups.items():
                if group_key:
                    header_id = f"{section_prefix}-{BidsEntityProcessor.clean_header_id(group_key)}"
                    html_parts.append(f'<h2 class="sub-report-group" id="{header_id}">{group_key}</h2>')
                render_snapshot_blocks(snapshots)
        
        return '\n'.join(html_parts)
    
    @staticmethod
    def _group_snapshots_by_entities(data: Dict[str, Any], section_prefix: str = "") -> Dict[str, Any]:
        """Group snapshots by BIDS entities. For anatomical (section_prefix=='anatomical'),
        returns two-level Dict[ses/run_key, Dict[modality, list]]; otherwise flat Dict[group_key, list]."""
        all_snapshots = []
        
        def collect_snapshots(level_data: Dict[str, Any]) -> None:
            for value in level_data.values():
                if isinstance(value, dict):
                    if 'path' in value:
                        filename = Path(value['path']).name
                        entities = parse_bids_entities(filename)
                        all_snapshots.append({
                            'filename': filename,
                            'path': value['path'],
                            'entities': entities,
                            'description': value.get('description', ''),
                            'snapshot_type': value.get('snapshot_type', ''),
                            'figure_description': value.get('figure_description', ''),
                        })
                    else:
                        collect_snapshots(value)
        
        collect_snapshots(data)
        
        def snapshot_sort_key(snapshot: Dict[str, Any]):
            base_order = SNAPSHOT_ORDER_INDEX.get(snapshot.get('snapshot_type', ''), 999)
            filename = snapshot.get('filename', '')
            modality_order = 0
            if filename.endswith('_T1w.png') or (snapshot.get('entities', {}).get('suffix') == 'T1w'):
                modality_order = 0
            elif filename.endswith('_T2w.png') or (snapshot.get('entities', {}).get('suffix') == 'T2w'):
                modality_order = 1
            return (base_order, modality_order, filename)
        
        # Anatomical: two-level grouping (ses/run -> T1w/T2w -> snapshots)
        if section_prefix == "anatomical":
            groups = {}
            for snapshot in all_snapshots:
                entities = snapshot['entities']
                entities_no_suffix = {k: v for k, v in entities.items() if k not in ['sub', 'desc', 'space', 'suffix']}
                base_group_key = BidsEntityProcessor.create_display_text(entities_no_suffix) or 'sub-level'
                filename = snapshot.get('filename', '')
                suffix = entities.get('suffix', '')
                # T1wT2wCombined comparison is shown under T2w (between T2w2T1w and T2w2template)
                if snapshot.get('snapshot_type') == 't1wt2w_combined_comparison':
                    modality = 'T2w'
                elif suffix == 'T1w' or (suffix != 'T2w' and filename.endswith('_T1w.png')):
                    modality = 'T1w'
                elif suffix == 'T2w' or filename.endswith('_T2w.png'):
                    modality = 'T2w'
                else:
                    modality = 'T1w'
                if base_group_key not in groups:
                    groups[base_group_key] = {}
                if modality not in groups[base_group_key]:
                    groups[base_group_key][modality] = []
                groups[base_group_key][modality].append(snapshot)
            for base_key in groups:
                for mod in groups[base_key]:
                    groups[base_key][mod].sort(key=snapshot_sort_key)
            # Sort top-level by session
            def anat_group_sort(item):
                group_name, modality_dict = item
                session_value = ''
                for snap_list in modality_dict.values():
                    if snap_list:
                        session_value = snap_list[0].get('entities', {}).get('ses', '')
                        break
                return (session_value or '', group_name)
            return dict(sorted(groups.items(), key=anat_group_sort))
        
        # Flat grouping for functional / field_mapping
        groups = {}
        for snapshot in all_snapshots:
            entities = {k: v for k, v in snapshot['entities'].items() if k not in ['sub', 'desc', 'space']}
            base_group_key = BidsEntityProcessor.create_display_text(entities) or 'sub-level'
            filename = snapshot.get('filename', '')
            ent = snapshot.get('entities', {})
            # T1wT2wCombined comparison is shown under T2w
            if snapshot.get('snapshot_type') == 't1wt2w_combined_comparison':
                group_key = "T2w" if base_group_key == 'sub-level' else f"{base_group_key} T2w"
            elif ent.get('suffix') == 'T1w' or (ent.get('suffix') != 'T2w' and filename.endswith('_T1w.png')):
                group_key = "T1w" if base_group_key == 'sub-level' else f"{base_group_key} T1w"
            elif ent.get('suffix') == 'T2w' or filename.endswith('_T2w.png'):
                group_key = "T2w" if base_group_key == 'sub-level' else f"{base_group_key} T2w"
            else:
                group_key = base_group_key
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(snapshot)
        
        for group_key in groups:
            groups[group_key].sort(key=snapshot_sort_key)
        
        def group_sort_key(group_item):
            group_name, snapshots = group_item
            is_func_coreg = any(
                s.get('snapshot_type') == 'func_coreg_overlay'
                and 'task' not in s.get('entities', {})
                and 'run' not in s.get('entities', {})
                for s in snapshots
            )
            session_value = None
            if snapshots:
                session_value = snapshots[0].get('entities', {}).get('ses', '')
            if group_name == 'T1w' or group_name.endswith(' T1w'):
                return (0, 0, session_value or '', group_name)
            elif group_name == 'T2w' or group_name.endswith(' T2w'):
                return (0, 1, session_value or '', group_name)
            elif is_func_coreg:
                return (1, 0, session_value or '', group_name)
            else:
                return (1, 1, session_value or '', group_name)
        
        return dict(sorted(groups.items(), key=group_sort_key))
    
    @staticmethod
    def _count_unique_images(data: Dict[str, Any]) -> int:
        """Count unique images from organized snapshots (excluding different processing steps)."""
        if not data:
            return 0
        
        unique_images = set()
        
        def collect_unique_entities(level_data: Dict[str, Any]) -> None:
            for value in level_data.values():
                if isinstance(value, dict):
                    if 'path' in value and 'entities' in value:
                        # Create identifier from entities excluding 'desc' (processing step)
                        entities = value['entities']
                        image_id = tuple(sorted(
                            (k, v) for k, v in entities.items() 
                            if k not in ['desc', 'sub']  # Exclude processing description and subject
                        ))
                        unique_images.add(image_id)
                    else:
                        collect_unique_entities(value)
        
        collect_unique_entities(data)
        return len(unique_images)

    @staticmethod
    def _count_anatomical_by_modality(data: Dict[str, Any]) -> Dict[str, int]:
        """Count unique T1w and T2w images from organized anatomical snapshots."""
        t1w_ids: set = set()
        t2w_ids: set = set()

        def collect(level_data: Dict[str, Any]) -> None:
            for value in level_data.values():
                if isinstance(value, dict):
                    if 'path' in value and 'entities' in value:
                        entities = value['entities']
                        image_id = tuple(sorted(
                            (k, v) for k, v in entities.items()
                            if k not in ['desc', 'sub']
                        ))
                        # BIDS suffix (T1w/T2w) is often not in entities for PNG filenames;
                        # parse_bids_entities only extracts key-value pairs. Use filename.
                        filename = Path(value['path']).name
                        if filename.endswith('_T2w.png'):
                            t2w_ids.add(image_id)
                        else:
                            # T1w or unspecified anatomical (_T1w.png or other)
                            t1w_ids.add(image_id)
                    else:
                        collect(value)

        if data:
            collect(data)
        return {"t1w": len(t1w_ids), "t2w": len(t2w_ids)}

    @staticmethod
    def _has_surface_recon_snapshots(data: Dict[str, Any]) -> bool:
        """Return True if any anatomical snapshot is from surface reconstruction QC."""
        if not data:
            return False

        def collect(level_data: Dict[str, Any]) -> bool:
            for value in level_data.values():
                if isinstance(value, dict):
                    if 'path' in value and 'snapshot_type' in value:
                        st = (value.get('snapshot_type') or '').lower()
                        if 'surf' in st or 'cortical' in st:
                            return True
                    else:
                        if collect(value):
                            return True
            return False

        return collect(data)
    
    @staticmethod
    def create_about_section(report_data: Dict[str, Any]) -> str:
        """Create about section."""
        metadata = report_data["metadata"]
        content = f'''<div class="boiler-html">
<p>This report was generated by <strong>{metadata["pipeline_name"]}</strong> version <strong>{metadata["version"]}</strong>.</p>
<p>Generated on: {metadata["generation_time"]}</p>
<p>Working directory: {metadata["working_directory"]}</p>
</div>'''
        return HtmlGenerator.create_section("About", "About", content)
    
    @staticmethod
    def _conform_sentence(data_label: str, space_label: str, skull_enabled: bool) -> str:
        """Return the conform-to-space sentence, shared between T1w and fMRI preprocessing."""
        if skull_enabled:
            return (
                f"The {data_label} was conformed to {space_label} to ensure better performance "
                "of the subsequent steps: first, initial skullstripping was performed using a CNN "
                "model fine-tuned from DeepBet (Wang et al., 2021), then rigid registration to the "
                f"{space_label} brain was performed with FLIRT (FSL; Jenkinson et al., 2002)."
            )
        return (
            f"The {data_label} was conformed to {space_label} via rigid registration with FLIRT "
            "(FSL; Jenkinson et al., 2002) to ensure better performance of the subsequent steps."
        )

    @staticmethod
    def _build_anat_methods_paragraph(config: Dict[str, Any], has_t2w: bool) -> tuple:
        """Build anatomical preprocessing paragraphs dynamically from config.

        Returns:
            (t1w_text, t2w_text): t2w_text is None when has_t2w is False.
        """
        # --- T1w paragraph ---
        t1w = [
            "T1w images were preprocessed as follows. "
            "When multiple T1w images existed per session or subject, a single synthesized T1w was "
            "created by rigid coregistration to the first image using ANTs "
            "(Avants et al., 2008) and averaging in reference space."
        ]

        if get_nested_config_value(config, "anat.reorient.enabled", False):
            t1w.append(
                "The T1w was reoriented to the target or standard orientation using AFNI 3dresample "
                "(Cox, 1996; Cox & Hyde, 1997)."
            )

        skull_enabled = bool(get_nested_config_value(config, "anat.skullstripping_segmentation.enabled", True))

        if get_nested_config_value(config, "anat.conform.enabled", True):
            t1w.append(HtmlGenerator._conform_sentence("T1w", "template space", skull_enabled))

        if skull_enabled:
            t1w.append(
                "Brain tissue segmentation and brain mask generation were performed using a "
                "CNN fine-tuned from FastSurfer one (Henschel et al., 2020) "
                "and trained on macaque brain atlases (CHARM/SARM level 2; Jung et al., 2021)."
            )

        if get_nested_config_value(config, "anat.bias_correction.enabled", True):
            t1w.append(
                "The T1w was corrected for intensity non-uniformity with "
                "N4BiasFieldCorrection (Tustison et al., 2010), "
                "using the brain mask to restrict the correction."
            )

        xfm_type = (get_nested_config_value(config, "registration.anat2template_xfm_type", "syn") or "syn").lower()
        stage = _XFM_STAGE_LABELS.get(xfm_type, xfm_type)
        reg_sentence = (
            f"Volume-based spatial normalization to the template was performed through "
            f"{stage} registration with antsRegistration (ANTs; Avants et al., 2008)."
        )
        if xfm_type == "syn":
            reg_sentence += (
                " When a GPU was available, FireANTs (Jena et al., 2024) "
                "was used for the non-linear stage."
            )
        t1w.append(reg_sentence)

        if get_nested_config_value(config, "anat.surface_reconstruction.enabled", True):
            t1w.append(
                "Cortical surface reconstruction was performed using a modified FastSurfer pipeline "
                "(Henschel et al., 2020) adapted for non-human primates, based on the FreeSurfer "
                "surface reconstruction framework (Dale et al., 1999)."
            )

        # --- T2w paragraph (only when T2w data is present) ---
        if not has_t2w:
            return " ".join(t1w), None

        t2w = [
            "As with the T1w, when multiple T2w images existed per session or subject, a single "
            "synthesized T2w was created."
        ]

        if get_nested_config_value(config, "anat.reorient.enabled", False):
            t2w.append(
                "The T2w was reoriented to the target or standard orientation using AFNI 3dresample "
                "(Cox, 1996; Cox & Hyde, 1997)."
            )

        t2w.append(
            "The T2w was rigidly coregistered to the T1w space using ANTs (Avants et al., 2008)."
        )

        return " ".join(t1w), " ".join(t2w)

    @staticmethod
    def _build_func_methods_paragraph(config: Dict[str, Any]) -> str:
        """Build the functional preprocessing paragraph dynamically from config."""
        anat_only = bool(get_nested_config_value(config, "general.anat_only", False))
        if anat_only:
            return "Functional data preprocessing was not performed (anatomical-only mode)."

        sentences = [
            "fMRI data were preprocessed as follows."
        ]

        if get_nested_config_value(config, "func.slice_timing_correction.enabled", True):
            sentences.append(
                "Slice timing correction was applied using AFNI 3dTshift (Cox, 1996; Cox & Hyde, 1997)."
            )

        if get_nested_config_value(config, "func.reorient.enabled", False):
            sentences.append(
                "fMRI data were reoriented to the target or standard orientation using AFNI 3dresample "
                "(Cox, 1996; Cox & Hyde, 1997)."
            )

        motion_enabled = bool(get_nested_config_value(config, "func.motion_correction.enabled", True))
        if motion_enabled:
            sentences.append(
                "Head motion correction was performed with mcflirt (FSL; Jenkinson et al., 2002)."
            )

        despike_enabled = bool(get_nested_config_value(config, "func.despike.enabled", False))
        if despike_enabled:
            sentences.append(
                "Despiking was applied using AFNI 3dDespike (Cox, 1996; Cox & Hyde, 1997) "
                "to reduce the impact of extreme timepoints."
            )

        if get_nested_config_value(config, "func.coreg_runs_within_session", True):
            sentences.append(
                "When multiple fMRI runs existed within a session, within-session coregistration was "
                "performed using ANTs (Avants et al., 2008) by registering each run's mean image to a reference run."
            )

        func_skull = bool(get_nested_config_value(config, "func.skullstripping.enabled", True))
        if get_nested_config_value(config, "func.conform.enabled", True):
            sentences.append(HtmlGenerator._conform_sentence("fMRI data", "target space", func_skull))
        elif func_skull:
            sentences.append(
                "The fMRI data was skullstripped using a CNN model fine-tuned from DeepBet (Wang et al., 2021)."
            )

        func2anat_xfm = (get_nested_config_value(config, "registration.func2anat_xfm_type", "syn") or "syn").lower()
        xfm_desc = _XFM_COREG_LABELS.get(func2anat_xfm, func2anat_xfm)
        composite = (
            "The composite transform was applied to the full 4D BOLD and brain mask using "
            "antsApplyTransforms (ANTs), with B-spline interpolation for the BOLD series."
        )
        if func2anat_xfm == "syn":
            sentences.append(
                f"The mean fMRI data was registered to the preprocessed anatomical (or template) using "
                f"ANTs ({xfm_desc}; Avants et al., 2008); when a GPU was available, FireANTs "
                f"(Jena et al., 2024) was used for the non-linear stage. {composite}"
            )
        else:
            sentences.append(
                f"The mean fMRI data was registered to the preprocessed anatomical (or template) using "
                f"ANTs ({xfm_desc}; Avants et al., 2008). {composite}"
            )

        skip_steps = []
        if motion_enabled:
            skip_steps.append("motion correction")
        if despike_enabled:
            skip_steps.append("despiking")
        if skip_steps:
            sentences.append(
                f"Runs with fewer than 15 volumes skipped {' and '.join(skip_steps)}; "
                "pass-through outputs were generated."
            )

        return " ".join(sentences)

    @staticmethod
    def create_methods_section(report_data: Dict[str, Any]) -> str:
        """Create methods section with fMRIPrep-style boilerplate (methods and references), structured with headings and lists."""
        meta = report_data.get("metadata", {})
        version = meta.get("version", "unknown")
        config = report_data.get("configuration", {}) or {}

        # Detect whether T2w data was actually processed for this subject
        dataset_context = report_data.get("dataset_context", {})
        if "subject_file_counts" in dataset_context:
            has_t2w = int(dataset_context["subject_file_counts"].get("t2w", 0) or 0) > 0
        else:
            anat_counts = HtmlGenerator._count_anatomical_by_modality(
                report_data.get("organized_snapshots", {}).get("anatomical", {})
            )
            has_t2w = anat_counts.get("t2w", 0) > 0

        parts = []

        # Intro paragraph
        intro = (
            "Results included in this manuscript come from preprocessing performed using "
            f"<b>brainana {html.escape(version)}</b>."
        )
        parts.append(f"<p class=\"methods-intro\">{intro}</p>")

        t1w_text = ""
        t2w_text = None
        func_text = ""

        # Anatomical section — built directly to support optional T2w subheadings
        parts.append("<h3 class=\"methods-subtitle\">Anatomical data preprocessing</h3>")
        if isinstance(config, dict):
            t1w_text, t2w_text = HtmlGenerator._build_anat_methods_paragraph(config, has_t2w)
            if has_t2w:
                parts.append("<h4 class=\"methods-subsubtitle\">T1w preprocessing</h4>")
            parts.append(f"<p>{html.escape(t1w_text)}</p>")
            if has_t2w and t2w_text:
                parts.append("<h4 class=\"methods-subsubtitle\">T2w preprocessing</h4>")
                parts.append(f"<p>{html.escape(t2w_text)}</p>")

        # Functional section
        parts.append("<h3 class=\"methods-subtitle\">Functional data preprocessing</h3>")
        if isinstance(config, dict):
            func_text = HtmlGenerator._build_func_methods_paragraph(config)
            parts.append(f"<p>{html.escape(func_text)}</p>")

        # References: only those cited in the methods text above
        methods_body = " ".join([intro, t1w_text, t2w_text or "", func_text])
        refs_list = _cited_references(methods_body)
        parts.append("<h3 class=\"methods-subtitle\">References</h3>")
        items = "".join(f"<li>{html.escape(ref)}</li>" for ref in refs_list)
        parts.append(f"<ul class=\"methods-refs\">{items}</ul>")

        content = "<div class=\"boiler-html methods-structured\">\n" + "\n".join(parts) + "\n</div>"
        return HtmlGenerator.create_section("Methods", "Methods", content)

def generate_qc_report(
    snapshot_dir: Union[str, Path],
    report_path: Union[str, Path],
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
    snapshot_paths: Optional[Dict[str, str]] = None,
    dataset_context: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, str]:
    """Generate comprehensive HTML quality control report."""
    snapshot_dir, report_path = Path(snapshot_dir), Path(report_path)
    
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        # Discover and parse snapshots
        snapshot_data = SnapshotProcessor.discover_and_parse(snapshot_dir, logger, snapshot_paths)
        
        # Organize snapshots by hierarchy
        organized_snapshots = SnapshotProcessor.organize_by_hierarchy(
            snapshot_data['snapshots'], snapshot_dir, report_path, logger
        )
        
        # Build report metadata
        subject_id_match = re.search(r'sub-(\w+)', report_path.name)
        subject_id = subject_id_match.group(1) if subject_id_match else None
        
        from nhp_mri_prep import __version__
        report_data = {
            "metadata": {
                "generation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pipeline_name": "brainana",
                "version": __version__,
                "working_directory": str(report_path.parent),
                "subject_id": subject_id
            },
            "configuration": config,
            "organized_snapshots": organized_snapshots,
            "dataset_context": dataset_context or {},
            "available_entities": snapshot_data['available_entities']
        }
        
        # Generate HTML report
        _generate_html_report(report_data, report_path, logger)
        
        logger.info(f"QC: report generated successfully - {report_path}")
        return {"html_report": str(report_path)}
        
    except Exception as e:
        logger.error(f"QC: report generation failed - {str(e)}")
        raise RuntimeError(f"Quality control report generation failed: {str(e)}")


def _generate_html_report(report_data: Dict[str, Any], report_path: Path, logger: logging.Logger) -> None:
    """Generate HTML report file."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate all sections
    navigation = HtmlGenerator.create_navigation_menu(report_data["organized_snapshots"])
    summary = HtmlGenerator.create_summary_section(report_data, report_data["configuration"])
    anatomical = HtmlGenerator.create_modality_section("Anatomical", report_data["organized_snapshots"]["anatomical"], "Structural")
    functional = HtmlGenerator.create_modality_section("Functional", report_data["organized_snapshots"]["functional"])
    field_mapping = HtmlGenerator.create_modality_section("FieldMapping", report_data["organized_snapshots"]["field_mapping"], "B₀ field mapping")
    about = HtmlGenerator.create_about_section(report_data)
    methods = HtmlGenerator.create_methods_section(report_data)
    
    # Create complete HTML
    html_content = _create_html_template().format(
        NAVIGATION_MENU=navigation,
        SUMMARY_SECTION=summary,
        ANATOMICAL_SECTION=anatomical,
        FUNCTIONAL_SECTION=functional,
        FIELD_MAPPING_SECTION=field_mapping,
        ABOUT_SECTION=about,
        METHODS_SECTION=methods,
        GENERATION_TIME=report_data["metadata"]["generation_time"],
        VERSION=report_data["metadata"]["version"]
    )
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"Output: HTML report written - {report_path}")


def _create_html_template() -> str:
    """Create base HTML template."""
    return """<?xml version="1.0" encoding="utf-8" ?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta name="generator" content="brainana {VERSION}" />
<title>brainana Quality Control Report</title>
<script src="https://code.jquery.com/jquery-3.3.1.slim.min.js" integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo" crossorigin="anonymous"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.1.3/js/bootstrap.min.js" integrity="sha384-ChfqqxuZUCnJSK3+MXmPNIyE6ZbWh2IMqE241rYiqJxyMiZ6OW/JmZQ5stwEULTy" crossorigin="anonymous"></script>
<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.1.3/css/bootstrap.min.css" integrity="sha384-MCw98/SFnGE8fJT3GXwEOngsV7Zt27NXFoaoApmYm81iuXoPkFOJwJ8ERdknLPMO" crossorigin="anonymous">
<style type="text/css">
.sub-report-title {{}}
.run-title {{}}
.sub-report-group {{}}

h1 {{ padding-top: 35px; }}
h2 {{ padding-top: 20px; }}
h3 {{ padding-top: 15px; }}

.elem-desc {{}}
.elem-caption {{
    margin-top: 15px;
    margin-bottom: 0;
}}
.elem-filename {{}}

div.elem-image {{
  width: 100%;
  page-break-before:always;
}}

.elem-image object.svg-reportlet {{
    width: 100%;
    padding-bottom: 5px;
}}

.svg-reportlet {{
    width: 100%;
}}

body {{
    padding: 65px 10px 10px;
}}

.boiler-html {{
    font-family: "Bitstream Charter", "Georgia", Times;
    margin: 20px 25px;
    padding: 10px;
    background-color: #F8F9FA;
}}

.methods-structured .methods-subtitle {{
    font-size: 1.1em;
    font-weight: 600;
    margin-top: 1em;
    margin-bottom: 0.4em;
}}

.methods-structured .methods-subtitle:first-of-type {{
    margin-top: 0;
}}

.methods-structured .methods-subsubtitle {{
    font-size: 1em;
    font-weight: 600;
    margin-top: 0.75em;
    margin-bottom: 0.3em;
}}

.methods-structured .methods-intro {{
    margin-bottom: 0.5em;
}}

.methods-structured .methods-refs {{
    margin: 0.5em 0 1em 1.2em;
    padding-left: 1.5em;
}}

.methods-structured .methods-refs li {{
    margin-bottom: 0.35em;
}}

div#boilerplate pre {{
    margin: 20px 25px;
    padding: 10px;
    background-color: #F8F9FA;
}}

#errors div, #errors p {{
    padding-left: 1em;
}}

.bids-entity {{
    background-color: #ddd;
    padding: 1px 4px;
    border-radius: 2px;
    font-family: monospace;
    font-size: 0.9em;
}}

.dropdown-menu {{
    max-height: 70vh;
    overflow-y: auto;
}}
</style>
</head>
<body>

<nav class="navbar fixed-top navbar-expand-lg navbar-light bg-light">
<div class="collapse navbar-collapse">
    <ul class="navbar-nav">
        {NAVIGATION_MENU}
    </ul>
</div>
</nav>
<noscript>
    <h1 class="text-danger"> The navigation menu uses Javascript. Without it this report might not work as expected </h1>
</noscript>

{SUMMARY_SECTION}
{ANATOMICAL_SECTION}
{FUNCTIONAL_SECTION}
{FIELD_MAPPING_SECTION}
{ABOUT_SECTION}
{METHODS_SECTION}

</body>
</html>"""
