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

    print("Fetching parts to find a parameter...")
    try:
        resp = requests.get(f"{api_url}/api/parts", headers=headers, params={'itemsPerPage': 5})
        resp.raise_for_status()
        parts = resp.json().get('hydra:member', [])
        
        for part in parts:
            print(f"Checking Part: {part['name']} (ID: {part['id']})")
            params = part.get('parameters', [])
            if params:
                print(f"  Found {len(params)} parameters.")
                # Fetch first parameter details
                p_ref = params[0]
                print(f"  Fetching details for parameter: {p_ref['name']} (ID: {p_ref['id']})")
                
                p_resp = requests.get(f"{api_url}/api/parameters/{p_ref['id']}", headers=headers)
                p_resp.raise_for_status()
                p_data = p_resp.json()
                
                print("  --- Parameter JSON Data ---")
                print(json.dumps(p_data, indent=2))
                print("  ---------------------------")
                return
            else:
                print("  No parameters on this part.")
                
        print("No parameters found on the first 5 parts.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
