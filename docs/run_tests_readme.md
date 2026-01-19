# Running Tests

This document describes how to run the test suite for the GnuCash Bill Processor project.

## Quick Start

```bash
# Run all tests
uv run pytest src/tests/ -v

# Run with coverage report
uv run pytest src/tests/ --cov=src --cov-report=html --cov-report=term-missing
```

## Test Organization

The test suite is organized in `src/tests/` with the following structure:

- **`conftest.py`** - Shared fixtures for database testing
- **`test_bill_workflow.py`** - Bill creation, posting, and payment workflow tests
- **`test_utils.py`** - Utility function tests (44 tests)
- **`test_address_lookup.py`** - Address lookup and parsing tests (24 tests)
- **`test_vendor_manager.py`** - Vendor management tests (11 tests)

**Total: 87 tests** (all passing)

## Running Tests

### All Tests

```bash
# Verbose output
uv run pytest src/tests/ -v

# Short output
uv run pytest src/tests/
```

### Specific Test File

```bash
uv run pytest src/tests/test_utils.py -v
uv run pytest src/tests/test_bill_workflow.py -v
uv run pytest src/tests/test_address_lookup.py -v
uv run pytest src/tests/test_vendor_manager.py -v
```

### Specific Test Class or Method

```bash
# Run a specific test class
uv run pytest src/tests/test_utils.py::TestStripVendorName -v

# Run a specific test method
uv run pytest src/tests/test_utils.py::TestStripVendorName::test_basic_name_stripping -v
```

### With Pattern Matching

```bash
# Run tests matching a pattern
uv run pytest src/tests/ -k "vendor" -v

# Run tests NOT matching a pattern
uv run pytest src/tests/ -k "not manual" -v
```

## Coverage Reports

### Generate Coverage Report

```bash
# HTML and terminal report
uv run pytest src/tests/ --cov=src --cov-report=html --cov-report=term-missing

# Open the HTML report (generated in htmlcov/)
# Windows:
start htmlcov/index.html

# Linux/Mac:
open htmlcov/index.html
```

### Current Coverage

- **Overall**: 32%
- **config.py**: 100% ✅
- **utils.py**: 88% ✅
- **conftest.py**: 92% ✅
- **test files**: 96-99% ✅

## Test Output Options

### Verbose with Print Statements

```bash
# Show print() output from tests
uv run pytest src/tests/ -v -s
```

### Short Traceback

```bash
# Shorter error messages
uv run pytest src/tests/ --tb=short
```

### Stop on First Failure

```bash
# Exit immediately on first failure
uv run pytest src/tests/ -x
```

### Show Slowest Tests

```bash
# Show the 10 slowest tests
uv run pytest src/tests/ --durations=10
```

## Property-Based Testing

Tests use [Hypothesis](https://hypothesis.readthedocs.io/) for property-based testing.

### View Hypothesis Statistics

```bash
uv run pytest src/tests/ --hypothesis-show-statistics
```

### Adjust Number of Examples

The test suite is configured to run 50-100 examples per property-based test. This is set in the test files using:

```python
@settings(max_examples=50)
@given(st.text())
def test_function(self, input_value):
    # Test implementation
```

## Manual Tests

Some tests are marked as `@pytest.mark.manual` and are skipped by default:

```bash
# Run only manual tests
uv run pytest src/tests/ -m manual -v

# Skip manual tests (default behavior)
uv run pytest src/tests/ -m "not manual" -v
```

## Debugging Failed Tests

### Show Local Variables

```bash
uv run pytest src/tests/ -l
```

### Enter Debugger on Failure

```bash
uv run pytest src/tests/ --pdb
```

### More Verbose Output

```bash
uv run pytest src/tests/ -vv
```

## Continuous Testing

### Watch Mode (requires pytest-watch)

```bash
# Install pytest-watch
uv add --dev pytest-watch

# Run tests on file changes
uv run ptw src/tests/
```

## Test Configuration

Tests are configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["src/tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = "-v --tb=short"
markers = [
    "manual: marks tests as requiring manual verification"
]
```

## Common Test Patterns

### Running Tests After Changes

```bash
# Quick check after editing utils
uv run pytest src/tests/test_utils.py -v

# Full suite before committing
uv run pytest src/tests/ -v --cov=src
```

### Pre-Commit Checks

```bash
# Run full test suite with coverage
uv run pytest src/tests/ --cov=src --cov-report=term-missing

# Verify all tests pass
uv run pytest src/tests/ -v
```

## Troubleshooting

### Import Errors

If you see import errors, ensure you're using `uv run`:

```bash
# ✅ Correct
uv run pytest src/tests/

# ❌ Wrong (bypasses virtual environment)
pytest src/tests/
```

### Database Locked Errors

The test suite creates temporary database copies. On Windows, file locking can sometimes cause issues:

- Tests automatically handle cleanup with error suppression
- Each test class uses a fresh database copy
- Temporary files are cleaned up automatically

### Slow Tests

If tests are running slowly:

```bash
# Run tests in parallel (requires pytest-xdist)
uv add --dev pytest-xdist
uv run pytest src/tests/ -n auto
```

## CI/CD Integration

For continuous integration:

```bash
# Basic CI command
uv run pytest src/tests/ --cov=src --cov-report=xml

# With exit code 1 if coverage below threshold
uv run pytest src/tests/ --cov=src --cov-fail-under=80
```

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)

## Development Workflow

1. Make code changes
2. Run relevant tests: `uv run pytest src/tests/test_<module>.py -v`
3. Check coverage: `uv run pytest src/tests/ --cov=src --cov-report=term-missing`
4. Fix any failures
5. Run full suite before committing: `uv run pytest src/tests/ -v`

---

**Remember**: Always use `uv run` prefix for all test commands as per the project style guide.
