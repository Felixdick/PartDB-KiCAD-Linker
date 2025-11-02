Part-DB to KiCad Library Generator

This Python script connects to a Part-DB instance, fetches parts, and generates KiCad symbol library files (.kicad_sym) based on a powerful template system.

The key feature is intelligent field generation:

It uses templates to precisely control the position, visibility, and style of standard fields (Reference, Value, etc.).

Any other parameter from Part-DB (like "Tolerance", "Voltage") is automatically added as a field to the KiCad symbol. If that field was part of the template, it will be placed correctly; otherwise, it will be hidden by default.

Prerequisites

Python 3.6 or newer.

The requests and pyyaml libraries.

Setup

File Structure:
Place all the script files in the same directory:

/your_project_folder/
├── generate_kicad_library.py
├── partdb_api_client.py
├── kicad_template_extractor.py  <-- The template helper
├── templates.yaml
└── kicad_libs/                  <-- Output directory




Install Required Libraries:
Open your terminal or command prompt and run:

pip install requests pyyaml




Configure the API Client:
Open partdb_api_client.py and edit the configuration variables at the top:

BASE_URL: The URL of your Part-DB server.

API_TOKEN: Your API bearer token.

AFTER_DATE: The date to filter parts by.

Configure the Templates (templates.yaml):
This file is the heart of the generator. Use the kicad_template_extractor.py script to generate the templates for you (see below).

How to Run the Generator

Make sure your files are set up as described above.

Navigate to that directory in your terminal.

Run the main generator script:

python generate_kicad_library.py




The generated .kicad_sym files will appear in the kicad_libs folder.

Helper Tool: Generating Templates

The kicad_template_extractor.py script now extracts everything needed for a complete template: graphics, pins, and the position/style of every property.

How to Use the Extractor

Find an existing KiCad symbol that has the look you want (e.g., from KiCad's default libraries or your own).

Run the script from your terminal, pointing it to the library file and the symbol name.

Example:

Let's extract a template for the standard R symbol.

python kicad_template_extractor.py --library "C:\Program Files\KiCad\7.0\share\kicad\symbols\Device.kicad_sym" --symbol "R"




(Note: Your path to Device.kicad_sym may be different.)

Output:

The script will print a complete, ready-to-use YAML block. Simply copy this entire block and paste it into your templates.yaml file.

--- Extracted Template (KiCad 7+) ---

Paste the following into your templates.yaml file:

# Category name from Part-DB (use quotes if it has spaces)
Resistors:
  field_mapping:
    "Reference": "'R?'"
    "Value": "name"
    "Footprint": "footprint.name"
    "Datasheet": "manufacturer_product_url"

  symbol_options: '(pin_numbers hide) (pin_names (offset 0.4) hide)'

  property_templates:
    "Reference": '(property "Reference" "{VALUE}" (at 0 3.81 0) (effects (font (size 1.27 1.27))))'
    "Value": '(property "Value" "{VALUE}" (at 0 -3.81 0) (effects (font (size 1.27 1.27))))'
    "Footprint": '(property "Footprint" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'
    "Datasheet": '(property "Datasheet" "{VALUE}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'

  symbol_template: |
    (symbol "R_0_1"
      (rectangle (start -1.0 -2.5) (end 1.0 2.5) (stroke (width 0.25) (type default)) (fill (type none)))
    )
    (pin passive line (at -3.81 0 0) (length 2.54) (name "~") (number "1"))
    (pin passive line (at 3.81 0 180) (length 2.54) (name "~") (number "2"))

-------------------------------------
