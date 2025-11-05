# PartDB-KiCAD-Linker

This tool automatically generates and updates KiCad symbol libraries from your PartDB inventory, keeping your electronic designs in sync with your component database.

## Features

*   **Automated Library Generation**: Fetches component data from PartDB and creates KiCad `.kicad_sym` library files.
*   **Template-Based**: Uses a flexible YAML-based template system to define how PartDB parts are mapped to KiCad symbols.
*   **Dynamic Symbol Generation**:
    *   Automatically creates complex IC symbols with multiple units for logic and power pins.
    *   Generates connector symbols of any size and configuration.
*   **GUI for Easy Management**: A simple graphical interface to configure the tool, run the generator, and review changes.
*   **Change Detection**: Compares newly generated symbols with existing ones and shows a diff, allowing you to selectively apply updates.
*   **Template Extraction Tool**: Includes a helper script to bootstrap the creation of new templates from your existing KiCad libraries.

## Workflow

1.  **Configure**: Set up your PartDB API credentials and file paths using the GUI.
2.  **Fetch**: The tool fetches all parts from PartDB that have been created or updated after a specified date.
3.  **Generate**: For each fetched part, the tool finds a matching template in `templates.yaml` based on its PartDB category. It then generates a KiCad symbol in memory.
4.  **Compare**: The newly generated symbol is compared against the corresponding symbol in your existing KiCad library files.
5.  **Review**: The GUI presents a list of all new and modified symbols.
6.  **Apply**: You can select which changes you want to write to your library files. The tool then updates the `.kicad_sym` files, preserving any unchanged symbols.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/PartDB-KiCAD-Linker.git
    cd PartDB-KiCAD-Linker
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

The easiest way to configure the tool is by running the GUI.

```bash
python gui_config_editor.py
```

This will open the configuration window.

*   **PartDB Settings**:
    *   `API Base URL`: The URL of your PartDB instance (e.g., `http://localhost:8080`).
    *   `API Token`: Your PartDB API token.
    *   `Parts After Date`: The tool will only fetch parts created or updated after this date (in `YYYY-MM-DD` format).
*   **Path Settings**:
    *   `Template File`: The path to your `templates.yaml` file.
    *   `Output Directory`: The directory where the generated `.kicad_sym` libraries will be saved.

Click **Save Config** to save your settings to `config.ini`.

## Usage

1.  **Run the GUI:**
    ```bash
    python gui_config_editor.py
    ```

2.  **Start the Generator**:
    *   After configuring the tool, click the **Run Generator...** button.
    *   The tool will fetch data from PartDB and compare it with your local libraries. This may take a few moments.

3.  **Review Changes**:
    *   If any new or modified parts are found, a "Review Library Changes" window will appear.
    *   **Available Changes**: The list on the left shows all detected changes, prefixed with `[NEW]` or `[MOD]`. You can filter this list by category.
    *   **Changes to Apply**: Move the changes you want to keep from the "Available" list to the "Changes to Apply" list on the right using the `>` and `>>` buttons.
    *   You can also remove changes from the "Apply" list using the `<` and `<<` buttons.

4.  **Apply Changes**:
    *   Once you are satisfied with your selection, click **Apply Changes**.
    *   The tool will write the selected new and updated symbols to the corresponding `.kicad_sym` files in your output directory.

## Template Creation

The `templates.yaml` file is the heart of this tool. It defines how parts from PartDB are translated into KiCad symbols.

### Template Structure

A template has the following structure:

```yaml
My_Template_Name:
  applies_to_categories:
    - "Category Name in PartDB"
  field_mapping:
    "KiCad Field": "partdb_field_or_parameter"
  symbol_options: '(kicad symbol options)'
  property_templates:
    "KiCad Property": '(kicad property template with {VALUE})'
  symbol_template: |
    (kicad symbol graphics and pin definitions)
```

### Using the Template Extractor

To make creating new templates easier, you can use the `kicad_template_extractor.py` script. This script reads an existing `.kicad_sym` file and a symbol name, and prints out a YAML template that you can copy into your `templates.yaml`.

**Usage:**

```bash
python kicad_template_extractor.py --library "path/to/your/library.kicad_sym" --symbol "SymbolName"
```

This will output a complete template structure, including graphics, pins, and properties, which you can then customize.

## Dependencies

*   [requests](https://pypi.org/project/requests/)
*   [PyYAML](https://pypi.org/project/PyYAML/)

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.