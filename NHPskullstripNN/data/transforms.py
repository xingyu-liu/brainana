"""
Data transforms for medical image processing.

This module provides transforms for data augmentation and preprocessing
of medical images and segmentation labels.
"""

import random
from typing import Union, List, Callable, Tuple, Optional, Any
import numpy as np
import torch
import torch.nn.functional as F


class Compose:
    """
    Compose multiple transforms together.
    
    Args:
        transforms: List of transforms to compose
    """
    
    def __init__(self, transforms: List[Callable]):
        self.transforms = transforms
    
    def __call__(self, data: Any) -> Any:
        """Apply all transforms in sequence."""
        for transform in self.transforms:
            data = transform(data)
        return data
    
    def __repr__(self) -> str:
        transform_strings = [str(t) for t in self.transforms]
        return f"Compose({transform_strings})"


class ToTensor:
    """Convert numpy arrays to PyTorch tensors."""
    
    def __call__(self, data: Union[np.ndarray, List[np.ndarray]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Convert data to tensors."""
        if isinstance(data, list):
            return [torch.from_numpy(item) if isinstance(item, np.ndarray) else item for item in data]
        elif isinstance(data, np.ndarray):
            return torch.from_numpy(data)
        else:
            return data
    
    def __repr__(self) -> str:
        return "ToTensor()"


class NormalizeIntensity:
    """
    Normalize image intensity to [0, 1] range.
    
    Args:
        min_val: Minimum value for clipping (optional)
        max_val: Maximum value for clipping (optional)
        percentile: Use percentile-based normalization (e.g., 99.0)
    """
    
    def __init__(
        self, 
        min_val: Optional[float] = None, 
        max_val: Optional[float] = None,
        percentile: Optional[float] = None
    ):
        self.min_val = min_val
        self.max_val = max_val
        self.percentile = percentile
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Normalize intensity values."""
        if isinstance(data, list):
            # Apply to first item (assuming it's the image)
            result = data.copy()
            result[0] = self._normalize_tensor(result[0])
            return result
        else:
            return self._normalize_tensor(data)
    
    def _normalize_tensor(self, tensor: torch.Tensor) -> torch.Tensor:
        """Normalize a single tensor."""
        if self.percentile is not None:
            # Percentile-based normalization
            low_val = torch.quantile(tensor, (100 - self.percentile) / 100)
            high_val = torch.quantile(tensor, self.percentile / 100)
        else:
            # Min-max normalization
            low_val = self.min_val if self.min_val is not None else tensor.min()
            high_val = self.max_val if self.max_val is not None else tensor.max()
        
        if high_val > low_val:
            tensor = torch.clamp(tensor, low_val, high_val)
            tensor = (tensor - low_val) / (high_val - low_val)
        
        return tensor
    
    def __repr__(self) -> str:
        return f"NormalizeIntensity(min_val={self.min_val}, max_val={self.max_val}, percentile={self.percentile})"


class RandomFlip:
    """
    Randomly flip images and labels along specified axes.
    
    Args:
        axes: Axes along which to flip (e.g., [0, 1, 2] for 3D)
        prob: Probability of applying flip for each axis
    """
    
    def __init__(self, axes: List[int] = [0, 1, 2], prob: float = 0.5):
        self.axes = axes
        self.prob = prob
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Apply random flips."""
        if isinstance(data, list):
            # Apply same flips to all items
            flip_axes = [axis for axis in self.axes if random.random() < self.prob]
            return [self._flip_tensor(item, flip_axes) for item in data]
        else:
            flip_axes = [axis for axis in self.axes if random.random() < self.prob]
            return self._flip_tensor(data, flip_axes)
    
    def _flip_tensor(self, tensor: torch.Tensor, flip_axes: List[int]) -> torch.Tensor:
        """Flip tensor along specified axes."""
        for axis in flip_axes:
            if axis < tensor.ndim:
                tensor = torch.flip(tensor, [axis])
        return tensor
    
    def __repr__(self) -> str:
        return f"RandomFlip(axes={self.axes}, prob={self.prob})"


class RandomRotation:
    """
    Apply random rotation to images and labels.
    
    Args:
        max_angle: Maximum rotation angle in degrees
        axes: Pair of axes to rotate around (e.g., (0, 1) for XY plane)
        prob: Probability of applying rotation
        mode: Interpolation mode ('bilinear' or 'nearest')
    """
    
    def __init__(
        self, 
        max_angle: float = 15.0, 
        axes: Tuple[int, int] = (0, 1), 
        prob: float = 0.5,
        mode: str = 'bilinear'
    ):
        self.max_angle = max_angle
        self.axes = axes
        self.prob = prob
        self.mode = mode
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Apply random rotation."""
        if random.random() > self.prob:
            return data
        
        angle = random.uniform(-self.max_angle, self.max_angle)
        
        if isinstance(data, list):
            result = []
            for i, item in enumerate(data):
                # Use nearest interpolation for labels (typically last item)
                interp_mode = 'nearest' if i == len(data) - 1 else self.mode
                result.append(self._rotate_tensor(item, angle, interp_mode))
            return result
        else:
            return self._rotate_tensor(data, angle, self.mode)
    
    def _rotate_tensor(self, tensor: torch.Tensor, angle: float, mode: str) -> torch.Tensor:
        """Rotate tensor by specified angle."""
        if tensor.ndim < 2:
            return tensor
        
        # Handle dtype conversion for grid_sample compatibility
        original_dtype = tensor.dtype
        needs_dtype_conversion = original_dtype in [torch.long, torch.int, torch.int64, torch.int32]
        
        if needs_dtype_conversion:
            tensor = tensor.float()
        
        # Convert angle to radians
        angle_rad = np.radians(angle)
        
        # Create rotation matrix
        cos_val = np.cos(angle_rad)
        sin_val = np.sin(angle_rad)
        
        rotation_matrix = torch.tensor([
            [cos_val, -sin_val, 0],
            [sin_val, cos_val, 0]
        ], dtype=torch.float32)
        
        # Add batch dimension if needed
        if tensor.ndim == 2:
            tensor = tensor.unsqueeze(0).unsqueeze(0)
            squeeze_dims = True
        elif tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)
            squeeze_dims = False
        else:
            squeeze_dims = False
        
        # Create grid and apply rotation
        grid = F.affine_grid(
            rotation_matrix.unsqueeze(0), 
            tensor.size(),
            align_corners=False
        )
        
        rotated = F.grid_sample(
            tensor, 
            grid, 
            mode=mode, 
            align_corners=False,
            padding_mode='border'
        )
        
        # Remove added dimensions
        if squeeze_dims:
            rotated = rotated.squeeze(0).squeeze(0)
        elif tensor.ndim == 4:
            rotated = rotated.squeeze(0)
        
        # Convert back to original dtype if needed
        if needs_dtype_conversion:
            if mode == 'nearest':
                # For nearest interpolation, round and convert back
                rotated = rotated.round().to(original_dtype)
            else:
                # For other interpolation modes, threshold at 0.5 for binary labels
                rotated = (rotated > 0.5).to(original_dtype)
        
        return rotated
    
    def __repr__(self) -> str:
        return f"RandomRotation(max_angle={self.max_angle}, axes={self.axes}, prob={self.prob})"


class RandomScale:
    """
    Apply random scaling to images and labels.
    
    Args:
        scale_range: Range for scaling factor (min, max) - e.g., (0.8, 1.15)
        prob: Probability of applying scaling
        mode: Interpolation mode ('bilinear' or 'nearest')
    """
    
    def __init__(
        self, 
        scale_range: Tuple[float, float] = (0.8, 1.15), 
        prob: float = 0.5,
        mode: str = 'bilinear'
    ):
        self.scale_range = scale_range
        self.prob = prob
        self.mode = mode
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Apply random scaling."""
        if random.random() > self.prob:
            return data
        
        # Sample scale factor (isotropic scaling)
        scale = random.uniform(*self.scale_range)
        
        if isinstance(data, list):
            result = []
            for i, item in enumerate(data):
                # Use nearest interpolation for labels (typically last item)
                interp_mode = 'nearest' if i == len(data) - 1 else self.mode
                result.append(self._scale_tensor(item, scale, interp_mode))
            return result
        else:
            return self._scale_tensor(data, scale, self.mode)
    
    def _scale_tensor(self, tensor: torch.Tensor, scale: float, mode: str) -> torch.Tensor:
        """Scale tensor by specified factor."""
        if tensor.ndim < 2:
            return tensor
        
        # Handle dtype conversion for grid_sample compatibility
        original_dtype = tensor.dtype
        needs_dtype_conversion = original_dtype in [torch.long, torch.int, torch.int64, torch.int32]
        
        if needs_dtype_conversion:
            tensor = tensor.float()
        
        # Create scaling matrix (isotropic scaling)
        scale_matrix = torch.tensor([
            [scale, 0, 0],
            [0, scale, 0]
        ], dtype=torch.float32)
        
        # Add batch dimension if needed
        if tensor.ndim == 2:
            tensor = tensor.unsqueeze(0).unsqueeze(0)
            squeeze_dims = True
        elif tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)
            squeeze_dims = False
        else:
            squeeze_dims = False
        
        # Create grid and apply scaling
        grid = F.affine_grid(
            scale_matrix.unsqueeze(0), 
            tensor.size(),
            align_corners=False
        )
        
        scaled = F.grid_sample(
            tensor, 
            grid, 
            mode=mode, 
            align_corners=False,
            padding_mode='border'
        )
        
        # Remove added dimensions
        if squeeze_dims:
            scaled = scaled.squeeze(0).squeeze(0)
        elif tensor.ndim == 4:
            scaled = scaled.squeeze(0)
        
        # Convert back to original dtype if needed
        if needs_dtype_conversion:
            if mode == 'nearest':
                # For nearest interpolation, round and convert back
                scaled = scaled.round().to(original_dtype)
            else:
                # For other interpolation modes, threshold at 0.5 for binary labels
                scaled = (scaled > 0.5).to(original_dtype)
        
        return scaled
    
    def __repr__(self) -> str:
        return f"RandomScale(scale_range={self.scale_range}, prob={self.prob})"


class RandomTranslation:
    """
    Apply random translation to images and labels.
    
    Args:
        translation_range: Range for translation in pixels (x, y) - e.g., (15.0, 15.0)
        prob: Probability of applying translation
        mode: Interpolation mode ('bilinear' or 'nearest')
    """
    
    def __init__(
        self, 
        translation_range: Tuple[float, float] = (15.0, 15.0), 
        prob: float = 0.5,
        mode: str = 'bilinear'
    ):
        self.translation_range = translation_range
        self.prob = prob
        self.mode = mode
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Apply random translation."""
        if random.random() > self.prob:
            return data
        
        # Sample translation values
        tx = random.uniform(-self.translation_range[0], self.translation_range[0])
        ty = random.uniform(-self.translation_range[1], self.translation_range[1])
        
        if isinstance(data, list):
            result = []
            for i, item in enumerate(data):
                # Use nearest interpolation for labels (typically last item)
                interp_mode = 'nearest' if i == len(data) - 1 else self.mode
                result.append(self._translate_tensor(item, tx, ty, interp_mode))
            return result
        else:
            return self._translate_tensor(data, tx, ty, self.mode)
    
    def _translate_tensor(self, tensor: torch.Tensor, tx: float, ty: float, mode: str) -> torch.Tensor:
        """Translate tensor by specified amounts."""
        if tensor.ndim < 2:
            return tensor
        
        # Handle dtype conversion for grid_sample compatibility
        original_dtype = tensor.dtype
        needs_dtype_conversion = original_dtype in [torch.long, torch.int, torch.int64, torch.int32]
        
        if needs_dtype_conversion:
            tensor = tensor.float()
        
        # Normalize translation to [-1, 1] range based on tensor size
        # For 2D: use last two dimensions; for 3D: use middle two dimensions
        if tensor.ndim == 2:
            height, width = tensor.shape
            norm_tx = 2.0 * tx / width
            norm_ty = 2.0 * ty / height
        elif tensor.ndim == 3:
            _, height, width = tensor.shape
            norm_tx = 2.0 * tx / width
            norm_ty = 2.0 * ty / height
        else:
            # For higher dimensions, use last two spatial dimensions
            height, width = tensor.shape[-2:]
            norm_tx = 2.0 * tx / width
            norm_ty = 2.0 * ty / height
        
        # Create translation matrix
        translation_matrix = torch.tensor([
            [1, 0, norm_tx],
            [0, 1, norm_ty]
        ], dtype=torch.float32)
        
        # Add batch dimension if needed
        if tensor.ndim == 2:
            tensor = tensor.unsqueeze(0).unsqueeze(0)
            squeeze_dims = True
        elif tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)
            squeeze_dims = False
        else:
            squeeze_dims = False
        
        # Create grid and apply translation
        grid = F.affine_grid(
            translation_matrix.unsqueeze(0), 
            tensor.size(),
            align_corners=False
        )
        
        translated = F.grid_sample(
            tensor, 
            grid, 
            mode=mode, 
            align_corners=False,
            padding_mode='border'
        )
        
        # Remove added dimensions
        if squeeze_dims:
            translated = translated.squeeze(0).squeeze(0)
        elif tensor.ndim == 4:
            translated = translated.squeeze(0)
        
        # Convert back to original dtype if needed
        if needs_dtype_conversion:
            if mode == 'nearest':
                # For nearest interpolation, round and convert back
                translated = translated.round().to(original_dtype)
            else:
                # For other interpolation modes, threshold at 0.5 for binary labels
                translated = (translated > 0.5).to(original_dtype)
        
        return translated
    
    def __repr__(self) -> str:
        return f"RandomTranslation(translation_range={self.translation_range}, prob={self.prob})"


