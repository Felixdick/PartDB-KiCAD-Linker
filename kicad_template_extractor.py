#
# Main script to generate a KiCad symbol library (.kicad_sym) from Part-DB.
#
# This script fetches parts from a Part-DB instance, processes them using
# templates defined in a YAML file, and generates a KiCad library file.
#
# It supports static templates (from 'symbol_template') and dynamic
# generation (from 'symbol_generator') for parts like ICs.
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
import math

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


def _build_one_unit(symbol_name_prefix: str, unit_number: int, pins_list: list, power_names_upper: list) -> (str, str):
    """
    Generates the KiCad graphics and pin text for a single unit (Part A, B, etc.).
    
    Returns a tuple of (graphics_string, pins_string)
    
    Args:
        symbol_name_prefix: The base name (e.g., "My_IC")
        unit_number: The unit number (1 for Part A, 2 for Part B)
        pins_list: A list of tuples, e.g., [("1", "VCC"), ("2", "GND")]
        power_names_upper: A list of uppercase power pin names for setting pin type
    """
    graphics_lines = []
    pin_lines = []
    
    # --- 1. Calculate Geometry ---
    # Standard KiCad grid sizes
    GRID_SPACING = 2.54  # 100mil
    PIN_LENGTH = 2.54
    BOX_WIDTH = 7.62     # 300mil
    
    total_pins = len(pins_list)
    left_pin_count = math.ceil(total_pins / 2.0)
    right_pin_count = total_pins // 2
    
    # Box height is determined by the side with more pins
    box_height_pins = max(left_pin_count, right_pin_count)
    # Ensure a minimum height for the box
    min_height_grids = 3
    # Calculate height based on pins, ensuring it's at least min_height
    # Add 1 grid spacing for padding if there are pins
    box_height_grids = max(min_height_grids, (box_height_pins - 1) if box_height_pins > 0 else 0)
    box_height = (box_height_grids * GRID_SPACING) + GRID_SPACING # Total height
    
    # Coordinates for the box
    top = (box_height / 2.0)
    bottom = -top
    left = -BOX_WIDTH / 2.0
    right = BOX_WIDTH / 2.0
    
    # Coordinates for pins
    pin_x_left = -BOX_WIDTH / 2.0 - PIN_LENGTH
    pin_x_right = BOX_WIDTH / 2.0 + PIN_LENGTH
    
    # --- 2. Add Graphics Block (e.g., _0_1 for unit 1) ---
    graphics_lines.append(f'    (symbol "{symbol_name_prefix}_0_{unit_number}" (unit {unit_number})')
    graphics_lines.append(f'      (rectangle (start {left:.2f} {top:.2f}) (end {right:.2f} {bottom:.2f})')
    graphics_lines.append('        (stroke (width 0.254) (type default)) (fill (type background))')
    graphics_lines.append('      )')
    graphics_lines.append('    )') # Close (symbol ... _0_X)
    
    # --- 3. Add Pins Block (e.g., _1_1 for unit 1) ---
    # *** THIS IS THE FIX ***
    # Pins are wrapped in their own (symbol ..._1_X ...) block
    pin_lines.append(f'    (symbol "{symbol_name_prefix}_1_{unit_number}" (unit {unit_number})')
    
    pin_index = 0
    # Calculate starting Y position
    start_y_left = (left_pin_count - 1) * GRID_SPACING / 2.0
    start_y_right = (right_pin_count - 1) * GRID_SPACING / 2.0

    # Add Left Pins
    for i in range(left_pin_count):
        pin_number, pin_name = pins_list[pin_index]
        pin_index += 1
        y_pos = start_y_left - (i * GRID_SPACING)
        pin_type = "power_in" if pin_name.upper() in power_names_upper else "passive"
        
        pin_lines.append(f'      (pin {pin_type} line (at {pin_x_left:.2f} {y_pos:.2f} 0) (length {PIN_LENGTH})')
        pin_lines.append(f'        (name "{pin_name}" (effects (font (size 1.27 1.27))))')
        pin_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
        pin_lines.append('      )')

    # Add Right Pins
    for i in range(right_pin_count):
        pin_number, pin_name = pins_list[pin_index]
        pin_index += 1
        y_pos = start_y_right - (i * GRID_SPACING)
        pin_type = "power_in" if pin_name.upper() in power_names_upper else "passive"
        
        pin_lines.append(f'      (pin {pin_type} line (at {pin_x_right:.2f} {y_pos:.2f} 180) (length {PIN_LENGTH})')
        pin_lines.append(f'        (name "{pin_name}" (effects (font (size 1.27 1.27))))')
        pin_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
        pin_lines.append('      )')
    
    pin_lines.append('    )') # Close (symbol ... _1_X)
        
    return ('\n'.join(graphics_lines), '\n'.join(pin_lines))


