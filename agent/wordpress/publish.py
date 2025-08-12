import re, requests
from pathlib import Path
from bs4 import BeautifulSoup
from .auth import get_auth_headers
from .taxonomy import get_or_create_term_id
from .media import upload_local_featured_image, upload_featured_image

def extract_metadata_from_html(html: str, default_image_url: str):
    soup = BeautifulSoup(html, "html.parser")
    header = html[:1000]
    cat = re.search(r'<!--\s*category\s*:\s*(.*?)\s*-->', header, re.I)
    tags = re.search(r'<!--\s*tags\s*:\s*(.*?)\s*-->', header, re.I)

    category = (cat.group(1).strip() if cat else "Uncategorized")
    tag_list = [t.strip() for t in (tags.group(1).split(",") if tags else []) if t.strip()]

    meta = soup.find("meta", attrs={"name": "description"})
    title_tag = soup.find("h1")
    img_tag = soup.find("img")

    return {
        "title": title_tag.get_text(strip=True) if title_tag else "Untitled Article",
        "meta_description": (meta.get("content","").strip() if meta else ""),
        "category": category,
        "tags": tag_list,
        "featured_image_url": (img_tag.get("src") if img_tag and img_tag.has_attr("src") else default_image_url)
    }

def publish_article_html_auto(*, html_content: str, site_url: str, username: str, app_password: str,
                              article_id: str, local_image_dir: Path, default_image_url: str = ""):
    headers = get_auth_headers(username, app_password)
    meta = extract_metadata_from_html(html_content, default_image_url=default_image_url or "")

    Path("debug").mkdir(exist_ok=True)
    Path("debug/html_output.html").write_text(html_content, encoding="utf-8")
    Path("debug/metadata.json").write_text(str(meta), encoding="utf-8")

    category_id = get_or_create_term_id(meta["category"], "categories", site_url, headers)
    tag_ids = [get_or_create_term_id(t, "tags", site_url, headers) for t in meta["tags"]]

    featured_media_id = None
    local = list(local_image_dir.glob(f"{article_id}.*"))
    if local:
        featured_media_id = upload_local_featured_image(local[0], site_url, headers)
    elif meta["featured_image_url"]:
        featured_media_id = upload_featured_image(meta["featured_image_url"], site_url, headers)

    post_data = {
        "title": meta["title"],
        "content": html_content,
        "status": "draft",
        "excerpt": meta["meta_description"],
        "categories": [category_id],
        "tags": tag_ids,
        "author": 7
    }
    if featured_media_id:
        post_data["featured_media"] = featured_media_id

    r = requests.post(f"{site_url}/wp-json/wp/v2/posts", headers=headers, json=post_data, timeout=120)
    print(f"📬 Response status code: {r.status_code}")
    print(f"📨 Response text: {r.text[:500]}")
    r.raise_for_status()
    post = r.json()
    return {"id": post["id"], "title": post["title"]["rendered"], "link": post["link"]}
