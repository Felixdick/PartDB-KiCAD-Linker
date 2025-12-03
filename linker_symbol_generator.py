import re
import math
from functools import reduce
from partdb_api_client import Part

def normalize_string(s: str) -> str:
    """Removes excess whitespace to make symbol strings comparable."""
    return re.sub(r'\s+', ' ', s).strip()

def generate_symbol(part: Part, template: dict) -> (str, str):
    """
    Generates a single KiCad symbol string for a given part.
    Returns tuple: (symbol_name, full_symbol_string)
    """
    symbol_name = part.name.replace(' ', '_')
    
    all_properties = {}
    for field_name, key_path in template.get('field_mapping', {}).items():
        if isinstance(key_path, str) and key_path.startswith("'") and key_path.endswith("'"):
            value = key_path.strip("'")
        else:
            value = _get_value_from_part(part, key_path)
            if not value:
                value = _get_value_from_part(part, field_name)
        all_properties[field_name] = value

    for param_name, param_value in part.parameters.items():
        if param_name not in all_properties and param_value:
            resolved_value = _get_value_from_part(part, param_name)
            all_properties[param_name] = resolved_value
    
    generator_type = template.get("symbol_generator")
    symbol_lines = []
    unit_1_geo = {}
    dynamic_symbol_blocks_str = ""

    if generator_type == "IC_Box":
        power_names_list = template.get("power_pin_names", [])
        pin_csv_string = _get_value_from_part(part, "Pin Description")
        (dynamic_symbol_blocks_str, unit_1_geo) = _generate_dynamic_symbol_blocks(
            symbol_name, pin_csv_string, power_names_list
        )
        
    elif generator_type == "Connector":
        (dynamic_symbol_blocks_str, unit_1_geo) = _generate_dynamic_connector_block(
            symbol_name, part
        )
        
    elif template.get("symbol_template"):
        symbol_lines.append(f'  (symbol "{symbol_name}" {template.get("symbol_options", "")} (in_bom yes) (on_board yes)')
        
        for prop_name, prop_value in all_properties.items():
            prop_template = template.get('property_templates', {}).get(prop_name)
            if prop_template:
                clean_template = " ".join(prop_template.split())
                prop_line = clean_template.replace('{VALUE}', prop_value)
                symbol_lines.append(f'    {prop_line}')
            else:
                symbol_lines.append(f'    (property "{prop_name}" "{prop_value}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)) )')

        raw_template = template.get("symbol_template", "")
        match = re.search(r'\(symbol\s+"(.*?)(?:_\d+_\d+)"', raw_template)
        if match:
            original_prefix = match.group(1)
            processed_template = raw_template.replace(original_prefix, symbol_name)
            indented_template = '\n'.join([f'  {line}' for line in processed_template.splitlines() if line.strip()])
            symbol_lines.append(indented_template)
        else:
            indented_template = '\n'.join([f'  {line}'for line in raw_template.splitlines() if line.strip()])
            symbol_lines.append(indented_template)
            
    else:
        symbol_lines.append(f'  (symbol "{symbol_name}" (in_bom yes) (on_board yes)')
        symbol_lines.append(f'    (text "No template found for {symbol_name}" (at 0 0 0) (effects (font (size 1.27 1.27))))')

    if generator_type in ["IC_Box", "Connector"]:
        box_left = unit_1_geo.get('box_left', 0)
        box_top = unit_1_geo.get('box_top', 3.81)
        box_bottom = -box_top 
        ref_x, ref_y = box_left, box_top + 1.27
        mpn_x, mpn_y = box_left, box_bottom - 1.27
        desc_x, desc_y = box_left, mpn_y - 2.54 
        
        symbol_options = template.get("symbol_options", "")
        symbol_lines.append(f'  (symbol "{symbol_name}" {symbol_options} (in_bom yes) (on_board yes)')
        
        for prop_name, prop_value in all_properties.items():
            prop_template_str = template.get('property_templates', {}).get(prop_name, '')
            font_size_match = re.search(r'\(size\s+([\d\.]+)\s+([\d\.]+)\)', prop_template_str)
            font_size_str = f"(size {font_size_match.group(1)} {font_size_match.group(2)})" if font_size_match else "(size 1.27 1.27)"
            
            if prop_name == "Reference":
                prop_line = f'(property "Reference" "{prop_value}" (at {ref_x:.2f} {ref_y:.2f} 0) (effects (font {font_size_str}) (justify left)) )'
                symbol_lines.append(f'    {prop_line}')
            elif prop_name == "Manufacturer Partnumber":
                prop_line = f'(property "Manufacturer Partnumber" "{prop_value}" (at {mpn_x:.2f} {mpn_y:.2f} 0) (effects (font {font_size_str}) (justify left)) )'
                symbol_lines.append(f'    {prop_line}')
            elif prop_name == "Description":
                prop_line = f'(property "Description" "{prop_value}" (at {desc_x:.2f} {desc_y:.2f} 0) (effects (font {font_size_str}) (justify left)) )'
                symbol_lines.append(f'    {prop_line}')
            else:
                prop_template = template.get('property_templates', {}).get(prop_name)
                if prop_template:
                    clean_template = " ".join(prop_template.split())
                    prop_line = clean_template.replace('{VALUE}', prop_value)
                    symbol_lines.append(f'    {prop_line}')
                else:
                    symbol_lines.append(f'    (property "{prop_name}" "{prop_value}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)) )')

        if dynamic_symbol_blocks_str:
            symbol_lines.append(f'  {dynamic_symbol_blocks_str}') 

    symbol_lines.append('  )') # Close the main (symbol ...)
    
    # Return the symbol name and the complete block as a string
    return symbol_name, '\n'.join(symbol_lines)

