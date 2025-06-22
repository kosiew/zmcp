# AGENTS Instructions

## Code style
- Use Python 3.10+ features and type hints.
- Include docstrings for all functions and classes.
- Keep line length under 100 characters.

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
