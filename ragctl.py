# ragctl.py
import os, json, argparse, datetime as dt, requests
from pathlib import Path
from typing import List, Dict
from html import unescape
from bs4 import BeautifulSoup

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, NamedVector

import torch
from sentence_transformers import SentenceTransformer

# ----------- ENV -----------
WP_BASE    = os.getenv("WP_BASE", "https://squarereporter.com")
WP_USER    = os.getenv("WP_USER") or os.getenv("WORDPRESS_USER")
# Accept both names for safety
WP_APP_PWD = (os.getenv("WP_APP_PWD")
              or os.getenv("WP_APP_PASSWORD")
              or os.getenv("WORDPRESS_APP_PASSWORD"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLL       = os.getenv("QDRANT_COLL", "sr_posts_dense")
STATE_PATH = Path(os.getenv("RAG_STATE_PATH", "/app_state/rag_state.json"))

def _require_wp_creds():
    if not WP_USER or not WP_APP_PWD:
        raise SystemExit("Missing creds: set WP_USER and WP_APP_PWD (or WP_APP_PASSWORD) in .env/compose.")


QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLL       = os.getenv("QDRANT_COLL", "sr_posts_dense")

STATE_PATH = Path(os.getenv("RAG_STATE_PATH", "/app_state/rag_state.json"))

# ----------- UTIL -----------
def _now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return " ".join(soup.get_text(" ").split())

def _require_wp_creds():
    if not WP_USER or not WP_APP_PWD:
        raise SystemExit("WP_USER / WP_APP_PASSWORD not set. Put them in .env and docker-compose.yml.")

# ----------- STATE -----------
def load_state() -> Dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"last_sync_iso": None}

def save_state(d: Dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2))

# ----------- WP CLIENT -----------
def wp_get(path, **params):
    _require_wp_creds()
    r = requests.get(f"{WP_BASE}{path}", params=params, auth=(WP_USER, WP_APP_PWD), timeout=30)
    r.raise_for_status()
    return r

def fetch_posts(after_iso: str | None = None, per_page=100) -> List[Dict]:
    """
    Robust pagination:
      - respects WP max per_page=100
      - stops on rest_post_invalid_page_number (400)
      - also stops when page >= X-WP-TotalPages (if header present)
    """
    out, page = [], 1
    per_page = min(int(per_page or 100), 100)
    base = f"{WP_BASE}/wp-json/wp/v2/posts"
    params = {
        "per_page": per_page,
        "status": "publish",
        "_fields": "id,slug,link,title,excerpt,content,date_gmt,categories,tags",
    }
    if after_iso:
        params["after"] = after_iso

    auth = (WP_USER, WP_APP_PWD)

    while True:
        params["page"] = page
        r = requests.get(base, params=params, auth=auth, timeout=30)

        # If WP says "invalid page number", we're done.
        if r.status_code == 400:
            try:
                err = r.json()
                if isinstance(err, dict) and err.get("code") == "rest_post_invalid_page_number":
                    break
            except Exception:
                pass
            r.raise_for_status()

        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        out.extend(batch)

        # If WP tells us the total number of pages, honor it
        total_pages = 0
        try:
            total_pages = int(r.headers.get("X-WP-TotalPages") or 0)
        except Exception:
            pass

        if total_pages and page >= total_pages:
            break

        page += 1

    return out


def fetch_post_by_id(post_id: int) -> Dict | None:
    r = wp_get(f"/wp-json/wp/v2/posts/{post_id}",
               **{"_fields": "id,slug,link,title,excerpt,content,date_gmt,categories,tags,status"})
    return r.json()

# ----------- EMBEDDER -----------
class Embedder:
    def __init__(self, name="Snowflake/snowflake-arctic-embed-l"):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(name, device=device)
        self.dim = self.model.get_sentence_embedding_dimension()
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass

    def encode_post(self, post: Dict):
        title   = unescape(post["title"]["rendered"])
        excerpt = post.get("excerpt", {}).get("rendered", "") or ""
        content = post.get("content", {}).get("rendered", "") or ""
        text = f"{title}\n\n{_strip_html(excerpt or content)}"
        vec = self.model.encode([text[:4000]], normalize_embeddings=True, convert_to_numpy=False)[0]
        return vec, title

# ----------- QDRANT -----------
def ensure_collection(client: QdrantClient, dim: int):
    cols = [c.name for c in client.get_collections().collections]
    if COLL not in cols:
        client.create_collection(
            collection_name=COLL,
            vectors_config={"dense": VectorParams(size=dim, distance=Distance.COSINE)}
        )

def to_point(post: Dict, vec) -> PointStruct:
    payload = {
        "post_id": post["id"],
        "url": post["link"],
        "slug": post["slug"],
        "title": unescape(post["title"]["rendered"]),
        "date_gmt": post.get("date_gmt"),
        "categories": post.get("categories", []),
        "tags": post.get("tags", []),
    }
    return PointStruct(id=post["id"], vector={"dense": vec}, payload=payload)

def upsert_posts(posts: List[Dict]) -> int:
    if not posts:
        return 0
    emb = Embedder()
    qc  = QdrantClient(url=QDRANT_URL)
    ensure_collection(qc, emb.dim)
    points = []
    for p in posts:
        vec, _title = emb.encode_post(p)
        points.append(to_point(p, vec))
    qc.upsert(collection_name=COLL, points=points)
    return len(points)

# ----------- COMMANDS -----------
def cmd_index_all(_args):
    posts = fetch_posts()
    n = upsert_posts(posts)
    state = load_state()
    state["last_sync_iso"] = _now_iso_utc()
    save_state(state)
    print(f"[index-all] Indexed {n} posts. last_sync={state['last_sync_iso']}")

def cmd_index_since(_args):
    state = load_state()
    after = state.get("last_sync_iso")
    if not after:
        print("[index-since] No last_sync found. Run `index-all` first.")
        return
    posts = fetch_posts(after_iso=after)
    n = upsert_posts(posts)
    state["last_sync_iso"] = _now_iso_utc()
    save_state(state)
    print(f"[index-since] Indexed {n} posts since {after}. last_sync={state['last_sync_iso']}")

def cmd_index_post(args):
    p = fetch_post_by_id(int(args.post_id))
    if not p or p.get("status") != "publish":
        print("[index-post] Post not found or not published.")
        return
    n = upsert_posts([p])
    print(f"[index-post] Indexed post {p['id']} (n={n})")

def cmd_status(_args):
    state = load_state()
    print(json.dumps({"collection": COLL, "last_sync_iso": state.get("last_sync_iso")}, indent=2))

def main():
    ap = argparse.ArgumentParser("ragctl")
    sub = ap.add_subparsers()

    a = sub.add_parser("index-all");   a.set_defaults(func=cmd_index_all)
    b = sub.add_parser("index-since"); b.set_defaults(func=cmd_index_since)
    c = sub.add_parser("index-post");  c.add_argument("post_id"); c.set_defaults(func=cmd_index_post)
    d = sub.add_parser("status");      d.set_defaults(func=cmd_status)

    args = ap.parse_args()
    if not hasattr(args, "func"):
        ap.print_help(); return
    args.func(args)

if __name__ == "__main__":
    main()