def _get_value_from_part(part: Part, key_path: str):
    val = None
    try:
        if '.' in key_path:
            val = reduce(lambda d, key: getattr(d, key, None) if hasattr(d, key) else d.get(key) if isinstance(d, dict) else None, key_path.split('.'), part)
        else:
            val = getattr(part, key_path, None)
            if val is None:
                param_val = part.parameters.get(key_path)
                if param_val is None:
                        param_val = part.parameters.get(key_path.capitalize())
                val = param_val
    except (AttributeError, TypeError): val = None
    if val is None: return ""
    return str(val)

def _build_symbol_child_block(symbol_name_prefix: str, unit_number: int, pins_list: list, power_names_upper: list) -> (str, dict):
    unit_lines = []
    GRID_SPACING = 2.54; PIN_LENGTH = 2.54; BOX_WIDTH = 15.24
    total_pins = len(pins_list); left_pin_count = math.ceil(total_pins / 2.0); right_pin_count = total_pins // 2
    box_height_pins = max(left_pin_count, right_pin_count)
    min_height_grids = 3 if unit_number == 1 else 2
    box_height_grids = max(min_height_grids, (box_height_pins - 1) if box_height_pins > 0 else 0)
    box_height = (box_height_grids * GRID_SPACING) + GRID_SPACING
    top = (box_height / 2.0); bottom = -top; left = -BOX_WIDTH / 2.0; right = BOX_WIDTH / 2.0
    geometry = {'box_top': top, 'box_left': left}
    pin_x_left = -BOX_WIDTH / 2.0 - PIN_LENGTH; pin_x_right = BOX_WIDTH / 2.0 + PIN_LENGTH
    
    unit_lines.append(f'    (symbol "{symbol_name_prefix}_{unit_number}_1"')
    unit_lines.append(f'      (rectangle (start {left:.2f} {top:.2f}) (end {right:.2f} {bottom:.2f})')
    unit_lines.append('        (stroke (width 0.254) (type default)) (fill (type background))')
    unit_lines.append('      )')
    
    pin_index = 0
    start_y_left = (left_pin_count - 1) * GRID_SPACING / 2.0
    start_y_right = (right_pin_count - 1) * GRID_SPACING / 2.0
    for i in range(left_pin_count):
        pin_number, pin_name = pins_list[pin_index]; pin_index += 1
        y_pos = start_y_left - (i * GRID_SPACING)
        pin_type = "power_in" if pin_name.upper() in power_names_upper else "passive"
        unit_lines.append(f'      (pin {pin_type} line (at {pin_x_left:.2f} {y_pos:.2f} 0) (length {PIN_LENGTH})')
        unit_lines.append(f'        (name "{pin_name}" (effects (font (size 1.27 1.27))))')
        unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
        unit_lines.append('      )')
    for i in range(right_pin_count):
        pin_number, pin_name = pins_list[pin_index]; pin_index += 1
        y_pos = start_y_right - (i * GRID_SPACING)
        pin_type = "power_in" if pin_name.upper() in power_names_upper else "passive"
        unit_lines.append(f'      (pin {pin_type} line (at {pin_x_right:.2f} {y_pos:.2f} 180) (length {PIN_LENGTH})')
        unit_lines.append(f'        (name "{pin_name}" (effects (font (size 1.27 1.27))))')
        unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
        unit_lines.append('      )')
    unit_lines.append('    )') 
    return ('\n'.join(unit_lines), geometry)

