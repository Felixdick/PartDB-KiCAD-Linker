import os
import re

def parse_existing_library(file_path: str) -> dict:
    """
    Parses a .kicad_sym file and returns a dict of symbol blocks.
    Returns: {symbol_name: full_symbol_block_string}
    """
    symbols = {}
    if not os.path.exists(file_path):
        return symbols
        
    print(f"  - Parsing existing file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Regex to find top-level (symbol "..." (...) ) blocks
        # This is a simplified parser; it relies on balanced parentheses
        # outside of strings.
        symbol_pattern = re.compile(r'\(\s*symbol\s+"(.*?)"', re.MULTILINE)
        
        for match in symbol_pattern.finditer(content):
            symbol_name = match.group(1)
            start_index = match.start()
            
            # Find the matching closing parenthesis
            end_index = _find_matching_paren(content, start_index)
            
            if end_index != -1:
                symbol_block = content[start_index : end_index + 1]
                symbols[symbol_name] = symbol_block
            else:
                print(f"Warning: Could not parse symbol '{symbol_name}' in {file_path}. Skipping.")
        
        print(f"  - Found {len(symbols)} existing symbols.")
        return symbols
        
    except Exception as e:
        print(f"Warning: Could not read or parse {file_path}. {e}")
        return {}

def _find_matching_paren(text, start_pos=0):
    """Finds the position of the matching parenthesis."""
    open_parens = 0
    in_string = False
    for i, char in enumerate(text[start_pos:]):
        if char == '"' and (i == 0 or text[start_pos + i - 1] != '\\'):
            in_string = not in_string
        elif char == '(' and not in_string:
            open_parens += 1
        elif char == ')' and not in_string:
            open_parens -= 1
            if open_parens == 0:
                return start_pos + i
    return -1
