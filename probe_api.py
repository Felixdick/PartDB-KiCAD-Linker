import requests

api_url = "http://100.106.52.51:3001/api"
headers = {
    'Authorization': 'Bearer tcp_46f6bebeccdcad86b76e249bee8ec2c09cec8bff5037bc8842565992684c99f6',
    'Accept': 'application/ld+json'
}

endpoints = [
    '/measurement_units',
    '/parameters',
    '/part_parameters',
    '/attributes',
    '/parts',
    '/docs.json'
]

for ep in endpoints:
    try:
        resp = requests.get(f"{api_url}{ep}", headers=headers)
        print(f"{ep}: {resp.status_code}")
    except Exception as e:
        print(f"{ep}: Error {e}")
