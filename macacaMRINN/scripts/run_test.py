#!/usr/bin/env python3
"""
Test script for macacaMRINN.
"""

import os
import sys
import argparse
import glob
import traceback

from ..inference.evaluate_testset import (
    evaluate_test_set_from_training, 
    evaluate_test_set_from_paths)


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate trained model on test set using robust inference pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use training output directory (reads testdataset_info.json automatically)
  run_test.py --training-output /path/to/training/output
  
  # Use training output with specific model
  run_test.py --training-output /path/to/training/output --model /path/to/best_model.pth
  
  # Use explicit test directories (legacy mode)
  run_test.py --model /path/to/model.pth --test-images /path/to/test/images --test-labels /path/to/test/labels --output /path/to/results
  
  # Save only labels, no probability maps
  run_test.py --training-output /path/to/training/output --no-save-prob-map
  
  # Save both labels and probability maps
  run_test.py --training-output /path/to/training/output --save-prob-map
  
  # Save only probability maps, no labels
  run_test.py --training-output /path/to/training/output --no-save-label --save-prob-map
        """
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--training-output', 
                           help='Training output directory containing testdataset_info.json (recommended)')
    mode_group.add_argument('--test-images', 
                           help='Directory containing test images (legacy mode, use with --test-labels)')
    parser.add_argument('--test-labels', 
                       help='Directory containing test labels (required with --test-images)')
    parser.add_argument('--output', 
                       help='Output directory (required with --test-images mode)')
    parser.add_argument('--model', 
                       help='Path to model checkpoint (auto-detected in training-output mode)')
    parser.add_argument('--device', default='auto',
                       help='Device to use (auto, cpu, cuda:0, etc.)')
    parser.add_argument('--save-label', action='store_true', default=True,
                       help='Save label output (default: True)')
    parser.add_argument('--no-save-label', action='store_false', dest='save_label',
                       help='Disable saving label output')
    parser.add_argument('--save-prob-map', action='store_true', default=False,
                       help='Save probability map output (default: False)')
    parser.add_argument('--no-save-prob-map', action='store_false', dest='save_prob_map',
                       help='Disable saving probability map output')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress verbose output')
    
    args = parser.parse_args()
    
    # Validate arguments based on mode
    if args.test_images:
        # Legacy mode validation
        if not args.test_labels:
            parser.error("--test-labels is required when using --test-images")
        if not args.model:
            parser.error("--model is required when using --test-images")
        if not args.output:
            parser.error("--output is required when using --test-images")
    
    # Validate file/directory existence
    if args.model and not os.path.exists(args.model):
        print(f"❌ Error: Model file not found: {args.model}")
        sys.exit(1)
    
    if args.test_images and not os.path.exists(args.test_images):
        print(f"❌ Error: Test images directory not found: {args.test_images}")
        sys.exit(1)
    
    if args.test_labels and not os.path.exists(args.test_labels):
        print(f"❌ Error: Test labels directory not found: {args.test_labels}")
        sys.exit(1)
    
    if args.training_output and not os.path.exists(args.training_output):
        print(f"❌ Error: Training output directory not found: {args.training_output}")
        sys.exit(1)
    
    try:
        if args.training_output:
            # Training output mode (recommended)
            print("🧪 Starting test evaluation using training output directory...")
            if not args.quiet:
                print(f"📁 Training output: {args.training_output}")
                if args.model:
                    print(f"🤖 Model: {args.model}")
                print("-" * 50)
            
            result = evaluate_test_set_from_training(
                training_output_dir=args.training_output,
                model_path=args.model,
                device=args.device,
                save_label=args.save_label,
                save_prob_map=args.save_prob_map,
                verbose=not args.quiet
            )
            
        else:
            # Legacy mode (explicit paths)
            print("🧪 Starting test evaluation using explicit paths...")
            if not args.quiet:
                print(f"🤖 Model: {args.model}")
                print(f"📥 Test images: {args.test_images}")
                print(f"📥 Test labels: {args.test_labels}")
                print(f"📤 Output: {args.output}")
                print("-" * 50)
            
            # Create output directory
            os.makedirs(args.output, exist_ok=True)
            
            # Get test file lists
            test_images = sorted(glob.glob(os.path.join(args.test_images, '*.nii.gz')))
            test_labels = sorted(glob.glob(os.path.join(args.test_labels, '*.nii.gz')))
            
            if len(test_images) != len(test_labels):
                print(f"⚠️  Warning: Mismatch in number of images ({len(test_images)}) and labels ({len(test_labels)})")
            
            result = evaluate_test_set_from_paths(
                test_images=test_images,
                test_labels=test_labels,
                model_path=args.model,
                output_dir=args.output,
                device=args.device,
                save_label=args.save_label,
                save_prob_map=args.save_prob_map,
                verbose=not args.quiet
            )
        
        # Print final summary
        summary = result['summary']
        print("\n" + "="*60)
        print("🎉 TEST EVALUATION COMPLETED SUCCESSFULLY!")
        print("="*60)
        print(f"📊 Results saved to: {result['eval_dir']}")
        print(f"📈 Total files: {summary['total_files']}")
        print(f"✅ Successful: {summary['successful_files']}")
        if summary['failed_files'] > 0:
            print(f"❌ Failed: {summary['failed_files']}")
        print(f"📊 Mean Dice: {summary['mean_dice']:.4f} ± {summary['std_dice']:.4f}")
        print(f"📊 Mean IoU: {summary['mean_iou']:.4f} ± {summary['std_iou']:.4f}")
        print(f"📊 Best Dice: {summary['max_dice']:.4f}")
        print(f"📊 Worst Dice: {summary['min_dice']:.4f}")
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        if not args.quiet:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
