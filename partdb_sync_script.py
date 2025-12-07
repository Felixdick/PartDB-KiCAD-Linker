import yaml
import requests
import configparser
import os
import re
from typing import Dict, List, Optional, Tuple

class PartDBSyncer:
    def __init__(self, api_url: str, api_token: str):
        self.api_url = api_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/ld+json'
        }
        self.existing_categories = {} # Path -> ID
        self.touched_ids = set()

    def log(self, message: str):
        print(f"[Sync] {message}")

    def fetch_existing_categories(self):
        """Fetches all existing categories to avoid duplicates."""
        self.log("Fetching existing categories...")
        self.existing_categories = {}
        
        try:
            # We need to fetch all categories. Pagination might be needed.
            # For now, assuming 500 is enough or we loop.
            page = 1
            while True:
                resp = requests.get(
                    f"{self.api_url}/api/categories", 
                    headers=self.headers, 
                    params={'page': page, 'itemsPerPage': 500}
                )
                resp.raise_for_status()
                data = resp.json()
                
                members = data.get('hydra:member', [])
                if not members:
                    break
                    
                for cat in members:
                    self.existing_categories[cat['id']] = cat
                    
                if 'hydra:view' in data and 'hydra:next' in data['hydra:view']:
                    page += 1
                else:
                    break
                    
            self.log(f"Found {len(self.existing_categories)} existing categories.")
            
        except requests.RequestException as e:
            self.log(f"Error fetching categories: {e}")
            raise

    def _find_category_id(self, name: str, parent_id: Optional[int] = None) -> Optional[int]:
        """Finds a category ID by name and parent ID."""
        for cat_id, cat_data in self.existing_categories.items():
            if cat_data['name'] == name:
                # Check parent
                cat_parent = cat_data.get('parent')
                # Parent in API response is usually a URI string like "/api/categories/1" or None
                cat_parent_id = None
                if cat_parent:
                    # Extract ID from URI
                    match = re.search(r'/(\d+)$', cat_parent)
                    if match:
                        cat_parent_id = int(match.group(1))
                
                if cat_parent_id == parent_id:
                    return cat_id
        return None

    def create_category(self, name: str, parent_id: Optional[int] = None) -> int:
        """Creates a category and returns its ID."""
        existing_id = self._find_category_id(name, parent_id)
        if existing_id:
            self.touched_ids.add(existing_id)
            return existing_id

        payload = {
            "name": name
        }
        if parent_id:
            payload["parent"] = f"/api/categories/{parent_id}"

        try:
            resp = requests.post(f"{self.api_url}/api/categories", headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            new_id = data['id']
            self.log(f"Created category: '{name}' (ID: {new_id})")
            
            # Update cache
            self.existing_categories[new_id] = data
            self.touched_ids.add(new_id)
            return new_id
        except requests.RequestException as e:
            self.log(f"Error creating category '{name}': {e}")
            if e.response is not None:
                self.log(f"Response: {e.response.text}")
            raise

    def ensure_manufacturer(self, name: str) -> int:
        """Ensures a manufacturer exists and returns its ID."""
        # Check if exists
        try:
            resp = requests.get(
                f"{self.api_url}/api/manufacturers",
                headers=self.headers,
                params={"name": name, "itemsPerPage": 1}
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('hydra:member'):
                return data['hydra:member'][0]['id']
        except requests.RequestException:
            pass

        # Create
        try:
            resp = requests.post(
                f"{self.api_url}/api/manufacturers",
                headers=self.headers,
                json={"name": name}
            )
            resp.raise_for_status()
            self.log(f"Created manufacturer '{name}'.")
            return resp.json()['id']
        except requests.RequestException as e:
            self.log(f"Error creating manufacturer '{name}': {e}")
            raise

    def ensure_dummy_part(self, category_id: int, parameters: List[dict] = None):
        """Ensures a dummy part exists in the given category and updates it if needed."""
        
        # Construct description
        desc = "Placeholder part for category structure."

        existing_part = None
        # First check if it exists
        try:
            resp = requests.get(
                f"{self.api_url}/api/parts",
                headers=self.headers,
                params={
                    "category": category_id, # Filter by ID
                    "name": "DUMMY",
                    "itemsPerPage": 1
                }
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('hydra:totalItems', 0) > 0:
                existing_part = data['hydra:member'][0]
        except requests.RequestException:
            pass 

        # Ensure manufacturer
        mfr_id = self.ensure_manufacturer("dbx-solutions")

        if existing_part:
            # Check if update is needed
            current_desc = existing_part.get('description', '')
            # Normalize newlines for comparison
            if current_desc.replace('\r\n', '\n').strip() != desc.strip():
                self.log(f"Updating DUMMY part in category {category_id}...")
                try:
                    # Use PATCH instead of PUT for updates
                    headers = self.headers.copy()
                    headers['Content-Type'] = 'application/merge-patch+json' # Common for API Platform
                    
                    resp = requests.patch(
                        f"{self.api_url}/api/parts/{existing_part['id']}",
                        headers=headers,
                        json={"description": desc, "manufacturer": f"/api/manufacturers/{mfr_id}"}
                    )
                    resp.raise_for_status()
                    self.log(f"Updated DUMMY part in category {category_id}.")
                except requests.RequestException as e:
                    self.log(f"Error updating dummy part: {e}")
                    if e.response is not None:
                        self.log(f"Response: {e.response.text}")
            
            # Sync native parameters
            self.sync_parameters(existing_part['id'], f"/api/parts/{existing_part['id']}", parameters)
            return

        # Create dummy part if not exists
        payload = {
            "name": "DUMMY",
            "description": desc,
            "category": f"/api/categories/{category_id}",
            "manufacturer": f"/api/manufacturers/{mfr_id}",
            "minStockLevel": 0,
        }
        
        try:
            resp = requests.post(f"{self.api_url}/api/parts", headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            new_id = data['id']
            self.log(f"Created DUMMY part in category ID {category_id}.")
            
            # Sync native parameters
            self.sync_parameters(new_id, f"/api/parts/{new_id}", parameters)
            
        except requests.RequestException as e:
            self.log(f"Error creating dummy part in category {category_id}: {e}")
            if e.response is not None:
                self.log(f"Response: {e.response.text}")

    def sync_tree(self, tree: List[dict], parent_id: Optional[int] = None, inherited_params: List[dict] = None):
        """Recursively syncs the category tree."""
        if inherited_params is None:
            inherited_params = []

        for node in tree:
            name = node['name']
            node_params = node.get('parameters', [])
            # Merge inherited params with node params (simple concatenation for now)
            current_params = inherited_params + node_params
            
            cat_id = self.create_category(name, parent_id)
            
            children = node.get('children', [])
            if children:
                self.sync_tree(children, cat_id, current_params)
            else:
                # It's a leaf node (in our tree structure), ensure dummy part
                # It's a leaf node (in our tree structure), ensure dummy part
                self.ensure_dummy_part(cat_id, current_params)
                # Also sync real parts in this category
                self.sync_real_parts(cat_id, current_params)

    def get_all_category_ids_from_tree(self, tree: List[dict]) -> set:
        """Helper to collect all category IDs defined in the YAML."""
        ids = set()
        for node in tree:
            name = node['name']
            # We need to find the ID for this name. 
            # Since sync_tree runs first, self.existing_categories should be populated/updated.
            # But names might be duplicated in different branches? 
            # For now, let's assume unique names or we need to track path.
            # A better way is to have sync_tree return the set of touched IDs.
            pass 
        return ids

    def prune_categories(self, touched_ids: set):
        """Safely removes categories that are in DB but not in YAML."""
        self.log("Checking for obsolete categories...")
        
        # self.existing_categories contains all categories in DB (fetched at start + created)
        # But wait, fetch_existing_categories only runs at start. 
        # created categories are added to it.
        # So self.existing_categories keys are ALL known IDs.
        
        for cat_id, cat_data in list(self.existing_categories.items()):
            if cat_id not in touched_ids:
                # This category is in DB but was not touched by sync_tree (so not in YAML)
                self.safe_delete_category(cat_id, cat_data['name'])

    def safe_delete_category(self, cat_id: int, name: str):
        """Deletes a category only if it's empty or has only DUMMY parts."""
        try:
            # Check for parts
            resp = requests.get(
                f"{self.api_url}/api/parts",
                headers=self.headers,
                params={"category": cat_id, "itemsPerPage": 50} # Check first 50 parts
            )
            resp.raise_for_status()
            data = resp.json()
            parts = data.get('hydra:member', [])
            
            non_dummy_parts = [p for p in parts if p['name'] != "DUMMY"]
            
            if non_dummy_parts:
                self.log(f"Skipping deletion of category '{name}' (ID: {cat_id}): Contains {len(non_dummy_parts)} non-dummy parts.")
                return
            
            # Check for children categories? 
            # If we delete a parent, children might be orphaned or deleted.
            # PartDB usually prevents deleting non-empty categories.
            # But if we are pruning bottom-up? 
            # The loop order in prune_categories is arbitrary.
            # If we delete a parent, we should ensure children are handled.
            # But if children are also not in touched_ids, they will be visited.
            
            # If it has only DUMMY parts, we should delete them first?
            # Or does PartDB cascade delete? Usually not safe.
            # Let's try to delete the category. If it fails, it fails.
            
            if parts:
                # Delete dummy parts first
                for p in parts:
                    requests.delete(f"{self.api_url}/api/parts/{p['id']}", headers=self.headers)
            
            requests.delete(f"{self.api_url}/api/categories/{cat_id}", headers=self.headers)
            self.log(f"Deleted obsolete category '{name}' (ID: {cat_id}).")
            
            # Remove from cache
            del self.existing_categories[cat_id]
            
        except requests.RequestException as e:
            self.log(f"Error deleting category '{name}': {e}")

    def sync_real_parts(self, category_id: int, parameters: List[dict]):
        """Syncs parameters for all non-dummy parts in a category."""
        try:
            # Fetch all parts in category
            # Pagination might be needed if many parts
            page = 1
            while True:
                resp = requests.get(
                    f"{self.api_url}/api/parts",
                    headers=self.headers,
                    params={"category": category_id, "page": page, "itemsPerPage": 100}
                )
                resp.raise_for_status()
                data = resp.json()
                members = data.get('hydra:member', [])
                
                if not members:
                    break
                    
                for part in members:
                    if part['name'] == "DUMMY":
                        continue
                    
                    # Sync with safe_delete=True
                    self.sync_parameters(part['id'], f"/api/parts/{part['id']}", parameters, safe_delete=True)
                
                if 'hydra:view' in data and 'hydra:next' in data['hydra:view']:
                    page += 1
                else:
                    break
                    
        except requests.RequestException as e:
            self.log(f"Error syncing real parts in category {category_id}: {e}")

    def sync_parameters(self, part_id: int, part_iri: str, desired_params: List[dict], safe_delete: bool = False):
        """Syncs native PartDB parameters for a part."""
        if not desired_params:
            desired_params = []

        # 1. Fetch existing parameters
        try:
            resp = requests.get(f"{self.api_url}/api/parts/{part_id}", headers=self.headers)
            resp.raise_for_status()
            part_data = resp.json()
            existing_params_list = part_data.get('parameters', [])
        except requests.RequestException as e:
            self.log(f"Error fetching parameters for part {part_id}: {e}")
            return

        # Map existing parameters by Name -> details
        existing_map = {}
        for p_ref in existing_params_list:
            p_id = p_ref['id']
            p_name = p_ref['name']
            
            try:
                p_resp = requests.get(f"{self.api_url}/api/parameters/{p_id}", headers=self.headers)
                p_resp.raise_for_status()
                p_data = p_resp.json()
                existing_map[p_name] = p_data
            except requests.RequestException:
                self.log(f"Warning: Could not fetch details for parameter ID {p_id}")
                continue

        # 2. Sync Desired Parameters
        desired_names = set()
        for dp in desired_params:
            name = dp['name']
            desired_names.add(name)
            unit = dp.get('unit') or ''
            symbol = dp.get('symbol') or ''
            value_type = "numeric" if unit else "string" 
            
            if name in existing_map:
                # Update if changed
                ep = existing_map[name]
                ep_unit = ep.get('unit') or ''
                ep_symbol = ep.get('symbol') or ''
                
                if ep_unit != unit or ep_symbol != symbol:
                    self.log(f"Updating parameter '{name}' for part {part_id}...")
                    try:
                        requests.put(
                            f"{self.api_url}/api/parameters/{ep['id']}",
                            headers=self.headers,
                            json={
                                "name": name,
                                "unit": unit,
                                "symbol": symbol,
                                "valueType": value_type
                            }
                        ).raise_for_status()
                    except requests.RequestException as e:
                        self.log(f"Error updating parameter '{name}': {e}")
            else:
                # Create
                self.log(f"Creating parameter '{name}' for part {part_id}...")
                try:
                    requests.post(
                        f"{self.api_url}/api/parameters",
                        headers=self.headers,
                        json={
                            "name": name,
                            "unit": unit,
                            "symbol": symbol,
                            "valueType": value_type,
                            "element": part_iri
                        }
                    ).raise_for_status()
                except requests.RequestException as e:
                    self.log(f"Error creating parameter '{name}': {e}")
                    if e.response is not None:
                        self.log(f"Response: {e.response.text}")

        # 3. Delete Obsolete Parameters
        for name, ep in existing_map.items():
            if name not in desired_names:
                if safe_delete:
                    # Check if parameter has a value
                    # The 'value' field in parameter object might be 'value' or 'valueNumeric' depending on type
                    # Let's check the fetched details
                    # Note: The /api/parameters/{id} response should contain the value.
                    # Based on API docs/experience, value is usually in 'value' or 'valueNumeric'.
                    # Let's check both or just 'value' if it's the string representation.
                    # If it's not empty, skip delete.
                    
                    # We need to check the actual value.
                    # The 'ep' object comes from /api/parameters/{id}
                    # Debugging showed 'value_text' is used.
                    val = ep.get('value')
                    val_text = ep.get('value_text')
                    val_num = ep.get('valueNumeric')
                    val_num_snake = ep.get('value_numeric')
                    
                    has_value = (
                        (val is not None and str(val).strip() != "") or 
                        (val_text is not None and str(val_text).strip() != "") or 
                        (val_num is not None) or
                        (val_num_snake is not None)
                    )
                    
                    if has_value:
                        # self.log(f"Skipping deletion of parameter '{name}' (ID: {ep['id']}) from part {part_id}: Has value")
                        continue

                self.log(f"Deleting obsolete parameter '{name}' from part {part_id}...")
                try:
                    requests.delete(f"{self.api_url}/api/parameters/{ep['id']}", headers=self.headers).raise_for_status()
                except requests.RequestException as e:
                    self.log(f"Error deleting parameter '{name}': {e}")

def parse_yaml_categories(file_path: str) -> Tuple[List[dict], List[dict]]:
    """
    Parses the YAML file and returns (tree, global_parameters).
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        return data.get('categories', []), data.get('global_parameters', [])

def main():
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    api_url = config.get('PartDB', 'api_base_url', fallback='http://localhost:3000')
    api_token = config.get('PartDB', 'api_token', fallback='')
    
    if not api_token:
        print("Error: API Token not found in config.ini")
        return

    print("Parsing categories.yaml...")
    try:
        tree, global_params = parse_yaml_categories('categories.yaml')
    except FileNotFoundError:
        print("Error: 'categories.yaml' not found.")
        return
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}")
        return

    print("Starting Sync...")
    syncer = PartDBSyncer(api_url, api_token)
    try:
        syncer.fetch_existing_categories()
        
        # We need to track touched IDs to know what to prune
        syncer.touched_ids = set()
        
        # Pass global parameters as the initial inherited parameters
        syncer.sync_tree(tree, inherited_params=global_params)
        syncer.prune_categories(syncer.touched_ids)
        
        print("Sync completed successfully.")
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    main()
