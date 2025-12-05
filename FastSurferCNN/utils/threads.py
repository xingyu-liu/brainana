# Copyright 2023 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os


def get_num_threads():
    """
    Determine the default number of threads to use.

    Returns the number of available cores if <= 8, otherwise defaults to 8
    to avoid resource cap issues and excessive thread overhead on systems with
    many cores. Users can override this by explicitly specifying --threads.

    Returns
    -------
    int
        Default number of threads (all cores if <=8, else 8). Use --threads to override.
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
