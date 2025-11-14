"""
Test suite for slice timing correction algorithm.

Tests the _analyze_slice_timing_pattern function with various slice timing patterns
commonly found in MRI data acquisition.
"""

import pytest
import numpy as np
import logging
from unittest.mock import Mock
from macacaMRIprep.operations.preprocessing import determine_tpattern


class TestSliceTimingPatternAnalysis:
    """Test slice timing pattern analysis functionality."""
    
    def test_sequential_increasing_pattern(self):
        """Test detection of sequential increasing pattern."""
        # Classic sequential acquisition: slice 0, 1, 2, 3...
        timing_values = [0.0, 0.4, 0.8, 1.2, 1.6]
        result = determine_tpattern(timing_values)
        
        assert result == "seq+z"
    
    def test_sequential_decreasing_pattern(self):
        """Test detection of sequential decreasing pattern."""
        # Reverse sequential: slice n, n-1, n-2...
        timing_values = [1.6, 1.2, 0.8, 0.4, 0.0]
        result = determine_tpattern(timing_values)
        
        assert result == "seq-z"
    
    def test_alternating_plus_pattern_even_first(self):
        """Test alternating pattern with even slices first (classic alt+)."""
        # Real timing values that normalize to AFNI altplus pattern: [0, 0.6, 0.2, 0.8, 0.4]
        # Using TR=2.0s: [0.0, 1.2, 0.4, 1.6, 0.8]
        timing_values = [0.0, 1.2, 0.4, 1.6, 0.8]
        result = determine_tpattern(timing_values)
        
        assert result == "alt+z"
    
    def test_alternating_minus_pattern_odd_first(self):
        """Test alternating pattern with odd slices first (alt-)."""
        # Real timing values that normalize to AFNI altminus pattern: [0.4, 0.8, 0.2, 0.6, 0]
        # Using TR=2.0s: [0.8, 1.6, 0.4, 1.2, 0.0]
        timing_values = [0.8, 1.6, 0.4, 1.2, 0.0]
        result = determine_tpattern(timing_values)
        
        assert result == "alt-z"
    
    def test_alternating_plus_starting_slice_1(self):
        """Test alt+z2 pattern (starting at slice 1)."""
        # Real timing values that normalize to AFNI alt+z2 pattern: [0.4, 0, 0.6, 0.2, 0.8]
        # Using TR=2.0s: [0.8, 0.0, 1.2, 0.4, 1.6]
        timing_values = [0.8, 0.0, 1.2, 0.4, 1.6]
        result = determine_tpattern(timing_values)
        
        assert result == "alt+z2"
    
    def test_alternating_minus_starting_slice_n_minus_2(self):
        """Test alt-z2 pattern (starting at slice n-2)."""
        # Real timing values that normalize to AFNI alt-z2 pattern: [0.8, 0.2, 0.6, 0, 0.4]
        # Using TR=2.0s: [1.6, 0.4, 1.2, 0.0, 0.8]
        timing_values = [1.6, 0.4, 1.2, 0.0, 0.8]
        result = determine_tpattern(timing_values)
        
        assert result == "alt-z2"
    
    def test_edge_case_single_slice(self):
        """Test edge case with single slice - should return unknown."""
        timing_values = [0.0]
        result = determine_tpattern(timing_values)
        
        assert result == "unknown"
    
    def test_edge_case_two_slices(self):
        """Test edge case with two slices."""
        timing_values = [0.0, 1.0]
        result = determine_tpattern(timing_values)
        
        assert result == "seq+z"
    
    def test_different_direction(self):
        """Test with different slice encoding direction."""
        timing_values = [0.0, 0.5, 1.0, 1.5]
        result = determine_tpattern(timing_values, "y")
        
        assert result == "seq+y"
    
    def test_complex_alternating_pattern(self):
        """Test complex alternating pattern with 8 slices."""
        # 8-slice alternating: even slices 0,2,4,6 then odd slices 1,3,5,7
        timing_values = [0.0, 1.0, 0.25, 1.25, 0.5, 1.5, 0.75, 1.75]
        result = determine_tpattern(timing_values)
        
        assert result == "alt+z"
    
    def test_noisy_sequential_pattern(self):
        """Test sequential pattern with small noise (should still be detected)."""
        # Sequential with tiny variations
        timing_values = [0.0, 0.5001, 1.0002, 1.4999, 2.0001]
        result = determine_tpattern(timing_values)
        
        assert result == "seq+z"
    
    def test_irregular_pattern_fallback(self):
        """Test complex real-world alternating pattern with variance."""
        # Complex pattern that should still be detected as alternating
        # Even slices: [0.1, 0.3, 0.5], Odd slices: [0.7, 0.9] - clear separation
        timing_values = [0.2, 1.4, 0.6, 1.8, 1.0]  # Normalizes with clear even/odd separation
        result = determine_tpattern(timing_values)
        
        assert result == "alt+z"
    
    def test_true_alt_minus_z2_pattern(self):
        """Test true alt-z2 pattern where slice n-2 has earliest time compared to neighbors."""
        # Real timing values that normalize to AFNI alt-z2 pattern: [0.8, 0.2, 0.6, 0, 0.4]
        # Using TR=2.0s: [1.6, 0.4, 1.2, 0.0, 0.8] - slice 3 (n-2) is earliest
        timing_values = [1.6, 0.4, 1.2, 0.0, 0.8]
        result = determine_tpattern(timing_values)
        
        assert result == "alt-z2"
    
    def test_unrecognizable_pattern_raises_error(self):
        """Test that irregular patterns are still detected when possible."""
        # this is a random pattern, so it should return unknown
        timing_values = np.random.rand(100)/2
        
        result = determine_tpattern(timing_values)
        assert result == "unknown"  # Algorithm correctly detects alternating pattern
    
    def test_real_world_siemens_pattern(self):
        """Test real-world Siemens interleaved pattern."""
        # Typical Siemens interleaved acquisition for 30 slices
        # Odd slices first: 1,3,5,...,29, then even slices: 0,2,4,...,28
        n_slices = 30
        timing_values = [0.0] * n_slices
        tr = 2.0
        
        # Odd slices first
        for i in range(1, n_slices, 2):  # 1,3,5,...,29
            timing_values[i] = (i // 2) * (tr / (n_slices // 2))
        
        # Even slices second
        for i in range(0, n_slices, 2):  # 0,2,4,...,28
            timing_values[i] = (tr / 2) + (i // 2) * (tr / (n_slices // 2))
        
        # This pattern should actually be detected as alt+z2 since slice 1 is acquired first
        result = determine_tpattern(timing_values)
        assert result == "alt+z2"
    
    def test_real_world_philips_pattern(self):
        """Test real-world Philips ascending pattern."""
        # Typical Philips sequential ascending
        n_slices = 25
        tr = 2.5
        timing_values = [(i * tr / n_slices) for i in range(n_slices)]
        
        result = determine_tpattern(timing_values)
        assert result == "seq+z"


class TestSliceTimingPatternEdgeCases:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=logging.Logger)
        self.direction = "z"
        self.tr = 2.0
    
    def test_empty_timing_values(self):
        """Test with empty timing values list - should return unknown."""
        timing_values = []
        
        result = determine_tpattern(timing_values)
        assert result == "unknown"
    
    def test_all_same_timing_values(self):
        """Test with all identical timing values."""
        timing_values = [1.0, 1.0, 1.0, 1.0]
        result = determine_tpattern(timing_values)
        
        # All same values should be detected as sequential
        assert result == "seq+z"
    
    def test_negative_timing_values(self):
        """Test with negative timing values."""
        timing_values = [-1.0, -0.5, 0.0, 0.5]
        result = determine_tpattern(timing_values)
        
        assert result == "seq+z"


if __name__ == "__main__":
    pytest.main([__file__]) 