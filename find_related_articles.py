# find_related_via_wp.py
import os
import json
from html import unescape
from bs4 import BeautifulSoup
import requests
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# ====== ENV CONFIG ======
WP_BASE = os.getenv("WP_BASE", "https://squarereporter.com")
WP_USER = os.getenv("WP_USER") or os.getenv("WORDPRESS_USER")
WP_APP_PWD = (os.getenv("WP_APP_PWD") or
              os.getenv("WP_APP_PASSWORD") or
              os.getenv("WORDPRESS_APP_PASSWORD"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLL = os.getenv("QDRANT_COLL", "sr_posts_dense")
VECTOR_NAME = "dense"
EMBED_MODEL = "Snowflake/snowflake-arctic-embed-l"

# ====== HELPERS ======
def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return " ".join(soup.get_text(" ").split())

def wp_get_post(post_id_or_slug):
    """
    Fetch WP post by numeric ID or slug.
    """
    auth = (WP_USER, WP_APP_PWD)
    if str(post_id_or_slug).isdigit():
        url = f"{WP_BASE}/wp-json/wp/v2/posts/{post_id_or_slug}"
        params = {"_fields": "id,slug,link,title,excerpt,content,date_gmt,categories,tags,status"}
        r = requests.get(url, params=params, auth=auth, timeout=30)
        r.raise_for_status()
        return r.json()
    else:
        # Search by slug
        url = f"{WP_BASE}/wp-json/wp/v2/posts"
        params = {"slug": post_id_or_slug,
                  "_fields": "id,slug,link,title,excerpt,content,date_gmt,categories,tags,status"}
        r = requests.get(url, params=params, auth=auth, timeout=30)
        r.raise_for_status()
        arr = r.json()
        return arr[0] if arr else None

# ====== MAIN ======
if not WP_USER or not WP_APP_PWD:
    raise SystemExit("❌ Missing WP credentials. Set WP_USER and WP_APP_PWD in environment.")

post_id_or_slug = input("Enter WordPress post ID or slug: ").strip()
post = wp_get_post(post_id_or_slug)

if not post:
    raise SystemExit(f"❌ Post '{post_id_or_slug}' not found.")

if post.get("status") != "publish":
    raise SystemExit(f"❌ Post is not published. Status: {post.get('status')}")

print(f"📄 Post: {post['title']['rendered']} ({post['id']})")

# Build text EXACTLY like ragctl.Embedder.encode_post
title = unescape(post["title"]["rendered"])
excerpt_html = post.get("excerpt", {}).get("rendered", "") or ""
content_html = post.get("content", {}).get("rendered", "") or ""
text = f"{title}\n\n{_strip_html(excerpt_html or content_html)}"
text = text[:4000]

# Load embedding model
print("⏳ Loading embedding model...")
model = SentenceTransformer(EMBED_MODEL)
print("✅ Model loaded.")

query_vector = model.encode([text], normalize_embeddings=True)[0].tolist()

# Connect to Qdrant
client = QdrantClient(QDRANT_URL)
print("✅ Connected to Qdrant.")

# Query for similar posts
results = client.query_points(
    collection_name=QDRANT_COLL,
    query=query_vector,
    using=VECTOR_NAME,
    limit=3,
    with_payload=True
)

# Display results
related_articles = []
for p in results.points:
    related_articles.append({
        "id": p.payload.get("post_id"),
        "title": p.payload.get("title"),
        "url": p.payload.get("url"),
        "score": p.score
    })

print("\n🔍 Top 3 similar articles:")
print(json.dumps(related_articles, indent=2, ensure_ascii=False))
