import yaml
from datetime import datetime
from functools import reduce
import os
import re
import math
import configparser
import requests
import copy

# Prerequisites:
# - Python 3.6+
# - PyYAML: pip install pyyaml
# - requests: pip install requests

# Import the Part-DB API client script
try:
    from partdb_api_client import fetch_parts_from_api, Part
except ImportError:
    print("Error: Could not import 'partdb_api_client.py'.")
    sys.exit(1)

# --- Custom Exception ---
class GeneratorException(Exception):
    """Custom exception for generator-related errors."""
    pass

class KiCadLibraryGenerator:
    """
    Manages fetching, comparing, and generating KiCad libraries.
    """
    def __init__(self, api_url, api_token, after_date, template_file, output_dir):
        print("Initializing Generator...")
        self.API_BASE_URL = api_url
        self.API_TOKEN = api_token
        self.PARTS_AFTER_DATE = after_date
        self.TEMPLATE_FILE = template_file
        self.OUTPUT_DIR = output_dir

        if not self.API_TOKEN:
            raise GeneratorException("API Token is missing. Please set it in the config.")

        # --- Internal State ---
        self.templates = self._load_templates()
        self.all_fetched_parts = []
        self.all_old_symbols = {} # {lib_path: {part_name: symbol_string}}
        self.parts_by_category = {}

    def _load_templates(self):
        """Loads the YAML template file."""
        try:
            with open(self.TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                templates = yaml.safe_load(f)
            if not templates:
                raise GeneratorException(f"Template file '{self.TEMPLATE_FILE}' is empty or invalid.")
            print(f"Loaded {len(templates)} templates.")
            return templates
        except FileNotFoundError:
            raise GeneratorException(f"Template file not found: '{self.TEMPLATE_FILE}'.")
        except yaml.YAMLError as e:
            raise GeneratorException(f"Error parsing YAML template file: {e}")

    def _get_template_for_part(self, part):
        """Finds the matching template for a given Part object."""
        api_category = part.category.get('full_path', part.category.get('name')) if part.category else 'Uncategorized'
        
        for template_data in self.templates.values():
            for template_cat_name in template_data.get('applies_to_categories', []):
                if api_category.strip().lower().endswith(template_cat_name.strip().lower()):
                    return template_data
        return None

    def _get_lib_path_for_part(self, part):
        """Determines the output .kicad_sym file path for a part."""
        api_category = part.category.get('full_path', part.category.get('name')) if part.category else 'Uncategorized'
        library_name = api_category.split(' → ')[-1].replace(' ', '_').replace('/', '_')
        return os.path.join(self.OUTPUT_DIR, f"{library_name}.kicad_sym")

    def _parse_existing_library(self, file_path: str) -> dict:
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
                end_index = self._find_matching_paren(content, start_index)
                
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

    def _find_matching_paren(self, text, start_pos=0):
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

    def _normalize_string(self, s: str) -> str:
        """Removes excess whitespace to make symbol strings comparable."""
        return re.sub(r'\s+', ' ', s).strip()

    def run_comparison(self):
        """
        Fetches all data, compares to local files, and returns lists of changes.
        Returns: (new_parts, modified_parts)
        """
        print("--- Running Library Comparison ---")
        
        # 1. Fetch all parts from API
        try:
            self.all_fetched_parts = fetch_parts_from_api(self.API_BASE_URL, self.API_TOKEN, self.PARTS_AFTER_DATE)
        except requests.RequestException as e:
            raise GeneratorException(f"API Error: Could not fetch parts.\n{e}")
        
        if not self.all_fetched_parts:
            print("No parts fetched from API.")
            return [], []
            
        print(f"Fetched {len(self.all_fetched_parts)} parts from Part-DB.")

        # 2. Group parts and parse existing libs
        self.parts_by_category = {}
        self.all_old_symbols = {}
        
        for part in self.all_fetched_parts:
            lib_path = self._get_lib_path_for_part(part)
            
            if lib_path not in self.parts_by_category:
                self.parts_by_category[lib_path] = []
                # Parse the corresponding library file *once*
                self.all_old_symbols[lib_path] = self._parse_existing_library(lib_path)
                
            self.parts_by_category[lib_path].append(part)

        # 3. Compare new vs. old
        new_parts_list = []
        modified_parts_list = []
        
        print("Comparing fetched parts to existing libraries...")
        for lib_path, parts_in_lib in self.parts_by_category.items():
            old_symbols_in_lib = self.all_old_symbols.get(lib_path, {})
            
            for part in parts_in_lib:
                template = self._get_template_for_part(part)
                if not template:
                    print(f"  - Info: No template for part '{part.name}'. Skipping.")
                    continue
                
                try:
                    # Generate the new symbol string in memory
                    new_symbol_name, new_symbol_string = self.generate_symbol(part, template)
                    
                    if new_symbol_name not in old_symbols_in_lib:
                        # This is a new part
                        new_parts_list.append(part)
                    else:
                        # Part exists, check if modified
                        old_symbol_string = old_symbols_in_lib[new_symbol_name]
                        
                        # Compare normalized strings
                        if self._normalize_string(new_symbol_string) != self._normalize_string(old_symbol_string):
                            modified_parts_list.append(part)
                        
                except Exception as e:
                    print(f"  - Error generating symbol for '{part.name}': {e}. Skipping.")

        print("--- Comparison Finished ---")
        print(f"Found {len(new_parts_list)} New Parts, {len(modified_parts_list)} Modified Parts.")
        
        return new_parts_list, modified_parts_list

    def write_selected_parts(self, selected_parts: list) -> list:
        """
        Writes *only* the selected parts, preserving all other parts
        from the existing files.
        """
        print(f"--- Writing {len(selected_parts)} Selected Changes ---")
        log = []
        
        # Create a quick lookup for selected parts
        selected_part_ids = {part.id for part in selected_parts}
        
        # We need to rebuild all library files that contain a selected part
        libs_to_rebuild = set()
        for part in selected_parts:
            libs_to_rebuild.add(self._get_lib_path_for_part(part))
            
        if not libs_to_rebuild:
            log.append("No libraries to rebuild.")
            return log

        # Ensure output directory exists
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
            
        for lib_path in libs_to_rebuild:
            log.append(f"Rebuilding library: {lib_path}")
            
            # Get all parts that *belong* in this library
            all_parts_for_this_lib = self.parts_by_category.get(lib_path, [])
            
            # Get the old symbols for this library
            old_symbols_in_lib = self.all_old_symbols.get(lib_path, {})
            
            new_symbol_blocks = [] # This will hold the strings for the new file
            
            parts_written = 0
            
            for part in all_parts_for_this_lib:
                template = self._get_template_for_part(part)
                if not template:
                    continue # Skip parts with no template
                    
                symbol_name, new_symbol_string = self.generate_symbol(part, template)
                
                if part.id in selected_part_ids:
                    # This part was selected, use its NEW symbol string
                    new_symbol_blocks.append(new_symbol_string)
                    parts_written += 1
                else:
                    # This part was not selected, use its OLD string if it exists
                    if symbol_name in old_symbols_in_lib:
                        new_symbol_blocks.append(old_symbols_in_lib[symbol_name])
            
            # Now, write the new library file
            try:
                with open(lib_path, 'w', encoding='utf-8') as f:
                    f.write('(kicad_symbol_lib (version 20211014) (generator partdb_linker_gui)\n')
                    for block in new_symbol_blocks:
                        f.write(block + '\n')
                    f.write(')\n')
                log.append(f"  -> Wrote {len(new_symbol_blocks)} symbols to {lib_path}.")
                
            except IOError as e:
                raise GeneratorException(f"Could not write to file: {lib_path}\n{e}")
                
        print("--- Write Operation Finished ---")
        return log

    # --- Symbol Generation Logic (Copied from original script) ---
    # Note: `generate_symbol` now returns (symbol_name, symbol_string)
    
    def generate_symbol(self, part: Part, template: dict) -> (str, str):
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
                value = self._get_value_from_part(part, key_path)
                if not value:
                    value = self._get_value_from_part(part, field_name)
            all_properties[field_name] = value

        for param_name, param_value in part.parameters.items():
            if param_name not in all_properties and param_value:
                resolved_value = self._get_value_from_part(part, param_name)
                all_properties[param_name] = resolved_value
        
        generator_type = template.get("symbol_generator")
        symbol_lines = []
        unit_1_geo = {}
        dynamic_symbol_blocks_str = ""

        if generator_type == "IC_Box":
            power_names_list = template.get("power_pin_names", [])
            pin_csv_string = self._get_value_from_part(part, "Pin Description")
            (dynamic_symbol_blocks_str, unit_1_geo) = self._generate_dynamic_symbol_blocks(
                symbol_name, pin_csv_string, power_names_list
            )
            
        elif generator_type == "Connector":
            (dynamic_symbol_blocks_str, unit_1_geo) = self._generate_dynamic_connector_block(
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

    def _get_value_from_part(self, part: Part, key_path: str):
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

    def _build_symbol_child_block(self, symbol_name_prefix: str, unit_number: int, pins_list: list, power_names_upper: list) -> (str, dict):
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

    def _generate_dynamic_symbol_blocks(self, symbol_name: str, pin_csv: str, power_names: list) -> (str, dict):
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
             unit_a_str, geo_a = self._build_symbol_child_block(symbol_name, 1, [], power_names_upper)
             all_unit_blocks.append(unit_a_str)
        else:
            unit_a_str, geo_a = self._build_symbol_child_block(symbol_name, 1, pins_for_part_a, power_names_upper)
            all_unit_blocks.append(unit_a_str)
        if has_part_b:
            unit_b_str, _ = self._build_symbol_child_block(symbol_name, 2, pins_for_part_b, power_names_upper)
            all_unit_blocks.append(unit_b_str)
        return ('\n'.join(all_unit_blocks), geo_a)

    def _generate_dynamic_connector_block(self, symbol_name_prefix: str, part: Part) -> (str, dict):
        unit_lines = []
        try: num_rows = int(self._get_value_from_part(part, "Number of Rows") or 1)
        except ValueError: num_rows = 1
        try: pins_per_row = int(self._get_value_from_part(part, "Pins per Row") or 0)
        except ValueError: pins_per_row = 0
        if pins_per_row == 0:
            try:
                total_pins_str = self._get_value_from_part(part, "Number of Pins")
                if not total_pins_str: total_pins_str = self._get_value_from_part(part, "Pin Count")
                total_pins = int(total_pins_str or 0)
                if total_pins > 0:
                    if num_rows == 1: pins_per_row = total_pins
                    elif num_rows > 1: pins_per_row = math.ceil(total_pins / num_rows)
            except ValueError: pass 
        if pins_per_row <= 0: pins_per_row = 1
        if num_rows <= 0: num_rows = 1
        gender = self._get_value_from_part(part, "Gender").lower()
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
        pin_annotation_str = self._get_value_from_part(part, "Pin Annotation").lower()
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


# --- This block is to check if the script is imported or run directly ---
if __name__ == "__main__":
    print("This script is intended to be imported by 'gui_config_editor.py'.")
    print("Please run the GUI script instead.")