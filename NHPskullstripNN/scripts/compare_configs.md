# Training Configuration Comparison

## Critical Differences

### Learning Rate (MAJOR ISSUE)
| Parameter | NHPskullstripNN | FastSurferCNN | Ratio |
|-----------|------------------|---------------|-------|
| **Learning Rate** | `1.0e-05` (0.00001) | `0.002` | **200x slower!** |
| **Min LR** | `1e-07` | `0.00001` | 100x lower |

**Impact**: The NHPskullstripNN learning rate is **200 times smaller** than FastSurferCNN, which will make training **extremely slow**.

### Batch Size
| Parameter | NHPskullstripNN | FastSurferCNN |
|-----------|------------------|---------------|
| **Batch Size** | `64` | `16` |
| **Effective LR** | 0.00001 × 64 = 0.00064 | 0.002 × 16 = 0.032 |

Even accounting for batch size, FastSurferCNN has **50x higher effective learning rate**.

### Optimizer & Scheduler
| Parameter | NHPskullstripNN | FastSurferCNN |
|-----------|------------------|---------------|
| **Optimizer** | Adam (default) | AdamW |
| **Scheduler** | ReduceLROnPlateau (factor=0.5) | CosineWarmRestarts |
| **Weight Decay** | `0.00001` | `0.0001` (10x higher) |

### Training Duration
| Parameter | NHPskullstripNN | FastSurferCNN |
|-----------|------------------|---------------|
| **Epochs** | `200` | `100` |
| **Early Stopping Patience** | `15` | `20` |

## Recommendations

### For Fine-tuning (Current Setup)
The learning rate of `1.0e-05` is **too conservative** even for fine-tuning. Recommended values:

1. **Conservative fine-tuning**: `1.0e-04` (10x increase)
2. **Moderate fine-tuning**: `5.0e-04` (50x increase) 
3. **Aggressive fine-tuning**: `1.0e-03` (100x increase)

### Suggested Configuration Update

```yaml
# Current (TOO SLOW)
learning_rate: 1.0e-05

# Recommended for fine-tuning
learning_rate: 1.0e-04  # or 5.0e-04 for faster convergence

# Optional: Enable cosine scheduler for better convergence
use_cosine_scheduler: true
min_lr: 1.0e-06  # Minimum learning rate
```

### Why FastSurferCNN is Faster

1. **200x higher learning rate** (0.002 vs 0.00001)
2. **CosineWarmRestarts scheduler** - more aggressive LR schedule
3. **AdamW optimizer** - better weight decay handling
4. **Higher weight decay** (0.0001 vs 0.00001) - better regularization

### Expected Impact

With current LR (`1.0e-05`):
- Training will be **extremely slow**
- May take **200+ epochs** to converge
- Risk of underfitting

With recommended LR (`1.0e-04` to `5.0e-04`):
- **10-50x faster convergence**
- Should see improvement within **10-20 epochs**
- Better utilization of pretrained weights