class RandomNoise:
    """
    Add random Gaussian noise to images.
    
    Args:
        noise_std: Standard deviation of Gaussian noise
        prob: Probability of applying noise
    """
    
    def __init__(self, noise_std: float = 0.01, prob: float = 0.5):
        self.noise_std = noise_std
        self.prob = prob
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Add random noise."""
        if random.random() > self.prob:
            return data
        
        if isinstance(data, list):
            # Apply noise only to first item (image)
            result = data.copy()
            result[0] = self._add_noise(result[0])
            return result
        else:
            return self._add_noise(data)
    
    def _add_noise(self, tensor: torch.Tensor) -> torch.Tensor:
        """Add Gaussian noise to tensor."""
        noise = torch.randn_like(tensor) * self.noise_std
        return tensor + noise
    
    def __repr__(self) -> str:
        return f"RandomNoise(noise_std={self.noise_std}, prob={self.prob})"


class RandomBrightnessContrast:
    """
    Randomly adjust brightness and contrast.
    
    Args:
        brightness_range: Range for brightness adjustment
        contrast_range: Range for contrast adjustment
        prob: Probability of applying adjustment
    """
    
    def __init__(
        self, 
        brightness_range: Tuple[float, float] = (-0.1, 0.1),
        contrast_range: Tuple[float, float] = (0.9, 1.1),
        prob: float = 0.5
    ):
        self.brightness_range = brightness_range
        self.contrast_range = contrast_range
        self.prob = prob
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Apply random brightness/contrast adjustment."""
        if random.random() > self.prob:
            return data
        
        brightness = random.uniform(*self.brightness_range)
        contrast = random.uniform(*self.contrast_range)
        
        if isinstance(data, list):
            # Apply only to first item (image)
            result = data.copy()
            result[0] = self._adjust_brightness_contrast(result[0], brightness, contrast)
            return result
        else:
            return self._adjust_brightness_contrast(data, brightness, contrast)
    
    def _adjust_brightness_contrast(self, tensor: torch.Tensor, brightness: float, contrast: float) -> torch.Tensor:
        """Adjust brightness and contrast of tensor."""
        # Apply contrast then brightness
        tensor = tensor * contrast + brightness
        return torch.clamp(tensor, 0, 1)
    
    def __repr__(self) -> str:
        return f"RandomBrightnessContrast(brightness_range={self.brightness_range}, contrast_range={self.contrast_range})"


