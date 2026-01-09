# Programming Style Guide

This document outlines the programming conventions, tools, and workflows used in this project.

> **⚠️ CRITICAL: All Python execution MUST use `uv run` prefix. pip is deprecated.**

## Dependency Management

### UV Package Manager (REQUIRED)

**Always use `uv` for all package management.** pip is deprecated and must not be used.

```bash
# ✅ CORRECT - Add dependencies with uv
uv add <package>                      # Production dependency
uv add --dev <package>                # Development/test dependency

# ✅ CORRECT - Run Python scripts (ALWAYS use uv run)
uv run python script.py
uv run pytest tests/

# ❌ WRONG - NEVER use these (pip is deprecated)
pip install <package>                 # DEPRECATED - Do not use
pip install -r requirements.txt       # DEPRECATED - Do not use
python script.py                      # WRONG - Bypasses uv environment
```

### Key Points

- **uv manages virtual environments automatically** - no manual venv creation needed
- `uv add` automatically updates `pyproject.toml` and `uv.lock`
- **All Python execution must use `uv run` prefix** to ensure correct environment
- Never install packages with pip - always use `uv add`

## Testing Philosophy

### Property-Based Testing with Hypothesis

- Use Hypothesis for discovering edge cases automatically
- Configure 50-100 examples per test for thorough coverage
- **Never fix discovered edge cases immediately** - suspend them for analysis
- Document edge cases in skip decorator reasons

```python
@pytest.mark.skip(reason="Edge case: specific behavior discovered")
@settings(max_examples=100)
@given(st.text())
def test_function_behavior(self, input_value):
    """Test description"""
    # Test implementation
```

### Test Organization

- One test file per function for property-based tests
- Name pattern: `test_<function_name>_property_based.py`
- Group tests in classes: `class Test<FunctionName>PropertyBased:`
- Always test crash resistance first: `test_never_crashes_on_any_input`

### Systematic Testing Workflow

1. Create comprehensive tests for one function
2. Run tests to discover failures
3. Suspend failing tests with `@pytest.mark.skip` and document reasons
4. Commit with descriptive message
5. Move to next function
6. **Do NOT fix edge cases** - preserve for future analysis

### Test Execution

**Remember: Always use `uv run` prefix for all Python/pytest commands.**

```bash
# ✅ CORRECT - Run tests with uv
uv run pytest tests/ -v
uv run pytest tests/test_specific_file.py -v
uv run pytest tests/ --cov=src

# ❌ WRONG - Never run pytest directly
pytest tests/ -v                      # WRONG - Bypasses uv environment
python -m pytest tests/               # WRONG - Bypasses uv environment
```

## Git Workflow

### Commit Discipline

- Commit after each logical unit of work
- One function's tests = one commit
- Use descriptive, multi-line commit messages
- Include statistics in commit messages (e.g., "15 passed, 3 skipped")
- Document discovered edge cases in commit messages

### Commit Message Format

```text
Short descriptive title (function X of Y)

- Bullet point summary of what was added
- Test statistics (X passed, Y skipped)
- Edge cases discovered:
  1. Specific edge case with brief description
  2. Another edge case
- Key test coverage areas
```

### Example

```
Add property-based tests for sanitize_for_filesystem() (function 1 of 7)

- 18 comprehensive property-based tests
- 15 tests passing, 3 suspended
- Edge cases discovered:
  1. Control chars appear in sanitized output
  2. Unicode normalization differs from expectations
  3. Truncation happens at different length than documented
- Tests cover: length limits, invalid chars, Windows reserved names,
  Unicode handling, path traversal prevention
```

## Code Organization

### Project Structure

- Production code: `src/` directory
- Tests: `tests/` directory  
- Documentation: `docs/` directory
- Configuration files at project root

### Naming Conventions

- Functions: `snake_case`
- Classes: `PascalCase`
- Test classes: `Test<FunctionName>PropertyBased`
- Test files: `test_<module>_property_based.py`
- Constants: `UPPER_SNAKE_CASE`

## Documentation Practices

### Inline Documentation

- Use descriptive docstrings for all functions and classes
- Include type hints in function signatures
- Document edge cases in comments when suspended tests reveal them

### File Headers

```python
"""
Module description.

This file contains [description of contents].

Created as part of [larger effort or feature].
"""
```

### Test File Headers

```python
"""
Property-based tests for <function_name> using Hypothesis.

This file contains property-based tests that generate random inputs
to discover edge cases in [description].

Created as part of systematic property-based testing expansion.
Function X of Y: function_name()
"""
```

## Python Code Style

### Type Hints

- Always use type hints for function parameters and return types
- Use `Optional[Type]` for nullable values
- Use `Union[Type1, Type2]` or `Type1 | Type2` for multiple types

### Error Handling

- Use specific exception types, not bare `except:`
- Document exceptions in docstrings
- Prefer `ValueError` for validation errors
- Use `try/except/else` pattern when appropriate

### Imports

- Standard library imports first
- Third-party imports second
- Local imports third
- Separate groups with blank lines

## Development Environment

### Required Tools

