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


def _build_symbol_child_block(symbol_name_prefix: str, unit_number: int, pins_list: list, power_names_upper: list) -> (str, dict):
    """
    Generates the KiCad symbol block for a single IC unit (e.g., ..._1_1 or ..._2_1),
    combining graphics and pins as required by KiCad 7+.
    
    Returns a tuple of (unit_block_string, geometry_dict)
    """
    unit_lines = []
    
    # --- 1. Calculate Geometry ---
    GRID_SPACING = 2.54  # 100mil
    PIN_LENGTH = 2.54
    BOX_WIDTH = 15.24    # 600mil
    
    total_pins = len(pins_list)
    left_pin_count = math.ceil(total_pins / 2.0)
    right_pin_count = total_pins // 2
    
    box_height_pins = max(left_pin_count, right_pin_count)
    
    if unit_number == 1:
        # Unit A (main block) has a min height of 400mil (3 grid units + padding)
        min_height_grids = 3
    else:
        # Unit B (power block) has a min height of 300mil (2 grid units + padding)
        min_height_grids = 2
    
    box_height_grids = max(min_height_grids, (box_height_pins - 1) if box_height_pins > 0 else 0)
    box_height = (box_height_grids * GRID_SPACING) + GRID_SPACING # Total height
    
    top = (box_height / 2.0)
    bottom = -top
    left = -BOX_WIDTH / 2.0
    right = BOX_WIDTH / 2.0
    
    geometry = {
        'box_top': top,
        'box_left': left
    }
    
    pin_x_left = -BOX_WIDTH / 2.0 - PIN_LENGTH
    pin_x_right = BOX_WIDTH / 2.0 + PIN_LENGTH
    
    # --- 2. Build the combined (symbol ..._X_1 ...) block ---
    unit_lines.append(f'    (symbol "{symbol_name_prefix}_{unit_number}_1"')
    
    # Add Graphics (Rectangle)
    unit_lines.append(f'      (rectangle (start {left:.2f} {top:.2f}) (end {right:.2f} {bottom:.2f})')
    unit_lines.append('        (stroke (width 0.254) (type default)) (fill (type background))')
    unit_lines.append('      )')
    
    # --- 3. Add Pins ---
    pin_index = 0
    start_y_left = (left_pin_count - 1) * GRID_SPACING / 2.0
    start_y_right = (right_pin_count - 1) * GRID_SPACING / 2.0

    # Add Left Pins
    for i in range(left_pin_count):
        pin_number, pin_name = pins_list[pin_index]
        pin_index += 1
        y_pos = start_y_left - (i * GRID_SPACING)
        pin_type = "power_in" if pin_name.upper() in power_names_upper else "passive"
        
        unit_lines.append(f'      (pin {pin_type} line (at {pin_x_left:.2f} {y_pos:.2f} 0) (length {PIN_LENGTH})')
        unit_lines.append(f'        (name "{pin_name}" (effects (font (size 1.27 1.27))))')
        unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
        unit_lines.append('      )')

    # Add Right Pins
    for i in range(right_pin_count):
        pin_number, pin_name = pins_list[pin_index]
        pin_index += 1
        y_pos = start_y_right - (i * GRID_SPACING)
        pin_type = "power_in" if pin_name.upper() in power_names_upper else "passive"
        
        unit_lines.append(f'      (pin {pin_type} line (at {pin_x_right:.2f} {y_pos:.2f} 180) (length {PIN_LENGTH})')
        unit_lines.append(f'        (name "{pin_name}" (effects (font (size 1.27 1.27))))')
        unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
        unit_lines.append('      )')
    
    # Close the child symbol block
    unit_lines.append('    )') 
        
    return ('\n'.join(unit_lines), geometry)


