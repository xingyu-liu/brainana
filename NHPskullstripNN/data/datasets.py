# %%
import torch
import torch.utils.data as data
import torch.nn as nn
import scipy.io as io
import numpy as np
import nibabel as nib
import os, sys
import glob
import warnings

from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union
from torch.utils.data import Dataset


def validate_labels(label_data: np.ndarray, num_classes: int, dataset_name: str = "dataset") -> np.ndarray:
    """Validate and potentially fix label data for multi-class segmentation.
    
    Args:
        label_data: Label array to validate
        num_classes: Expected number of classes
        dataset_name: Name for error messages
        
    Returns:
        Validated label array
        
    Raises:
        ValueError: If labels are invalid and cannot be fixed
    """
    unique_labels = np.unique(label_data)
    max_label = unique_labels.max()
    min_label = unique_labels.min()
    
    # Check for negative labels
    if min_label < 0:
        print(f"Warning: Found negative labels in {dataset_name}. Setting negative values to 0.")
        label_data = np.maximum(label_data, 0)
        unique_labels = np.unique(label_data)
        max_label = unique_labels.max()
    
    # Check if labels exceed expected range
    if max_label >= num_classes:
        print(f"Warning: Found labels up to {max_label} in {dataset_name}, but num_classes={num_classes}")
        print(f"Unique labels found: {unique_labels}")
        print("Consider checking your label data or increasing num_classes in config.")
        
        # Option 1: Clip labels to valid range
        print(f"Clipping labels to range [0, {num_classes-1}]")
        label_data = np.clip(label_data, 0, num_classes - 1)
    
    return label_data

# %%
class VolumeDataset(data.Dataset):
    """
    Dataset class for loading 3D medical image volumes and their corresponding labels.
    
    This dataset loads single NIfTI files for both images and labels.
    
    Args:
        input_image (str, optional): Path to image file (.nii or .nii.gz).
                                    - Single file path: loads the specific file
                                    - None: no images loaded
        input_label (str, optional): Path to label file (.nii or .nii.gz).
                                    - Single file path: loads the specific file
                                    - None: no labels loaded
        debug (bool): Enable debug printing. Defaults to True.
    """
    def __init__(self,
        input_image=None,
        input_label=None,
        debug=True
                ):
        super(VolumeDataset, self).__init__()

        # ===== IMAGE PROCESSING =====
        # Store the input image parameter
        self.input_image = input_image
        
        # Handle case when no image is provided
        if isinstance(input_image, type(None)):
            self.image_path = None
        else:
            # Validate that input_image is a valid file path
            if isinstance(input_image, str) and os.path.isfile(input_image):
                self.image_path = input_image
            else:
                # Invalid input - not a file
                print("Invalid input_image: must be a valid file path")
                sys.exit(1)

        # ===== LABEL PROCESSING =====
        # Store the input label parameter
        self.input_label = input_label
        
        # Handle case when no label is provided
        if isinstance(input_label, type(None)):
            self.label_path = None
        else:
            # Validate that input_label is a valid file path
            if isinstance(input_label, str) and os.path.isfile(input_label):
                self.label_path = input_label
            else:
                # Invalid input - not a file
                print("Invalid input_label: must be a valid file path")
                sys.exit(1)

        # ===== STORAGE FOR CURRENT LOADED DATA =====
        # Store the currently loaded NIfTI objects for potential reuse
        self.current_image_nifti = None
        self.current_label_nifti = None

        # ===== DEBUG SETTING =====
        self.debug = debug

    def get_current_image_nifti(self):
        """Get the currently loaded image NIfTI object."""
        return self.current_image_nifti

    def get_current_label_nifti(self):
        """Get the currently loaded label NIfTI object."""
        return self.current_label_nifti

    def __len__(self):
        """
        Return the number of samples in the dataset.
        
        Returns:
            int: Always 1 since we only load single files
        """
        return 1

    def __getitem__(self, index):
        """
        Load and return the sample (always index 0 since we only have one file).
        
        Args:
            index (int): Index of the sample to load (ignored, always loads the single file)
            
        Returns:
            torch.Tensor or tuple: 
                - If only image: returns single image tensor
                - If image and label: returns tuple (image_tensor, label_tensor)
                - If only label: returns single label tensor
        """
        # Debug printing (commented out by default)
        # if self.debug:
        #     if self.image_path:
        #         print(f"Loading image: {self.image_path}")
        #     if self.label_path:
        #         print(f"Loading label: {self.label_path}")

        # Initialize output list to collect all loaded data
        Out = list()
        
        # ===== LOAD IMAGE DATA =====
        if self.image_path is not None:
            # Load the NIfTI file using nibabel
            image_nifti = nib.load(self.image_path)
            
            # Extract the actual image data as numpy array
            image = np.array(image_nifti.get_fdata(), dtype=np.float32)
            
            # Handle 4D images: if image has 4 dimensions, average the last dimension
            if image.ndim == 4:
                print(f"Warning: 4D image detected. Averaging the last dimension.")
                image = np.mean(image, axis=-1)
            
            # Normalize image data to range [0, 1] for better training stability
            image = (image - image.min()) / (image.max() - image.min())
            
            # Convert numpy array to PyTorch tensor
            image = torch.from_numpy(image)
            
            # Add image to output list
            Out.append(image)

            # Store the NIfTI object for potential reuse
            self.current_image_nifti = image_nifti

        # ===== LOAD LABEL DATA =====
        if self.label_path is not None:
            # Load the NIfTI file using nibabel
            label_nifti = nib.load(self.label_path)
            
            # Extract the actual label data as numpy array
            # Convert to int64 for classification labels
            label = np.array(label_nifti.get_fdata(), dtype=np.int64)
            
            # Handle 4D labels: if label has 4 dimensions, take the first slice of the last dimension
            if label.ndim == 4:
                print(f"Warning: 4D label detected. Taking the first slice of the last dimension.")
                label = label[..., 0]  # Take first channel/slice
            
            # Convert numpy array to PyTorch tensor
            label = torch.from_numpy(label)
            
            # Add label to output list
            Out.append(label)

            # Store the NIfTI object for potential reuse
            self.current_label_nifti = label_nifti

        # ===== FORMAT OUTPUT =====
        # If only one item was loaded, return it directly
        if len(Out) == 1:
            Out = Out[0]
        else:
            # If multiple items, return as tuple
            Out = tuple(Out)
            
        return Out

