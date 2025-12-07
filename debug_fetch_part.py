import requests
import configparser
import json

def main():
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    api_url = config.get('PartDB', 'api_base_url', fallback='http://localhost:3000').rstrip('/')
    api_token = config.get('PartDB', 'api_token', fallback='')
    
    if not api_token:
        print("Error: API Token not found.")
        return

    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/ld+json'
    }

    part_name = "CGA2B3X7R1E104K050BB"
    print(f"Fetching part '{part_name}'...")
    
    try:
        resp = requests.get(
            f"{api_url}/api/parts", 
            headers=headers, 
            params={'name': part_name}
        )
        resp.raise_for_status()
        data = resp.json()
        members = data.get('hydra:member', [])
        
        if not members:
            print(f"Part '{part_name}' NOT FOUND in API.")
            return

        part = members[0]
        print(f"Found Part: {part['name']} (ID: {part['id']})")
        print(f"  Added Date: {part.get('addedDate')}")
        print(f"  Category: {part.get('category')}")
        
        # Check category details
        cat_iri = part.get('category')
        if cat_iri:
            if isinstance(cat_iri, dict):
                cat_iri = cat_iri.get('@id')
            
            print(f"  Fetching category details for {cat_iri}...")
            cat_resp = requests.get(f"{api_url}{cat_iri}", headers=headers)
            cat_resp.raise_for_status()
            cat_data = cat_resp.json()
            print(f"  Category Name: {cat_data.get('name')}")
            print(f"  Category Full Path: {cat_data.get('full_path')}") # Check if full_path exists
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
