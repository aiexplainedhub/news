import requests
from pathlib import Path

def upload_featured_image(image_url: str, site_url: str, headers: dict) -> int | None:
    try:
        image_data = requests.get(image_url, timeout=60).content
        media_headers = dict(headers)
        media_headers.pop("Content-Type", None)
        media_headers["Content-Disposition"] = 'attachment; filename="featured.jpg"'
        r = requests.post(f"{site_url}/wp-json/wp/v2/media", headers=media_headers,
                          files={"file": ("featured.jpg", image_data, "image/jpeg")}, timeout=120)
        if r.status_code == 201:
            return r.json()["id"]
    except Exception as e:
        print(f"⚠️ Remote image upload failed: {e}")
    return None

def upload_local_featured_image(image_path: Path, site_url: str, headers: dict) -> int | None:
    try:
        media_headers = dict(headers)
        media_headers.pop("Content-Type", None)
        media_headers["Content-Disposition"] = f'attachment; filename="{image_path.name}"'
        with open(image_path, "rb") as f:
            r = requests.post(f"{site_url}/wp-json/wp/v2/media", headers=media_headers,
                              files={"file": (image_path.name, f, "image/jpeg")}, timeout=120)
        print(f"📤 Image upload status: {r.status_code}")
        if r.status_code == 201:
            return r.json()["id"]
    except Exception as e:
        print(f"⚠️ Local image upload exception: {e}")
    return None
