"""
Thread configuration utilities for macacaMRINN.

Provides default thread count that avoids resource cap issues on systems
with many CPU cores.

IMPORTANT: CPU Threads vs GPU Operations vs Process-Level Parallelism
======================================================================
1. PyTorch CPU threads (torch.set_num_threads): Controls CPU tensor operations,
   data preprocessing, and CPU↔GPU transfers. Used for BOTH:
   * CPU-only operations (model on CPU)
   * GPU operations (data loading, preprocessing, CPU↔GPU transfers)
   
2. GPU operations: Run on GPU hardware, don't directly use CPU threads.
   However, they still need CPU threads for:
   * Data loading from disk
   * Preprocessing (resize, normalize, etc.)
   * CPU↔GPU memory transfers
   * Post-processing results

3. DataLoader num_workers: Separate parameter - these are separate PROCESSES
   for parallel data loading. Each worker can use CPU threads internally.

So YES, use the same CPU thread count (default 8) for both CPU-only and GPU
workflows, because GPU workflows still need CPU threads for data operations.
"""

import os


def get_num_threads():
    """
    Determine the default number of threads to use.

    Returns the number of available cores if <= 8, otherwise defaults to 8
    to avoid resource cap issues and excessive thread overhead on systems with
    many cores. Users can override this by explicitly specifying thread settings.

    This applies to BOTH CPU-only and GPU workflows, because GPU workflows
    still need CPU threads for data loading, preprocessing, and transfers.

    Returns
    -------
    int
        Default number of threads (all cores if <=8, else 8).
    """
    try:
        from os import sched_getaffinity as __getaffinity

        num_cores = len(__getaffinity(0))
    except ImportError:
        from os import cpu_count

        num_cores = cpu_count()
    
    # If system has 8 or fewer cores, use all of them
    # If system has more than 8 cores, default to 8 to avoid resource cap issues
    if num_cores <= 8:
        return num_cores
    else:
        return 8


def setup_pytorch_threads(num_threads: int = None):
    """
    Configure PyTorch to use a specific number of threads.
    
    This sets CPU threads for PyTorch operations, which are used for:
    - CPU-only model operations
    - GPU workflows (data loading, preprocessing, CPU↔GPU transfers)
    
    Parameters
    ----------
    num_threads : int, optional
        Number of threads to use. If None, uses get_num_threads() default.
    """
    import torch
    
    if num_threads is None:
        num_threads = get_num_threads()
    
    torch.set_num_threads(num_threads)
    
    # Also set environment variables for OpenMP and MKL
    # These libraries are used by PyTorch for CPU operations
    os.environ['OMP_NUM_THREADS'] = str(num_threads)
    os.environ['MKL_NUM_THREADS'] = str(num_threads)
    os.environ['NUMEXPR_NUM_THREADS'] = str(num_threads)
    os.environ['OPENBLAS_NUM_THREADS'] = str(num_threads)