def _generate_dynamic_symbol_blocks(symbol_name: str, pin_csv: str, power_names: list) -> (str, dict):
    main_pins = []; power_pins = []; power_names_upper = [name.upper() for name in power_names]
    all_pin_names = [name.strip() for name in pin_csv.split(',') if name.strip()]
    current_pin_number = 1
    for pin_name in all_pin_names:
        pin_data = (str(current_pin_number), pin_name)
        if pin_name.upper() in power_names_upper: power_pins.append(pin_data)
        else: main_pins.append(pin_data)
        current_pin_number += 1
    has_part_b = len(main_pins) > 0 and len(power_pins) > 0
    pins_for_part_a = main_pins if has_part_b else main_pins + power_pins
    pins_for_part_b = power_pins if has_part_b else []
    all_unit_blocks = []; geo_a = {}
    if not pins_for_part_a and not pins_for_part_b:
            unit_a_str, geo_a = _build_symbol_child_block(symbol_name, 1, [], power_names_upper)
            all_unit_blocks.append(unit_a_str)
    else:
        unit_a_str, geo_a = _build_symbol_child_block(symbol_name, 1, pins_for_part_a, power_names_upper)
        all_unit_blocks.append(unit_a_str)
    if has_part_b:
        unit_b_str, _ = _build_symbol_child_block(symbol_name, 2, pins_for_part_b, power_names_upper)
        all_unit_blocks.append(unit_b_str)
    return ('\n'.join(all_unit_blocks), geo_a)

