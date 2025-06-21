"""Helper functions for processing and streamlining Rust import statements."""

def parse_import_statements(lines):
    """
    Parse Rust import statements from the input lines.
    
    Args:
        lines: List of text lines containing import statements
    
    Returns:
        tuple: (use_statements, other_lines)
            - use_statements: List of (cfg_attr, statement, is_pub) tuples
            - other_lines: List of non-import lines
    """
    # Process lines to capture cfg attributes with their use statements
    use_statements = []  # Will contain (cfg_attr, full_statement, is_pub) tuples
    other_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Handle cfg attributes
        if line.startswith("#[cfg") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            is_pub = next_line.startswith("pub use ")
            is_use = next_line.startswith("use ")

            if (is_pub or is_use) and next_line.endswith(";"):
                use_statements.append((line, next_line, is_pub))
                i += 2
                continue
            elif (is_pub or is_use) and "{" in next_line and not next_line.endswith("};"): 
                # Multi-line import with cfg attribute
                full_statement = next_line
                j = i + 2
                while j < len(lines) and not lines[j].strip().endswith("};"):
                    full_statement += " " + lines[j].strip()
                    j += 1
                if j < len(lines):
                    full_statement += " " + lines[j].strip()
                    use_statements.append((line, full_statement, is_pub))
                    i = j + 1
                    continue

        # Handle single-line imports
        elif line.startswith("pub use ") and line.endswith(";"):
            use_statements.append((None, line, True))
            i += 1
        elif line.startswith("use ") and line.endswith(";"):
            use_statements.append((None, line, False))
            i += 1
        # Handle multi-line imports
        elif (line.startswith("pub use ") or line.startswith("use ")) and "{" in line and not line.endswith("};"):
            is_pub = line.startswith("pub use ")
            full_statement = line
            j = i + 1
            # Track brace levels to handle nested braces correctly
            brace_count = line.count("{") - line.count("}")
            
            while j < len(lines) and brace_count > 0:
                current_line = lines[j].strip()
                full_statement += " " + current_line
                brace_count += current_line.count("{") - current_line.count("}")
                j += 1
                
                # Break if we've balanced all braces and have a semicolon
                if brace_count == 0 and full_statement.endswith(";"):
                    break
            
            if brace_count == 0 and full_statement.endswith(";"):
                use_statements.append((None, full_statement, is_pub))
                i = j
                continue
            else:
                # If we couldn't properly parse the statement, leave it as-is
                other_lines.append(line)
                i += 1
        else:
            other_lines.append(line)
            i += 1
    
    return use_statements, other_lines


def parse_nested_import_items(items_str):
    """
    Parse import items with nested curly braces.
    
    Args:
        items_str: String containing import items inside curly braces
    
    Returns:
        set: Set of parsed import items
    """
    # Process nested curly braces to maintain proper structure
    items = set()
    current_item = ""
    brace_level = 0
    
    for char in items_str:
        if char == '{':
            brace_level += 1
            current_item += char
        elif char == '}':
            brace_level -= 1
            current_item += char
        elif char == ',' and brace_level == 0:
            # Only split at top-level commas
            if current_item.strip():
                items.add(current_item.strip())
            current_item = ""
        else:
            current_item += char
    
    # Add the last item if there is one
    if current_item.strip():
        items.add(current_item.strip())
        
    return items


def process_import_with_braces(import_path):
    """
    Process an import statement with curly braces.
    
    Args:
        import_path: Import path string like 'std::io::{Read, Write}'
    
    Returns:
        tuple: (base_path, items)
            - base_path: Base module path
            - items: Set of import items
    """
    # Get everything before the curly brace as the base path
    full_path = import_path[:import_path.index("{")].rstrip("::")
    items_str = import_path[import_path.index("{")+1:-1]
    
    # Parse the nested items
    items = parse_nested_import_items(items_str)
        
    # Extract the top-level module and remaining path for better grouping
    path_parts = full_path.split("::")
    
    # For imports like datafusion_datasource::file::{FileSource}
    # We want to group by the top-level module (datafusion_datasource)
    top_level_module = path_parts[0]
    
    if len(path_parts) > 1:
        # Get submodule path (like "file" or "file_scan_config")
        submodule_path = "::".join(path_parts[1:])
        
        # Format each item to include its submodule
        formatted_items = set()
        for item in items:
            # Don't add additional braces around the item
            formatted_items.add(f"{submodule_path}::{item}")
        
        # Use the top-level module for grouping
        base_path = top_level_module
        return base_path, formatted_items
    else:
        # For simple cases like std::{io, fmt}
        return full_path, items