def _generate_dynamic_ic_units(symbol_name: str, pin_csv: str, power_names: list) -> (str, str, bool):
    """
    Parses a pin CSV and generates KiCad unit blocks for main and power pins.
    Returns a tuple: (all_graphics_blocks, all_pin_blocks, has_part_b_boolean)
    """
    if not pin_csv:
        # No pins, generate a box with a warning
        graphics_block = (
            f'    (symbol "{symbol_name}_0_1" (unit 1)\n'
            f'      (rectangle (start -5.08 2.54) (end 5.08 -2.54) (stroke (width 0.254) (type default)) (fill (type background)))\n'
            f'      (text "No \'Pin Description\'" (at 0 0 0) (effects (font (size 1.27 1.27))))\n'
            f'    )\n'
            # Add an empty pin block
            f'    (symbol "{symbol_name}_1_1" (unit 1))\n'
        )
        return (graphics_block, "", False)

    # 1. Prepare lists
    main_pins = []
    power_pins = []
    # Convert power_names to uppercase for case-insensitive compare
    power_names_upper = [name.upper() for name in power_names]

    # 2. Parse and Sort Pins
    all_pin_names = [name.strip() for name in pin_csv.split(',') if name.strip()]
    
    for i, pin_name in enumerate(all_pin_names):
        pin_number = str(i + 1)
        pin_data = (pin_number, pin_name) # Store as (number, name)

        if pin_name.upper() in power_names_upper:
            power_pins.append(pin_data)
        else:
            main_pins.append(pin_data)
            
    # 3. Decide on unit structure
    # Create Part B *only* if there are both main pins AND power pins.
    has_part_b = len(main_pins) > 0 and len(power_pins) > 0

    pins_for_part_a = []
    pins_for_part_b = []
    
    if has_part_b:
        pins_for_part_a = main_pins
        pins_for_part_b = power_pins
    else:
        # Dump all pins into Part A
        pins_for_part_a = main_pins + power_pins
        
    # 4. Build the final string
    all_graphics_strings = []
    all_pin_strings = []

    # 5. Generate Part A (Main Pins or All Pins)
    if not pins_for_part_a and not pins_for_part_b:
         # This should only happen if pin_csv was empty, which is handled above,
         # but as a fallback, create an empty part A.
         graphics_a, pins_a = _build_one_unit(symbol_name, 1, [], power_names_upper)
         all_graphics_strings.append(graphics_a)
         all_pin_strings.append(pins_a)
    else:
        graphics_a, pins_a = _build_one_unit(symbol_name, 1, pins_for_part_a, power_names_upper)
        all_graphics_strings.append(graphics_a)
        all_pin_strings.append(pins_a)

    # 6. Generate Part B (Power Pins) - ONLY if it makes sense
    if has_part_b:
        graphics_b, pins_b = _build_one_unit(symbol_name, 2, pins_for_part_b, power_names_upper)
        all_graphics_strings.append(graphics_b)
        all_pin_strings.append(pins_b)

    # 7. Return the combined string and the flag
    return ('\n'.join(all_graphics_strings), '\n'.join(all_pin_strings), has_part_b)