def _generate_dynamic_symbol_blocks(symbol_name: str, pin_csv: str, power_names: list) -> (str, dict):
    """
    Parses a pin CSV and generates KiCad symbol blocks for IC main and power pins.
    
    Returns a tuple: (all_unit_blocks_string, unit_1_geometry_dict)
    """
    
    # 1. Prepare lists
    main_pins = []
    power_pins = []
    power_names_upper = [name.upper() for name in power_names]

    # 2. Parse and Sort Pins
    all_pin_names = [name.strip() for name in pin_csv.split(',') if name.strip()]
    
    current_pin_number = 1
    
    for pin_name in all_pin_names:
        pin_number = str(current_pin_number)
        pin_data = (pin_number, pin_name) # Store as (number, name)

        if pin_name.upper() in power_names_upper:
            power_pins.append(pin_data)
        else:
            main_pins.append(pin_data)
        
        current_pin_number += 1 # Increment for every pin
            
    # 3. Decide on unit structure
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
    all_unit_blocks = []
    geo_a = {}

    # 5. Generate Part A (Unit 1)
    if not pins_for_part_a and not pins_for_part_b:
         unit_a_str, geo_a = _build_symbol_child_block(symbol_name, 1, [], power_names_upper)
         all_unit_blocks.append(unit_a_str)
    else:
        unit_a_str, geo_a = _build_symbol_child_block(symbol_name, 1, pins_for_part_a, power_names_upper)
        all_unit_blocks.append(unit_a_str)

    # 6. Generate Part B (Unit 2) - ONLY if it makes sense
    if has_part_b:
        unit_b_str, _ = _build_symbol_child_block(symbol_name, 2, pins_for_part_b, power_names_upper)
        all_unit_blocks.append(unit_b_str)

    # 7. Return the combined string and Unit 1's geometry
    return ('\n'.join(all_unit_blocks), geo_a)