def process_simple_import(parts):
    """
    Process a simple import statement without braces.
    
    Args:
        parts: List of parts from splitting the import path by '::'
    
    Returns:
        tuple: (base_path, items)
            - base_path: Base module path
            - items: Set of import items
    """
    # For simple imports like `std::io::Read`
    if len(parts) >= 2:
        # Get the root module for better grouping
        root_module = parts[0]
        
        if len(parts) == 2:
            # For simple two-part paths
            base_path = root_module
            items = {f"{parts[1]}"}
        else:
            # For longer paths, group by top module and preserve submodule structure
            base_path = root_module
            submodule_path = "::".join(parts[1:-1])
            item_name = parts[-1]
            items = {f"{submodule_path}::{item_name}"}
    else:
        # Fallback for unusual cases
        base_path = "::".join(parts[:-1]) if len(parts) > 1 else parts[0]
        items = {parts[-1]}
    
    return base_path, items


def group_imports_by_base_path(use_statements):
    """
    Group imports by their base path.
    
    Args:
        use_statements: List of (cfg_attr, statement, is_pub) tuples
    
    Returns:
        tuple: (grouped_by_base, special_imports)
            - grouped_by_base: Dict mapping (base_path, is_pub) to {cfg_attr: set(import_items)}
            - special_imports: List of special import statements that can't be grouped
    """
    grouped_by_base = {}  # {(base_path, is_pub): {cfg_attr: set(import_items)}}
    special_imports = []

    for cfg_attr, statement, is_pub in use_statements:
        prefix_len = 8 if is_pub else 4
        import_path = statement[prefix_len:-1].strip()

        if "::" not in import_path or import_path.endswith("::*"):
            special_imports.append((cfg_attr, statement, is_pub))
            continue

        # Extract the module and path components for better grouping
        parts = import_path.split("::")
        
        # For imports with curly braces like `std::io::{Read, Write}`
        if "{" in import_path:
            base_path, items = process_import_with_braces(import_path)
        else:
            base_path, items = process_simple_import(parts)

        key = (base_path, is_pub)
        if key not in grouped_by_base:
            grouped_by_base[key] = {}

        attr_key = cfg_attr or ""
        grouped_by_base[key].setdefault(attr_key, set()).update(items)

    return grouped_by_base, special_imports


def process_nested_module_items(nested_content):
    """
    Process nested module items with brace awareness.
    
    Args:
        nested_content: String containing nested items
    
    Returns:
        tuple: (items_list, has_self)
            - items_list: List of parsed items
            - has_self: Boolean indicating if 'self' is among the items
    """
    nested_items = []
    current = ""
    brace_level = 0
    has_self = False
    
    for char in nested_content:
        if char == '{':
            brace_level += 1
            current += char
        elif char == '}':
            brace_level -= 1
            current += char
        elif char == ',' and brace_level == 0:
            item = current.strip()
            if item:
                if item == 'self':
                    has_self = True
                else:
                    nested_items.append(item)
            current = ""
        else:
            current += char
    
    # Process final item
    item = current.strip()
    if item:
        if item == 'self':
            has_self = True
        else:
            nested_items.append(item)
    
    return nested_items, has_self


