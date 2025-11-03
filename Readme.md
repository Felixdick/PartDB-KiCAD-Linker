Part-DB to KiCad Library GeneratorThis Python project connects to a Part-DB instance, fetches parts, and generates KiCad 7+ symbol library files (.kicad_sym) based on a powerful and flexible template system.The script supports both static templates for parts with fixed graphics (like resistors) and dynamic generators for parts with variable pin-outs (like ICs and connectors).Key FeaturesStatic Templates: Create symbols from graphics and pin definitions extracted from existing KiCad libraries. Ideal for passives and common components.Dynamic "IC_Box" Generator: Automatically generates a standard IC box symbol with logic pins (Part A) and power pins (Part B) based on a simple pin list from Part-DB.Dynamic "Connector" Generator: Automatically generates connector symbols of any size.Supports single or multi-row (left/right) pin layouts.Draws "Male" or "Female" gender graphics on pins.Supports two pin numbering styles ("Row" vs. "Line") via a Part-DB parameter.Automatically creates a slimmer symbol for single-row headers.Intelligent Field Mapping: Maps Part-DB fields (like value, footprint.name) directly to KiCad symbol properties.Automatic Property Placement: All Part-DB parameters not in the mapping are added as hidden fields, ensuring all data is preserved in the symbol.Template Extractor: A helper script is included to easily create static templates from any existing KiCad symbol.PrerequisitesPython 3.6 or newerThe requests and pyyaml librariesSetup & Configuration1. File StructurePlace all the script files in the same directory:/your_project_folder/
├── generate_kicad_library.py   <-- Main script
├── partdb_api_client.py
├── kicad_template_extractor.py <-- Helper script
├── templates.yaml              <-- Your template definitions
└── kicad_libs/                 <-- Output directory
2. Install Required LibrariesOpen your terminal or command prompt and run:pip install requests pyyaml
3. Configure the API ClientOpen generate_kicad_library.py and edit the configuration variables at the top of the file:# --- API Configuration ---
# Your Part-DB instance URL
API_BASE_URL = 'http://localhost:8888'
# Your Part-DB API token
API_TOKEN = 'your_api_token_goes_here'
# Fetch parts created after this date
PARTS_AFTER_DATE = '2020-01-01' # Format: YYYY-MM-DD
How to Run the GeneratorMake sure your files are set up and configured as described above.Define your templates in templates.yaml (see below).Navigate to your project directory in your terminal.Run the main generator script:python generate_kicad_library.py
The script will connect to the API, fetch parts, and generate .kicad_sym files in the kicad_libs folder, one for each Part-DB category that had a matching template.The templates.yaml FileThis file is the brain of the generator. You can define multiple templates. The script will find the correct template for a part by matching the part's category name.Common StructureAll templates share this basic structure:# A unique name for your template
My_Template_Name:
  # List of Part-DB category names.
  # The script will use this template if a part's category *ends with* one of these strings.
  applies_to_categories:
    - "Resistors"
    - "Logic Gates"

  # Maps KiCad properties to Part-DB fields.
  # Use 'quotes' for static values like 'R?'
  field_mapping:
    "Reference": "'R?'"
    "Value": "value"
    "Footprint": "footprint.name"
    "Datasheet": "manufacturer_product_url"

  # KiCad options for the symbol
  symbol_options: '(pin_numbers hide) (pin_names (offset 0.4) hide)'

  # Defines the style, position, and visibility for every property.
  # This is the most important part for a clean symbol.
  property_templates:
    "Reference": '(property "Reference" "{VALUE}" (at 0 3.81 0) (effects (font (size 1.27 1.27))))'
    "Value": '(property "Value" "{VALUE}" (at 0 -3.81 0) (effects (font (size 1.27 1.27))))'
    "Footprint": '(property "Footprint" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'
    "Datasheet": '(property "Datasheet" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'
    # Any other Part-DB parameter (e.g., "Tolerance") will use its matching template here.
    "Tolerance": '(property "Tolerance" "{VALUE}" (at 0 -5.08 0) (effects (font (size 1.0 1.0)) (justify left)))'
