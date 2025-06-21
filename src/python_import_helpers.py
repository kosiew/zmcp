"""
Helper functions for processing Python import statements.
Contains functions to parse, consolidate, and generate Python import statements.
"""


def parse_python_import_statements(lines):
    """
    Parse Python import statements from the input lines.
    
    Args:
        lines: List of text lines containing import statements
    
    Returns:
        tuple: (simple_imports, from_imports)
            - simple_imports: Set of simple imports ("import x")
            - from_imports: Dict mapping module names to lists of imported items
    """
    simple_imports = set()  # For "import x"
    from_imports = {}  # For "from x import y"

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Handle "import x" statements
        if line.startswith("import ") and "from " not in line:
            modules = [m.strip() for m in line[7:].split(",")]
            for module in modules:
                simple_imports.add(module)
            i += 1

        # Handle "from x import y" statements
        elif line.startswith("from "):
            # Check if this is a multi-line parenthesized import
            if "(" in line and ")" not in line:
                module, items = parse_multiline_from_import(lines, i)
                
                # Add to from_imports
                add_from_imports(from_imports, module, items)
                
                # Update index to skip processed lines
                i += count_lines_until_closing_paren(lines, i)
            else:
                # Regular single-line import
                module, items = parse_single_line_from_import(line)
                if module and items:
                    add_from_imports(from_imports, module, items)
                i += 1
        else:
            i += 1  # Skip non-import lines

    return simple_imports, from_imports


def parse_multiline_from_import(lines, start_idx):
    """
    Parse a multi-line from-import statement.
    
    Args:
        lines: List of text lines
        start_idx: Starting index of the import statement
    
    Returns:
        tuple: (module, items)
            - module: The module being imported from
            - items: List of imported items
    """
    line = lines[start_idx].strip()
    
    # Extract module name
    module = line.split(" import ")[0][5:].strip()
    
    # Collect all items until closing parenthesis
    items = []
    idx = start_idx + 1  # Move to the next line
    
    while idx < len(lines) and ")" not in lines[idx]:
        item_line = lines[idx].strip()
        if item_line and not item_line.startswith("#"):  # Skip comments
            # Remove trailing commas and whitespace
            item = item_line.rstrip(",").strip()
            if item:
                items.append(item)
        idx += 1
    
    # Process the line with closing parenthesis
    if idx < len(lines):
        item_line = lines[idx].strip()
        # Check if there's an item before the closing parenthesis
        if item_line != ")":
            item = item_line.rstrip(",").rstrip(")").strip()
            if item and item != ")":
                items.append(item)
    
    return module, items


def count_lines_until_closing_paren(lines, start_idx):
    """
    Count lines until we find a closing parenthesis.
    
    Args:
        lines: List of text lines
        start_idx: Starting index
    
    Returns:
        int: Number of lines to skip
    """
    count = 1  # Start from the next line
    idx = start_idx + 1
    
    while idx < len(lines) and ")" not in lines[idx]:
        count += 1
        idx += 1
    
    # Include the line with closing parenthesis
    if idx < len(lines):
        count += 1
        
    return count


def parse_single_line_from_import(line):
    """
    Parse a single-line from-import statement.
    
    Args:
        line: Line of text containing the import statement
    
    Returns:
        tuple: (module, items)
            - module: The module being imported from
            - items: List of imported items
    """
    parts = line.split(" import ")
    if len(parts) != 2:
        return None, []
        
    module = parts[0][5:].strip()  # Remove 'from ' prefix
    
    # Handle both normal and parenthesized single-line imports
    items_part = parts[1].strip()
    if items_part.startswith("(") and items_part.endswith(")"):
        items_part = items_part[1:-1]  # Remove parentheses
    
    items = [item.strip() for item in items_part.split(",")]
    return module, [item for item in items if item]


def add_from_imports(from_imports, module, items):
    """
    Add items to the from_imports dictionary.
    
    Args:
        from_imports: Dictionary of from-imports
        module: Module name
        items: List of items to import
    """
    if module not in from_imports:
        from_imports[module] = []
    
    for item in items:
        if item and item not in from_imports[module]:
            from_imports[module].append(item)


def generate_python_import_statements(simple_imports, from_imports):
    """
    Generate consolidated import statements.
    
    Args:
        simple_imports: Set of simple imports
        from_imports: Dict mapping module names to lists of imported items
    
    Returns:
        list: List of consolidated import statements
    """
    result = []

    # Simple imports
    if simple_imports:
        sorted_imports = sorted(simple_imports)
        for module in sorted_imports:
            result.append(f"import {module}")

    # From imports
    for module, items in sorted(from_imports.items()):
        sorted_items = sorted(items)
        # If many items, use multi-line format
        if len(", ".join(sorted_items)) > 79:
            result.append(f"from {module} import (")
            for item in sorted_items:
                result.append(f"    {item},")
            result.append(")")
        else:
            items_str = ", ".join(sorted_items)
            result.append(f"from {module} import {items_str}")

    return result



