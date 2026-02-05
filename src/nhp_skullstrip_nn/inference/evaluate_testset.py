#!/usr/bin/env python3
"""
Evaluation module for nhp_skullstrip_nn test sets.
"""

import os
import sys
import argparse
import glob
import traceback
from datetime import datetime
import torch
import numpy as np
import pandas as pd
import json
from typing import Dict, List, Optional
from matplotlib import pyplot as plt


from .prediction import predict_volumes
from ..model import ModelLoader
from ..utils import get_device, setup_logging
from ..config import TrainingConfig


def evaluate_test_set_from_training(training_output_dir: str, 
                                   model_path: Optional[str] = None,
                                   output_subdir: str = "test_evaluation",
                                   config: Optional[TrainingConfig] = None,
                                   device: str = "auto",
                                   save_label: bool = True,
                                   save_prob_map: bool = False,
                                   verbose: bool = True) -> Dict:
    """
    Evaluate test set using training output directory and testdataset_info.json.
    
    Args:
        training_output_dir: Directory containing testdataset_info.json
        model_path: Path to model checkpoint (if None, uses best model from training)
        output_subdir: Subdirectory name for evaluation results
        config: Training configuration (if None, tries to load from checkpoint)
        device: Device to use for inference
        save_label: Whether to save label output (default: True)
        save_prob_map: Whether to save probability map output (default: False)
        verbose: Whether to print verbose output
        
    Returns:
        Dictionary containing evaluation results and statistics
    """
    logger = setup_logging('nhp_skullstrip_nn.test_evaluation') if verbose else None
    
    if logger:
        logger.info("🧪 Starting comprehensive test set evaluation...")
        logger.info(f"📁 Training output dir: {training_output_dir}")
    
    # Read testdataset_info.json
    test_info_path = os.path.join(training_output_dir, 'testdataset_info.json')
    if not os.path.exists(test_info_path):
        raise FileNotFoundError(f"testdataset_info.json not found: {test_info_path}")
    
    with open(test_info_path, 'r') as f:
        test_info = json.load(f)
    
    test_images = test_info['images']
    test_labels = test_info['labels']
    
    if logger:
        logger.info(f"📊 Found {len(test_images)} test files from training split")
    
    # Determine model path if not provided
    if model_path is None:
        # Look for best model checkpoint
        checkpoints_dir = os.path.join(training_output_dir, 'checkpoints')
        possible_models = [
            os.path.join(checkpoints_dir, 'best_model.pth'),
            os.path.join(training_output_dir, 'best_model.pth'),
            os.path.join(training_output_dir, 'final_model.pth')
        ]
        
        for model_candidate in possible_models:
            if os.path.exists(model_candidate):
                model_path = model_candidate
                break
        
        if model_path is None:
            raise FileNotFoundError(f"No model checkpoint found in {training_output_dir}")
    
    if logger:
        logger.info(f"🤖 Using model: {model_path}")
    
    # Create evaluation output directory
    eval_dir = os.path.join(training_output_dir, output_subdir)
    os.makedirs(eval_dir, exist_ok=True)
    
    # Load model and config
    if config is None:
        config = load_config_from_checkpoint(model_path, logger)
    
    model = ModelLoader.load_model_from_file(
        model_path=model_path,
        device_id=device if device != "auto" else get_device(),
        config=config,
        logger=logger
    )
    
    # Evaluate each test file
    results = []
    total_files = len(test_images)
    
    for i, (image_path, label_path) in enumerate(zip(test_images, test_labels)):
        result = evaluate_single_volume(
            model=model,
            image_path=image_path,
            label_path=label_path,
            config=config,
            output_dir=eval_dir,
            file_index=i,
            save_label=save_label,
            save_prob_map=save_prob_map,
            logger=logger
        )
        results.append(result)
        if logger:
            print(f"🔄 {i+1}/{total_files}: {os.path.basename(image_path)}, Dice: {result['dice_score']:.2f}, IoU: {result['iou_score']:.2f}")
    
    # Generate comprehensive evaluation summary
    summary_stats = generate_evaluation_summary(results, eval_dir, logger)
    
    if logger:
        logger.info("✅ Test set evaluation completed!")
        logger.info(f"📊 Results saved to: {eval_dir}")
        logger.info(f"📈 Mean Dice: {summary_stats['mean_dice']:.2f} ± {summary_stats['std_dice']:.2f}")
        logger.info(f"📈 Mean IoU: {summary_stats['mean_iou']:.2f} ± {summary_stats['std_iou']:.2f}")
    
    return {
        'results': results,
        'summary': summary_stats,
        'eval_dir': eval_dir
    }


