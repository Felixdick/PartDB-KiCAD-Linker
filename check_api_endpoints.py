import requests
import configparser
import json

config = configparser.ConfigParser()
config.read('config.ini')

api_url = config.get('PartDB', 'api_base_url')
api_token = config.get('PartDB', 'api_token')

headers = {
    'Authorization': f'Bearer {api_token}',
    'Accept': 'application/ld+json'
}

print(f"Checking API at {api_url}/api ...")
try:
    resp = requests.get(f"{api_url}/api", headers=headers)
    resp.raise_for_status()
    data = resp.json()
    print("Available endpoints:")
    # In Hydra/JSON-LD, the entry point often lists resources.
    # If it's a documentation page, we might get HTML if Accept header isn't respected or if the URL is wrong.
    # But usually /api with ld+json returns the entry point.
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")
    # Try fetching /api/categories directly to see if it works
    print("\nTrying /api/categories...")
    try:
        resp = requests.get(f"{api_url}/api/categories", headers=headers)
        print(f"Status: {resp.status_code}")
    except Exception as e2:
        print(f"Error: {e2}")