class BlockDataset(data.Dataset):
    """
    Dataset for processing 2D slices from 3D volumes.
    
    This dataset takes 3D volumes and extracts 2D multi-slice blocks for training.
    It processes slices in three orientations (axial, sagittal, coronal) to provide
    comprehensive coverage of the 3D volume.
    
    Note: This is NOT the same as batch_size in DataLoader config.
    - DataLoader batch_size: Controls how many volumes are processed together (traditional CNN batching)
    - BlockDataset: Processes 2D slices extracted from individual 3D volumes
    
    Args:
        image (torch.Tensor): 3D image volume tensor with shape [channels, height, width, depth]
        label (torch.Tensor, optional): 3D label volume tensor with same spatial dimensions as image
        num_slice (int): Number of consecutive slices to include in each block. Defaults to 3.
        rescale_dim (int): Target dimension for rescaling. Defaults to 256.
    """
    def __init__(self,
        image=None,
        label=None,
        num_slice=3,
        rescale_dim=256):
        super(BlockDataset, self).__init__()
        
        # Initialize transform attribute
        self.transform = None
        
        # Validate that image and label have matching shapes if both are provided
        if isinstance(label, torch.Tensor) and image.shape != label.shape:
            print("Invalid shape of image")
            return
        
        # ===== DIMENSION CALCULATION AND RESCALING =====
        # Handle both 3D and 4D input tensors
        if image.dim() == 3:
            # Direct 3D tensor from VolumeDataset: [height, width, depth]
            raw_shape = image.shape
            # Add batch dimension for consistency
            image = torch.unsqueeze(image, 0)  # [1, height, width, depth]
        elif image.dim() == 4:
            # 4D tensor from training (already has batch dim): [batch, height, width, depth]
            raw_shape = image.shape[1:]  # Get spatial dimensions only
        else:
            raise ValueError(f"Expected 3D or 4D tensor, got {image.dim()}D tensor with shape {image.shape}")
        
        # Find the maximum dimension to calculate rescale factor
        max_dim = torch.tensor(raw_shape).max()
        
        # Calculate rescale factor to fit within target dimension
        rescale_factor = float(rescale_dim) / float(max_dim)

        # ===== IMAGE RESCALING =====
        # Add channel dimension for interpolation: [batch, channel, height, width, depth]
        uns_image = torch.unsqueeze(image, 1)
        
        # Rescale image using trilinear interpolation (good for continuous data)
        uns_image = nn.functional.interpolate(uns_image, scale_factor=rescale_factor, mode="trilinear", align_corners=False)
        
        # Remove channel dimension but keep batch dimension
        image = torch.squeeze(uns_image, 1)

        # ===== LABEL RESCALING =====
        if isinstance(label, torch.Tensor):
            # Handle both 3D and 4D input tensors for labels
            if label.dim() == 3:
                # Direct 3D tensor from VolumeDataset: [height, width, depth]
                # Add batch dimension for consistency
                label = torch.unsqueeze(label, 0)  # [1, height, width, depth]
            elif label.dim() != 4:
                raise ValueError(f"Expected 3D or 4D label tensor, got {label.dim()}D tensor with shape {label.shape}")
            
            # Add channel dimension for interpolation: [batch, channel, height, width, depth]
            uns_label = torch.unsqueeze(label.float(), 1)
            
            # Rescale label using nearest neighbor interpolation (preserves discrete values)
            uns_label = nn.functional.interpolate(uns_label, scale_factor=rescale_factor, mode="nearest")
            
            # Remove channel dimension but keep batch dimension, convert back to long
            label = torch.squeeze(uns_label, 1).long()
        
        # ===== SLICE EXTRACTION SETUP =====
        # Get the rescaled dimensions (skip batch dimension)
        rescale_shape = image.shape[1:]  # Skip batch dimension to get [height, width, depth]
        
        # Create lists of slice ranges for each orientation
        # Each range contains consecutive slice indices
        
        # Axial slices (along first dimension)
        slice_list_0 = list()
        for i in range(rescale_shape[0] - num_slice + 1):
            slice_list_0.append(range(i, i + num_slice))
        self.slice_list_0 = slice_list_0
        
        # Sagittal slices (along second dimension)  
        slice_list_1 = list()
        for i in range(rescale_shape[1] - num_slice + 1):
            slice_list_1.append(range(i, i + num_slice))
        self.slice_list_1 = slice_list_1
        
        # Coronal slices (along third dimension)
        slice_list_2 = list()
        for i in range(rescale_shape[2] - num_slice + 1):
            slice_list_2.append(range(i, i + num_slice))
        self.slice_list_2 = slice_list_2
        
        # ===== STORE PARAMETERS =====
        self.image = image
        self.label = label
        
        # Calculate dataset properties
        self.num_volumes = image.shape[0]  # Number of volumes in this BlockDataset
        self.total_slices = len(self.slice_list_0) + len(self.slice_list_1) + len(self.slice_list_2)  # Total slices across all orientations
        self.num_slice = num_slice
        self.rescale_dim = rescale_dim
        self.rescale_factor = rescale_factor
        self.rescale_shape = rescale_shape
        self.raw_shape = raw_shape
    
    def get_rescale_factor(self):
        """Get the rescale factor used for dimension adjustment."""
        return self.rescale_factor

    def get_rescale_shape(self):
        """Get the shape of the volume after rescaling."""
        return self.rescale_shape

    def get_raw_shape(self):
        """Get the original shape of the volume before rescaling."""
        return self.raw_shape

    def get_rescale_dim(self):
        """Get the target dimension used for rescaling."""
        return self.rescale_dim

    def get_one_directory(self, axis=0):
        """
        Get slices from a specific orientation (axis).
        
        Args:
            axis (int): Orientation to extract slices from
                        0: Axial (first dimension)
                        1: Sagittal (second dimension) 
                        2: Coronal (third dimension)
        
        Returns:
            tuple: (slice_data, slice_list, slice_weight)
                - slice_data: List of extracted slice blocks
                - slice_list: List of slice ranges used
                - slice_weight: Weight array indicating slice overlap
        """
        # Determine which orientation to process based on axis parameter
        if axis == 0:
            # Axial slices (first dimension)
            ind = range(0, len(self.slice_list_0))
            slice_list = self.slice_list_0
        elif axis == 1:
            # Sagittal slices (second dimension)
            ind = range(len(self.slice_list_0), len(self.slice_list_0) + len(self.slice_list_1))
            slice_list = self.slice_list_1
        elif axis == 2:
            # Coronal slices (third dimension)
            ind = range(len(self.slice_list_0) + len(self.slice_list_1), 
                len(self.slice_list_0) + len(self.slice_list_1) + len(self.slice_list_2))
            slice_list = self.slice_list_2
        
        # Calculate slice weights based on overlap
        # Slices that appear in multiple blocks get higher weights
        slice_weight = np.zeros(slice_list[-1][-1] + 1)
        for l in slice_list:
            slice_weight[l] += 1
        
        # Extract slice data for the specified orientation
        slice_data = list()
        for i in ind:
            slice_data.append(self.__getitem__(i))
        
        return slice_data, slice_list, slice_weight

    def __len__(self):
        """
        Return the total number of slices available across all orientations.
        
        Returns:
            int: Total number of slices (num_volumes * total_slices_per_volume)
        """
        list_len = self.num_volumes * self.total_slices
        return list_len
    
    def __getitem__(self, index):
        """
        Get a specific slice block from the dataset.
        
        Args:
            index (int): Index of the slice block to retrieve
            
        Returns:
            torch.Tensor or tuple: 
                - If label is provided: (image_block, label_block)
                - If no label: image_block only
        """
        # Calculate which volume and slice to extract
        volume_idx = int(index / self.total_slices)  # Which volume in the BlockDataset
        slice_idx = index % self.total_slices  # Which slice within that volume
        
        # Initialize label_tmp as None
        label_tmp = None
        
        # ===== AXIAL SLICES (first dimension) =====
        if slice_idx < len(self.slice_list_0):
            slice_range = self.slice_list_0[slice_idx]

            # Extract slices along the first dimension (skip batch dimension)
            image_tmp = self.image[volume_idx][slice_range, :, :]

            # Extract corresponding label slices if available
            if isinstance(self.label, torch.Tensor):
                label_tmp = self.label[volume_idx][slice_range, :, :]
                
        # ===== SAGITTAL SLICES (second dimension) =====
        elif slice_idx < len(self.slice_list_1) + len(self.slice_list_0):
            slice_range = self.slice_list_1[slice_idx - len(self.slice_list_0)]

            # Extract slices along the second dimension (skip batch dimension)
            image_tmp = self.image[volume_idx][:, slice_range, :]
            # Permute dimensions to maintain consistent orientation
            image_tmp = image_tmp.permute([1, 0, 2])

            # Extract corresponding label slices if available
            if isinstance(self.label, torch.Tensor):
                label_tmp = self.label[volume_idx][:, slice_range, :]
                label_tmp = label_tmp.permute([1, 0, 2])
        # ===== CORONAL SLICES (third dimension) =====
        else:
            slice_range = self.slice_list_2[slice_idx - len(self.slice_list_0) - len(self.slice_list_1)]

            # Extract slices along the third dimension (skip batch dimension)
            image_tmp = self.image[volume_idx][:, :, slice_range]
            # Permute dimensions to maintain consistent orientation
            image_tmp = image_tmp.permute([2, 0, 1])
        
            # Extract corresponding label slices if available
            if isinstance(self.label, torch.Tensor):
                label_tmp = self.label[volume_idx][:, :, slice_range]
                label_tmp = label_tmp.permute([2, 0, 1])

        # ===== CREATE OUTPUT BLOCKS =====
        # Target dimension for the output blocks
        extend_dim = self.rescale_dim
        
        # Get the actual shape of the extracted slice
        slice_shape = image_tmp.shape[1:]  # Skip the num_slice dimension to get [height, width]

        # Create image block with padding to reach target dimension
        image_block = torch.zeros([self.num_slice, extend_dim, extend_dim], dtype=torch.float32)
        image_block[:, :slice_shape[0], :slice_shape[1]] = image_tmp

        # Create label block if label is available
        if isinstance(self.label, torch.Tensor) and label_tmp is not None:
            label_block = torch.zeros([self.num_slice, extend_dim, extend_dim], dtype=torch.long)
            label_block[:, :slice_shape[0], :slice_shape[1]] = label_tmp
            
            # Apply transforms if available
            if self.transform is not None:
                # Apply transforms to image and label as a list
                try:
                    transformed = self.transform([image_block, label_block])
                    image_block, label_block = transformed[0], transformed[1]
                except Exception as e:
                    # If transform fails, log warning and continue without transforms
                    warnings.warn(f"Transform failed: {e}. Continuing without transforms.")
            
            return image_block, label_block

        # Apply transforms to image only if available
        if self.transform is not None:
            try:
                image_block = self.transform(image_block)
            except Exception as e:
                # If transform fails, log warning and continue without transforms
                warnings.warn(f"Transform failed: {e}. Continuing without transforms.")

        # Return only image block if no label
        return image_block

