import yaml
from linker_exceptions import GeneratorException

def load_templates(template_file):
    """Loads the YAML template file."""
    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            templates = yaml.safe_load(f)
        if not templates:
            raise GeneratorException(f"Template file '{template_file}' is empty or invalid.")
        print(f"Loaded {len(templates)} templates.")
        return templates
    except FileNotFoundError:
        raise GeneratorException(f"Template file not found: '{template_file}'.")
    except yaml.YAMLError as e:
        raise GeneratorException(f"Error parsing YAML template file: {e}")

def get_template_for_part(part, templates):
    """Finds the matching template for a given Part object."""
    api_category = part.category.get('full_path', part.category.get('name')) if part.category else 'Uncategorized'
    
    for template_data in templates.values():
        for template_cat_name in template_data.get('applies_to_categories', []):
            if api_category.strip().lower().endswith(template_cat_name.strip().lower()):
                return template_data
    return None