def _generate_dynamic_connector_block(symbol_name_prefix: str, part: Part) -> (str, dict):
    """
    Generates the KiCad symbol block for a single Connector.
    
    Returns a tuple of (symbol_block_string, geometry_dict)
    """
    unit_lines = []
    
    # --- 1. Fetch Connector Parameters ---
    try:
        num_rows_str = get_value_from_part(part, "Number of Rows")
        num_rows = int(num_rows_str or 1)
    except ValueError:
        num_rows = 1
        
    try:
        pins_per_row_str = get_value_from_part(part, "Pins per Row")
        pins_per_row = int(pins_per_row_str or 0) # Default to 0 to detect if it was found
    except ValueError:
        pins_per_row = 0

    # Fallback: If "Pins per Row" isn't specified, check for "Number of Pins" or "Pin Count"
    if pins_per_row == 0:
        try:
            total_pins_str = get_value_from_part(part, "Number of Pins")
            if not total_pins_str:
                 total_pins_str = get_value_from_part(part, "Pin Count")
                 
            total_pins = int(total_pins_str or 0)
            
            if total_pins > 0:
                if num_rows == 1:
                    pins_per_row = total_pins
                elif num_rows > 1:
                    pins_per_row = math.ceil(total_pins / num_rows)
                    
        except ValueError:
            pass 

    # Final fallback: If still no pins, default to 1
    if pins_per_row <= 0:
        pins_per_row = 1
        
    if num_rows <= 0:
        num_rows = 1
        
    gender = get_value_from_part(part, "Gender").lower()
    
    # --- 2. Calculate Geometry ---
    GRID_SPACING = 2.54  # 100mil
    PIN_LENGTH = 2.54
    
    # --- *** MODIFIED: Adjust box width for single-row headers *** ---
    if num_rows == 1:
        BOX_WIDTH = 3.81 # 150mil
    else:
        BOX_WIDTH = 7.62     # 300mil
    
    left_pin_count = 0
    right_pin_count = 0
    
    if num_rows == 1:
        left_pin_count = pins_per_row
    else:
        # Assume 2 or more rows means pins on both sides
        left_pin_count = pins_per_row
        right_pin_count = pins_per_row
        
    box_height_pins = max(left_pin_count, right_pin_count)
    
    box_height_grids = max(2, (box_height_pins - 1) if box_height_pins > 0 else 0)
    box_height = (box_height_grids * GRID_SPACING) + GRID_SPACING
    
    top = (box_height / 2.0)
    bottom = -top
    left = -BOX_WIDTH / 2.0
    right = BOX_WIDTH / 2.0
    
    geometry = {
        'box_top': top,
        'box_left': left
    }
    
    pin_x_left = -BOX_WIDTH / 2.0 - PIN_LENGTH
    pin_x_right = BOX_WIDTH / 2.0 + PIN_LENGTH
    
    # --- 3. Build the combined (symbol ..._1_1 ...) block ---
    unit_lines.append(f'    (symbol "{symbol_name_prefix}_1_1"')
    
    # Add Graphics (Rectangle)
    unit_lines.append(f'      (rectangle (start {left:.2f} {top:.2f}) (end {right:.2f} {bottom:.2f})')
    unit_lines.append('        (stroke (width 0.254) (type default)) (fill (type background))')
    unit_lines.append('      )')
    
    # --- 4. Add Pins and Gender Graphics ---
    start_y_left = (left_pin_count - 1) * GRID_SPACING / 2.0
    start_y_right = (right_pin_count - 1) * GRID_SPACING / 2.0
    
    stroke_style = '(stroke (width 0.2) (type default)) (fill (type none))'

    # --- Fetch Pin Annotation and select numbering style ---
    pin_annotation_str = get_value_from_part(part, "Pin Annotation").lower()
    is_line_annotation = (num_rows > 1 and pin_annotation_str == "line")

    if is_line_annotation:
        # --- "Line" Annotation (e.g., Left: 1, 3; Right: 2, 4) ---
        current_pin_number = 1
        
        for i in range(pins_per_row): # Iterate row by row
            # --- Add Left Pin (1, 3, 5...) ---
            pin_number_left = str(current_pin_number)
            current_pin_number += 1
            y_pos = start_y_left - (i * GRID_SPACING)
            
            unit_lines.append(f'      (pin passive line (at {pin_x_left:.2f} {y_pos:.2f} 0) (length {PIN_LENGTH})')
            unit_lines.append(f'        (name "{pin_number_left}" (effects (font (size 1.27 1.27)) (hide yes)))')
            unit_lines.append(f'        (number "{pin_number_left}" (effects (font (size 1.27 1.27))))')
            unit_lines.append('      )')
            
            # Left Gender Graphic
            if gender == "male":
                gx_start = left + 0.635
                gx_end = left + (0.635 + 1.905) # left + 2.54
                unit_lines.append(f'      (polyline (pts (xy {gx_start:.2f} {y_pos:.2f}) (xy {gx_end:.2f} {y_pos:.2f})) {stroke_style})')
            
            elif gender == "female":
                radius = 0.635
                arc_base = left + (0.635 + 1.27 + radius) # left + 2.54
                arc_mid = arc_base - radius     # left + 1.905
                line_start = left + 0.635
                line_end = arc_mid 
                
                unit_lines.append(f'      (polyline (pts (xy {line_start:.2f} {y_pos:.2f}) (xy {line_end:.2f} {y_pos:.2f})) {stroke_style})')
                unit_lines.append(f'      (arc (start {arc_base:.2f} {y_pos + radius:.2f}) (mid {line_end:.2f} {y_pos:.2f}) (end {arc_base:.2f} {y_pos - radius:.2f}) {stroke_style})')
            
            # --- Add Right Pin (2, 4, 6...) ---
            if right_pin_count > 0:
                pin_number_right = str(current_pin_number)
                current_pin_number += 1
                y_pos = start_y_right - (i * GRID_SPACING)

                unit_lines.append(f'      (pin passive line (at {pin_x_right:.2f} {y_pos:.2f} 180) (length {PIN_LENGTH})')
                unit_lines.append(f'        (name "{pin_number_right}" (effects (font (size 1.27 1.27)) (hide yes)))')
                unit_lines.append(f'        (number "{pin_number_right}" (effects (font (size 1.27 1.27))))')
                unit_lines.append('      )')
                
                # Right Gender Graphic
                if gender == "male":
                    gx_start = right - 0.635
                    gx_end = right - (0.635 + 1.905) # right - 2.54
                    unit_lines.append(f'      (polyline (pts (xy {gx_start:.2f} {y_pos:.2f}) (xy {gx_end:.2f} {y_pos:.2f})) {stroke_style})')

                elif gender == "female":
                    # Symmetrical to left side
                    radius = 0.635
                    line_start = right - 0.635
                    arc_mid = right - (0.635 + 1.27) # right - 1.905
                    line_end = arc_mid
                    arc_base = right - (0.635 + 1.27 + radius) # right - 2.54
                    
                    unit_lines.append(f'      (polyline (pts (xy {line_start:.2f} {y_pos:.2f}) (xy {line_end:.2f} {y_pos:.2f})) {stroke_style})')
                    unit_lines.append(f'      (arc (start {arc_base:.2f} {y_pos + radius:.2f}) (mid {arc_mid:.2f} {y_pos:.2f}) (end {arc_base:.2f} {y_pos - radius:.2f}) {stroke_style})')

    else:
        # --- "Row" Annotation (Default) or Single Row (e.g., Left: 1, 2; Right: 3, 4) ---
        current_pin_number = 1
        
        # Add Left Pins
        for i in range(left_pin_count):
            pin_number = str(current_pin_number)
            current_pin_number += 1
            y_pos = start_y_left - (i * GRID_SPACING)
            
            unit_lines.append(f'      (pin passive line (at {pin_x_left:.2f} {y_pos:.2f} 0) (length {PIN_LENGTH})')
            unit_lines.append(f'        (name "{pin_number}" (effects (font (size 1.27 1.27)) (hide yes)))')
            unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
            unit_lines.append('      )')
            
            # Left Gender Graphic
            if gender == "male":
                gx_start = left + 0.635
                gx_end = left + (0.635 + 1.905) # left + 2.54
                unit_lines.append(f'      (polyline (pts (xy {gx_start:.2f} {y_pos:.2f}) (xy {gx_end:.2f} {y_pos:.2f})) {stroke_style})')
            
            elif gender == "female":
                radius = 0.635
                arc_base = left + (0.635 + 1.27 + radius) # left + 2.54
                arc_mid = arc_base - radius     # left + 1.905
                line_start = left + 0.635
                line_end = arc_mid 
                
                unit_lines.append(f'      (polyline (pts (xy {line_start:.2f} {y_pos:.2f}) (xy {line_end:.2f} {y_pos:.2f})) {stroke_style})')
                unit_lines.append(f'      (arc (start {arc_base:.2f} {y_pos + radius:.2f}) (mid {line_end:.2f} {y_pos:.2f}) (end {arc_base:.2f} {y_pos - radius:.2f}) {stroke_style})')

        # Add Right Pins (This loop will be skipped if num_rows == 1)
        for i in range(right_pin_count):
            pin_number = str(current_pin_number)
            current_pin_number += 1
            y_pos = start_y_right - (i * GRID_SPACING)
            
            unit_lines.append(f'      (pin passive line (at {pin_x_right:.2f} {y_pos:.2f} 180) (length {PIN_LENGTH})')
            unit_lines.append(f'        (name "{pin_number}" (effects (font (size 1.27 1.27)) (hide yes)))')
            unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
            unit_lines.append('      )')
            
            # Right Gender Graphic
            if gender == "male":
                gx_start = right - 0.635
                gx_end = right - (0.635 + 1.905) # right - 2.54
                unit_lines.append(f'      (polyline (pts (xy {gx_start:.2f} {y_pos:.2f}) (xy {gx_end:.2f} {y_pos:.2f})) {stroke_style})')

            elif gender == "female":
                # Symmetrical to left side
                radius = 0.635
                line_start = right - 0.635
                arc_mid = right - (0.635 + 1.27) # right - 1.905
                line_end = arc_mid
                arc_base = right - (0.635 + 1.27 + radius) # right - 2.54
                
                unit_lines.append(f'      (polyline (pts (xy {line_start:.2f} {y_pos:.2f}) (xy {line_end:.2f} {y_pos:.2f})) {stroke_style})')
                unit_lines.append(f'      (arc (start {arc_base:.2f} {y_pos + radius:.2f}) (mid {arc_mid:.2f} {y_pos:.2f}) (end {arc_base:.2f} {y_pos - radius:.2f}) {stroke_style})')

    # Close the child symbol block
    unit_lines.append('    )') 
        
    return ('\n'.join(unit_lines), geometry)


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
    unit_1_geo = {} # Store geometry for property placement
    dynamic_symbol_blocks_str = ""

    if generator_type == "IC_Box":
        # --- DYNAMIC "IC_Box" GENERATOR ---
        
        power_names_list = template.get("power_pin_names", [])
        pin_csv_string = get_value_from_part(part, "Pin Description")
        (dynamic_symbol_blocks_str, unit_1_geo) = _generate_dynamic_symbol_blocks(
            symbol_name,
            pin_csv_string,
            power_names_list
        )
        
    elif generator_type == "Connector":
        # --- DYNAMIC "Connector" GENERATOR ---
        (dynamic_symbol_blocks_str, unit_1_geo) = _generate_dynamic_connector_block(
            symbol_name,
            part
        )
        
    elif template.get("symbol_template"):
        # --- STATIC "symbol_template" GENERATOR (Original Logic) ---
        
        symbol_lines.append(
            f'    (symbol "{symbol_name}" {template.get("symbol_options", "")} (in_bom yes) (on_board yes)'
        )
        
        for prop_name, prop_value in all_properties.items():
            prop_template = template.get('property_templates', {}).get(prop_name)
            if prop_template:
                clean_template = " ".join(prop_template.split())
                prop_line = clean_template.replace('{VALUE}', prop_value)
                symbol_lines.append(f'      {prop_line}')
            else:
                symbol_lines.append(f'      (property "{prop_name}" "{prop_value}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)) )')

        raw_template = template.get("symbol_template", "")
        
        match = re.search(r'\(symbol\s+"(.*?)(?:_\d+_\d+)"', raw_template)
        if match:
            original_prefix = match.group(1)
            processed_template = raw_template.replace(original_prefix, symbol_name)
            indented_template = '\n'.join([f'    {line}' for line in processed_template.splitlines() if line.strip()])
            symbol_lines.append(indented_template)
        else:
            indented_template = '\n'.join([f'    {line}'for line in raw_template.splitlines() if line.strip()])
            symbol_lines.append(indented_template)
            
    else:
        # --- FALLBACK (No template or generator) ---
        symbol_lines.append(
            f'    (symbol "{symbol_name}" (in_bom yes) (on_board yes)'
        )
        symbol_lines.append(f'      (text "No template found for {symbol_name}" (at 0 0 0) (effects (font (size 1.27 1.27))))')
        print(f"  - Warning: No symbol_template or symbol_generator for category, part '{part.name}'. No graphics will be added.")

    # --- *** COMMON LOGIC FOR ALL DYNAMIC GENERATORS *** ---
    if generator_type in ["IC_Box", "Connector"]:
        
        # --- Dynamic Property Positions ---
        box_left = unit_1_geo.get('box_left', 0)
        box_top = unit_1_geo.get('box_top', 3.81)
        box_bottom = -box_top 

        ref_x = box_left
        ref_y = box_top + 1.27  

        mpn_x = box_left
        mpn_y = box_bottom - 1.27 
        
        desc_x = box_left
        desc_y = mpn_y - 2.54 
        
        
        # 4. Get base symbol options
        symbol_options = template.get("symbol_options", "")
        
        # 5. Create the main (symbol ...) definition
        symbol_lines.append(
            f'    (symbol "{symbol_name}" {symbol_options} (in_bom yes) (on_board yes)'
        )
        
        # 7. Generate property strings using templates
        for prop_name, prop_value in all_properties.items():
            
            prop_template_str = template.get('property_templates', {}).get(prop_name, '')
            font_size_match = re.search(r'\(size\s+([\d\.]+)\s+([\d\.]+)\)', prop_template_str)
            font_size_str = f"(size {font_size_match.group(1)} {font_size_match.group(2)})" if font_size_match else "(size 1.27 1.27)"

            
            if prop_name == "Reference":
                prop_line = f'(property "Reference" "{prop_value}" (at {ref_x:.2f} {ref_y:.2f} 0) (effects (font {font_size_str}) (justify left)) )'
                symbol_lines.append(f'      {prop_line}')

            elif prop_name == "Manufacturer Partnumber":
                prop_line = f'(property "Manufacturer Partnumber" "{prop_value}" (at {mpn_x:.2f} {mpn_y:.2f} 0) (effects (font {font_size_str}) (justify left)) )'
                symbol_lines.append(f'      {prop_line}')

            elif prop_name == "Description":
                prop_line = f'(property "Description" "{prop_value}" (at {desc_x:.2f} {desc_y:.2f} 0) (effects (font {font_size_str}) (justify left)) )'
                symbol_lines.append(f'      {prop_line}')
                
            else:
                # Use the template for all other properties (Value, Footprint, etc.)
                prop_template = template.get('property_templates', {}).get(prop_name)
                if prop_template:
                    clean_template = " ".join(prop_template.split())
                    prop_line = clean_template.replace('{VALUE}', prop_value)
                    symbol_lines.append(f'      {prop_line}')
                else:
                    symbol_lines.append(f'      (property "{prop_name}" "{prop_value}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)) )')

        # 8. Add the generated child symbol blocks
        if dynamic_symbol_blocks_str:
            symbol_lines.append(f'  {dynamic_symbol_blocks_str}') 

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
        category_name = part.category.get('full_path', part.category.get('name')) if part.category else 'Uncategorized'
        if category_name not in parts_by_category:
            parts_by_category[category_name] = []
        parts_by_category[category_name].append(part)

    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for api_category, parts_in_category in parts_by_category.items():
        
        found_template = None
        for template_name, template_data in templates.items():
            template_categories = template_data.get('applies_to_categories', [])
            
            for template_cat_name in template_categories:
                if api_category.strip().lower().endswith(template_cat_name.strip().lower()):
                    found_template = template_data
                    break
            if found_template:
                break 

        if not found_template:
            print(f"Info: No template found with a matching 'applies_to_categories' entry for '{api_category}'. Skipping.")
            continue
            
        library_name = api_category.split(' → ')[-1].replace(' ', '_').replace('/', '_')
        output_path = os.path.join(OUTPUT_DIR, f"{library_name}.kicad_sym")
        
        print(f"Generating library for category '{api_category}' with {len(parts_in_category)} parts...")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('(kicad_symbol_lib (version 20211014) (generator partdb_linker)\n')
            for part in parts_in_category:
                try:
                    symbol_str = generate_symbol(part, found_template)
                    f.write(symbol_str + '\n')
                except Exception as e:
                    print(f"  - Error generating symbol for part '{part.name}': {e}")
            f.write(')\n')
        
        print(f"  -> Successfully created library at '{output_path}'")

    print("\n--- KiCad Library Generation Finished ---")

if __name__ == "__main__":
    main()