class RandomFieldBias:
    """
    Add random field bias to simulate MRI intensity inhomogeneity.
    
    Args:
        bias_strength_range: Range for bias strength (min, max) - e.g., (0.1, 0.5)
        spatial_freq_range: Range for spatial frequency (min, max) - e.g., (0.3, 0.8)
        num_peaks_range: Range for number of peaks (min, max) - e.g., (1, 3)
        prob: Probability of applying field bias
    """
    
    def __init__(
        self, 
        bias_strength_range: Tuple[float, float] = (0.1, 0.4), 
        spatial_freq_range: Tuple[float, float] = (0.3, 0.8),
        num_peaks_range: Tuple[int, int] = (1, 3),
        prob: float = 0.3
    ):
        self.bias_strength_range = bias_strength_range
        self.spatial_freq_range = spatial_freq_range
        self.num_peaks_range = num_peaks_range
        self.prob = prob
    
    def __call__(self, data: Union[torch.Tensor, List[torch.Tensor]]) -> Union[torch.Tensor, List[torch.Tensor]]:
        """Apply random field bias."""
        if random.random() > self.prob:
            return data
        
        if isinstance(data, list):
            # Apply bias only to first item (image)
            result = data.copy()
            result[0] = self._add_field_bias(result[0])
            return result
        else:
            return self._add_field_bias(data)
    
    def _add_field_bias(self, tensor: torch.Tensor) -> torch.Tensor:
        """Add field bias to tensor."""
        if tensor.ndim < 2:
            return tensor
        
        # Generate random bias field with random parameters
        bias_field = self._generate_random_bias_field(tensor.shape)
        
        # Apply bias field
        biased_tensor = tensor * bias_field
        
        # Ensure values stay in valid range
        return torch.clamp(biased_tensor, 0, 1)
    
    def _generate_random_bias_field(self, shape: Tuple[int, ...]) -> torch.Tensor:
        """Generate a bias field with random peaks, strength, and spatial frequency."""
        # Randomly sample parameters for this augmentation
        bias_strength = random.uniform(*self.bias_strength_range)
        spatial_freq = random.uniform(*self.spatial_freq_range)
        num_peaks = random.randint(*self.num_peaks_range)
        
        if len(shape) == 2:
            # 2D case
            bias_field = self._generate_2d_bias_field(shape, bias_strength, spatial_freq, num_peaks)
        elif len(shape) == 3:
            # 3D case - generate 2D bias field and apply to each slice
            bias_field_2d = self._generate_2d_bias_field(shape[1:], bias_strength, spatial_freq, num_peaks)
            bias_field = bias_field_2d.unsqueeze(0).expand(shape[0], -1, -1)
        else:
            # Higher dimensional case - treat last two dimensions as spatial
            bias_field_2d = self._generate_2d_bias_field(shape[-2:], bias_strength, spatial_freq, num_peaks)
            bias_field = bias_field_2d.unsqueeze(0).expand(*shape[:-2], -1, -1)
        
        return bias_field
    
    def _generate_2d_bias_field(self, shape: Tuple[int, int], bias_strength: float, 
                               spatial_freq: float, num_peaks: int) -> torch.Tensor:
        """Generate 2D bias field with random peaks."""
        height, width = shape
        
        # Create coordinate grids
        y_coords = torch.linspace(-1, 1, height, dtype=torch.float32)
        x_coords = torch.linspace(-1, 1, width, dtype=torch.float32)
        Y, X = torch.meshgrid(y_coords, x_coords, indexing='ij')
        
        # Initialize bias field
        bias_field = torch.ones_like(X)
        
        # Add random peaks
        for _ in range(num_peaks):
            # Random peak location
            peak_y = random.uniform(-0.8, 0.8)
            peak_x = random.uniform(-0.8, 0.8)
            
            # Random peak characteristics
            peak_amplitude = random.uniform(0.5, 1.5)
            peak_width = spatial_freq * random.uniform(0.5, 1.5)
            
            # Create Gaussian peak
            distance_sq = (Y - peak_y)**2 + (X - peak_x)**2
            peak = peak_amplitude * torch.exp(-distance_sq / (2 * peak_width**2))
            
            bias_field += peak
        
        # Add low-frequency spatial variation
        freq_x = spatial_freq * random.uniform(0.5, 2.0)
        freq_y = spatial_freq * random.uniform(0.5, 2.0)
        phase_x = random.uniform(0, 2 * np.pi)
        phase_y = random.uniform(0, 2 * np.pi)
        
        spatial_variation = (
            0.3 * torch.sin(2 * np.pi * freq_x * X + phase_x) +
            0.3 * torch.cos(2 * np.pi * freq_y * Y + phase_y)
        )
        
        bias_field += spatial_variation
        
        # Normalize to [1 - bias_strength, 1 + bias_strength]
        bias_field = (bias_field - bias_field.min()) / (bias_field.max() - bias_field.min())
        bias_field = 1.0 + bias_strength * (2.0 * bias_field - 1.0)
        
        return bias_field
    
    def __repr__(self) -> str:
        return f"RandomFieldBias(bias_strength_range={self.bias_strength_range}, spatial_freq_range={self.spatial_freq_range}, num_peaks_range={self.num_peaks_range}, prob={self.prob})"


