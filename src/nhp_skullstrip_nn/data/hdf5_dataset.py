"""
HDF5 Dataset loader for nhp_skullstrip_nn.

This module provides a PyTorch Dataset class that loads preprocessed slices
from HDF5 files created by step2_create_hdf5.py.
"""

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset
from typing import Optional, Tuple, Callable
from pathlib import Path


class HDF5Dataset(Dataset):
    """
    Dataset for loading preprocessed slices from HDF5 files.
    
    This dataset loads slices that have been preprocessed and stored in HDF5 format,
    which is much faster than loading and processing NIfTI files on-the-fly.
    
    Args:
        hdf5_path: Path to HDF5 file containing preprocessed data
        transform: Optional transform to apply to samples
    """
    
    def __init__(self, hdf5_path: str, transform: Optional[Callable] = None):
        super().__init__()
        
        self.hdf5_path = Path(hdf5_path)
        if not self.hdf5_path.exists():
            raise FileNotFoundError(f"HDF5 file not found: {hdf5_path}")
        
        self.transform = transform
        
        # Open HDF5 file to get metadata
        with h5py.File(self.hdf5_path, 'r') as hf:
            self.num_samples = hf['images'].shape[0]
            self.num_slices = hf.attrs.get('num_slices', 3)
            self.rescale_dim = hf.attrs.get('rescale_dim', 256)
        
        # Keep file handle open for faster access (optional optimization)
        # For now, we'll open/close on each access to avoid file handle issues
        self._file_handle = None
    
    def __len__(self) -> int:
        """Return the number of samples in the dataset."""
        return self.num_samples
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get a sample from the dataset.
        
        Args:
            idx: Sample index
            
        Returns:
            Tuple of (image, label) tensors
                - image: [num_slices, H, W] where num_slices is the number of consecutive slices
                - label: [H, W]
        """
        with h5py.File(self.hdf5_path, 'r') as hf:
            # Load image and label
            image = hf['images'][idx]  # [num_slices, H, W]
            label = hf['labels'][idx]  # [H, W]
        
        # Convert to torch tensors
        image = torch.from_numpy(image).float()
        label = torch.from_numpy(label).long()
        
        # Apply transforms if provided
        if self.transform is not None:
            try:
                transformed = self.transform([image, label])
                image, label = transformed[0], transformed[1]
            except Exception as e:
                import warnings
                warnings.warn(f"Transform failed: {e}. Continuing without transforms.")
        
        return image, label
    
    def get_subject_name(self, idx: int) -> str:
        """Get the subject name for a given index."""
        with h5py.File(self.hdf5_path, 'r') as hf:
            subject_name = hf['subject'][idx]
            if isinstance(subject_name, bytes):
                subject_name = subject_name.decode('utf-8')
            return str(subject_name).strip()
    
    def get_metadata(self) -> dict:
        """Get metadata from the HDF5 file."""
        with h5py.File(self.hdf5_path, 'r') as hf:
            metadata = {
                'num_samples': hf['images'].shape[0],
                'num_slices': hf.attrs.get('num_slices', 3),
                'rescale_dim': hf.attrs.get('rescale_dim', 256),
                'image_shape': hf['images'].shape,
                'label_shape': hf['labels'].shape,
            }
        return metadata

