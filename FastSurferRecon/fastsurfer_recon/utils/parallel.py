"""
Parallel execution utilities for FastSurfer surface reconstruction.
"""

from typing import Callable, TypeVar, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_parallel_hemis(
    func: Callable[[str], T],
    hemis: Sequence[str] = ("lh", "rh"),
) -> dict[str, T]:
    """
    Run a function on both hemispheres in parallel.
    
    Parameters
    ----------
    func : callable
        Function that takes hemisphere ('lh' or 'rh') as argument
    hemis : sequence of str
        Hemispheres to process (default: both)
        
    Returns
    -------
    dict
        Results keyed by hemisphere
        
    Raises
    ------
    Exception
        Re-raises any exception from hemisphere processing
    """
    results = {}
    
    with ThreadPoolExecutor(max_workers=len(hemis)) as executor:
        futures = {executor.submit(func, hemi): hemi for hemi in hemis}
        
        for future in as_completed(futures):
            hemi = futures[future]
            try:
                results[hemi] = future.result()
                logger.debug(f"Completed {hemi}")
            except Exception as e:
                logger.error(f"Error processing {hemi}: {e}")
                raise
    
    return results


def run_parallel(
    func: Callable[[T], None],
    items: Sequence[T],
    max_workers: int = 2,
) -> None:
    """
    Run a function on multiple items in parallel.
    
    Parameters
    ----------
    func : callable
        Function to call for each item
    items : sequence
        Items to process
    max_workers : int
        Maximum number of parallel workers
    """
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(func, item): item for item in items}
        
        for future in as_completed(futures):
            item = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error processing {item}: {e}")
                raise

