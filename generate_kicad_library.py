#
# Main script to generate a KiCad symbol library (.kicad_sym) from Part-DB.
#
# This script fetches parts from a Part-DB instance, processes them using
# templates defined in a YAML file, and generates a KiCad library file.
#
# Prerequisites:
# - Python 3.6+
# - PyYAML: pip install pyyaml
# - requests: pip install requests
#
# Usage:
# python generate_kicad_library.py
#

import yaml
from datetime import datetime
from functools import reduce
import os
import re # Import the regular expression module

# Import the Part-DB API client script
from partdb_api_client import fetch_parts_from_api, Part

# --- Configuration ---
# Path to the YAML template file
TEMPLATE_FILE = 'templates.yaml'
# Directory where the generated library files will be saved
OUTPUT_DIR = 'kicad_libs'
# --- API Configuration ---
# Your Part-DB instance URL
API_BASE_URL = 'http://localhost:8888'
# Your Part-DB API token
API_TOKEN = 'tcp_549c6a43b2de4b34e7a9cdd7640751a2dc3d68d24b002241b2a911320270b091'
# Fetch parts created after this date
PARTS_AFTER_DATE = '2025-10-01' # Format: YYYY-MM-DD


def get_value_from_part(part: Part, key_path: str):
    """
    Retrieves a value from a Part object based on a key path (e.g., 'name' or 'footprint.name').
    It first checks direct attributes, then checks the parameters dictionary.
    """
    val = None
    try:
        # Handle nested keys like 'footprint.name'
        if '.' in key_path:
            # Use getattr to safely access nested attributes
            val = reduce(lambda d, key: getattr(d, key, None) if hasattr(d, key) else d.get(key) if isinstance(d, dict) else None, key_path.split('.'), part)
        else:
            # First, try to get as a direct attribute
            val = getattr(part, key_path, None)
            # If not found, check inside the parameters dictionary
            if val is None:
                # Check for key_path as-is and with first letter capitalized for robustness
                param_val = part.parameters.get(key_path)
                if param_val is None:
                     param_val = part.parameters.get(key_path.capitalize())
                val = param_val

    except (AttributeError, TypeError):
        val = None

    # Handle case where value is None or not found
    if val is None:
        return ""

    # Return the raw value, preserving variables like ${Resistance}
    return str(val)


def generate_symbol(part: Part, template: dict) -> str:
    """
    Generates a single KiCad symbol string for a given part using a template.
    """
    symbol_name = part.name.replace(' ', '_')
    symbol_lines = [
        f'    (symbol "{symbol_name}" {template.get("symbol_options", "")} (in_bom yes) (on_board yes)'
    ]

    # --- Process and place all properties ---
    all_properties = {}
    
    # 1. Process field_mapping
    for field_name, key_path in template.get('field_mapping', {}).items():
        # Check if the key_path is a literal string (e.g., "'R?'")
        if isinstance(key_path, str) and key_path.startswith("'") and key_path.endswith("'"):
            # It's a literal value, just strip the quotes
            value = key_path.strip("'")
        else:
            # It's a path to data, so fetch it from the part object
            value = get_value_from_part(part, key_path)
            # --- NEW FALLBACK LOGIC ---
            # If the primary mapping returns nothing, try looking for a parameter
            # with the same name as the KiCad field itself (e.g., "Datasheet").
            if not value:
                value = get_value_from_part(part, field_name)
        
        all_properties[field_name] = value

    # 2. Add all other parameters from the part
    for param_name, param_value in part.parameters.items():
        if param_name not in all_properties and param_value:
            # Get the raw value, which might be a variable
            resolved_value = get_value_from_part(part, param_name)
            all_properties[param_name] = resolved_value
    
    # 3. Generate property strings using templates
    for prop_name, prop_value in all_properties.items():
        prop_template = template.get('property_templates', {}).get(prop_name)
        if prop_template:
            # Use the template for placement and visibility
            prop_line = prop_template.replace('{VALUE}', prop_value)
            symbol_lines.append(f'      {prop_line}')
        else:
            # If no template, place at origin and hide
            symbol_lines.append(f'      (property "{prop_name}" "{prop_value}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))')

    # Add the symbol graphics and pins from the template, replacing the hard-coded name
    raw_template = template.get("symbol_template", "")
    if raw_template:
        # Find the original symbol name prefix from the template
        # e.g., find "Some_Cap_Name" from `(symbol "Some_Cap_Name_0_1"`
        match = re.search(r'\(symbol\s+"(.*?)(?:_\d+_\d+)"', raw_template)
        if match:
            original_prefix = match.group(1)
            # Replace the old, hard-coded prefix with the new symbol's name
            processed_template = raw_template.replace(original_prefix, symbol_name)
            symbol_lines.append(f'      {processed_template}')
        else:
            # Fallback for templates that might not follow the standard naming
            symbol_lines.append(f'      {raw_template}')

    symbol_lines.append('    )')

    return '\n'.join(symbol_lines)


def main():
    """Main execution function."""
    print("--- Starting KiCad Library Generation ---")

    # Load templates from YAML file
    try:
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            templates = yaml.safe_load(f)
        if not templates:
            print(f"Error: The template file '{TEMPLATE_FILE}' is empty or invalid.")
            return
    except FileNotFoundError:
        print(f"Error: Template file not found at '{TEMPLATE_FILE}'. Please create it.")
        return
    except yaml.YAMLError as e:
        print(f"Error: Could not parse the YAML template file. {e}")
        return

    # Fetch parts from the Part-DB API using the configuration from this file
    parts = fetch_parts_from_api(API_BASE_URL, API_TOKEN, PARTS_AFTER_DATE)
    if not parts:
        print("No parts were fetched from the API. Exiting.")
        return
    
    print(f"Fetched {len(parts)} parts from Part-DB.")

    # Organize parts by category
    parts_by_category = {}
    for part in parts:
        # Use the full_path for more specific category matching if available
        category_name = part.category.get('full_path', part.category.get('name')) if part.category else 'Uncategorized'
        if category_name not in parts_by_category:
            parts_by_category[category_name] = []
        parts_by_category[category_name].append(part)

    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Generate a .kicad_sym file for each category found in the templates
    for template_category_name, template in templates.items():
        # Find the parts list that corresponds to the current template category.
        # This logic checks if the full category path from the API ends with the
        # category name defined in the template YAML. This allows for flexible matching.
        parts_in_category = None
        full_category_name = None

        for api_category, parts_list in parts_by_category.items():
            # Robust matching: strip whitespace and compare in lowercase
            if api_category.strip().lower().endswith(template_category_name.strip().lower()):
                parts_in_category = parts_list
                full_category_name = api_category
                break # Found the matching parts, exit the inner loop

        if not parts_in_category:
            print(f"Info: No parts found for the category '{template_category_name}' defined in the template.")
            continue

        # Use the last part of the category path for the filename.
        library_name = full_category_name.split(' → ')[-1].replace(' ', '_')
        output_path = os.path.join(OUTPUT_DIR, f"{library_name}.kicad_sym")
        
        print(f"Generating library for category '{full_category_name}' with {len(parts_in_category)} parts...")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('(kicad_symbol_lib (version 20211014) (generator partdb_linker)\n')
            for part in parts_in_category:
                try:
                    symbol_str = generate_symbol(part, template)
                    f.write(symbol_str + '\n')
                except Exception as e:
                    print(f"  - Error generating symbol for part '{part.name}': {e}")
            f.write(')\n')
        
        print(f"  -> Successfully created library at '{output_path}'")

    print("\n--- KiCad Library Generation Finished ---")

if __name__ == "__main__":
    main()