def create_training_transforms(
    enable_flips: bool = True,
    enable_rotation: bool = True,
    enable_scale: bool = True,
    enable_translation: bool = True,
    enable_noise: bool = True,
    enable_brightness: bool = True,
    enable_field_bias: bool = True,
    rotation_angle: float = 10.0,
    scale_range: Tuple[float, float] = (0.8, 1.15),
    translation_range: Tuple[float, float] = (15.0, 15.0),
    noise_std: float = 0.01,
    brightness_range: List[float] = None,
    contrast_range: List[float] = None,
    bias_strength_range: Tuple[float, float] = (0.1, 0.4),
    spatial_freq_range: Tuple[float, float] = (0.3, 0.8),
    num_peaks_range: Tuple[int, int] = (1, 3),
    prob_flips: float = 0.5,
    prob_rotation: float = 0.3,
    prob_scale: float = 0.3,
    prob_translation: float = 0.3,
    prob_noise: float = 0.3,
    prob_brightness: float = 0.3,
    prob_field_bias: float = 0.3
) -> Compose:
    """
    Create a standard set of training transforms.
    
    Args:
        enable_flips: Whether to include random flips
        enable_rotation: Whether to include random rotation
        enable_scale: Whether to include random scaling
        enable_translation: Whether to include random translation
        enable_noise: Whether to include random noise
        enable_brightness: Whether to include brightness/contrast adjustment
        enable_field_bias: Whether to include field bias simulation
        rotation_angle: Maximum rotation angle in degrees
        scale_range: Range for scaling factor (min, max)
        translation_range: Range for translation in pixels (x, y)
        noise_std: Standard deviation for Gaussian noise
        brightness_range: Range for brightness adjustment
        contrast_range: Range for contrast adjustment
        bias_strength_range: Range for field bias strength (min, max)
        spatial_freq_range: Range for spatial frequency (min, max)
        num_peaks_range: Range for number of peaks (min, max)
        prob_flips: Probability of applying flips (0.0 to 1.0)
        prob_rotation: Probability of applying rotation (0.0 to 1.0)
        prob_scale: Probability of applying scaling (0.0 to 1.0)
        prob_translation: Probability of applying translation (0.0 to 1.0)
        prob_noise: Probability of applying noise (0.0 to 1.0)
        prob_brightness: Probability of applying brightness/contrast (0.0 to 1.0)
        prob_field_bias: Probability of applying field bias (0.0 to 1.0)
        
    Returns:
        Composed transforms for training
    """
    transforms = []
    
    # Set default values if not provided
    if brightness_range is None:
        brightness_range = [-0.1, 0.1]
    if contrast_range is None:
        contrast_range = [0.9, 1.1]
    
    if enable_flips:
        transforms.append(RandomFlip(axes=[1, 2], prob=prob_flips))
    
    if enable_rotation:
        transforms.append(RandomRotation(max_angle=rotation_angle, prob=prob_rotation))
    
    if enable_scale:
        transforms.append(RandomScale(scale_range=scale_range, prob=prob_scale))
    
    if enable_translation:
        transforms.append(RandomTranslation(translation_range=translation_range, prob=prob_translation))
    
    if enable_noise:
        transforms.append(RandomNoise(noise_std=noise_std, prob=prob_noise))
    
    if enable_brightness:
        transforms.append(RandomBrightnessContrast(
            brightness_range=brightness_range,
            contrast_range=contrast_range,
            prob=prob_brightness
        ))
    
    if enable_field_bias:
        transforms.append(RandomFieldBias(
            bias_strength_range=bias_strength_range,
            spatial_freq_range=spatial_freq_range,
            num_peaks_range=num_peaks_range,
            prob=prob_field_bias
        ))
    
    return Compose(transforms)


