# Contributing to macacaMRIprep

Thank you for your interest in contributing to macacaMRIprep! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Documentation](#documentation)
- [Submitting Changes](#submitting-changes)
- [Code Style](#code-style)
- [Issue Guidelines](#issue-guidelines)
- [Community](#community)

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to [your.email@example.com].

### Our Pledge

We pledge to make participation in our project a harassment-free experience for everyone, regardless of age, body size, disability, ethnicity, gender identity and expression, level of experience, nationality, personal appearance, race, religion, or sexual identity and orientation.

## Getting Started

### Ways to Contribute

- **Bug Reports**: Help us identify and fix issues
- **Feature Requests**: Suggest new functionality
- **Code Contributions**: Fix bugs or implement new features
- **Documentation**: Improve or expand documentation
- **Examples**: Add usage examples or tutorials
- **Testing**: Help improve test coverage

### Before You Start

1. Check existing [issues](https://github.com/yourusername/macacaMRIprep/issues) and [pull requests](https://github.com/yourusername/macacaMRIprep/pulls)
2. For large changes, open an issue to discuss your idea first
3. Read through this contributing guide
4. Set up your development environment

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Git
- External neuroimaging tools (FSL, ANTs, AFNI)

### Setting Up Your Environment

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/yourusername/macacaMRIprep.git
   cd macacaMRIprep
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies:**
   ```bash
   pip install -e ".[dev,docs]"
   ```

4. **Set up pre-commit hooks:**
   ```bash
   pre-commit install
   ```

5. **Set up environment variables:**
   ```bash
   export FSLDIR=/usr/local/fsl
   export AFNI_HOME=/usr/local/afni
   export ANTSPATH=/usr/local/ants/bin/
   export PATH=$FSLDIR/bin:$AFNI_HOME:$ANTSPATH:$PATH
   ```

6. **Verify installation:**
   ```bash
   python -c "import macacaMRIprep; print('Installation successful!')"
   macacaMRIprep-preproc --check-only
   ```

### Development Tools

We use several tools to maintain code quality:

- **Black**: Code formatting
- **flake8**: Linting
- **mypy**: Type checking
- **pytest**: Testing
- **pre-commit**: Git hooks

## Making Changes

### Workflow

1. **Create a new branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**

3. **Test your changes:**
   ```bash
   pytest tests/
   ```

4. **Check code quality:**
   ```bash
   black macacaMRIprep/
   flake8 macacaMRIprep/
   mypy macacaMRIprep/
   ```

5. **Commit your changes:**
   ```bash
   git add .
   git commit -m "Add your descriptive commit message"
   ```

6. **Push and create a pull request**

### Commit Message Guidelines

Use clear, descriptive commit messages:

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

**Examples:**
```
Add skull stripping validation

- Implement environment variable checking
- Add UNet model path validation
- Update configuration validation tests

Closes #123
```

### Branch Naming

Use descriptive branch names:
- `feature/add-skull-stripping`
- `bugfix/fix-motion-correction`
- `docs/improve-readme`
- `test/add-integration-tests`

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=macacaMRIprep

# Run specific test file
pytest tests/test_config.py

# Run tests matching a pattern
pytest -k "test_validation"
```

### Writing Tests

- Write tests for all new functionality
- Ensure good test coverage (aim for >80%)
- Use descriptive test names
- Follow the existing test structure

**Example test:**
```python
def test_validate_slice_timing_config():
    """Test slice timing configuration validation."""
    config = {"repetition_time": 2.0, "slice_order": "ascending"}
    validate_slice_timing_config(config)  # Should not raise
    
    with pytest.raises(ValueError):
        validate_slice_timing_config({"repetition_time": -1})
```

### Test Data

- Use small, synthetic test data when possible
- Store test data in `tests/data/`
- Document test data requirements clearly

## Documentation

### Building Documentation

```bash
cd docs/
make html
```

### Documentation Guidelines

- Update docstrings for any new or modified functions
- Use [NumPy docstring format](https://numpydoc.readthedocs.io/en/latest/format.html)
- Update README.rst for user-facing changes
- Add examples for new features

**Example docstring:**
```python
def slice_timing_correction(imagef: str, config: Dict[str, Any]) -> Dict[str, str]:
    """Perform slice timing correction on functional data.
    
    Parameters
    ----------
    imagef : str
        Path to input functional image
    config : dict
        Configuration dictionary containing slice timing parameters
        
    Returns
    -------
    dict
        Dictionary with output file paths
        
    Raises
    ------
    ValueError
        If repetition time is not positive
    FileNotFoundError
        If input file does not exist
        
    Examples
    --------
    >>> config = {"slice_timing": {"repetition_time": 2.0}}
    >>> result = slice_timing_correction("func.nii.gz", config)
    """
```

## Submitting Changes

### Pull Request Process

1. **Ensure your code follows our style guidelines**
2. **Update documentation** for any public API changes
3. **Add tests** for new functionality
4. **Update CHANGELOG.md** if applicable
5. **Create descriptive pull request**

### Pull Request Template

When creating a pull request, include:

- **Description**: What does this PR do?
- **Related Issues**: Link to relevant issues
- **Testing**: How was this tested?
- **Checklist**: Use our PR checklist

**Example PR description:**
```markdown
## Description
Adds comprehensive validation for slice timing configuration parameters.

## Related Issues
Closes #123

## Changes
- Add `validate_slice_timing_config()` function
- Implement parameter range checking
- Add comprehensive error messages
- Update tests and documentation

## Testing
- [x] Unit tests pass
- [x] Integration tests pass
- [x] Manual testing completed

## Checklist
- [x] Code follows style guidelines
- [x] Self-review completed
- [x] Documentation updated
- [x] Tests added/updated
- [x] CHANGELOG.md updated
```

### Review Process

1. **Automated checks** must pass (CI/CD pipeline)
2. **Code review** by maintainers
3. **Address feedback** if any
4. **Merge** once approved

## Code Style

### Python Style Guide

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with some modifications:

- **Line length**: 88 characters (Black default)
- **Quotes**: Use double quotes for strings
- **Imports**: Use absolute imports when possible
- **Type hints**: Use type hints for all public functions

### Formatting Tools

- **Black**: Automatic code formatting
- **isort**: Import sorting
- **flake8**: Style checking

Run formatting tools:
```bash
black macacaMRIprep/
isort macacaMRIprep/
flake8 macacaMRIprep/
```

### Pre-commit Hooks

Our pre-commit hooks automatically:
- Format code with Black
- Sort imports with isort
- Check style with flake8
- Run type checking with mypy
- Check for large files and merge conflicts

## Issue Guidelines

### Bug Reports

When reporting bugs, include:

- **Environment information** (OS, Python version, package versions)
- **Steps to reproduce** the issue
- **Expected behavior**
- **Actual behavior**
- **Error messages** and stack traces
- **Minimal example** if possible

### Feature Requests

When requesting features:

- **Use case**: Why is this feature needed?
- **Proposed solution**: How should it work?
- **Alternatives**: What alternatives have you considered?
- **Additional context**: Any other relevant information

### Issue Labels

We use labels to categorize issues:

- `bug`: Something isn't working
- `enhancement`: New feature or improvement
- `documentation`: Documentation improvements
- `good first issue`: Good for newcomers
- `help wanted`: Extra attention needed
- `question`: Further information requested

## Community

### Getting Help

- **Documentation**: Check our [documentation](https://macacaMRIprep.readthedocs.io/)
- **Issues**: Search existing [issues](https://github.com/yourusername/macacaMRIprep/issues)
- **Discussions**: Join our [GitHub discussions](https://github.com/yourusername/macacaMRIprep/discussions)
- **Email**: Contact maintainers at [your.email@example.com]

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion
- **Email**: Direct contact with maintainers

### Recognition

Contributors are recognized in:
- **README.rst**: Major contributors listed
- **CHANGELOG.md**: Contributions noted in releases
- **GitHub**: Contributor statistics visible

## Release Process

For maintainers:

1. **Update version** in `macacaMRIprep/info.py` and `pyproject.toml`
2. **Update CHANGELOG.md** with release notes
3. **Create release tag**: `git tag v0.1.0`
4. **Push tag**: `git push origin v0.1.0`
5. **GitHub Actions** automatically builds and publishes to PyPI
6. **Create GitHub release** with release notes

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to macacaMRIprep! 🧠🐒

*For questions about contributing, please contact [your.email@example.com]* 