def _generate_dynamic_connector_block(symbol_name_prefix: str, part: Part) -> (str, dict):
    unit_lines = []
    try: num_rows = int(_get_value_from_part(part, "Number of Rows") or 1)
    except ValueError: num_rows = 1
    try: pins_per_row = int(_get_value_from_part(part, "Pins per Row") or 0)
    except ValueError: pins_per_row = 0
    if pins_per_row == 0:
        try:
            total_pins_str = _get_value_from_part(part, "Number of Pins")
            if not total_pins_str: total_pins_str = _get_value_from_part(part, "Pin Count")
            total_pins = int(total_pins_str or 0)
            if total_pins > 0:
                if num_rows == 1: pins_per_row = total_pins
                elif num_rows > 1: pins_per_row = math.ceil(total_pins / num_rows)
        except ValueError: pass 
    if pins_per_row <= 0: pins_per_row = 1
    if num_rows <= 0: num_rows = 1
    gender = _get_value_from_part(part, "Gender").lower()
    GRID_SPACING = 2.54; PIN_LENGTH = 2.54
    BOX_WIDTH = 3.81 if num_rows == 1 else 7.62
    left_pin_count = pins_per_row if num_rows == 1 else pins_per_row
    right_pin_count = 0 if num_rows == 1 else pins_per_row
    box_height_pins = max(left_pin_count, right_pin_count)
    box_height_grids = max(2, (box_height_pins - 1) if box_height_pins > 0 else 0)
    box_height = (box_height_grids * GRID_SPACING) + GRID_SPACING
    top = (box_height / 2.0); bottom = -top; left = -BOX_WIDTH / 2.0; right = BOX_WIDTH / 2.0
    geometry = {'box_top': top, 'box_left': left}
    pin_x_left = -BOX_WIDTH / 2.0 - PIN_LENGTH; pin_x_right = BOX_WIDTH / 2.0 + PIN_LENGTH
    
    unit_lines.append(f'    (symbol "{symbol_name_prefix}_1_1"')
    unit_lines.append(f'      (rectangle (start {left:.2f} {top:.2f}) (end {right:.2f} {bottom:.2f})')
    unit_lines.append('        (stroke (width 0.254) (type default)) (fill (type background))')
    unit_lines.append('      )')
    
    start_y_left = (left_pin_count - 1) * GRID_SPACING / 2.0
    start_y_right = (right_pin_count - 1) * GRID_SPACING / 2.0
    stroke_style = '(stroke (width 0.2) (type default)) (fill (type none))'
    pin_annotation_str = _get_value_from_part(part, "Pin Annotation").lower()
    is_line_annotation = (num_rows > 1 and pin_annotation_str == "line")

    if is_line_annotation:
        current_pin_number = 1
        for i in range(pins_per_row):
            pin_number_left = str(current_pin_number); current_pin_number += 1
            y_pos = start_y_left - (i * GRID_SPACING)
            unit_lines.append(f'      (pin passive line (at {pin_x_left:.2f} {y_pos:.2f} 0) (length {PIN_LENGTH})')
            unit_lines.append(f'        (name "{pin_number_left}" (effects (font (size 1.27 1.27)) (hide yes)))')
            unit_lines.append(f'        (number "{pin_number_left}" (effects (font (size 1.27 1.27))))')
            unit_lines.append('      )')
            if gender == "male":
                unit_lines.append(f'      (polyline (pts (xy {left:.2f} {y_pos:.2f}) (xy {left+2.54:.2f} {y_pos:.2f})) {stroke_style})')
            elif gender == "female":
                unit_lines.append(f'      (polyline (pts (xy {left:.2f} {y_pos:.2f}) (xy {left+1.905:.2f} {y_pos:.2f})) {stroke_style})')
                unit_lines.append(f'      (arc (start {left+2.54:.2f} {y_pos+0.635:.2f}) (mid {left+1.905:.2f} {y_pos:.2f}) (end {left+2.54:.2f} {y_pos-0.635:.2f}) {stroke_style})')
            if right_pin_count > 0:
                pin_number_right = str(current_pin_number); current_pin_number += 1
                y_pos = start_y_right - (i * GRID_SPACING)
                unit_lines.append(f'      (pin passive line (at {pin_x_right:.2f} {y_pos:.2f} 180) (length {PIN_LENGTH})')
                unit_lines.append(f'        (name "{pin_number_right}" (effects (font (size 1.27 1.27)) (hide yes)))')
                unit_lines.append(f'        (number "{pin_number_right}" (effects (font (size 1.27 1.27))))')
                unit_lines.append('      )')
                if gender == "male":
                    unit_lines.append(f'      (polyline (pts (xy {right:.2f} {y_pos:.2f}) (xy {right-2.54:.2f} {y_pos:.2f})) {stroke_style})')
                elif gender == "female":
                    unit_lines.append(f'      (polyline (pts (xy {right:.2f} {y_pos:.2f}) (xy {right-1.905:.2f} {y_pos:.2f})) {stroke_style})')
                    unit_lines.append(f'      (arc (start {right-2.54:.2f} {y_pos-0.635:.2f}) (mid {right-1.905:.2f} {y_pos:.2f}) (end {right-2.54:.2f} {y_pos+0.635:.2f}) {stroke_style})')
                    print("do")
    else:
        current_pin_number = 1
        for i in range(left_pin_count):
            pin_number = str(current_pin_number); current_pin_number += 1
            y_pos = start_y_left - (i * GRID_SPACING)
            unit_lines.append(f'      (pin passive line (at {pin_x_left:.2f} {y_pos:.2f} 0) (length {PIN_LENGTH})')
            unit_lines.append(f'        (name "{pin_number}" (effects (font (size 1.27 1.27)) (hide yes)))')
            unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
            unit_lines.append('      )')
            if gender == "male":
                unit_lines.append(f'      (polyline (pts (xy {left:.2f} {y_pos:.2f}) (xy {left+2.54:.2f} {y_pos:.2f})) {stroke_style})')
            elif gender == "female":
                unit_lines.append(f'      (polyline (pts (xy {left:.2f} {y_pos:.2f}) (xy {left+1.905:.2f} {y_pos:.2f})) {stroke_style})')
                unit_lines.append(f'      (arc (start {left+2.54:.2f} {y_pos+0.635:.2f}) (mid {left+1.905:.2f} {y_pos:.2f}) (end {left+2.54:.2f} {y_pos-0.635:.2f}) {stroke_style})')
        for i in range(right_pin_count):
            pin_number = str(current_pin_number); current_pin_number += 1
            y_pos = start_y_right - (i * GRID_SPACING)
            unit_lines.append(f'      (pin passive line (at {pin_x_right:.2f} {y_pos:.2f} 180) (length {PIN_LENGTH})')
            unit_lines.append(f'        (name "{pin_number}" (effects (font (size 1.27 1.27)) (hide yes)))')
            unit_lines.append(f'        (number "{pin_number}" (effects (font (size 1.27 1.27))))')
            unit_lines.append('      )')
            if gender == "male":
                unit_lines.append(f'      (polyline (pts (xy {right:.2f} {y_pos:.2f}) (xy {right-2.54:.2f} {y_pos:.2f})) {stroke_style})')
            elif gender == "female":
                unit_lines.append(f'      (polyline (pts (xy {right:.2f} {y_pos:.2f}) (xy {right-1.905:.2f} {y_pos:.2f})) {stroke_style})')
                unit_lines.append(f'      (arc (start {right-2.54:.2f} {y_pos-0.635:.2f}) (mid {right-1.905:.2f} {y_pos:.2f}) (end {right-2.54:.2f} {y_pos+0.635:.2f}) {stroke_style})')
                print("di")
    
    unit_lines.append('    )') 
    return ('\n'.join(unit_lines), geometry)
