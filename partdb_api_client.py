#
# A client script to interact with the Part-DB API.
# Fetches parts and their detailed parameters.
#
# Prerequisites:
# - requests: pip install requests
#

import requests
from datetime import datetime

class Part:
    """A class to hold part data dynamically."""
    def __init__(self, **kwargs):
        self.parameters = {}  # Initialize parameters dictionary
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __repr__(self):
        return f"<Part: {self.name}>"

def fetch_parts_from_api(base_url: str, token: str, after_date: str) -> list[Part]:
    """
    Fetches a list of parts from the Part-DB API created after a specific date.
    
    Args:
        base_url: The base URL of the Part-DB instance (e.g., 'http://localhost:8888').
        token: The API bearer token.
        after_date: The date string in 'YYYY-MM-DD' format.
    
    Returns:
        A list of Part objects.
    """
    # Convert YYYY-MM-DD to the DD.MM.YYYY format required by the API
    try:
        api_date_str = datetime.strptime(after_date, '%Y-%m-%d').strftime('%d.%m.%Y')
    except ValueError:
        print(f"Error: Invalid date format for PARTS_AFTER_DATE. Please use YYYY-MM-DD.")
        return []

    headers = {
        'accept': 'application/ld+json',
        'Authorization': f'Bearer {token}'
    }
    # Using a high itemsPerPage count to simplify pagination for now.
    # A more robust solution would handle multiple pages if necessary.
    params = {
        'page': 1,
        'itemsPerPage': 500,
        'addedDate[after]': api_date_str,
        'order[name]': 'asc'
    }

    parts_list = []
    try:
        print(f"Fetching parts from {base_url}/api/parts...")
        response = requests.get(f'{base_url}/api/parts', headers=headers, params=params, timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()

        if 'hydra:member' not in data:
            print("Warning: API response does not contain 'hydra:member'. No parts found or unexpected format.")
            return []

        for part_data in data['hydra:member']:
            # Create a Part object from the main part data
            part_obj = Part(**part_data)
            
            # Fetch and process detailed parameters for each part
            if hasattr(part_obj, 'parameters') and isinstance(part_obj.parameters, list):
                detailed_params = {}
                for param_ref in part_obj.parameters:
                    param_url = f"{base_url}{param_ref['@id']}"
                    try:
                        param_res = requests.get(param_url, headers=headers, timeout=10)
                        param_res.raise_for_status()
                        param_data = param_res.json()
                        param_name = param_data.get('name')
                        param_value = param_data.get('value_text')
                        if param_name:
                            detailed_params[param_name] = param_value if param_value else "-"
                    except requests.RequestException as e:
                        print(f"  - Warning: Could not fetch parameter at {param_url}. Error: {e}")
                
                # Replace the list of refs with the dictionary of detailed params
                part_obj.parameters = detailed_params
            
            parts_list.append(part_obj)

    except requests.RequestException as e:
        print(f"Error connecting to Part-DB API: {e}")
        print("Please ensure Part-DB is running and the URL/token are correct.")
        return []
    
    return parts_list

def print_part_details(parts: list[Part]):
    """A helper function to print details of fetched parts."""
    if not parts:
        print("No parts to display.")
        return

    print(f"\n--- Fetched Part Details ({len(parts)}) ---\n")
    for part in parts:
        print("-" * 42)
        print(f" Part Name:     {part.name}")
        print(f" ID:            {part.id}")
        print(f" Description:   {part.description}")
        print(f" Manufacturer:  {part.manufacturer.get('name') if part.manufacturer else 'N/A'}")
        print(f" Footprint:     {part.footprint.get('name') if part.footprint else 'N/A'}")
        print(f" Category:      {part.category.get('full_path') if part.category else 'N/A'}")
        print(f" Date Added:    {part.addedDate}")
        
        if part.parameters:
            print("--- Parameters ---")
            # Find the longest parameter name for alignment
            max_len = max(len(name) for name in part.parameters.keys())
            for name, value in sorted(part.parameters.items()):
                print(f"  {name.ljust(max_len)} : {value}")
        print("\n")

# This block allows the script to be run directly for testing purposes
if __name__ == '__main__':
    # --- Configuration for Direct Testing ---
    # These values are used ONLY when you run `python partdb_api_client.py`
    TEST_API_BASE_URL = 'http://localhost:8888'
    TEST_API_TOKEN = 'tcp_549c6a43b2de4b34e7a9cdd7640751a2dc3d68d24b002241b2a911320270b091'

    # Note: For real use, the date will be passed from the main script.
    # This is a fallback for testing.
    TEST_PARTS_AFTER_DATE = datetime.now().strftime('%Y-%m-%d')
    
    fetched_parts = fetch_parts_from_api(TEST_API_BASE_URL, TEST_API_TOKEN, TEST_PARTS_AFTER_DATE)
    print_part_details(fetched_parts)

