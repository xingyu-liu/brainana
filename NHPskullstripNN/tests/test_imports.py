#!/usr/bin/env python3
"""
Test script to verify all imports work correctly.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test all the main imports."""
    print("Testing imports...")
    
    try:
        # Test config imports
        print("✓ Testing config imports...")
        from config import TrainingConfig
        print("  ✓ TrainingConfig imported successfully")
        
        # Test model imports
        print("✓ Testing model imports...")
        from model.unet import UNet2d
        print("  ✓ UNet2d imported successfully")
        
        # Test utils imports
        print("✓ Testing utils imports...")
        from utils import get_device
        from utils.log import setup_logging, get_logger
        print("  ✓ Utils imported successfully")
        
        # Test model loader imports
        print("✓ Testing model loader imports...")
        from model.model_loader import ModelLoader
        print("  ✓ ModelLoader imported successfully")
        
        # Test data imports
        print("✓ Testing data imports...")
        from data.datasets import VolumeDataset, BlockDataset, FileListDataset
        print("  ✓ Data datasets imported successfully")
        
        # Test train imports
        print("✓ Testing train imports...")
        from train.trainer import Trainer
        from train.metrics import compute_foreground_dice
        from train.losses import DiceLoss
        print("  ✓ Train modules imported successfully")
        
        # Test inference imports
        print("✓ Testing inference imports...")
        from inference.prediction import predict_volumes
        print("  ✓ Inference modules imported successfully")
        
        print("\n🎉 All imports successful! The relative import conversion is working correctly.")
        return True
        
    except ImportError as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_individual_modules():
    """Test each module individually to identify specific issues."""
    modules_to_test = [
        ("config", "TrainingConfig"),
        ("model.unet", "UNet2d"),
        ("utils", "get_device"),
        ("model.model_loader", "ModelLoader"),
        ("utils.log", "setup_logging"),
        ("data.datasets", "VolumeDataset"),
        ("train.trainer", "Trainer"),
        ("train.metrics", "compute_foreground_dice"), 
        ("train.losses", "DiceLoss"),
        ("inference.prediction", "predict_volumes")
    ]
    
    results = {}
    
    for module_name, class_name in modules_to_test:
        try:
            print(f"Testing {module_name}.{class_name}...")
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)
            print(f"  ✓ {module_name}.{class_name} imported successfully")
            results[f"{module_name}.{class_name}"] = "SUCCESS"
        except Exception as e:
            print(f"  ❌ {module_name}.{class_name} failed: {e}")
            results[f"{module_name}.{class_name}"] = f"FAILED: {e}"
    
    return results

if __name__ == "__main__":
    print("=" * 60)
    print("COMPREHENSIVE IMPORT TEST")
    print("=" * 60)
    
    # First try the complete test
    success = test_imports()
    
    if not success:
        print("\n" + "=" * 60)
        print("INDIVIDUAL MODULE TESTING")
        print("=" * 60)
        results = test_individual_modules()
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for module, result in results.items():
            if "SUCCESS" in result:
                print(f"✓ {module}")
            else:
                print(f"❌ {module}: {result}")
    
    sys.exit(0 if success else 1)
