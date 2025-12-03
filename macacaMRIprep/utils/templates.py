"""
Template management utilities for macacaMRIprep.

This module provides functionality to manage and resolve template specifications
from a predefined pool of templates.
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Optional, Set

from .logger import get_logger

logger = get_logger(__name__)


class TemplateManager:
    """Manages template discovery and resolution."""
    
    def __init__(self, template_dir: Optional[str] = None):
        """Initialize template manager."""
        self.template_dir = self._get_template_directory(template_dir)
        self._templates = self._discover_templates()
        
        # Default values for template resolution
        self.defaults = {
            'template': 'NMT2Sym',
            'res': 'res-1', 
            'desc': 'brain'
        }
    
    def _get_template_directory(self, custom_dir: Optional[str]) -> Path:
        """Get the template directory path."""
        if custom_dir:
            return Path(custom_dir)
        
        # Templates are always in project_root/templatezoo
        project_root = Path(__file__).parent.parent.parent  # macacaMRIprep/utils/templates.py -> macacaMRIprep -> banana
        template_dir = project_root / 'templatezoo'
        
        if not template_dir.exists():
            raise FileNotFoundError(f"Template directory not found: {template_dir}")
        
        logger.debug(f"System: template directory - {template_dir}")
        return template_dir
    
    def _discover_templates(self) -> Dict[str, Dict[str, str]]:
        """Discover available templates.
        
        Parses: tpl-{name}_res-{resolution}[_{components}]*_T1w[_{desc}].nii.gz
        Returns: Dict mapping template_name -> {spec: file_path}
        """
        templates = defaultdict(dict)
        
        for template_file in self.template_dir.glob('*.nii.gz'):
            parsed = self._parse_template_filename(template_file)
            if parsed:
                template_name, components, spec = parsed
                templates[template_name][spec] = str(template_file)
                # Also store the parsed components for later use
                templates[template_name][f"_components_{spec}"] = components
                logger.debug(f"Data: found template - {template_name} -> {spec} -> {template_file.name}")
        
        return dict(templates)
    
    def _parse_template_filename(self, template_file: Path) -> Optional[tuple[str, Dict[str, str], str]]:
        """Parse a template filename into components.
        
        Returns: (template_name, components_dict, spec_string)
        """
        filename = template_file.name
        
        # Match: tpl-{name}_res-{resolution}[_{other}]*_T1w[_{desc}].nii.gz
        if not filename.startswith('tpl-') or not filename.endswith('.nii.gz'):
            return None
            
        # Remove tpl- prefix and .nii.gz suffix
        name_part = filename.replace('tpl-', '').replace('.nii.gz', '')
        
        # Split by underscore
        parts = name_part.split('_')
        
        # Find T1w position (required)
        if 'T1w' not in parts:
            return None
            
        t1w_idx = parts.index('T1w')
        
        # Everything before T1w contains template name and components
        # Everything after T1w is description
        before_t1w = parts[:t1w_idx]
        after_t1w = parts[t1w_idx + 1:]
        
        if not before_t1w:
            return None
            
        # First part is template name
        template_name = before_t1w[0]
        
        # Parse components
        components = {}
        for part in before_t1w[1:]:
            if '-' in part:
                key, value = part.split('-', 1)
                components[key] = f"{key}-{value}"
            else:
                # Handle components without '-' (shouldn't happen normally)
                components[part] = part
        
        # Add description if present
        if after_t1w:
            components['desc'] = '_'.join(after_t1w)
        
        # Create spec string: template_name:component1:component2:...
        spec_parts = [template_name]
        
        # Add components in a consistent order
        component_order = ['res', 'hemi', 'desc']  # Define preferred order
        for key in component_order:
            if key in components:
                spec_parts.append(components[key])
        
        # Add any remaining components not in the standard order
        for key, value in sorted(components.items()):
            if key not in component_order:
                spec_parts.append(value)
        
        spec = ':'.join(spec_parts)
        
        return template_name, components, spec
    
    def _parse_template_spec(self, template_spec: str) -> tuple[str, Dict[str, str]]:
        """Parse a user-provided template specification into components.
        
        Args:
            template_spec: User spec like "NMT2Sym:res-1:brain"
            
        Returns:
            (template_name, components_dict)
        """
        spec_parts = template_spec.split(':')
        if not spec_parts:
            raise ValueError(f"Invalid template spec: '{template_spec}'")
        
        template_name = spec_parts[0]
        components = {}
        
        for part in spec_parts[1:]:
            if '-' in part:
                # Handle res-1, hemi-lh, etc.
                key, value = part.split('-', 1)
                components[key] = f"{key}-{value}"
            else:
                # Handle desc components like 'brain', 'brainWoCerebellumBrainstem'
                components['desc'] = part
        
        return template_name, components
    
    def list_available_templates(self) -> List[str]:
        """List all available template specifications."""
        all_specs = []
        for template_name, specs in self._templates.items():
            # Filter out internal _components_ entries
            filtered_specs = [spec for spec in specs.keys() if not spec.startswith('_components_')]
            all_specs.extend(filtered_specs)
        return sorted(all_specs)
    
    def list_templates(self) -> Dict[str, List[str]]:
        """List templates grouped by name."""
        result = {}
        for name, specs in self._templates.items():
            # Filter out internal _components_ entries
            filtered_specs = [spec for spec in specs.keys() if not spec.startswith('_components_')]
            result[name] = sorted(filtered_specs)
        return result
    
    def resolve_template(self, template_spec: Optional[str] = None) -> str:
        """Resolve template specification to file path.
        
        Args:
            template_spec: Specification like:
                          "NMT2Sym" 
                          "NMT2Sym:res-1"
                          "NMT2Sym:res-1:brain"
                          "NMT2Sym:hemi-lh:res-1:brain"
                          If None, uses default "NMT2Sym:res-1:brain"
        
        Returns:
            Absolute path to template file
        
        Raises:
            ValueError: If specification is invalid or not found
        """
        # Use default if none provided
        if template_spec is None:
            template_spec = f"{self.defaults['template']}:{self.defaults['res']}:{self.defaults['desc']}"
        
        logger.debug(f"System: resolving template spec - {template_spec}")
        
        # Parse the requested specification using the same logic as file parsing
        template_name, requested_components = self._parse_template_spec(template_spec)
        
        # Check if template name exists
        if template_name not in self._templates:
            available_names = sorted(self._templates.keys())
            raise ValueError(f"Template '{template_name}' not found. Available templates: {available_names}")
        
        # Get all specifications for this template
        available_specs = {k: v for k, v in self._templates[template_name].items() 
                          if not k.startswith('_components_')}
        
        # Find best match using component-based scoring algorithm
        best_match = self._find_best_match_by_components(template_name, requested_components, available_specs)
        
        if best_match:
            logger.debug(f"System: resolved template spec '{template_spec}' to best match '{best_match}'")
            return available_specs[best_match]
        
        # If no match found, list available options
        available_specs_list = sorted(available_specs.keys())
        raise ValueError(f"No suitable match found for '{template_spec}'. Available options for {template_name}: {available_specs_list}")
    
    def _find_best_match_by_components(self, template_name: str, requested_components: Dict[str, str], 
                                     available_specs: Dict[str, str]) -> Optional[str]:
        """Find the best matching template specification using component-based logic."""
        
        valid_candidates = []
        
        for spec, _ in available_specs.items():
            # Get the stored components for this spec
            components_key = f"_components_{spec}"
            if components_key not in self._templates[template_name]:
                continue
                
            spec_components = self._templates[template_name][components_key]
            
            # Check if this candidate meets ALL requested components
            if self._meets_all_requirements(requested_components, spec_components):
                score = self._calculate_component_score(requested_components, spec_components)
                valid_candidates.append((score, spec))
                logger.debug(f"Data: valid candidate {spec} - components={spec_components}, score={score}")
            else:
                logger.debug(f"Data: rejected candidate {spec} - missing required components")
        
        if not valid_candidates:
            return None
        
        # Sort by score (highest first) and return the best match
        valid_candidates.sort(reverse=True, key=lambda x: x[0])
        return valid_candidates[0][1]
    
    def _meets_all_requirements(self, requested: Dict[str, str], available: Dict[str, str]) -> bool:
        """Check if available components satisfy all requested components."""
        for key, value in requested.items():
            if key not in available or available[key] != value:
                return False
        return True
    
    def _calculate_component_score(self, requested: Dict[str, str], available: Dict[str, str]) -> int:
        """Calculate matching score between requested and available components."""
        score = 0
        
        # Base score for exact matches (already guaranteed by _meets_all_requirements)
        score += len(requested) * 100
        
        # Bonus for having default components when not explicitly specified
        # If user didn't specify a resolution, prefer res-1
        if 'res' not in requested and 'res' in available and available['res'] == 'res-1':
            score += 20
        
        # If user didn't specify a description, prefer brain
        if 'desc' not in requested and 'desc' in available and available['desc'] == 'brain':
            score += 20
        
        # Among candidates with same defaults, prefer simpler matches (fewer extra components)
        extra_components = len(available) - len(requested)
        score += max(0, 10 - extra_components)  # Bonus for fewer extra components
        
        return score
    
    def validate_template_spec(self, template_spec: str) -> bool:
        """Check if template specification exists."""
        try:
            self.resolve_template(template_spec)
            return True
        except ValueError:
            return False
    
    def print_available_templates(self):
        """Print available templates in a user-friendly format."""
        templates = self.list_templates()
        
        if not templates:
            print("No templates found.")
            return
        
        print("Available templates:")
        print("-" * 50)
        
        for template_name, specs in templates.items():
            print(f"{template_name}:")
            for spec in specs:
                print(f"  - {spec}")
        
        print("\nUsage: --output-space TEMPLATE_SPEC")
        print("Examples:")
        print("  --output-space NMT2Sym")
        print("  --output-space NMT2Sym:res-1")
        print("  --output-space NMT2Sym:res-1:brain")
        print("  --output-space NMT2Sym:hemi-lh:res-1:brain")


# Global template manager instance
_template_manager = None


def get_template_manager(template_dir: Optional[str] = None) -> TemplateManager:
    """Get or create the global template manager instance."""
    global _template_manager
    if _template_manager is None or template_dir is not None:
        _template_manager = TemplateManager(template_dir)
    return _template_manager


# Wrapper functions for backward compatibility
def resolve_template(template_spec: Optional[str] = None) -> str:
    """Resolve template specification to file path.
    
    Wrapper function that uses the global TemplateManager instance.
    
    Args:
        template_spec: Specification like "NMT2Sym:res-1:brain"
                      If None, uses default "NMT2Sym:res-1:brain"
    
    Returns:
        Absolute path to template file
    
    Raises:
        ValueError: If specification is invalid or not found
    """
    return get_template_manager().resolve_template(template_spec)


def resolve_template_file(template_spec: Optional[str] = None) -> str:
    """Alias for resolve_template for backward compatibility."""
    return resolve_template(template_spec)


def list_available_templates() -> List[str]:
    """List all available template specifications.
    
    Wrapper function that uses the global TemplateManager instance.
    
    Returns:
        List of available template specifications
    """
    return get_template_manager().list_available_templates()


def validate_template_spec(template_spec: str) -> bool:
    """Check if template specification exists.
    
    Wrapper function that uses the global TemplateManager instance.
    
    Args:
        template_spec: Template specification to validate
    
    Returns:
        True if specification exists, False otherwise
    """
    return get_template_manager().validate_template_spec(template_spec)


def print_available_templates():
    """Print available templates in a user-friendly format.
    
    Wrapper function that uses the global TemplateManager instance.
    """
    return get_template_manager().print_available_templates() 