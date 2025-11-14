"""
Command-line interface for macacaMRIprep.

This module provides:
1. Command-line tools for preprocessing and registration
2. Configuration management
3. Logging setup
"""

# Don't import main directly to avoid circular import issues
# Instead, provide a function to get the main function when needed

def get_main():
    """Get the main function from preproc module."""
    from .preproc import main
    return main

__all__ = ['get_main'] 