def evaluate_test_set_from_paths(test_images: List[str],
                                test_labels: List[str], 
                                model_path: str,
                                output_dir: str,
                                config: Optional[TrainingConfig] = None,
                                device: str = "auto",
                                save_label: bool = True,
                                save_prob_map: bool = False,
                                verbose: bool = True) -> Dict:
    """
    Evaluate test set from explicit file paths.
    
    Args:
        test_images: List of test image file paths
        test_labels: List of test label file paths
        model_path: Path to model checkpoint
        output_dir: Output directory for results
        config: Training configuration
        device: Device to use for inference
        save_label: Whether to save label output (default: True)
        save_prob_map: Whether to save probability map output (default: False)
        verbose: Whether to print verbose output
        
    Returns:
        Dictionary containing evaluation results and statistics
    """
    logger = setup_logging('nhp_skullstrip_nn.test_evaluation') if verbose else None
    
    if logger:
        logger.info("🧪 Starting test set evaluation from explicit paths...")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load model and config
    if config is None:
        config = load_config_from_checkpoint(model_path, logger)
    
    model = ModelLoader.load_model_from_file(
        model_path=model_path,
        device_id=device if device != "auto" else get_device(),
        config=config,
        logger=logger
    )
    
    # Evaluate each test file
    results = []
    total_files = len(test_images)
    
    for i, (image_path, label_path) in enumerate(zip(test_images, test_labels)):
        if logger:
            logger.info(f"🔄 Processing {i+1}/{total_files}: {os.path.basename(image_path)}")
        
        result = evaluate_single_volume(
            model=model,
            image_path=image_path,
            label_path=label_path,
            config=config,
            output_dir=output_dir,
            file_index=i,
            save_label=save_label,
            save_prob_map=save_prob_map,
            logger=logger
        )
        results.append(result)
    
    # Generate comprehensive evaluation summary
    summary_stats = generate_evaluation_summary(results, output_dir, logger)
    
    if logger:
        logger.info("✅ Test set evaluation completed!")
        logger.info(f"📊 Results saved to: {output_dir}")
    
    return {
        'results': results,
        'summary': summary_stats,
        'eval_dir': output_dir
    }


