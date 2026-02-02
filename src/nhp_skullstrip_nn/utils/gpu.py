"""
Simple GPU utilities for device selection.
"""

import torch
import subprocess
from typing import Union


def get_device():
    """Get the best available device."""
    if torch.cuda.is_available():
        return torch.device(f"cuda:{get_least_busy_gpu()}")
    return torch.device("cpu")


def get_least_busy_gpu():
    """Get the GPU with the least memory usage based on system-wide memory usage."""
    if not torch.cuda.is_available():
        return 0
    
    gpu_count = torch.cuda.device_count()
    if gpu_count == 1:
        return 0
    
    try:
        # Use nvidia-smi to get actual system-wide memory usage
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            memory_usages = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    memory_usages.append(int(line.strip()))
            
            # Find GPU with minimum memory usage
            if memory_usages:
                best_gpu = memory_usages.index(min(memory_usages))
                return best_gpu
    
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, IndexError):
        # Fall back to PyTorch's memory allocation if nvidia-smi fails
        pass
    
    # Fallback: Check memory usage for each GPU using PyTorch
    min_memory = float('inf')
    best_gpu = 0
    
    for i in range(gpu_count):
        torch.cuda.set_device(i)
        memory_used = torch.cuda.memory_allocated(i)
        if memory_used < min_memory:
            min_memory = memory_used
            best_gpu = i
    
    return best_gpu


def setup_device(device_id: Union[int, str] = 'auto') -> torch.device:
    """Setup device for model training/inference.
    
    Args:
        device_id: Device specification ('auto', -1 for CPU, specific GPU index, or full device string)
        
    Returns:
        torch.device object
    """
    if device_id == 'auto':
        return get_device()
    elif device_id == -1 or device_id == 'cpu':
        return torch.device('cpu')
    elif isinstance(device_id, str) and device_id.startswith('cuda:'):
        # If it's already a full cuda device string, use it directly
        return torch.device(device_id)
    elif isinstance(device_id, torch.device):
        # If it's already a torch.device object, return it directly
        return device_id
    else:
        # Otherwise, treat it as a GPU index
        return torch.device(f'cuda:{device_id}')