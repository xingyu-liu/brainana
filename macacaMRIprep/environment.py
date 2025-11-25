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
import shutil
import logging
import subprocess
import importlib
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from packaging import version

from .info import __version__

# Define minimum required versions
REQUIRED_PYTHON_PACKAGES = {
    'nibabel': '3.0.0',
    'numpy': '1.19.0',
    'scipy': '1.5.0',
    'matplotlib': '3.0.0',
    'pandas': '1.0.0',
    'packaging': '20.0'
}

OPTIONAL_PYTHON_PACKAGES = {
    'psutil': '5.0.0',
    'nilearn': '0.7.0',
    'seaborn': '0.11.0',
    'plotly': '4.0.0',
    'jupyter': '1.0.0'
}

REQUIRED_EXTERNAL_TOOLS = {
    'fsl': {
        'commands': ['fslmaths', 'mcflirt', 'slicetimer'],
        'env_var': 'FSLDIR',
        'version_cmd': 'flirt -version',
        'min_version': '6.0'
    },
    'ants': {
        'commands': ['antsRegistration', 'N4BiasFieldCorrection'],
        'env_var': 'ANTSPATH',
        'version_cmd': 'antsRegistration --version',
        'min_version': '2.3'
    },
    'afni': {
        'commands': ['3dDespike'],
        'env_var': 'AFNIPATH',
        'version_cmd': '3dinfo -ver',
        'min_version': '20.0'
    }
}

def get_logger() -> logging.Logger:
    """Get logger for environment checking."""
    return logging.getLogger(__name__)


def check_python_version(min_version: str = "3.7") -> Tuple[bool, str]:
    """Check Python version requirement.
    
    Args:
        min_version: Minimum required Python version
        
    Returns:
        Tuple of (is_compatible, version_info)
    """
    current_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    is_compatible = version.parse(current_version) >= version.parse(min_version)
    
    return is_compatible, current_version


def check_package_version(package_name: str, min_version: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check if a Python package meets version requirements.
    
    Args:
        package_name: Name of the package
        min_version: Minimum required version
        
    Returns:
        Tuple of (is_available, installed_version, error_message)
    """
    try:
        module = importlib.import_module(package_name)
        
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
        
        if result.returncode == 0:
            # Extract version from output (this is tool-specific)
            output = result.stdout + result.stderr
            return output.strip()
        
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass
    
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
        'errors': []
    }
    
    # Check environment variable
    env_var = tool_config.get('env_var')
    if env_var:
        env_path = os.environ.get(env_var)
        result['env_var_set'] = env_path is not None
        result['env_var_path'] = env_path
        
        if not env_path:
            result['errors'].append(f"Environment variable {env_var} not set")
    
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
    if version_cmd and len(result['commands_found']) > 0:
        version_info = get_command_version(version_cmd)
        if version_info:
            result['version_info'] = version_info
        else:
            result['errors'].append(f"Could not get version info using: {version_cmd}")
    
    # Tool is available if all commands are found
    result['available'] = len(result['commands_missing']) == 0
    
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
        result['errors'].append(f"Python version {py_version} < required 3.7")
        logger.error(f"System: incompatible Python version - {py_version}")
    
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
        # Check if either anat or func skullstripping is enabled and using fastsurfercnn
        anat_ss = config.get('anat', {}).get('skullstripping', {})
        func_ss = config.get('func', {}).get('skullstripping', {})
        anat_enabled = anat_ss.get('enabled', False) and anat_ss.get('method', '').lower() == 'fastsurfercnn'
        func_enabled = func_ss.get('enabled', False) and func_ss.get('method', '').lower() == 'fastsurfercnn'
        if anat_enabled or func_enabled:
            gpu_info = result['system_resources'].get('gpu', {})
            if not gpu_info.get('cuda_available', False):
                warn_msg = (
                    "GPU (CUDA) not available, but skullstripping with FastSurferCNN is enabled for "
                    f"{'anat' if anat_enabled else ''}{' and ' if anat_enabled and func_enabled else ''}{'func' if func_enabled else ''}. "
                    "This will be very slow on CPU."
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
        if tool_info['version_info']:
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


# Run basic checks on import
if __name__ != "__main__":
    # Only run basic checks when imported
    try:
        check_dependencies(include_optional=False)
    except Exception:
        pass  # Don't break import if check fails 