def evaluate_single_volume(model: torch.nn.Module,
                          image_path: str,
                          label_path: str,
                          config: TrainingConfig,
                          output_dir: str,
                          file_index: int,
                          save_label: bool = True,
                          save_prob_map: bool = False,
                          logger = None) -> Dict:
    """
    Evaluate a single volume using the robust prediction pipeline.
    
    Args:
        model: Loaded model
        image_path: Path to test image
        label_path: Path to test label
        config: Training configuration
        output_dir: Output directory
        file_index: Index of file for naming
        save_label: Whether to save label output (default: True)
        save_prob_map: Whether to save probability map output (default: False)
        logger: Logger instance
        
    Returns:
        Dictionary with evaluation results for this volume
    """
    try:
        file_name = os.path.basename(image_path)
        
        # Create output paths for this volume
        predictions_dir = os.path.join(output_dir, 'predictions')
        os.makedirs(predictions_dir, exist_ok=True)
        
        base_name = file_name.replace('.nii.gz', '')
        pred_output_path = os.path.join(predictions_dir, f"{base_name}_pred.nii.gz")
        
        # Run robust prediction using the full inference pipeline
        metrics_result = predict_volumes(
            model=model,
            rescale_dim=getattr(config, 'rescale_dim', 256),
            num_slices=getattr(config, 'num_input_slices', 3),
            num_classes=getattr(config, 'num_classes', 2),  # Use num_classes from checkpoint config
            input_image=image_path,
            input_label=label_path,
            save_label=save_label,
            save_prob_map=save_prob_map,
            output_path=pred_output_path,
            compute_metrics=True,
            force_softmax=None,  # Let the function determine
            erosion_dilation_iterations=0,  # Can be made configurable
            plot_QC_snaps=True,
            verbose=False
        )
        
        # Extract metrics from prediction result
        dice_score = 0.0
        iou_score = 0.0
        
        if metrics_result and base_name in metrics_result:
            volume_metrics = metrics_result[base_name]
            # Handle both binary and multiclass metrics
            dice_score = volume_metrics.get('dice', volume_metrics.get('mean_dice', volume_metrics.get('brain_tissue_dice', 0.0)))
            iou_score = volume_metrics.get('iou', volume_metrics.get('mean_iou', 0.0))
        elif metrics_result:
            # If base_name not found, take the first (and likely only) result
            first_key = list(metrics_result.keys())[0]
            volume_metrics = metrics_result[first_key]
            # Handle both binary and multiclass metrics
            dice_score = volume_metrics.get('dice', volume_metrics.get('mean_dice', volume_metrics.get('brain_tissue_dice', 0.0)))
            iou_score = volume_metrics.get('iou', volume_metrics.get('mean_iou', 0.0))
        
        return {
            'file_name': file_name,
            'dice_score': float(dice_score),
            'iou_score': float(iou_score),
            'image_path': image_path,
            'label_path': label_path,
            'pred_path': pred_output_path,
            'status': 'success'
        }
        
    except Exception as e:
        if logger:
            logger.error(f"❌ Error evaluating {image_path}: {e}")
        
        return {
            'file_name': os.path.basename(image_path),
            'dice_score': 0.0,
            'iou_score': 0.0,
            'image_path': image_path,
            'label_path': label_path,
            'error': str(e),
            'status': 'failed'
        }



def generate_evaluation_summary(results: List[Dict], 
                               eval_dir: str,
                               logger = None) -> Dict:
    """Generate comprehensive evaluation summary with statistics and plots."""
    
    # Filter successful results
    successful_results = [r for r in results if r['status'] == 'success']
    failed_results = [r for r in results if r['status'] == 'failed']
    
    if not successful_results:
        raise ValueError("No successful evaluations found!")
    
    # Extract metrics
    dice_scores = [r['dice_score'] for r in successful_results]
    iou_scores = [r['iou_score'] for r in successful_results]
    file_names = [r['file_name'] for r in successful_results]
    
    # Calculate statistics
    stats = {
        'total_files': len(results),
        'successful_files': len(successful_results),
        'failed_files': len(failed_results),
        'mean_dice': float(np.mean(dice_scores)),
        'std_dice': float(np.std(dice_scores)),
        'min_dice': float(np.min(dice_scores)),
        'max_dice': float(np.max(dice_scores)),
        'median_dice': float(np.median(dice_scores)),
        'mean_iou': float(np.mean(iou_scores)),
        'std_iou': float(np.std(iou_scores)),
        'min_iou': float(np.min(iou_scores)),
        'max_iou': float(np.max(iou_scores)),
        'median_iou': float(np.median(iou_scores))
    }
    
    # Save detailed results CSV
    results_df = pd.DataFrame(results)
    csv_path = os.path.join(eval_dir, 'detailed_results.csv')
    results_df.to_csv(csv_path, index=False)
    
    # Save summary statistics
    summary_path = os.path.join(eval_dir, 'summary_statistics.json')
    with open(summary_path, 'w') as f:
        json.dump(stats, f, indent=2)
    
    # Create text summary report
    create_text_summary_report(results, stats, eval_dir)
    
    # Create summary plots
    create_summary_plots(successful_results, stats, eval_dir)
    
    if logger:
        logger.info(f"📊 Summary statistics saved to: {summary_path}")
        logger.info(f"📋 Detailed results saved to: {csv_path}")
    
    return stats