def generate_symbol(part: Part, template: dict) -> str:
    """
    Generates a single KiCad symbol string for a given part using a template.
    Can be static (from 'symbol_template') or dynamic (from 'symbol_generator').
    """
    symbol_name = part.name.replace(' ', '_')
    
    # --- Process and place all properties ---
    all_properties = {}
    
    # 1. Process field_mapping
    for field_name, key_path in template.get('field_mapping', {}).items():
        if isinstance(key_path, str) and key_path.startswith("'") and key_path.endswith("'"):
            value = key_path.strip("'")
        else:
            value = get_value_from_part(part, key_path)
            if not value:
                value = get_value_from_part(part, field_name)
        all_properties[field_name] = value

    # 2. Add all other parameters from the part
    for param_name, param_value in part.parameters.items():
        if param_name not in all_properties and param_value:
            resolved_value = get_value_from_part(part, param_name)
            all_properties[param_name] = resolved_value
    
    
    # --- NEW DYNAMIC/STATIC SYMBOL LOGIC ---
    
    generator_type = template.get("symbol_generator")
    symbol_lines = [] # Initialize list to build the symbol string

    if generator_type == "IC_Box":
        # --- DYNAMIC "IC_Box" GENERATOR ---
        
        # 1. Get pin-sorting info
        power_names_list = template.get("power_pin_names", [])
        
        # 2. Get the raw pin description string
        pin_csv_string = get_value_from_part(part, "Pin Description")
        
        # 3. Generate the KiCad text for all units (A, B, etc.)
        (dynamic_graphics_str, dynamic_pins_str, has_part_b) = _generate_dynamic_ic_units(
            symbol_name,
            pin_csv_string,
            power_names_list
        )
        
        # 4. Get base symbol options
        symbol_options = template.get("symbol_options", "")
        
        # 5. Add multi-unit definitions if Part B was created
        if has_part_b:
            symbol_options += ' (all_units_locked yes) (unit_name "A" (inner_sym 0 0)) (unit_name "B" (inner_sym 0 0))'

        # 6. Create the main (symbol ...) definition
        symbol_lines.append(
            f'    (symbol "{symbol_name}" {symbol_options} (in_bom yes) (on_board yes)'
        )
        
        # 7. Generate property strings using templates
        for prop_name, prop_value in all_properties.items():
            prop_template = template.get('property_templates', {}).get(prop_name)
            if prop_template:
                # Replace tabs/newlines from YAML multi-line strings
                clean_template = " ".join(prop_template.split())
                prop_line = clean_template.replace('{VALUE}', prop_value)
                symbol_lines.append(f'      {prop_line}')
            else:
                # Added the missing final closing parenthesis
                symbol_lines.append(f'      (property "{prop_name}" "{prop_value}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)) )')

        # 8. Add the generated graphics/pins for all units
        if dynamic_graphics_str:
            symbol_lines.append(f'  {dynamic_graphics_str}') # Add the graphics blocks
        if dynamic_pins_str:
            symbol_lines.append(f'  {dynamic_pins_str}') # Add the pin blocks

    elif template.get("symbol_template"):
        # --- STATIC "symbol_template" GENERATOR (Original Logic) ---
        
        # 1. Create the main (symbol ...) definition
        symbol_lines.append(
            f'    (symbol "{symbol_name}" {template.get("symbol_options", "")} (in_bom yes) (on_board yes)'
        )
        
        # 2. Generate property strings
        for prop_name, prop_value in all_properties.items():
            prop_template = template.get('property_templates', {}).get(prop_name)
            if prop_template:
                # Replace tabs/newlines from YAML multi-line strings
                clean_template = " ".join(prop_template.split())
                prop_line = clean_template.replace('{VALUE}', prop_value)
                symbol_lines.append(f'      {prop_line}')
            else:
                # Added the missing final closing parenthesis
                symbol_lines.append(f'      (property "{prop_name}" "{prop_value}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)) )')

        # 3. Add the static symbol graphics and pins
        raw_template = template.get("symbol_template", "")
        
        match = re.search(r'\(symbol\s+"(.*?)(?:_\d+_\d+)"', raw_template)
        if match:
            original_prefix = match.group(1)
            processed_template = raw_template.replace(original_prefix, symbol_name)
            # Add indentation
            indented_template = '\n'.join([f'    {line}' for line in processed_template.splitlines() if line.strip()])
            symbol_lines.append(indented_template)
        else:
            # Fallback for templates that might not follow the standard naming
            indented_template = '\n'.join([f'    {line}' for line in raw_template.splitlines() if line.strip()])
            symbol_lines.append(indented_template)
            
    else:
        # --- FALLBACK (No template or generator) ---
        symbol_lines.append(
            f'    (symbol "{symbol_name}" (in_bom yes) (on_board yes)'
        )
        symbol_lines.append(f'      (text "No template found for {symbol_name}" (at 0 0 0) (effects (font (size 1.27 1.27))))')
        print(f"  - Warning: No symbol_template or symbol_generator for category, part '{part.name}'. No graphics will be added.")

    symbol_lines.append('    )') # Close the main (symbol ...)
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

    # --- *** NEW LOGIC *** ---
    # Iterate through each fetched PART CATEGORY first
    for api_category, parts_in_category in parts_by_category.items():
        
        found_template = None
        # Now, search the templates to find one that applies to this category
        for template_name, template_data in templates.items():
            template_categories = template_data.get('applies_to_categories', [])
            
            for template_cat_name in template_categories:
                # Check if the API category ENDS WITH the one from the template list
                # This allows matching "Electronics -> ICs -> Logic" with just "Logic"
                if api_category.strip().lower().endswith(template_cat_name.strip().lower()):
                    found_template = template_data
                    break
            if found_template:
                break # Found a template, stop searching

        # If no template claims this category, skip it
        if not found_template:
            print(f"Info: No template found with a matching 'applies_to_categories' entry for '{api_category}'. Skipping.")
            continue
            
        # --- Found a template, proceed as before ---
        
        # Use the last part of the category path for the filename.
        library_name = api_category.split(' → ')[-1].replace(' ', '_').replace('/', '_')
        output_path = os.path.join(OUTPUT_DIR, f"{library_name}.kicad_sym")
        
        print(f"Generating library for category '{api_category}' with {len(parts_in_category)} parts...")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('(kicad_symbol_lib (version 20211014) (generator partdb_linker)\n')
            for part in parts_in_category:
                try:
                    # Use the found_template to generate the symbol
                    symbol_str = generate_symbol(part, found_template)
                    f.write(symbol_str + '\n')
                except Exception as e:
                    print(f"  - Error generating symbol for part '{part.name}': {e}")
            f.write(')\n')
        
        print(f"  -> Successfully created library at '{output_path}'")

    print("\n--- KiCad Library Generation Finished ---")

if __name__ == "__main__":
    main()