import re, requests
from pathlib import Path
from bs4 import BeautifulSoup
from .auth import get_auth_headers
from .taxonomy import get_or_create_term_id
from .media import upload_local_featured_image, upload_featured_image

def _post_json(url: str, headers: dict, payload: dict, label: str, timeout: int = 120):
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    print(f"{label} → {r.status_code}")
    try:
        body = r.json()
    except Exception:
        body = {"_raw": r.text[:500]}
    if r.status_code >= 400:
        print(f"⚠️ {label} failed: {str(body)[:500]}")
    return r, body

def push_yoast_meta(site_url: str, headers: dict, post_id: int, meta: dict) -> bool:
    """Push Yoast meta via REST and print a per-field result."""
    yoast_meta_payload = {"meta": {}}
    if meta.get("yoast_keyphrase"):
        yoast_meta_payload["meta"]["_yoast_wpseo_focuskw"] = meta["yoast_keyphrase"]
    if meta.get("yoast_title"):
        yoast_meta_payload["meta"]["_yoast_wpseo_title"] = meta["yoast_title"]
    if meta.get("yoast_metadesc"):
        yoast_meta_payload["meta"]["_yoast_wpseo_metadesc"] = meta["yoast_metadesc"]
    if meta.get("canonical"):
        yoast_meta_payload["meta"]["_yoast_wpseo_canonical"] = meta["canonical"]

    if not yoast_meta_payload["meta"]:
        print("ℹ️ No Yoast meta to push.")
        return True

    url = f"{site_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
    r, body = _post_json(url, headers, yoast_meta_payload, "🧩 Yoast meta update")

    # If the server doesn’t echo "meta", the keys likely aren’t registered for REST writes.
    echoed = (body if isinstance(body, dict) else {}).get("meta")
    if echoed is None:
        print("❌ Server did not echo `meta`. Likely your Yoast keys aren’t registered with show_in_rest.")
        print("   Ensure an MU-plugin registers these keys: _yoast_wpseo_focuskw, _yoast_wpseo_title, _yoast_wpseo_metadesc, _yoast_wpseo_canonical.")
        return False

    ok = True
    for k, v in yoast_meta_payload["meta"].items():
        got = echoed.get(k)
        if got == v:
            print(f"✅ {k} set")
        else:
            print(f"❌ {k} not set (sent='{v}', got='{got}')")
            ok = False
    return ok

def verify_yoast_head_json(site_url: str, headers: dict, post_id: int, expect: dict) -> dict:
    """Fetch yoast_head_json and compare key fields; print a concise report."""
    url = f"{site_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}?_fields=yoast_head_json,link,status"
    r = requests.get(url, headers=headers, timeout=60)
    print(f"🔎 yoast_head_json check → {r.status_code}")
    if r.status_code >= 400:
        print(f"⚠️ Couldn’t read yoast_head_json: {r.text[:300]}")
        return {"checked": False}

    data = r.json() or {}
    yh = data.get("yoast_head_json") or {}
    def _cmp(label, got, want):
        if not want:
            print(f"• {label}: (no expectation)")
            return True
        if (got or "").strip() == (want or "").strip():
            print(f"✅ {label} matches")
            return True
        print(f"❌ {label} mismatch → got='{(got or '')[:120]}', want='{(want or '')[:120]}'")
        return False

    title_ok = _cmp("title", yh.get("title"), expect.get("yoast_title"))
    desc_ok  = _cmp("meta_description", yh.get("description"), expect.get("yoast_metadesc"))
    can_ok   = _cmp("canonical", yh.get("canonical"), expect.get("canonical"))

    # Focus keyphrase isn’t exposed in yoast_head_json; try meta if available
    focus_ok = None
    try:
        r2 = requests.get(
            f"{site_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}?context=edit&_fields=meta",
            headers=headers,
            timeout=60,
        )
        if r2.status_code < 400:
            m = (r2.json() or {}).get("meta") or {}
            want = expect.get("yoast_keyphrase")
            got = m.get("_yoast_wpseo_focuskw")
            if want:
                focus_ok = (got == want)
                print("✅ focus keyphrase matches" if focus_ok else f"❌ focus keyphrase mismatch → got='{got}', want='{want}'")
            else:
                print("• focus keyphrase: (no expectation)")
        else:
            print("ℹ️ Focus keyphrase not readable via REST (meta not exposed).")
    except Exception as e:
        print(f"ℹ️ Focus keyphrase check skipped: {e}")

    overall = all(x for x in [title_ok, desc_ok, can_ok] if x is not None)
    return {
        "checked": True,
        "title_ok": title_ok,
        "metadesc_ok": desc_ok,
        "canonical_ok": can_ok,
        "focus_ok": focus_ok,
        "overall": overall
    }
# --- Keep: your existing _short_desc if you already added it; otherwise include this helper ---
def _short_desc(text: str, max_len: int = 155) -> str:
    text = ' '.join(text.split())
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(' ', 1)[0]
    return cut if cut else text[:max_len]

# --- NEW: WP media alt_text setter (uses REST: /wp/v2/media/{id}) ---
def set_media_alt_text(site_url: str, headers: dict, media_id: int, alt_text: str) -> None:
    """Set the attachment's alt text (stored as _wp_attachment_image_alt)."""
    if not media_id or not alt_text:
        return
    payload = {"alt_text": _short_desc(alt_text, 125)}  # common UX guideline: keep alt concise
    url = f"{site_url.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    print(f"🖼️ Set alt_text for media {media_id}: {r.status_code}")
    if r.status_code >= 400:
        print(f"⚠️ Failed to set alt_text: {r.text[:300]}")