def create_text_summary_report(results: List[Dict], 
                              stats: Dict, 
                              eval_dir: str):
    """Create comprehensive text summary report."""
    summary_file = os.path.join(eval_dir, 'evaluation_summary.txt')
    
    with open(summary_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("COMPREHENSIVE TEST SET EVALUATION SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Evaluation completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total test files: {stats['total_files']}\n")
        f.write(f"Successful evaluations: {stats['successful_files']}\n")
        f.write(f"Failed evaluations: {stats['failed_files']}\n\n")
        
        if stats['successful_files'] > 0:
            f.write("DICE SCORE STATISTICS:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Mean:     {stats['mean_dice']:.2f} ± {stats['std_dice']:.2f}\n")
            f.write(f"Median:   {stats['median_dice']:.2f}\n")
            f.write(f"Range:    {stats['min_dice']:.2f} - {stats['max_dice']:.2f}\n\n")
            
            f.write("IOU SCORE STATISTICS:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Mean:     {stats['mean_iou']:.2f} ± {stats['std_iou']:.2f}\n")
            f.write(f"Median:   {stats['median_iou']:.2f}\n")
            f.write(f"Range:    {stats['min_iou']:.2f} - {stats['max_iou']:.2f}\n\n")
        
        # Individual results
        f.write("INDIVIDUAL RESULTS:\n")
        f.write("-" * 40 + "\n")
        for i, result in enumerate(results):
            if result['status'] == 'success':
                f.write(f"{i+1:3d}. {result['file_name']:<40} "
                       f"Dice: {result['dice_score']:.2f} "
                       f"IoU: {result['iou_score']:.2f}\n")
            else:
                f.write(f"{i+1:3d}. {result['file_name']:<40} "
                       f"ERROR: {result.get('error', 'Unknown error')}\n")


def create_summary_plots(successful_results: List[Dict], 
                        stats: Dict, 
                        eval_dir: str):
    """Create summary visualization plots."""
    dice_scores = [r['dice_score'] for r in successful_results]
    iou_scores = [r['iou_score'] for r in successful_results]
    file_names = [r['file_name'] for r in successful_results]
    
    # 1. Histogram of metrics
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Dice histogram
    ax1.hist(dice_scores, bins=20, alpha=0.7, color='skyblue', edgecolor='black')
    ax1.axvline(stats['mean_dice'], color='red', linestyle='--', 
               label=f"Mean: {stats['mean_dice']:.2f}")
    ax1.axvline(stats['median_dice'], color='orange', linestyle='--', 
               label=f"Median: {stats['median_dice']:.2f}")
    ax1.set_xlabel('Dice Score')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Distribution of Dice Scores')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # IoU histogram
    ax2.hist(iou_scores, bins=20, alpha=0.7, color='lightcoral', edgecolor='black')
    ax2.axvline(stats['mean_iou'], color='red', linestyle='--', 
               label=f"Mean: {stats['mean_iou']:.2f}")
    ax2.axvline(stats['median_iou'], color='orange', linestyle='--', 
               label=f"Median: {stats['median_iou']:.2f}")
    ax2.set_xlabel('IoU Score')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Distribution of IoU Scores')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(eval_dir, 'metrics_distribution.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Individual performance bar chart
    n_files = len(file_names)
    fig_width = max(12, n_files * 0.4)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_width, 12))
    
    x_pos = range(n_files)
    short_names = [f.replace('.nii.gz', '') for f in file_names]
    
    # Dice scores
    bars1 = ax1.bar(x_pos, dice_scores, alpha=0.7, color='skyblue')
    ax1.set_xlabel('Test Files')
    ax1.set_ylabel('Dice Score')
    ax1.set_title('Individual Dice Score Performance')
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(short_names, rotation=45, ha='right')
    ax1.set_ylim(0, 1)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(stats['mean_dice'], color='red', linestyle='--', alpha=0.7)
    
    # IoU scores
    bars2 = ax2.bar(x_pos, iou_scores, alpha=0.7, color='lightcoral')
    ax2.set_xlabel('Test Files')
    ax2.set_ylabel('IoU Score')
    ax2.set_title('Individual IoU Score Performance')
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(short_names, rotation=45, ha='right')
    ax2.set_ylim(0, 1)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(stats['mean_iou'], color='red', linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig(os.path.join(eval_dir, 'individual_performance.png'), dpi=300, bbox_inches='tight')
    plt.close()


def load_config_from_checkpoint(model_path: str, logger = None) -> Optional[TrainingConfig]:
    """Load configuration from model checkpoint."""
    try:
        checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)
        
        if 'config' in checkpoint:
            checkpoint_config = checkpoint['config']
            # Filter to valid parameters
            from dataclasses import fields
            valid_params = {field.name for field in fields(TrainingConfig)}
            filtered_config = {k: v for k, v in checkpoint_config.items() if k in valid_params}
            # Ensure required fields are present (can be empty for inference)
            if 'TRAINING_DATA_DIR' not in filtered_config:
                filtered_config['TRAINING_DATA_DIR'] = ""
            if 'OUTPUT_DIR' not in filtered_config:
                filtered_config['OUTPUT_DIR'] = ""
            if 'modal' not in filtered_config:
                filtered_config['modal'] = ""
            if 'label' not in filtered_config:
                filtered_config['label'] = ""
            config = TrainingConfig(**filtered_config)
            
            if logger:
                logger.info("✅ Configuration loaded from checkpoint")
            return config
        else:
            if logger:
                logger.warning("⚠️  No config found in checkpoint, using defaults")
            return None
            
    except Exception as e:
        if logger:
            logger.warning(f"⚠️  Could not load config from checkpoint: {e}")
        return None


