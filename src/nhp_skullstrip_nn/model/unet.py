import torch
import torch.nn as nn
from .blocks import Conv2dBlock, UpConv2dBlock

def weights_init(m):
    """Initialize weights for the model."""
    if isinstance(m, nn.Conv2d):
        nn.init.normal_(m.weight.data)
        if m.bias is not None:
            nn.init.constant_(m.bias.data, 0)

class UNet2d(nn.Module):
    """
    2D U-Net model for image segmentation.
    
    Args:
        dim_in: Number of input channels
        num_conv_block: Number of convolution blocks in encoder/decoder
        kernel_root: Base number of kernels (doubles at each level)
        use_inst_norm: Whether to use instance normalization
        num_classes: Number of output classes (default: 2 for binary segmentation)
        apply_softmax: If True, applies softmax in forward pass during inference.
                      If False, returns raw logits. Use False for training with CrossEntropyLoss,
                      True for inference and probability-based metrics.
    """
    def __init__(self, 
            dim_in=6, num_conv_block=3, kernel_root=4, 
            use_inst_norm=True, num_classes=2, apply_softmax=False):
        super(UNet2d, self).__init__()
        self.layers=dict()
        self.num_conv_block=num_conv_block
        self.num_classes = num_classes
        self.apply_softmax = apply_softmax
        # Conv Layers
        for n in range(num_conv_block):
            if n==0:
                setattr(self, "conv%d" % (n+1), Conv2dBlock(dim_in, kernel_root, use_inst_norm=use_inst_norm))
            else:
                setattr(self, "conv%d" % (n+1), Conv2dBlock(kernel_root*(2**(n-1)), kernel_root*(2**n), use_inst_norm=use_inst_norm))

        # UpConv Layers
        for n in range(num_conv_block-1):
            i=num_conv_block-1-n
            setattr(self, "upconv%dto%d" % (i+1, i), UpConv2dBlock(kernel_root*(2**i), kernel_root*(2**(i-1))))
            setattr(self, "conv%dm" % (i), Conv2dBlock(kernel_root*(2**i), kernel_root*(2**(i-1)), use_inst_norm=use_inst_norm))    
        setattr(self, "max_pool", nn.MaxPool2d(2))
        setattr(self, "out_layer", nn.Conv2d(kernel_root, num_classes, 3, 1, 1))
        
        # Weight Initialization
        self.apply(weights_init)

    def forward(self, x):
        num_conv_block=self.num_conv_block
        conv_out=dict()
        for n in range(num_conv_block):
            if n==0:
                conv_out["conv%d" % (n+1)]=getattr(self, "conv%d" % (n+1))(x)
            else:
                conv_out["conv%d" % (n+1)]=getattr(self, "conv%d" % (n+1))(self.max_pool(conv_out["conv%d" % n])) 

        for n in range(num_conv_block-1):
            i=num_conv_block-1-n
            if n==0:
                tmp=torch.cat(
                        (
                        getattr(self, "upconv%dto%d" % (i+1, i))(conv_out["conv%d" % (i+1)]),
                        conv_out["conv%d" % (i)]
                        ),
                        1
                    )
            else:
                tmp=torch.cat(
                        (
                        getattr(self, "upconv%dto%d" % (i+1, i))(out),
                        conv_out["conv%d" % (i)]
                        ),
                        1
                    )

            out=getattr(self, "conv%dm" % (i))(tmp)

        out=self.out_layer(out)
        
        # Apply softmax if requested and not in training mode
        if self.apply_softmax and not self.training:
            out = torch.softmax(out, dim=1)
            
        return out
