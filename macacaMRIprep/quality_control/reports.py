"""
Quality Control Report Generation

This module generates comprehensive HTML reports summarizing preprocessing results,
including embedded snapshots, processing parameters, and quality metrics.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Union, List, Optional, Tuple
import re

from ..utils.bids import parse_bids_entities, BIDS_ENTITY_ORDER


# Configuration constants
SNAPSHOT_MAPPINGS = {
    'biasCorrection': {'key': 'bias_correction_comparison', 'description': 'Bias field correction'},
    'skullStripping': {'key': 'skullstripping_overlay', 'description': 'Skullstripping'},
    'anat2template': {'key': 'anat2template_registration_overlay', 'description': 'Structural to template registration'},
    'func2anat': {'key': 'func2anat_registration_overlay', 'description': 'Functional to structural registration'},
    'func2template': {'key': 'func2template_registration_overlay', 'description': 'Functional to template registration'},
    'T2w2T1w': {'key': 'T2w2T1w_registration_overlay', 'description': 'T2w to T1w coregistration'},
    'motion': {'key': 'motion_parameters', 'description': 'Motion parameters'},
}

SNAPSHOT_ORDER = [
    'bias_correction_comparison', 'skullstripping_overlay', 'anat2template_registration_overlay', 
    'T2w2T1w_registration_overlay', 'func2anat_registration_overlay', 'func2template_registration_overlay', 'motion_parameters'
]

SNAPSHOT_ORDER_INDEX = {key: index for index, key in enumerate(SNAPSHOT_ORDER)}


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
                        entities = {k: v for k, v in value['entities'].items() if k not in ['sub', 'desc']}
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
            
            snapshots[name] = {
                'path': str(path),
                'entities': entities,
                'modality': SnapshotProcessor._determine_modality(path.name),
                'description': mapping.get('description', ''),
                'snapshot_type': snapshot_type
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
        elif filename.endswith('_bold.png'):
            key_parts.append('bold')
        
        return "_".join(key_parts)
    
    @staticmethod
    def _determine_modality(name: str) -> str:
        """Determine modality from filename."""
        if 'T1w' in name or 'T2w' in name:
            return "anatomical"
        elif 'bold' in name.lower():
            return "functional"
        elif 'fmap' in name.lower():
            return "field_mapping"
        else:
            return "summary"
    
    @staticmethod
    def organize_by_hierarchy(snapshots: Dict[str, Any], snapshot_dir: Path, 
                            report_path: Path, logger: logging.Logger) -> Dict[str, Any]:
        """Organize snapshots by BIDS hierarchy."""
        organized = {"anatomical": {}, "functional": {}, "field_mapping": {}, "summary": {}}
        
        for name, snapshot_info in snapshots.items():
            relative_path = os.path.relpath(snapshot_info['path'], report_path.parent)
            snapshot_data = {
                "path": relative_path,
                "entities": snapshot_info['entities'],
                "description": snapshot_info['description'],
                "snapshot_type": snapshot_info['snapshot_type']
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
                entities_list = BidsEntityProcessor.extract_entities_from_snapshots(organized_snapshots[modality])
                
                if len(entities_list) > 1:  # Create dropdown for multiple items
                    dropdown_items = []
                    for entities in entities_list:
                        display_text = BidsEntityProcessor.create_display_text(entities)
                        # Use the same ID format as the headers (section_prefix + clean_header_id)
                        section_prefix = "anatomical" if modality == "anatomical" else "functional"
                        nav_id = f"{section_prefix}-{BidsEntityProcessor.clean_header_id(display_text)}"
                        dropdown_items.append(f'<a class="dropdown-item" href="#{nav_id}">{display_text}</a>')
                    
                    dropdown_content = '\n'.join(dropdown_items)
                    nav_items.append(f'''<li class="nav-item dropdown">
<a class="nav-link dropdown-toggle" id="navbar{modality.title()}" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false" href="#">{title}</a>
<div class="dropdown-menu" aria-labelledby="navbar{modality.title()}">
{dropdown_content}
</div>
</li>''')
                else:  # Single item, no dropdown needed
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
        
        # Use original counts from dataset_context if available
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
            # Handle missing data gracefully
            t1w_count = "N/A"
            t2w_count = "N/A"
            func_count = "N/A"
        
        # Field mapping count from snapshots (not tracked in job counts)
        fmap_count = HtmlGenerator._count_unique_images(report_data["organized_snapshots"]["field_mapping"])
        
        # Build structural images description
        structural_desc = []
        if t1w_count and t1w_count != "N/A" and t1w_count > 0:
            structural_desc.append(f"{t1w_count} T1w")
        if t2w_count and t2w_count != "N/A" and t2w_count > 0:
            structural_desc.append(f"{t2w_count} T2w")
        
        if structural_desc:
            structural_text = ", ".join(structural_desc)
        elif t1w_count == "N/A":
            structural_text = "N/A"
        else:
            structural_text = "0"
        
        content = f'''<div class="boiler-html">
<p><strong>Configuration:</strong> For detailed processing parameters and configuration settings, 
please refer to the macacaMRIprep configuration files in your preprocessing directory.</p>
</div>
<ul class="elem-desc">
<li>Subject ID: {subject_id}</li>
<li>Structural images: {structural_text}</li>
<li>Functional images: {func_count}</li>
<li>Field mapping images: {fmap_count}</li>
<li>Standard output spaces: {config.get("output_spaces", "NMT2Sym")}</li>
<li>Non-standard output spaces: </li>
<li>FreeSurfer reconstruction: Not applicable</li>
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
        
        # Group snapshots by BIDS entities
        snapshot_groups = HtmlGenerator._group_snapshots_by_entities(data)
        
        for group_key, snapshots in snapshot_groups.items():
            if group_key:
                header_id = f"{section_prefix}-{BidsEntityProcessor.clean_header_id(group_key)}"
                html_parts.append(f'<h2 class="sub-report-group" id="{header_id}">{group_key}</h2>')
            
            for snapshot_data in snapshots:
                snapshot_id = f"{section_prefix}-{snapshot_data['filename'].replace('.', '-')}"
                title = snapshot_data.get('description', snapshot_data['filename'])
                
                html_parts.append(f'''<div id="{snapshot_id}">
<h3 class="run-title">{title}</h3>
<img class="svg-reportlet" src="{snapshot_data["path"]}" style="width: 100%" />
</div>
<div class="elem-filename">
    Get figure file: <a href="{snapshot_data["path"]}" target="_blank">{snapshot_data["filename"]}</a>
</div>''')
        
        return '\n'.join(html_parts)
    
    @staticmethod
    def _group_snapshots_by_entities(data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Group snapshots by BIDS entities."""
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
                            'snapshot_type': value.get('snapshot_type', '')
                        })
                    else:
                        collect_snapshots(value)
        
        collect_snapshots(data)
        
        # Group by entity combinations, with special handling for T1w/T2w separation
        groups = {}
        for snapshot in all_snapshots:
            entities = {k: v for k, v in snapshot['entities'].items() if k not in ['sub', 'desc']}
            base_group_key = BidsEntityProcessor.create_display_text(entities) or 'ungrouped'
            
            # For anatomical snapshots, separate T1w and T2w into different groups
            filename = snapshot.get('filename', '')
            # Use entities to determine modality - more reliable than filename parsing
            entities = snapshot.get('entities', {})
            if entities.get('suffix') == 'T1w' or (entities.get('suffix') != 'T2w' and filename.endswith('_T1w.png')):
                group_key = f"{base_group_key} (T1w)"
            elif entities.get('suffix') == 'T2w' or filename.endswith('_T2w.png'):
                group_key = f"{base_group_key} (T2w)"
            else:
                group_key = base_group_key
            
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(snapshot)
        
        # Sort snapshots within groups
        for group_key in groups:
            def sort_key(snapshot):
                base_order = SNAPSHOT_ORDER_INDEX.get(snapshot.get('snapshot_type', ''), 999)
                filename = snapshot.get('filename', '')
                
                # For anatomical snapshots, ensure T1w comes before T2w
                # Also ensure that within the same snapshot type, T1w comes before T2w
                modality_order = 0
                # Use more specific logic - check file ending for modality
                if filename.endswith('_T1w.png') or (snapshot.get('entities', {}).get('suffix') == 'T1w'):
                    modality_order = 0  # T1w first
                elif filename.endswith('_T2w.png') or (snapshot.get('entities', {}).get('suffix') == 'T2w'):
                    modality_order = 1  # T2w second
                
                return (base_order, modality_order, filename)
            
            groups[group_key].sort(key=sort_key)
        
        # Sort groups so that T1w comes before T2w
        def group_sort_key(group_item):
            group_name = group_item[0]
            if '(T1w)' in group_name:
                return (0, group_name)
            elif '(T2w)' in group_name:
                return (1, group_name)
            else:
                return (2, group_name)
        
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
    def create_methods_section(report_data: Dict[str, Any]) -> str:
        """Create methods section."""
        content = '''<div class="boiler-html">
<p>This report was generated using macacaMRIprep, a preprocessing pipeline for macaque functional MRI data.</p>
<p><strong>Configuration Details:</strong> Complete processing parameters and configuration settings are available in the macacaMRIprep configuration files located in your preprocessing output directory.</p>
<p><strong>Source Code:</strong> The macacaMRIprep pipeline source code and documentation are available at the project repository.</p>
</div>'''
        return HtmlGenerator.create_section("Methods", "Methods", content)

def generate_qc_report(
    snapshot_dir: Union[str, Path],
    report_path: Union[str, Path],
    config: Dict[str, Any],
    logger: logging.Logger,
    snapshot_paths: Optional[Dict[str, str]] = None,
    dataset_context: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, str]:
    """Generate comprehensive HTML quality control report."""
    snapshot_dir, report_path = Path(snapshot_dir), Path(report_path)
    
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
        
        report_data = {
            "metadata": {
                "generation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pipeline_name": "macacaMRIprep",
                "version": "1.0.0",
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
        PIPELINE_NAME=report_data["metadata"]["pipeline_name"],
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
<meta name="generator" content="macacaMRIprep {VERSION}" />
<title>macacaMRIprep Quality Control Report</title>
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