There are three types of templates you can create.Template Type 1: Static Symbol (from symbol_template)This is the standard template type, used for parts with fixed graphics like resistors, capacitors, and diodes.How it works: You provide the full (symbol ...) block.Key: symbol_template: |The easiest way to get this is to use the kicad_template_extractor.py helper script.Helper Tool: kicad_template_extractor.pyFind an existing KiCad symbol that has the look you want (e.g., from KiCad's default libraries).Run the script from your terminal, pointing it to the library file and the symbol name.Example:# Example path for KiCad 7 on Windows
python kicad_template_extractor.py --library "C:\Program Files\KiCad\7.0\share\kicad\symbols\Device.kicad_sym" --symbol "R"
The script will print a complete, ready-to-use YAML block. Copy this and paste it into your templates.yaml file. You will get everything: field_mapping, symbol_options, property_templates, and the symbol_template block.Example templates.yaml entry:Static_Resistor_Template:
  applies_to_categories:
    - "Thick Film Resistors"
  
  # ... field_mapping, symbol_options, property_templates ...
  
  # This block is pasted from the extractor tool
  symbol_template: |
    (symbol "R_0_1"
      (rectangle (start -1.0 -2.5) (end 1.0 2.5) (stroke (width 0.25) (type default)) (fill (type none)))
    )
    (pin passive line (at -3.81 0 0) (length 2.54) (name "~") (number "1"))
    (pin passive line (at 3.81 0 180) (length 2.54) (name "~") (number "2"))
Template Type 2: Dynamic "IC_Box" GeneratorThis template dynamically builds a standard rectangular IC symbol. It's perfect for logic chips, op-amps, MCUs, etc.How it works: The script reads a pin list from Part-DB and builds the symbol, automatically splitting logic and power pins.Key: symbol_generator: "IC_Box" (This replaces symbol_template)Part-DB RequirementsThe script reads a Part-DB parameter named "Pin Description".This field must be a comma-separated list of pin names.Example: IN,OUT,GND,VCC,NC,SDA,SCL,VIOTemplate ConfigurationYou must add one more key to your template:power_pin_names: A list of pin names (case-insensitive) that should be moved to a separate "Part B" power unit.Example templates.yaml entry:Dynamic_IC_Box_Generator:
  applies_to_categories:
    - "Integrated Circuits"
    - "Logic Gates"
  
  field_mapping:
    "Reference": "'U?'"
    "Value": "value"
    # ... etc ...
  
  symbol_options: '(pin_numbers) (pin_names (offset 0.508))'
  
  property_templates:
    "Reference": '(property "Reference" "{VALUE}" (at 0 3.81 0) (effects (font (size 1.27 1.27)) (justify right)))'
    "Value": '(property "Value" "{VALUE}" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) (justify right)))'
    # This property is CRITICAL for the generator to read the pin list
    "Pin Description": '(property "Pin Description" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
    # ... etc ...

  # --- Generator configuration ---
  
  # Use the dynamic box generator
  symbol_generator: "IC_Box"
  
  # List of pin names to move to Part B (case-insensitive)
  power_pin_names: 
    - "VCC"
    - "VDD"
    - "VSS"
    - "GND"
    - "VEE"
    - "VIN"
Template Type 3: Dynamic "Connector" GeneratorThis template dynamically builds a connector symbol.How it works: The script reads parameters from Part-DB to determine the pin count, row count, and gender.Key: symbol_generator: "Connector" (This replaces symbol_template)Part-DB RequirementsThe script will look for the following Part-DB parameters:Number of Rows: (e.g., 1 or 2). Defaults to 1.Pins per Row: (e.g., 10).Fallback: If not found, it will look for Number of Pins or Pin Count and divide by Number of Rows.Gender: (e.g., Male or Female). This is used to draw the pin graphics.Pin Annotation: (Optional) For multi-row connectors.If set to Line, pins are numbered 1-2, 3-4, 5-6.If blank or set to Row (default), pins are numbered 1-3, 2-4 (KiCad standard).Special FeaturesSmart Sizing: If Number of Rows is 1, the symbol box is automatically drawn at half-width for a slim, clean look.Pin Numbering: The Pin Annotation parameter gives you full control over the numbering scheme for 2-row headers.Example templates.yaml entry:Dynamic_Connector_Generator:
  applies_to_categories:
    - "Pin Headers"
    - "PCB to PCB"

  field_mapping:
    "Reference": "'J?'" # 'J' is standard for Connectors
    "Value": "value"
    # ... etc ...

  symbol_options: '(pin_numbers) (pin_names (hide yes) (offset 0.508))'

  property_templates:
    "Reference": '(property "Reference" "{VALUE}" (at 0 3.81 0) (effects (font (size 1.27 1.27)) (justify left)))'
    "Value": '(property "Value" "{VALUE}" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) (justify right)))'
    
    # --- Key fields for this generator (MUST be defined here) ---
    "Number of Rows": '(property "Number of Rows" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
    "Pins per Row": '(property "Pins per Row" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
    "Gender": '(property "Gender" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
    "Pin Annotation": '(property "Pin Annotation" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
    
    # --- Fallback fields ---
    "Number of Pins": '(property "Number of Pins" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
    "Pin Count": '(property "Pin Count" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
    # ... etc ...

  # --- Generator configuration ---
  
  # Use the new dynamic connector generator
  symbol_generator: "Connector"