class FileListDataset(data.Dataset):
    """
    Dataset for loading paired images and labels from file lists for proper train/val/test splitting.
    
    This dataset is designed to work with explicit file lists rather than directories,
    which allows for better control over data splitting and ensures proper pairing
    between images and labels.
    
    Args:
        image_files (List[str]): List of image file paths
        label_files (List[str]): List of corresponding label file paths
        num_slices (int): Number of input slices for the model. Defaults to 3.
        rescale_dim (int): Target dimension for rescaling. Defaults to 256.
        transform: Optional transforms to apply to the data
    """
    
    def __init__(self, 
                 image_files: List[str], 
                 label_files: List[str], 
                 num_slices: int = 3, 
                 rescale_dim: int = 256,
                 transform=None):
        """Initialize the dataset.
        
        Args:
            image_files: List of image file paths
            label_files: List of corresponding label file paths
            num_slices: Number of input slices for the model
            rescale_dim: Target dimension for rescaling
            transform: Optional transforms to apply
        """
        super().__init__()
        
        # Ensure we have the same number of images and labels
        assert len(image_files) == len(label_files), "Number of images and labels must match"
        
        # Store the file lists and parameters
        self.image_files = image_files
        self.label_files = label_files
        self.num_slices = num_slices
        self.rescale_dim = rescale_dim
        self.transform = transform
        
        # Validate that all files exist before proceeding
        for img_file, label_file in zip(image_files, label_files):
            if not os.path.exists(img_file):
                raise FileNotFoundError(f"Image file not found: {img_file}")
            if not os.path.exists(label_file):
                raise FileNotFoundError(f"Label file not found: {label_file}")
    
    def __len__(self) -> int:
        """
        Return the number of samples in the dataset.
        
        Returns:
            int: Number of image-label pairs
        """
        return len(self.image_files)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get a sample from the dataset.
        
        Args:
            idx: Sample index
            
        Returns:
            BlockDataset: A BlockDataset instance containing the loaded image and label
        """
        # Load image from NIfTI file
        img_nifti = nib.load(self.image_files[idx])
        img_data = np.array(img_nifti.get_fdata(), dtype=np.float32)
        
        # Load label from NIfTI file
        label_nifti = nib.load(self.label_files[idx])
        # Keep original label values for multi-class segmentation
        # Convert to int64 for class indices
        label_data = np.array(label_nifti.get_fdata(), dtype=np.int64)
        
        # Normalize image to [0, 1] range before creating BlockDataset
        # This ensures consistent data scaling across different images
        img_min, img_max = img_data.min(), img_data.max()
        if img_max > img_min:
            img_data = (img_data - img_min) / (img_max - img_min)
        
        # Convert numpy arrays to PyTorch tensors
        img_tensor = torch.from_numpy(img_data).float()
        label_tensor = torch.from_numpy(label_data).long()
        
        # Create BlockDataset from the 3D volume
        # This handles interpolation, rescaling, and slice extraction
        block_dataset = BlockDataset(
            image=img_tensor,
            label=label_tensor,
            num_slice=self.num_slices,
            rescale_dim=self.rescale_dim
        )
        
        # Store transform in BlockDataset for slice-level application
        if self.transform is not None:
            block_dataset.transform = self.transform
        
        return block_dataset

