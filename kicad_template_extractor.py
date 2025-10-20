#
# A helper script to extract the symbol graphics, pins, and property templates
# from an existing KiCad symbol library (.kicad_sym) file.
#
# This version is designed to work robustly with the modern KiCad 7+ format.
# The output can be pasted directly into the templates.yaml file.
#
# Prerequisites:
# - Python 3.6+
#
# Usage:
# python kicad_template_extractor.py --library "path/to/library.kicad_sym" --symbol "Symbol_Name"
#

import argparse
import re

def find_matching_paren(text, start_pos=0):
    """Finds the position of the matching parenthesis for the one at start_pos."""
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

def extract_symbol_template(library_path: str, symbol_name: str):
    """
    Parses a .kicad_sym file to find a specific symbol and extract its
    graphics, pin definitions, options, and property templates.
    """
    try:
        with open(library_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: Library file not found at '{library_path}'")
        return

    # Find the start of the main symbol definition
    symbol_start_pattern = re.compile(r'\(\s*symbol\s+"' + re.escape(symbol_name) + r'"', re.MULTILINE)
    match = symbol_start_pattern.search(content)

    if not match:
        print(f"Error: Symbol '{symbol_name}' not found in '{library_path}'.")
        print("Please check the symbol name (it is case-sensitive).")
        return

    start_index = match.start()
    end_index = find_matching_paren(content, start_index)
    if end_index == -1:
        print("Error: Could not parse the symbol definition (mismatched parentheses).")
        return

    full_symbol_block = content[start_index : end_index + 1]

    # --- Extract relevant pieces from the full block ---
    
    # 1. Extract Symbol Options (e.g., pin_numbers, pin_names)
    options = []
    for option_name in ["pin_numbers", "pin_names", "exclude_from_sim"]:
        match = re.search(r'\(\s*' + option_name + r'\s+', full_symbol_block)
        if match:
            start = match.start()
            end = find_matching_paren(full_symbol_block, start)
            if end != -1:
                option_block = full_symbol_block[start:end+1]
                options.append(' '.join(option_block.strip().split()))

    symbol_options_str = ' '.join(options)

    # 2. Extract Graphics and Pins (child symbols and pin definitions)
    template_parts = []
    for match in re.finditer(r'\(\s*(pin|symbol)\s+', full_symbol_block):
        token_type = match.group(1)
        start = match.start()
        end = find_matching_paren(full_symbol_block, start)
        
        if end != -1:
            block = full_symbol_block[start:end+1]
            # Check if it's a pin or a child symbol for graphics
            if token_type == 'pin' or (token_type == 'symbol' and f'"{symbol_name}_' in block.split('\n')[0]):
                lines = block.strip().split('\n')
                cleaned_block = '\n'.join([lines[0]] + ['  ' + line.strip() for line in lines[1:]])
                template_parts.append(cleaned_block)
    
    # 3. Extract Property Templates
    property_templates = {}
    for match in re.finditer(r'\(\s*property\s+', full_symbol_block):
        start = match.start()
        end = find_matching_paren(full_symbol_block, start)
        if end != -1:
            prop_block = full_symbol_block[start:end+1]
            
            # Extract the property name (the first quoted string)
            name_match = re.search(r'\(\s*property\s+"(.*?)"', prop_block)
            if not name_match:
                continue
            prop_name = name_match.group(1)

            # Find the value (the second quoted string) and replace it with {VALUE}
            first_quote_end = prop_block.find('"', name_match.start(1)) + 1
            second_quote_start = prop_block.find('"', first_quote_end)
            second_quote_end = prop_block.find('"', second_quote_start + 1)
            
            if second_quote_start != -1 and second_quote_end != -1:
                template_str = prop_block[:second_quote_start+1] + "{VALUE}" + prop_block[second_quote_end:]
                property_templates[prop_name] = ' '.join(template_str.strip().split())


    # --- Print the final YAML output ---
    print("--- Extracted Template (KiCad 7+) ---")
    print("\nPaste the following into your templates.yaml file:\n")
    
    print("# Replace the category name below with the exact name from your Part-DB.")
    print(f'"{symbol_name}_Category": # <-- RENAME THIS')
    print("  field_mapping:")
    print("    \"Reference\": \"'R?'\" # <-- EDIT THIS AS NEEDED")
    print("    \"Value\": \"value\"")
    print("    \"Footprint\": \"footprint.name\"")
    print("    \"Datasheet\": \"manufacturer_product_url\"")
    print("    # Add other direct mappings here if needed")
    print("")

    if symbol_options_str:
        print(f"  symbol_options: '{symbol_options_str}'")
        print("")

    if property_templates:
        print("  property_templates:")
        for name, template in property_templates.items():
            # **FIXED**: Use single quotes around the template value to handle nested double quotes
            print(f"    \"{name}\": '{template}'")
        print("")

    print("  symbol_template: |")
    for part in template_parts:
        for line in part.split('\n'):
            print(f"    {line}")
    
    print("\n-------------------------------------")


def main():
    parser = argparse.ArgumentParser(
        description="Extract a full symbol template from a .kicad_sym file (v7+).",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-l', '--library', required=True,
        help="Path to the KiCad symbol library file (e.g., 'symbols/Device.kicad_sym')."
    )
    parser.add_argument(
        '-s', '--symbol', required=True,
        help="The exact name of the symbol to extract (e.g., 'R')."
    )
    args = parser.parse_args()
    extract_symbol_template(args.library, args.symbol)

if __name__ == "__main__":
    main()
