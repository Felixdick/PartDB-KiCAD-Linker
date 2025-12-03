import os
import requests
import sys

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

# Import new modules
from linker_exceptions import GeneratorException
from linker_templates import load_templates, get_template_for_part
from linker_parser import parse_existing_library
from linker_symbol_generator import generate_symbol, normalize_string

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
        self.templates = load_templates(self.TEMPLATE_FILE)
        self.all_fetched_parts = []
        self.all_old_symbols = {} # {lib_path: {part_name: symbol_string}}
        self.parts_by_category = {}

    def _get_lib_path_for_part(self, part):
        """Determines the output .kicad_sym file path for a part."""
        api_category = part.category.get('full_path', part.category.get('name')) if part.category else 'Uncategorized'
        library_name = api_category.split(' → ')[-1].replace(' ', '_').replace('/', '_')
        return os.path.join(self.OUTPUT_DIR, f"{library_name}.kicad_sym")

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
            if part.name == "DUMMY":
                continue
            lib_path = self._get_lib_path_for_part(part)
            
            if lib_path not in self.parts_by_category:
                self.parts_by_category[lib_path] = []
                # Parse the corresponding library file *once*
                self.all_old_symbols[lib_path] = parse_existing_library(lib_path)
                
            self.parts_by_category[lib_path].append(part)

        # 3. Compare new vs. old
        new_parts_list = []
        modified_parts_list = []
        
        print("Comparing fetched parts to existing libraries...")
        for lib_path, parts_in_lib in self.parts_by_category.items():
            old_symbols_in_lib = self.all_old_symbols.get(lib_path, {})
            
            for part in parts_in_lib:
                template = get_template_for_part(part, self.templates)
                if not template:
                    print(f"  - Info: No template for part '{part.name}'. Skipping.")
                    continue
                
                try:
                    # Generate the new symbol string in memory
                    new_symbol_name, new_symbol_string = generate_symbol(part, template)
                    
                    if new_symbol_name not in old_symbols_in_lib:
                        # This is a new part
                        new_parts_list.append(part)
                    else:
                        # Part exists, check if modified
                        old_symbol_string = old_symbols_in_lib[new_symbol_name]
                        
                        # Compare normalized strings
                        if normalize_string(new_symbol_string) != normalize_string(old_symbol_string):
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
                template = get_template_for_part(part, self.templates)
                if not template:
                    continue # Skip parts with no template
                    
                symbol_name, new_symbol_string = generate_symbol(part, template)
                
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

# --- This block is to check if the script is imported or run directly ---
if __name__ == "__main__":
    print("This script is intended to be imported by 'gui_config_editor.py'.")
    print("Please run the GUI script instead.")