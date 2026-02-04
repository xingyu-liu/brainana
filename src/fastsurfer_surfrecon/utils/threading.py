"""
Threading utilities for FastSurfer surface reconstruction.

Provides functions to set environment variables for controlling thread usage
in numerical computing libraries (OpenMP, MKL, OpenBLAS, ITK, etc.).
"""

import os
import logging

logger = logging.getLogger(__name__)


def set_numerical_threads(threads: int, max_threads: int = 32, include_itk: bool = False) -> int:
    """
    Set environment variables to limit threading for numerical computing libraries.
    
    This function sets environment variables that control thread usage in:
    - OpenMP (OMP_NUM_THREADS) - used by many numerical libraries
    - Intel MKL (MKL_NUM_THREADS) - linear algebra library
    - NumExpr (NUMEXPR_NUM_THREADS) - numerical expression evaluator
    - OpenBLAS (OPENBLAS_NUM_THREADS) - linear algebra library
    - ITK (ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS, optional) - image processing
    
    This is critical because numerical operations (eigendecomposition, matrix
    operations, etc.) can use all available CPU cores by default, making the
    system unresponsive. Setting these environment variables limits thread usage.
    
    Parameters
    ----------
    threads : int
        Number of threads to use (will be capped at max_threads)
    max_threads : int, default=32
        Maximum allowed threads to prevent excessive resource usage
    include_itk : bool, default=False
        If True, also set ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS
        
    Returns
    -------
    int
        The actual number of threads set (after capping)
        
    Examples
    --------
    >>> set_numerical_threads(8)
    8
    >>> set_numerical_threads(100)  # Will be capped at 32
    32
    >>> set_numerical_threads(4, include_itk=True)  # Also sets ITK threads
    4
    """
    num_threads = min(threads, max_threads)
    
    os.environ['OMP_NUM_THREADS'] = str(num_threads)
    os.environ['MKL_NUM_THREADS'] = str(num_threads)
    os.environ['NUMEXPR_NUM_THREADS'] = str(num_threads)
    os.environ['OPENBLAS_NUM_THREADS'] = str(num_threads)
    
    if include_itk:
        os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(num_threads)
    
    logger.debug(f"Set numerical threads to {num_threads} (requested {threads})")
    
    return num_threads

