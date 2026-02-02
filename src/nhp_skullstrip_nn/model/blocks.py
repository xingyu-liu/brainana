"""
Reusable neural network building blocks.

This module contains foundational building blocks for constructing
neural network architectures, including 2D and 3D convolution blocks
with various configurations.
"""

from typing import Optional
import torch.nn as nn


def Conv2dBlock(
    dim_in: int, 
    dim_out: int,
    kernel_size: int = 3, 
    stride: int = 1, 
    padding: int = 1,
    bias: bool = True, 
    use_inst_norm: bool = True
) -> nn.Sequential:
    """
    Create a 2D convolution block with optional instance normalization.
    
    Args:
        dim_in: Input channels
        dim_out: Output channels
        kernel_size: Convolution kernel size
        stride: Convolution stride
        padding: Convolution padding
        bias: Whether to use bias in convolution layers
        use_inst_norm: Whether to use instance normalization
        
    Returns:
        Sequential module containing the convolution block
    """
    if use_inst_norm:
        return nn.Sequential(
            nn.Conv2d(dim_in, dim_out, kernel_size=kernel_size, stride=stride, padding=padding, bias=bias),
            nn.InstanceNorm2d(dim_out),
            nn.LeakyReLU(0.1),
            nn.Conv2d(dim_out, dim_out, kernel_size=kernel_size, stride=stride, padding=padding, bias=bias),
            nn.InstanceNorm2d(dim_out),
            nn.LeakyReLU(0.1)
        )
    else:
        return nn.Sequential(
            nn.Conv2d(dim_in, dim_out, kernel_size=kernel_size, stride=stride, padding=padding, bias=bias),
            nn.LeakyReLU(0.1),
            nn.Conv2d(dim_out, dim_out, kernel_size=kernel_size, stride=stride, padding=padding, bias=bias),
            nn.LeakyReLU(0.1)
        )


def UpConv2dBlock(
    dim_in: int, 
    dim_out: int, 
    kernel_size: int = 4, 
    stride: int = 2, 
    padding: int = 1,
    bias: bool = True
) -> nn.Sequential:
    """
    Create a 2D upsampling convolution block.
    
    Args:
        dim_in: Input channels
        dim_out: Output channels
        kernel_size: Transposed convolution kernel size
        stride: Transposed convolution stride
        padding: Transposed convolution padding
        bias: Whether to use bias
        
    Returns:
        Sequential module containing the upconv block
    """
    return nn.Sequential(
        nn.ConvTranspose2d(dim_in, dim_out, kernel_size=kernel_size, stride=stride, padding=padding, bias=bias),
        nn.LeakyReLU(0.1)
    )