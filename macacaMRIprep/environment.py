"""
Environment and dependency checking for macacaMRIprep.

This module provides comprehensive system environment validation including:
- Python package dependencies with version checking
- External software tool availability
- Environment variable validation
- System resource assessment
- CUDA/GPU availability checking
"""

import os
import sys
import re
import shutil
import logging
import subprocess
import importlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from packaging import version

from . import __version__

# Read dependencies from pyproject.toml to avoid duplication
def _load_dependencies_from_pyproject() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Load required and optional dependencies from pyproject.toml.
    
    Returns:
        Tuple of (required_packages, optional_packages) dictionaries
        with package names as keys and minimum versions as values.
    
    Raises:
        FileNotFoundError: If pyproject.toml is not found
        ValueError: If pyproject.toml cannot be parsed
    """
    required = {}
    optional = {}
    
    # Use same pattern as info.py for reading pyproject.toml
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")
    
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    
    # Parse dependencies from pyproject.toml
    dependencies = data.get("project", {}).get("dependencies", [])
    if not dependencies:
        raise ValueError("No dependencies found in pyproject.toml")
    
    for dep in dependencies:
        # Skip conditional dependencies (e.g., "tomli>=2.0.0; python_version<'3.11'")
        if ";" in dep:
            continue
        
        # Parse package name and version requirement
        # Format: "package>=version" or "package==version" or "package~=version"
        match = re.match(r"([a-zA-Z0-9_-]+)\s*(?:>=|==|~=)([\d.]+)", dep)
        if match:
            pkg_name = match.group(1).lower()
            min_version = match.group(2)
            required[pkg_name] = min_version
    
    # Optional dependencies from optional-dependencies groups
    optional_deps = data.get("project", {}).get("optional-dependencies", {})
    for group_name, deps in optional_deps.items():
        for dep in deps:
            if ";" in dep:
                continue
            match = re.match(r"([a-zA-Z0-9_-]+)\s*(?:>=|==|~=)([\d.]+)", dep)
            if match:
                pkg_name = match.group(1).lower()
                min_version = match.group(2)
                optional[pkg_name] = min_version
    
    return required, optional

# Load dependencies from pyproject.toml
REQUIRED_PYTHON_PACKAGES, OPTIONAL_PYTHON_PACKAGES = _load_dependencies_from_pyproject()

# Define required external tools with minimum version requirements
REQUIRED_EXTERNAL_TOOLS = {
    'fsl': {
        'env_var': 'FSLDIR',
        'version_cmd': 'flirt -version',
        'required_version': '6.0'
    },
    'ants': {
        'env_var': 'ANTSPATH',
        'version_cmd': 'antsRegistration --version',
        'required_version': '2.3'
    },
    'afni': {
        'env_var': 'AFNIPATH',
        'version_cmd': 'afni_vcheck',
        'required_version': '24.0'
    },
    'freesurfer': {
        'env_var': 'FREESURFER_HOME',
        'version_cmd': 'mri_info --version',
        'required_version': '7.4.1'
    }
}

def get_logger() -> logging.Logger:
    """Get logger for environment checking."""
    return logging.getLogger(__name__)


def check_python_version(min_version: str = "3.11") -> Tuple[bool, str]:
    """Check Python version requirement.
    
    Args:
        min_version: Minimum required Python version (default: 3.11)
        
    Returns:
        Tuple of (is_compatible, version_info)
    """
    current_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    is_compatible = version.parse(current_version) >= version.parse(min_version)
    
    return is_compatible, current_version


# Mapping from package names (as in pyproject.toml) to their import names
PACKAGE_IMPORT_MAP = {
    'pillow': 'PIL',  # Pillow package is imported as PIL
    'pyyaml': 'yaml',  # pyyaml package is imported as yaml
    'simpleitk': 'SimpleITK',  # SimpleITK package is imported as SimpleITK
    'scikit-image': 'skimage',  # scikit-image package is imported as skimage
    'pybids': 'bids',  # pybids package is imported as bids
}

def check_package_version(package_name: str, min_version: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check if a Python package meets version requirements.
    
    Args:
        package_name: Name of the package (as in pyproject.toml, lowercase)
        min_version: Minimum required version
        
    Returns:
        Tuple of (is_available, installed_version, error_message)
    """
    # Map package name to import name if needed
    import_name = PACKAGE_IMPORT_MAP.get(package_name.lower(), package_name)
    
    try:
        module = importlib.import_module(import_name)
        
        # Try to get version from different common attributes
        installed_version = None
        for attr in ['__version__', 'VERSION', 'version']:
            if hasattr(module, attr):
                installed_version = getattr(module, attr)
                break
        
        if installed_version is None:
            return True, "unknown", None  # Package exists but version unknown
        
        # Handle version strings that might have extra info
        installed_version_clean = installed_version.split('+')[0].split('-')[0]
        
        is_compatible = version.parse(installed_version_clean) >= version.parse(min_version)
        
        if not is_compatible:
            error_msg = f"Version {installed_version} < required {min_version}"
            return False, installed_version, error_msg
        
        return True, installed_version, None
        
    except ImportError:
        return False, None, f"Package '{package_name}' not found"
    except Exception as e:
        return False, None, f"Error checking package: {str(e)}"