if __name__ == "__main__":
    """Command-line interface for test evaluation."""
    
    parser = argparse.ArgumentParser(
        description='Comprehensive test set evaluation using robust inference pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate using training output directory (reads testdataset_info.json)
  evaluate_test_set.py --training-output /path/to/training/output
  
  # Evaluate with specific model
  evaluate_test_set.py --training-output /path/to/training/output --model /path/to/best_model.pth
  
  # Evaluate with explicit test file paths
  evaluate_test_set.py --test-images /path/to/test/images --test-labels /path/to/test/labels --model /path/to/model.pth --output /path/to/results
        """
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--training-output', 
                           help='Training output directory containing testdataset_info.json')
    mode_group.add_argument('--test-images', 
                           help='Directory containing test images (use with --test-labels)')
    
    # Additional arguments
    parser.add_argument('--test-labels', 
                       help='Directory containing test labels (required with --test-images)')
    parser.add_argument('--model', 
                       help='Path to model checkpoint (auto-detected if not provided)')
    parser.add_argument('--output', 
                       help='Output directory (required with --test-images mode)')
    parser.add_argument('--device', default='auto',
                       help='Device to use (auto, cpu, cuda:0, etc.)')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress verbose output')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.test_images and not args.test_labels:
        parser.error("--test-labels is required when using --test-images")
    
    if args.test_images and not args.output:
        parser.error("--output is required when using --test-images")
    
    try:
        if args.training_output:
            # Training output mode
            result = evaluate_test_set_from_training(
                training_output_dir=args.training_output,
                model_path=args.model,
                device=args.device,
                verbose=not args.quiet
            )
        else:
            # Explicit paths mode  
            test_images = sorted(glob.glob(os.path.join(args.test_images, '*.nii.gz')))
            test_labels = sorted(glob.glob(os.path.join(args.test_labels, '*.nii.gz')))
            
            if len(test_images) != len(test_labels):
                print(f"Warning: Mismatch in number of images ({len(test_images)}) and labels ({len(test_labels)})")
            
            result = evaluate_test_set_from_paths(
                test_images=test_images,
                test_labels=test_labels,
                model_path=args.model,
                output_dir=args.output,
                device=args.device,
                verbose=not args.quiet
            )
        
        print("\n✓ Evaluation completed successfully!")
        print(f"✓ Results saved to: {result['eval_dir']}")
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        if not args.quiet:
            traceback.print_exc()
        sys.exit(1)
