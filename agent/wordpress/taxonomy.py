import requests

def get_or_create_term_id(term_name: str, endpoint: str, site_url: str, headers: dict) -> int:
    url = f"{site_url}/wp-json/wp/v2/{endpoint}?search={term_name}"
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    res = r.json()
    if isinstance(res, list) and res:
        return res[0]["id"]
    cr = requests.post(f"{site_url}/wp-json/wp/v2/{endpoint}", headers=headers, json={"name": term_name}, timeout=30)
    cr.raise_for_status()
    return cr.json()["id"]