def extract_metadata_from_html(html: str, default_image_url: str):
    soup = BeautifulSoup(html, "html.parser")
    header = html[:2000]

    cat = re.search(r'<!--\s*category\s*:\s*(.*?)\s*-->', header, re.I)
    tags = re.search(r'<!--\s*tags\s*:\s*(.*?)\s*-->', header, re.I)
    keyphrase_match = re.search(r'<!--\s*(?:keyphrase|focuskw|focus_keyphrase)\s*:\s*(.*?)\s*-->', header, re.I)
    canonical_match = re.search(r'<!--\s*canonical\s*:\s*(https?://[^\s]+)\s*-->', header, re.I)

    category = (cat.group(1).strip() if cat else "Uncategorized")
    tag_list = [t.strip() for t in (tags.group(1).split(",") if tags else []) if t.strip()]

    meta_tag = soup.find("meta", attrs={"name": "description"})
    title_tag = soup.find("h1")
    img_tag = soup.find("img")

    title = title_tag.get_text(strip=True) if title_tag else "Untitled Article"

    meta_description = (meta_tag.get("content", "").strip() if meta_tag else "")
    if not meta_description:
        first_p = soup.find("p")
        if first_p:
            meta_description = _short_desc(first_p.get_text(" ", strip=True))
        else:
            meta_description = ""

    yoast_keyphrase = (keyphrase_match.group(1).strip() if keyphrase_match else title)
    yoast_title = title
    yoast_metadesc = _short_desc(meta_description) if meta_description else ""
    canonical_url = canonical_match.group(1).strip() if canonical_match else ""

    return {
        "title": title,
        "meta_description": yoast_metadesc,
        "category": category,
        "tags": tag_list,
        "featured_image_url": (img_tag.get("src") if img_tag and img_tag.has_attr("src") else default_image_url),
        "yoast_keyphrase": yoast_keyphrase,
        "yoast_title": yoast_title,
        "yoast_metadesc": yoast_metadesc,
        "canonical": canonical_url
    }

# --- NEW: ensure first inline <img> has an alt (non-destructive: only if missing) ---
def ensure_first_img_alt(html: str, alt_text: str) -> str:
    if not alt_text:
        return html
    soup = BeautifulSoup(html, "html.parser")
    img = soup.find("img")
    if img and not img.has_attr("alt"):
        img["alt"] = _short_desc(alt_text, 125)
        return str(soup)
    return html

def publish_article_html_auto(
    *, 
    html_content: str, 
    site_url: str, 
    username: str, 
    app_password: str,
    article_id: str, 
    local_image_dir: Path, 
    default_image_url: str = "",
    publish: bool = False,
    check_yoast_head: bool = True,
    set_inline_img_alt_if_missing: bool = True
):
    headers = get_auth_headers(username, app_password)
    meta = extract_metadata_from_html(html_content, default_image_url=default_image_url or "")

    if set_inline_img_alt_if_missing:
        html_content = ensure_first_img_alt(html_content, meta["yoast_keyphrase"])

    Path("debug").mkdir(exist_ok=True)
    Path("debug/html_output.html").write_text(html_content, encoding="utf-8")
    Path("debug/metadata.json").write_text(str(meta), encoding="utf-8")

    # Taxonomies
    category_id = get_or_create_term_id(meta["category"], "categories", site_url, headers)
    tag_ids = [get_or_create_term_id(t, "tags", site_url, headers) for t in meta["tags"]]

    # Featured media
    featured_media_id = None
    local = list(local_image_dir.glob(f"{article_id}.*"))
    if local:
        featured_media_id = upload_local_featured_image(local[0], site_url, headers)
    elif meta["featured_image_url"]:
        featured_media_id = upload_featured_image(meta["featured_image_url"], site_url, headers)

    if featured_media_id:
        alt_basis = meta["yoast_keyphrase"] or meta["title"]
        set_media_alt_text(site_url, headers, featured_media_id, alt_basis)

    # Create post (basic fields only so we can clearly test Yoast push right after)
    status = "publish" if publish else "draft"
    post_data = {
        "title": meta["title"],
        "content": html_content,
        "status": status,
        "excerpt": meta["meta_description"],
        "categories": [category_id],
        "tags": tag_ids,
        "author": 7,
    }
    if featured_media_id:
        post_data["featured_media"] = featured_media_id

    url_create = f"{site_url.rstrip('/')}/wp-json/wp/v2/posts"
    r, body = _post_json(url_create, headers, post_data, "📬 Create post")
    r.raise_for_status()
    post = body
    post_id = post["id"]
    print(f"🆔 Post ID: {post_id} • status: {post.get('status')} • link: {post.get('link')}")

    # --- NEW: Push Yoast meta and verify ---
    yoast_push_ok = push_yoast_meta(site_url, headers, post_id, meta)

    verify = {}
    if check_yoast_head:
        verify = verify_yoast_head_json(site_url, headers, post_id, meta)

    # Clear, one-line summary that you can grep in logs
    print("==== YOAST SUMMARY ====")
    print(f"push_ok={yoast_push_ok}  "
          f"title_ok={verify.get('title_ok')}  "
          f"metadesc_ok={verify.get('metadesc_ok')}  "
          f"canonical_ok={verify.get('canonical_ok')}  "
          f"focus_ok={verify.get('focus_ok')}")
    print("=======================")

    return {
        "id": post_id,
        "title": post["title"]["rendered"],
        "link": post["link"],
        "yoast_push_ok": yoast_push_ok,
        "yoast_verify": verify
    }

