from typing import Dict, Any, Optional
import logging
import numpy as np


def update_config_from_bids_metadata(
        config: Dict[str, Any], 
        metadata: Dict[str, Any],
        logger: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """
    Update slice timing configuration based on BIDS metadata.
    
    Args:
        config: Configuration dictionary
        metadata: BIDS metadata dictionary
        
    Returns:
        Updated configuration dictionary
    """
    # Ensure config has the proper nested structure
    if 'func' not in config:
        config['func'] = {}
    if 'slice_timing_correction' not in config['func']:
        config['func']['slice_timing_correction'] = {}
    
    slice_timing_config = config['func']['slice_timing_correction']
    
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Check if slice timing can be enabled
    slice_times = metadata.get('SliceTiming')
    tr = metadata.get('RepetitionTime')
    if not _is_valid_slice_timing_data(slice_times, tr):
        slice_timing_config['enabled'] = False
        logger.warning(f"Config: slice timing longer than repetition time ({np.max(slice_times)} > {tr}) - slice timing correction disabled")
        return config
    
    # Calculate tzero based on slice timing reference
    first, last = min(slice_times), max(slice_times)
    slice_time_ref = slice_timing_config.get('slice_time_ref')
    tzero = np.round(first + slice_time_ref * (last - first), 3)
    
    # Update slice timing configuration
    slice_timing_config.update({
        'enabled': True,
        'slice_timing': slice_times,
        'tzero': tzero,
        'repetition_time': tr
    })

    # Determine slice encoding direction
    slice_direction = _determine_slice_encoding_direction(metadata)
    if slice_direction:
        slice_timing_config['slice_encoding_direction'] = slice_direction
    
        logger.info(f"Config: slice timing correction updated from BIDS metadata and enabled")

    return config

def _is_valid_slice_timing_data(slice_times: Any, tr: Any) -> bool:
    """
    Validate slice timing data requirements.
    
    Args:
        slice_times: SliceTiming array from BIDS metadata
        tr: RepetitionTime from BIDS metadata
        
    Returns:
        True if slice timing data is valid, False otherwise
    """
    # Check slice times
    if not slice_times or not isinstance(slice_times, (list, tuple)) or len(slice_times) == 0:
        return False
    
    # Check repetition time
    if tr is None or not isinstance(tr, (int, float)) or tr <= 0:
        return False
    
    # if max of slice times is greater than tr, return False
    if np.max(slice_times) > tr:
        return False
    
    return True


def _determine_slice_encoding_direction(metadata: Dict[str, Any]) -> Optional[str]:
    """
    Determine slice encoding direction from BIDS metadata.
    
    Args:
        metadata: BIDS metadata dictionary
        
    Returns:
        Slice encoding direction string or None if not determinable
    """
    # First try direct SliceEncodingDirection field
    slice_direction = metadata.get('SliceEncodingDirection')
    if slice_direction in ['x', '-x', 'y', '-y', 'z', '-z']:
        return slice_direction
    
    # Fallback to ImageOrientationPatientDICOM calculation
    orientation = metadata.get('ImageOrientationPatientDICOM')
    if orientation and len(orientation) >= 6:
        try:
            row_x, row_y, row_z, col_x, col_y, col_z = orientation[:6]
            slice_direction_vector = np.cross([row_x, row_y, row_z], [col_x, col_y, col_z])
            
            # Find dominant axis
            axis_index = np.argmax(np.abs(slice_direction_vector))
            axis_names = ['x', 'y', 'z']
            sign = '-' if slice_direction_vector[axis_index] < 0 else ''
            
            return f"{sign}{axis_names[axis_index]}"
        except (ValueError, IndexError):
            # Handle malformed orientation data gracefully
            pass
    
    return None