def organize_items_by_module(items):
    """
    Organize import items by their parent module.
    
    Args:
        items: Set of import items
    
    Returns:
        tuple: (module_groups, simple_items)
            - module_groups: Dict mapping module names to their items
            - simple_items: List of simple (non-nested) items
    """
    module_groups = {}
    simple_items = []
    
    for item in items:
        # Handle items with nested braces or module paths
        if "::" in item or "{" in item:
            # Check if this is a submodule path with nested items
            if "{" in item:
                # Extract the module name and its nested items
                module_name = item.split("{")[0].strip().rstrip(":")
                
                # Handle special case with 'self'
                if module_name == 'self':
                    simple_items.append('self')
                    continue
                    
                # Extract nested content handling potential nested braces
                brace_level = 0
                start_idx = item.index("{") + 1
                end_idx = 0
                
                for i, char in enumerate(item[start_idx:], start=start_idx):
                    if char == '{':
                        brace_level += 1
                    elif char == '}':
                        if brace_level == 0:
                            end_idx = i
                            break
                        brace_level -= 1
                
                # If we couldn't properly parse, keep as is
                if end_idx == 0:
                    simple_items.append(item)
                    continue
                
                nested_content = item[start_idx:end_idx].strip()
                
                # Process the nested items with brace awareness
                if module_name not in module_groups:
                    module_groups[module_name] = set()
                
                nested_items, has_nested_self = process_nested_module_items(nested_content)
                
                # Add all non-self items (using set to avoid duplicates)
                module_groups[module_name].update(nested_items)
                
                # If we found 'self', add it separately to ensure it gets sorted to the end
                if has_nested_self:
                    module_groups[module_name].add('self')
            else:
                # This is a module path (like "io::Read" or "file_scan_config::FileScanConfig")
                # Extract the module name and member
                parts = item.split("::")
                if len(parts) >= 2:
                    module_name = parts[0]
                    item_name = "::".join(parts[1:])
                    
                    if module_name not in module_groups:
                        module_groups[module_name] = set()
                    
                    module_groups[module_name].add(item_name)
                else:
                    # Fall back for unusual formats
                    simple_items.append(item)
        else:
            simple_items.append(item)
    
    return module_groups, simple_items


def format_module_groups(module_groups):
    """
    Format module groups into proper import strings.
    
    Args:
        module_groups: Dict mapping module names to their items
    
    Returns:
        list: List of formatted module import strings
    """
    sorted_items = []
    
    # Format nested groups
    for module in sorted(module_groups.keys()):
        # Ensure 'self' comes last in nested groups
        module_items = module_groups[module]
        sorted_module_items = sorted([item for item in module_items if item != 'self'])
        if 'self' in module_items:
            sorted_module_items.append('self')
        
        # Handle single item case without adding unnecessary braces
        if len(sorted_module_items) == 1:
            # For single items, don't add braces no matter what
            sorted_items.append(f"{module}::{sorted_module_items[0]}")
        else:
            nested_content = ", ".join(sorted_module_items)
            sorted_items.append(f"{module}::{{{nested_content}}}")
    
    return sorted_items


def generate_import_statements(grouped_by_base, special_imports):
    """
    Generate consolidated import statements from grouped imports.
    
    Args:
        grouped_by_base: Dict mapping (base_path, is_pub) to {cfg_attr: set(import_items)}
        special_imports: List of special import statements that can't be grouped
    
    Returns:
        list: List of consolidated import statements
    """
    result = []

    # Handle special imports first
    for cfg_attr, stmt, _ in special_imports:
        if cfg_attr:
            result.append(cfg_attr)
        result.append(stmt)

    # Process grouped imports
    for (base_path, is_pub), attr_groups in sorted(grouped_by_base.items()):
        for cfg_attr, items in sorted(attr_groups.items()):
            if cfg_attr:
                result.append(cfg_attr)
            
            prefix = "pub use " if is_pub else "use "
            
            # Organize items by module
            module_groups, simple_items = organize_items_by_module(items)
            
            # Sort simple items (self comes last by convention)
            sorted_simple_items = sorted([item for item in simple_items if item != 'self'])
            if 'self' in simple_items:
                sorted_simple_items.append('self')
            
            # Add sorted module groups
            sorted_items = sorted_simple_items + format_module_groups(module_groups)
            
            # Format the final import statement
            # For readability and consistency with rustfmt standards
            if len(sorted_items) == 1:
                # Single item - no braces needed
                result.append(f"{prefix}{base_path}::{sorted_items[0]};")
            elif any("{" in item for item in sorted_items) or len(sorted_items) > 2:
                result.append(f"{prefix}{base_path}::{{")
                for item in sorted_items:
                    result.append(f"    {item},")
                result.append("};")
            else:
                result.append(f"{prefix}{base_path}::{{{', '.join(sorted_items)}}};")

    return result