- Python 3.11+ (project uses 3.11.1+)
- **`uv` package manager (REQUIRED)** - handles all dependency and environment management
- `pytest` for testing (install via `uv add --dev pytest`)
- `hypothesis` for property-based testing (install via `uv add --dev hypothesis`)
- **`loguru` for logging (REQUIRED)** - simpler API than standard library `logging`

### Logging with Loguru (REQUIRED)

**Always use `loguru` for logging. Do NOT use the standard library `logging` module.**

```python
# ✅ CORRECT - Use loguru
from loguru import logger

logger.info("Processing bill for {}", vendor_name)
logger.debug("Matched vendor with score: {}", score)
logger.error("Failed to connect: {}", error)
logger.warning("Vendor not found, creating new entry")

# ❌ WRONG - Do not use standard logging
import logging
logger = logging.getLogger(__name__)  # WRONG
```

### Loguru Configuration

Configure loguru at the application entry point (e.g., `bill_processor.py`):

```python
from loguru import logger
import sys

# Remove default handler and add custom configuration
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/app.log", rotation="1 MB", retention="7 days")
```

### Environment Setup

```bash
# Clone project and let uv handle everything
git clone <repo>
cd <project>
uv sync                               # Creates venv and installs all dependencies

# Run any Python code
uv run python src/script.py           # ALWAYS use uv run
uv run pytest tests/                  # ALWAYS use uv run
```

### IDE Configuration

- Use `.gitignore` to exclude:
  - `.hypothesis/` directory (test databases)
  - `__pycache__/`
  - `*.pyc`
  - `.pytest_cache/`
  - `.venv/` directory (uv-managed environment)

## Project-Specific Patterns

### Database Access

- Use context managers for database connections
- Always close connections properly
- Use parameterized queries to prevent SQL injection
- Wrap database operations in try/except blocks

### Configuration

- Keep all configurable values in `config.py`
- Use Path objects for file paths
- Provide sensible defaults
- Document each configuration option

### Vendor Matching

- Use fuzzy matching for user-entered vendor names
- Configure match thresholds in `config.py`
- Store aliases for common variations
- Log match decisions for debugging

### Date Handling

- Use ISO format (YYYY-MM-DD) as the standard
- Support multiple input formats for user convenience
- Use `datetime.date` objects internally
- Format dates consistently for display

## Common Pitfalls to Avoid

### ❌ DON'T

- **Use pip for anything** - pip is deprecated, use `uv add` instead
- **Run Python directly** - always use `uv run python` prefix
- **Run pytest directly** - always use `uv run pytest` prefix
- **Manually create virtual environments** - uv handles this automatically
- Fix edge cases discovered during systematic testing without documenting them first
- Create overly broad test assumptions
- Skip documenting edge cases in skip decorators
- Batch multiple logical commits into one
- Use escape sequences in strings without raw strings (`r"..."`)
- Ignore type hints for function signatures
- Use bare `except:` clauses
- Hardcode file paths - use `config.py`

### ✅ DO

- **Use `uv add` for all package installations**
- **Use `uv run` prefix for ALL Python execution**
- **Use `uv sync` to set up environments**
- Suspend discovered edge cases with documentation
- Test with diverse input strategies (text, numbers, edge values)
- Use raw strings for Windows paths and regex patterns
- Commit after each logical unit of work
- Document the "why" in comments and commit messages
- Use type hints consistently
- Use specific exception types
- Use `loguru` for all logging (NOT standard library `logging`)

## Performance Considerations

### Database Operations

- Minimize database round-trips
- Use transactions for multiple related operations
- Cache frequently-used lookups (like vendor lists)
- Close connections promptly

### API Calls

- Respect rate limits (especially for address lookup services)
- Cache API responses when appropriate
- Use timeouts on all network requests
- Handle network errors gracefully

### Test Execution

- Run specific test files during development: `uv run pytest tests/test_file.py`
- Use `-v` flag for verbose output: `uv run pytest -v`
- Use `-k` flag to run specific test patterns: `uv run pytest -k "test_name"`

## Maintenance Notes

### Regular Updates

- Keep dependencies updated via `uv add --upgrade <package>`
- Use `uv sync` after pulling changes to update environment
- Review and address suspended tests periodically
- Update this style guide as patterns evolve

### Code Review Checklist

- [ ] All Python execution uses `uv run` prefix
- [ ] Dependencies added via `uv add` (not pip)
- [ ] Tests include edge case checks
- [ ] Edge cases documented
- [ ] Commit messages are descriptive
- [ ] Type hints present for all functions
- [ ] Configuration values in `config.py`
- [ ] Logging used appropriately

---

## Quick Reference: UV Commands

 | Task | Command |
 |------|--------|
 | Add dependency | `uv add <package>` |
 | Add dev dependency | `uv add --dev <package>` |
 | Run Python script | `uv run python script.py` |
 | Run tests | `uv run pytest tests/` |
 | Sync environment | `uv sync` |
 | Update package | `uv add --upgrade <package>` |

**Remember: NEVER use pip. ALWAYS use uv run for Python execution.**

---

**Last Updated:** January 8, 2026
**Project:** GnuCash Bill Processor
