# AGENTS Instructions

## Python Code Style

When generating Python code for this project, adhere to the following style guidelines:

1. **Follow PEP 8 and Ruff Rules:**
   - Use Python 3.10+ features and type hints
   - Use double quotes for string literals
   - Use explicit relative imports (e.g., `from .module import Class`)
   - Limit line length to 88 characters (Black formatter standard)
   - Use type hints for function parameters and return values
   - Avoid unused imports
   - Use f-strings instead of `.format()` or `%` formatting
   - Avoid unnecessary `else` statements after `return`
   - Use `isinstance()` instead of comparing types directly
   - Assign exception message strings to variables before raising:
     ```python
     # Correct:
     msg = "Invalid input value"
     raise ValueError(msg)

     # Incorrect:
     raise ValueError("Invalid input value")
     ```

2. **Documentation:**
   - Include comprehensive docstrings for modules, classes, and functions/methods
   - Follow Google-style docstring format
   - Keep docstrings concise but informative

3. **Code Organization:**
   - Keep functions concise and focused on a single task
   - Aim for functions under 40-50 lines of code
   - Break long or complex operations into smaller, well-named helper functions
   - Before creating new utility functions, check if existing helper functions can be reused or extended
   - Consider adding parameters to existing functions rather than creating similar parallel implementations
   - Don't overengineer; avoid creating abstractions that are not needed
   - Look for similar patterns in the codebase and follow established conventions

4. **Testing:**
   - Use meaningful test function names that describe what is being tested
   - Group related tests in classes
   - Use pytest style assertions instead of unittest style

## Rust Code Style

When generating Rust code, follow these guidelines:

1. **Style Conventions:**
   - Do not add unnecessary parentheses around `if` conditions:
     - Correct: `if some_condition`
     - Incorrect: `if (some_condition)`
   - Follow the standard Rust style conventions from rustfmt

2. **Code Organization:**
   - Keep functions concise and focused on a single task
   - Aim for functions under 40-50 lines of code
   - Break long or complex operations into smaller, well-named helper functions
   - Before creating new utility functions, check if existing helper functions can be reused or extended
   - Don't overengineer; avoid creating abstractions that are not needed
   - Look for similar patterns in the codebase and follow established conventions

## Comments
- Add meaningful comments for complex logic
- Avoid obvious comments
- Start inline comments with a capital letter

## Example Python Style

```python
from typing import Optional, List

def process_data(data: List[str], max_length: Optional[int] = None) -> List[str]:
    """Process a list of string data.

    Args:
        data: List of strings to process
        max_length: Optional maximum length for each string

    Returns:
        List of processed strings

    Raises:
        ValueError: If invalid data is provided
    """
    if not data:
        msg = "Empty data list provided"
        raise ValueError(msg)

    result = []
    for item in data:
        # Skip empty items
        if not item.strip():
            continue

        processed = item.strip().lower()
        if max_length is not None and len(processed) > max_length:
            processed = processed[:max_length]

        result.append(processed)

    return result
```

## Commit messages
- Write a short summary in present-tense imperative, e.g. "Add new tool".

## Documentation
- Update `README.md` when adding or modifying functionality.

## Testing
- There are no unit tests. Run a syntax check before committing:
  ```bash
  python -m py_compile $(git ls-files '*.py')
  ```

## Pull Request
- In the PR description, include **Summary** and **Testing** sections describing your changes and the command results.