def create_transforms_from_config(augmentation_config: dict) -> Compose:
    """
    Create training transforms from augmentation configuration.
    
    Args:
        augmentation_config: Dictionary containing augmentation settings
        
    Returns:
        Composed transforms for training
    """
    # Helper function to convert lists to tuples for range parameters
    def to_tuple(value, default):
        if value is None:
            return default
        if isinstance(value, list):
            return tuple(value)
        return value
    
    return create_training_transforms(
        enable_flips=augmentation_config.get('enable_flips', True),
        enable_rotation=augmentation_config.get('enable_rotation', True),
        enable_scale=augmentation_config.get('enable_scale', True),
        enable_translation=augmentation_config.get('enable_translation', True),
        enable_noise=augmentation_config.get('enable_noise', True),
        enable_brightness=augmentation_config.get('enable_brightness', True),
        enable_field_bias=augmentation_config.get('enable_field_bias', True),
        rotation_angle=augmentation_config.get('rotation_angle', 10.0),
        scale_range=to_tuple(augmentation_config.get('scale_range'), (0.8, 1.15)),
        translation_range=to_tuple(augmentation_config.get('translation_range'), (15.0, 15.0)),
        noise_std=augmentation_config.get('noise_std', 0.01),
        brightness_range=augmentation_config.get('brightness_range', [-0.1, 0.1]),
        contrast_range=augmentation_config.get('contrast_range', [0.9, 1.1]),
        bias_strength_range=to_tuple(augmentation_config.get('bias_strength_range'), (0.1, 0.4)),
        spatial_freq_range=to_tuple(augmentation_config.get('spatial_freq_range'), (0.3, 0.8)),
        num_peaks_range=to_tuple(augmentation_config.get('num_peaks_range'), (1, 3)),
        prob_flips=augmentation_config.get('prob_flips', 0.5),
        prob_rotation=augmentation_config.get('prob_rotation', 0.3),
        prob_scale=augmentation_config.get('prob_scale', 0.3),
        prob_translation=augmentation_config.get('prob_translation', 0.3),
        prob_noise=augmentation_config.get('prob_noise', 0.3),
        prob_brightness=augmentation_config.get('prob_brightness', 0.3),
        prob_field_bias=augmentation_config.get('prob_field_bias', 0.3)
    )


def create_validation_transforms() -> Compose:
    """
    Create transforms for validation (no augmentation).
    
    Returns:
        Composed transforms for validation
    """
    return Compose([
        # Only normalization, no augmentation
        NormalizeIntensity()
    ])