def check_external_command(command: str) -> Tuple[bool, Optional[str]]:
    """Check if an external command is available.
    
    Args:
        command: Command to check
        
    Returns:
        Tuple of (is_available, path_to_command)
    """
    command_path = shutil.which(command)
    return command_path is not None, command_path


def get_command_version(version_cmd: str) -> Optional[str]:
    """Get version information from a command.
    
    Args:
        version_cmd: Command to run for version info
        
    Returns:
        Version string or None if unavailable
    """
    try:
        result = subprocess.run(
            version_cmd.split(),
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Some commands (like afni_vcheck) return non-zero exit codes but still produce valid output
        # Check if we have any output (stdout or stderr)
        output = (result.stdout + result.stderr).strip()
        if output:
            return output
        
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass
    
    return None


def extract_version_number(version_string: str) -> Optional[str]:
    """Extract version number from version string output.
    
    Handles various formats like:
    - "mri_info freesurfer 7.4.1"
    - "6.0.5.2"
    - "ANTs Version: 2.5.1.post13-g4a0fb48" -> "2.5.1"
    - "Version ID = AFNI_24.0.08" -> "24.0.08"
    
    Args:
        version_string: Raw version output from command
        
    Returns:
        Extracted version number (e.g., "7.4.1") or None
    """
    if not version_string:
        return None
    
    # Try multiple patterns to handle different formats
    
    # Pattern 1: Standard version pattern with word boundaries (handles most cases)
    # Matches: "2.5.1", "24.0.08", "7.4.1"
    version_pattern1 = r'\b(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)\b'
    matches1 = re.findall(version_pattern1, version_string)
    
    # Pattern 2: Version after underscore or prefix (for AFNI_24.0.08 format)
    # Matches: "AFNI_24.0.08" -> "24.0.08"
    version_pattern2 = r'[A-Z_]+(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)'
    matches2 = re.findall(version_pattern2, version_string)
    
    # Pattern 3: Version after colon or equals (for "Version: 2.5.1" format)
    # Matches: "ANTs Version: 2.5.1" -> "2.5.1"
    version_pattern3 = r'[:=]\s*(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)'
    matches3 = re.findall(version_pattern3, version_string)
    
    # Combine all matches and prefer longer/more complete versions
    all_matches = matches1 + matches2 + matches3
    
    if all_matches:
        # Sort by length (longer = more complete) and return the longest
        # This handles cases where multiple patterns match
        all_matches_sorted = sorted(all_matches, key=lambda x: (len(x), x), reverse=True)
        return all_matches_sorted[0]
    
    return None


def check_external_tool(tool_name: str, tool_config: Dict[str, Any]) -> Dict[str, Any]:
    """Check availability and configuration of an external tool.
    
    Args:
        tool_name: Name of the tool
        tool_config: Configuration dictionary for the tool
        
    Returns:
        Dictionary with tool check results
    """
    logger = get_logger()
    
    result = {
        'name': tool_name,
        'available': False,
        'commands_found': [],
        'commands_missing': [],
        'env_var_set': False,
        'env_var_path': None,
        'version_info': None,
        'version_matches': False,
        'installed_version': None,
        'required_version': None,
        'errors': []
    }
    
    # Check environment variable
    env_var = tool_config.get('env_var')
    if env_var:
        env_path = os.environ.get(env_var)
        result['env_var_set'] = env_path is not None
        result['env_var_path'] = env_path
    
    # Check required commands
    commands = tool_config.get('commands', [])
    for cmd in commands:
        is_available, cmd_path = check_external_command(cmd)
        if is_available:
            result['commands_found'].append({'command': cmd, 'path': cmd_path})
        else:
            result['commands_missing'].append(cmd)
            result['errors'].append(f"Command '{cmd}' not found in PATH")
    
    # Check version if available
    version_cmd = tool_config.get('version_cmd')
    required_version = tool_config.get('required_version')
    result['required_version'] = required_version
    
    # Extract version command name once if it exists
    version_cmd_name = None
    if version_cmd:
        version_cmd_name = version_cmd.split()[0]
        
        # Check if version command is available
        is_available, cmd_path = check_external_command(version_cmd_name)
        if is_available:
            # Add to commands_found if not already there
            if not any(c['command'] == version_cmd_name for c in result['commands_found']):
                result['commands_found'].append({'command': version_cmd_name, 'path': cmd_path})
    
    # Check version if available
    if version_cmd:
        # Check version if we have commands found, or if no commands are required
        if len(result['commands_found']) > 0 or len(commands) == 0:
            version_info = get_command_version(version_cmd)
            if version_info:
                result['version_info'] = version_info
                # Extract and compare version
                installed_version = extract_version_number(version_info)
                if installed_version:
                    result['installed_version'] = installed_version
                    if required_version:
                        # Check for minimum version requirement (>=)
                        try:
                            result['version_matches'] = version.parse(installed_version) >= version.parse(required_version)
                            if not result['version_matches']:
                                result['errors'].append(
                                    f"Version too old: installed {installed_version} < required minimum {required_version}"
                                )
                        except Exception as e:
                            result['errors'].append(f"Error comparing versions: {str(e)}")
                    else:
                        # No version requirement, consider it a match
                        result['version_matches'] = True
                else:
                    result['errors'].append(f"Could not extract version number from: {version_info}")
            else:
                if not version_cmd_name or not any(c['command'] == version_cmd_name for c in result['commands_found']):
                    result['errors'].append(f"Version command '{version_cmd_name}' not found in PATH")
                else:
                    result['errors'].append(f"Could not get version info using: {version_cmd}")
    
    # Tool is available if:
    # 1. All required commands are found (if commands are specified), OR
    # 2. Version command is available and version can be checked (if no commands specified), OR
    # 3. Env var is set and version can be checked (if no commands and no version_cmd)
    # AND version matches if required
    if len(commands) > 0:
        # If commands are specified, check if they're found
        # Commands in PATH are sufficient even if env var is not set
        commands_ok = len(result['commands_missing']) == 0
    elif version_cmd and version_cmd_name:
        # No commands specified, but version_cmd exists - check if version command is available
        commands_ok = any(c['command'] == version_cmd_name for c in result['commands_found']) and result['version_info'] is not None
    else:
        # No commands and no version_cmd - check env_var and version instead
        commands_ok = result['env_var_set'] and result['version_info'] is not None
    
    # Version must match if required
    version_ok = result['required_version'] is None or result['version_matches']
    
    # Tool is available if commands are OK and version is OK
    # Note: env_var not being set is a warning, not a blocker if commands/version_cmd are found
    result['available'] = commands_ok and version_ok
    
    # Only add env var error if tool is not available and env var is required
    if not result['available'] and not result['env_var_set'] and env_var:
        # Check if commands/version_cmd are also missing - if so, env var might be the issue
        if len(result['commands_found']) == 0 and (not version_cmd or not result['version_info']):
            result['errors'].append(f"Environment variable {env_var} not set and tool not found in PATH")
    
    # If env var is not set but tool is available via commands, add a warning (not error)
    if not result['env_var_set'] and result['available'] and env_var:
        logger.warning(f"System: {tool_name} available via PATH but environment variable {env_var} not set")
    
    logger.debug(f"System: tool check for {tool_name} - {'✓' if result['available'] else '✗'}")
    
    return result


def check_system_resources() -> Dict[str, Any]:
    """Check system resources (memory, disk, CPU).
    
    Returns:
        Dictionary with system resource information
    """
    result = {
        'memory': {},
        'disk': {},
        'cpu': {},
        'gpu': {}
    }
    
    try:
        # Try to use psutil if available
        psutil = importlib.import_module('psutil')
        
        # Memory information
        memory = psutil.virtual_memory()
        result['memory'] = {
            'total_gb': round(memory.total / (1024**3), 2),
            'available_gb': round(memory.available / (1024**3), 2),
            'percent_used': memory.percent
        }
        
        # Disk information (working directory)
        disk = psutil.disk_usage('.')
        result['disk'] = {
            'total_gb': round(disk.total / (1024**3), 2),
            'free_gb': round(disk.free / (1024**3), 2),
            'percent_used': round((disk.used / disk.total) * 100, 1)
        }
        
        # CPU information
        result['cpu'] = {
            'count': psutil.cpu_count(),
            'count_logical': psutil.cpu_count(logical=True),
            'percent_usage': psutil.cpu_percent(interval=1)
        }
        
    except ImportError:
        # Fallback without psutil
        result['memory'] = {'note': 'psutil not available - cannot check memory'}
        result['disk'] = {'note': 'psutil not available - cannot check disk'}
        result['cpu'] = {'note': 'psutil not available - cannot check CPU'}
    
    # Check GPU/CUDA availability
    try:
        # Try to check CUDA
        result_cuda = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        
        if result_cuda.returncode == 0:
            gpu_info = []
            for line in result_cuda.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split(', ')
                    if len(parts) >= 3:
                        gpu_info.append({
                            'name': parts[0],
                            'memory_total_mb': int(parts[1]),
                            'memory_free_mb': int(parts[2])
                        })
            result['gpu'] = {'cuda_available': True, 'devices': gpu_info}
        else:
            result['gpu'] = {'cuda_available': False, 'note': 'nvidia-smi not available'}
            
    except (subprocess.SubprocessError, FileNotFoundError):
        result['gpu'] = {'cuda_available': False, 'note': 'CUDA/nvidia-smi not found'}
    
    return result


def check_dependencies(
    include_optional: bool = True,
    logger: Optional[logging.Logger] = None
) -> Dict[str, Any]:
    """Check all Python package dependencies.
    
    Args:
        include_optional: Whether to check optional packages
        logger: Logger instance
        
    Returns:
        Dictionary with dependency check results
    """
    if logger is None:
        logger = get_logger()
    
    result = {
        'python': {},
        'required_packages': {},
        'optional_packages': {},
        'missing_required': [],
        'missing_optional': [],
        'errors': []
    }
    
    # Check Python version
    is_compatible, py_version = check_python_version()
    result['python'] = {
        'version': py_version,
        'compatible': is_compatible
    }
    
    if not is_compatible:
        min_py_version = "3.11"  # Match pyproject.toml requires-python
        result['errors'].append(f"Python version {py_version} < required {min_py_version}")
        logger.error(f"System: incompatible Python version - {py_version} < {min_py_version}")
    
    # Check required packages
    for pkg_name, min_version in REQUIRED_PYTHON_PACKAGES.items():
        is_available, installed_version, error_msg = check_package_version(pkg_name, min_version)
        
        result['required_packages'][pkg_name] = {
            'required_version': min_version,
            'installed_version': installed_version,
            'compatible': is_available,
            'error': error_msg
        }
        
        if not is_available:
            result['missing_required'].append(pkg_name)
            if error_msg:
                result['errors'].append(f"Required package issue: {pkg_name} - {error_msg}")
                logger.error(f"System: required package missing - {pkg_name} (>= {min_version})")
                print(f"Required package missing: {pkg_name} (>= {min_version})")
        else:
            logger.debug(f"System: required package OK - {pkg_name} {installed_version}")
    
    # Check optional packages
    if include_optional:
        for pkg_name, min_version in OPTIONAL_PYTHON_PACKAGES.items():
            is_available, installed_version, error_msg = check_package_version(pkg_name, min_version)
            
            result['optional_packages'][pkg_name] = {
                'required_version': min_version,
                'installed_version': installed_version,
                'compatible': is_available,
                'error': error_msg
            }
            
            if not is_available:
                result['missing_optional'].append(pkg_name)
                if error_msg:
                    logger.debug(f"System: optional package missing - {pkg_name} - {error_msg}")
            else:
                logger.debug(f"System: optional package OK - {pkg_name} {installed_version}")
    
    return result


def check_environment(
    logger: Optional[logging.Logger] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Perform comprehensive environment check.
    
    Args:
        logger: Logger instance
        config: Configuration dictionary (optional)
        
    Returns:
        Dictionary with environment check results
    """
    if logger is None:
        logger = get_logger()
    
    logger.info("System: starting environment check")
    
    result = {
        'dependencies': {},
        'external_tools': {},
        'system_resources': {},
        'summary': {
            'all_dependencies_ok': True,
            'external_tools_ok': True,
            'overall_status': 'unknown',
            'critical_issues': [],
            'warnings': []
        }
    }
    
    # Check dependencies
    result['dependencies'] = check_dependencies(logger=logger)
    if result['dependencies']['missing_required']:
        result['summary']['all_dependencies_ok'] = False
        result['summary']['critical_issues'].append("Missing required Python packages")
    
    # Check external tools
    for tool_name, tool_config in REQUIRED_EXTERNAL_TOOLS.items():
        tool_result = check_external_tool(tool_name, tool_config)
        result['external_tools'][tool_name] = tool_result
        
        if not tool_result['available']:
            result['summary']['external_tools_ok'] = False
            result['summary']['critical_issues'].append(f"External tool not available: {tool_name}")
            logger.error(f"System: external tool not available - {tool_name}")
            print(f"External tool not available: {tool_name}")
    
    # Check system resources
    result['system_resources'] = check_system_resources()
    
    # ---- GPU check for skullstripping ----
    if config is not None:
        # Check if either anat or func skullstripping is enabled and using fastSurferCNN or macacaMRINN
        anat_ss = config.get('anat', {}).get('skullstripping_segmentation', {})
        func_ss = config.get('func', {}).get('skullstripping', {})
        anat_method = anat_ss.get('method', '').lower() if anat_ss.get('enabled', False) else None
        func_method = func_ss.get('method', '').lower() if func_ss.get('enabled', False) else None
        
        anat_fscnn = anat_method == 'fastsurfercnn'
        func_fscnn = func_method == 'fastsurfercnn'
        anat_mrin = anat_method == 'macacamrinn'
        func_mrin = func_method == 'macacamrinn'
        
        # Check GPU availability for GPU-accelerated skullstripping methods
        gpu_info = result['system_resources'].get('gpu', {})
        cuda_available = gpu_info.get('cuda_available', False)
        
        if (anat_fscnn or func_fscnn) and not cuda_available:
            modalities = []
            if anat_fscnn:
                modalities.append('anat')
            if func_fscnn:
                modalities.append('func')
            warn_msg = (
                f"GPU (CUDA) not available, but skullstripping with FastSurferCNN is enabled for "
                f"{' and '.join(modalities)}. This will be very slow on CPU."
            )
            result['summary']['warnings'].append(warn_msg)
            logger.warning(warn_msg)
        
        if (anat_mrin or func_mrin) and not cuda_available:
            modalities = []
            if anat_mrin:
                modalities.append('anat')
            if func_mrin:
                modalities.append('func')
            warn_msg = (
                f"GPU (CUDA) not available, but skullstripping with macacaMRINN is enabled for "
                f"{' and '.join(modalities)}. This will be very slow on CPU."
            )
            result['summary']['warnings'].append(warn_msg)
            logger.warning(warn_msg)
    # -------------------------------------
    
    # Determine overall status
    critical_count = len(result['summary']['critical_issues'])
    warning_count = len(result['summary']['warnings'])
    
    if critical_count == 0 and warning_count == 0:
        result['summary']['overall_status'] = 'excellent'
        logger.info("System: ✓ environment check passed - all requirements met")
    elif critical_count == 0:
        result['summary']['overall_status'] = 'good'
        logger.info(f"System: ✓ environment check passed with {warning_count} warnings")
    else:
        result['summary']['overall_status'] = 'failed'
        logger.error(f"System: ✗ environment check failed - {critical_count} critical issues found")
        print(f"✗ Environment check failed - critical issues found")
        for issue in result['summary']['critical_issues']:
            print(f"  - {issue}")
    
    return result


def check_environment_and_exit(
    logger: Optional[logging.Logger] = None,
    config: Optional[Dict[str, Any]] = None,
    exit_on_failure: bool = True
) -> Dict[str, Any]:
    """Perform comprehensive environment check and exit on critical failures.
    
    Args:
        logger: Logger instance
        config: Configuration dictionary (optional)
        exit_on_failure: If True, exit with code 1 on critical failures
        
    Returns:
        Dictionary with environment check results
        
    Exits:
        sys.exit(1) if exit_on_failure=True and critical issues are found
    """
    result = check_environment(logger=logger, config=config)
    
    if exit_on_failure and result['summary']['overall_status'] == 'failed':
        logger.error("System: exiting due to environment check failures")
        sys.exit(1)
    
    return result


def print_environment_report(env_results: Dict[str, Any]) -> None:
    """Print a formatted environment report.
    
    Args:
        env_results: Results from check_environment()
    """
    print("\n" + "="*60)
    print("MACACAMRIPREP ENVIRONMENT REPORT")
    print("="*60)
    
    # Summary
    summary = env_results['summary']
    status_icon = "✓" if summary['overall_status'] != 'failed' else "✗"
    print(f"\nOverall Status: {status_icon} {summary['overall_status'].upper()}")
    
    if summary['critical_issues']:
        print(f"\nCritical Issues ({len(summary['critical_issues'])}):")
        for issue in summary['critical_issues']:
            print(f"  ✗ {issue}")
    
    if summary['warnings']:
        print(f"\nWarnings ({len(summary['warnings'])}):")
        for warning in summary['warnings']:
            print(f"  ⚠ {warning}")
    
    # Python and packages
    deps = env_results['dependencies']
    print(f"\nPython: {deps['python']['version']} {'✓' if deps['python']['compatible'] else '✗'}")
    
    print(f"\nRequired Packages ({len(deps['required_packages'])}):")
    for pkg, info in deps['required_packages'].items():
        status = "✓" if info['compatible'] else "✗"
        version_str = info['installed_version'] or 'not found'
        print(f"  {status} {pkg}: {version_str} (>= {info['required_version']})")
    
    # External tools
    tools = env_results['external_tools']
    print(f"\nExternal Tools ({len(tools)}):")
    for tool_name, tool_info in tools.items():
        status = "✓" if tool_info['available'] else "✗"
        print(f"  {status} {tool_name}")
        if tool_info['env_var_set']:
            print(f"      env: {tool_info['env_var_path']}")
        for cmd_info in tool_info['commands_found']:
            print(f"      cmd: {cmd_info['command']} -> {cmd_info['path']}")
        if tool_info['installed_version']:
            version_status = "✓" if tool_info.get('version_matches', False) else "✗"
            required = tool_info.get('required_version', 'any')
            print(f"      ver: {tool_info['installed_version']} (required: {required}) {version_status}")
        elif tool_info['version_info']:
            version_line = tool_info['version_info'].split('\n')[0]
            print(f"      ver: {version_line}")
    
    # System resources
    resources = env_results['system_resources']
    print(f"\nSystem Resources:")
    if 'total_gb' in resources['memory']:
        mem = resources['memory']
        print(f"  Memory: {mem['available_gb']:.1f}GB available / {mem['total_gb']:.1f}GB total")
    if 'total_gb' in resources['disk']:
        disk = resources['disk']
        print(f"  Disk: {disk['free_gb']:.1f}GB free / {disk['total_gb']:.1f}GB total")
    if 'count' in resources['cpu']:
        cpu = resources['cpu']
        print(f"  CPU: {cpu['count']} cores ({cpu['count_logical']} logical)")
    if 'cuda_available' in resources['gpu']:
        gpu = resources['gpu']
        if gpu['cuda_available'] and 'devices' in gpu:
            print(f"  GPU: {len(gpu['devices'])} CUDA device(s)")
            for i, device in enumerate(gpu['devices']):
                mem_gb = device['memory_total_mb'] / 1024
                print(f"       [{i}] {device['name']} ({mem_gb:.1f}GB)")
        else:
            print(f"  GPU: Not available")
    
    print("\n" + "="*60 + "\n")


def info() -> str:
    """Get basic environment information string.
    
    Returns:
        Environment information string
    """
    
    # Get basic info without full environment check
    python_compatible, python_version = check_python_version()
    
    # Check key packages quickly
    key_packages = ['nibabel', 'numpy', 'scipy']
    packages_ok = 0
    for pkg in key_packages:
        try:
            importlib.import_module(pkg)
            packages_ok += 1
        except ImportError:
            pass
    
    status = "OK" if python_compatible and packages_ok == len(key_packages) else "ISSUES"
    
    return f"macacaMRIprep v{__version__} | Python {python_version} | Core packages: {packages_ok}/{len(key_packages)} | Status: {status}"


# Note: We don't run checks on import to avoid slowing down module loading
# Checks are performed explicitly when needed via check_environment() or check_dependencies() 