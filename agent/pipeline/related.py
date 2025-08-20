# pipeline/related.py
import os
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import logging
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
logger = logging.getLogger(__name__)
# Env / constants (matches your ragctl + test)
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLL = os.getenv("QDRANT_COLL", "sr_posts_dense")
VECTOR_NAME = os.getenv("QDRANT_VECTOR_NAME", "dense")
EMBED_MODEL = os.getenv("EMBED_MODEL", "Snowflake/snowflake-arctic-embed-l")  # 1024-dim

# ---------- helpers ----------

def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return " ".join(soup.get_text(" ").split())

def _load_first_existing(article_dir: Path, basename: str, exts: List[str]) -> Optional[Path]:
    for ext in exts:
        p = article_dir / f"{basename}{ext}"
        if p.exists():
            return p
    return None

def _load_seo_or_publisher_html(article_dir: Path) -> Tuple[Optional[str], str]:
    """
    Return (html, source_name) from best available file:
    - seo_optimizer.html/.txt
    - article_publisher.html/.txt
    - fallback None if nothing found
    """
    # Prefer the SEO’d HTML if present
    p = _load_first_existing(article_dir, "seo_optimizer", [".html", ".txt"])
    if p:
        return p.read_text(encoding="utf-8"), "seo_optimizer"
    # Fall back to publisher HTML
    p = _load_first_existing(article_dir, "article_publisher", [".html", ".txt"])
    if p:
        return p.read_text(encoding="utf-8"), "article_publisher"
    return None, ""

def _extract_title_and_body_from_html(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ").strip()
    # Extract visible text (avoid scripts/styles)
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    # Body text (minus h1)
    if h1:
        h1.extract()
    text = soup.get_text(" ")
    text = " ".join(text.split())
    return title, text

def _build_query_text_from_html(html: str) -> str:
    title, body = _extract_title_and_body_from_html(html)
    text = f"{title}\n\n{_strip_html(body)}".strip()
    return text[:4000]

def _load_link_plan(article_dir: Path) -> Optional[Dict]:
    # The identifier should have produced a JSON-ish output; try .json then .txt
    plan_path = _load_first_existing(article_dir, "internal_links_identifier", [".json", ".txt"])
    if not plan_path:
        return None
    try:
        return json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        # If the tool saved JSON-as-text with backticks or other wrappers, try to salvage
        raw = plan_path.read_text(encoding="utf-8")
        raw = raw.strip().strip("```").strip()
        try:
            return json.loads(raw)
        except Exception:
            return None

# ---------- public API ----------

def find_related_articles(article_id: str, article_dir: Path) -> Dict:
    """
    Build an embedding for the current article (SEO or Publisher HTML),
    query Qdrant for top-3 similar posts, save to JSON, and return the dict.
    Output format:
      { "related": [ { "title","url","score","id" }, ... ], "source_html": "seo_optimizer|article_publisher" }
    """
    html, source = _load_seo_or_publisher_html(article_dir)
    if not html:
        raise FileNotFoundError("No seo_optimizer.html/.txt or article_publisher.html/.txt found.")

    query_text = _build_query_text_from_html(html)

    # Embedding
    model = SentenceTransformer(EMBED_MODEL)
    vec = model.encode([query_text], normalize_embeddings=True)[0].tolist()

    # Qdrant search
    client = QdrantClient(QDRANT_URL)
    res = client.query_points(
        collection_name=QDRANT_COLL,
        query=vec,
        using=VECTOR_NAME,
        limit=3,
        with_payload=True,
    )

    related = []
    for p in res.points:
        payload = p.payload or {}
        related.append({
            "id": payload.get("post_id"),
            "title": payload.get("title"),
            "url": payload.get("url"),
            "score": p.score
        })

    out = {"related": related, "source_html": source}
    # Save
    (article_dir / "related_internal_articles.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return out

def build_internal_links_identifier_prompt(agents_list: List[Dict], article_dir: Path) -> str:
    """
    Compose the prompt for internal_links_identifier by taking the agent base prompt
    and appending the SEO HTML and related JSON as inputs.
    """
    base = next((a["prompt"] for a in agents_list if a["name"] == "internal_links_identifier"), "").strip()
    if not base:
        raise ValueError("internal_links_identifier prompt not found in agents_list")

    # Load SEO (preferred) or publisher HTML
    html, source = _load_seo_or_publisher_html(article_dir)
    if not html:
        raise FileNotFoundError("No seo_optimizer/article_publisher output found for identifier prompt.")

    # Load related JSON
    rel_path = article_dir / "related_internal_articles.json"
    if not rel_path.exists():
        raise FileNotFoundError("related_internal_articles.json not found. Run find_related_articles first.")
    related_json = rel_path.read_text(encoding="utf-8")

    prompt = (
        f"{base}\n\n"
        f"Inputs:\n"
        f"- RELATED_INTERNALS = {related_json}\n"
        f"- ARTICLE_HTML:\n<BEGIN_HTML>\n{html}\n</END_HTML>\n"
    )
    return prompt
def _find_latest_file(base: Path, patterns: list[str]) -> Optional[Path]:
    """Return the most recently modified file matching any of the patterns."""
    matches = []
    for pat in patterns:
        matches.extend((base / "").glob(pat))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)
def build_internal_links_publisher_prompt(
    agents_list,
    article_dir: Path,
    keyphrase: Optional[str] = None
) -> str:
    """
    Compose the prompt (string) for internal_links_publisher.

    Behavior:
    - Loads SEO-optimized (preferred) or publisher HTML from the given article_dir.
    - Loads LINK_PLAN from internal_links_identifier.{json|txt}.
    - If LINK_PLAN is missing/invalid/empty -> instruct to return ARTICLE_HTML unchanged.
    - Otherwise -> instruct to apply LINK_PLAN.
    """

    # 0) Get base prompt from agents_list
    base = next((a["prompt"] for a in agents_list if a.get("name") == "internal_links_publisher"), "").strip()
    if not base:
        raise ValueError("internal_links_publisher prompt not found in agents_list")

    # 1) Load SEO (preferred) or publisher HTML from the *current article dir*
    article_html, _source = _load_seo_or_publisher_html(article_dir)
    if not article_html:
        # Optional fallback: if called with project root, look once under article_content/*
        latest = _find_latest_file(
            article_dir,
            [
                "article_content/*/seo_optimizer.txt",
                "article_content/*/seo_optimizer.html",
                "article_content/*/article_publisher.txt",
                "article_content/*/article_publisher.html",
            ],
        )
        if latest and latest.exists():
            article_html = latest.read_text(encoding="utf-8")
        else:
            try:
                contents = [p.name for p in article_dir.iterdir()]
            except Exception:
                contents = []
            logger.error("Expected seo_optimizer/article_publisher HTML in %s; contents: %s",
                         article_dir, contents)
            raise FileNotFoundError(f"No seo_optimizer/article_publisher HTML under {article_dir}.")

    # 2) Load LINK_PLAN (.json or .txt; salvage JSON if wrapped)
    link_plan = _load_link_plan(article_dir)

    def _unchanged_prompt() -> str:
        logger.warning("No usable LINK_PLAN found. Publisher must return ARTICLE_HTML unchanged.")
        return (
            f"{base}\n\n"
            "No LINK_PLAN was found or it is empty/invalid. Do not insert any internal links.\n"
            "Return the ARTICLE_HTML exactly as provided. Output pure HTML only.\n\n"
            "Inputs:\n"
            f"- LINK_PLAN = {json.dumps({'plan': []}, ensure_ascii=False)}\n"
            f"- KEYPHRASE = {json.dumps(keyphrase or '', ensure_ascii=False)}\n"
            "- ARTICLE_HTML:\n"
            "<BEGIN_HTML>\n"
            f"{article_html}\n"
            "</END_HTML>\n"
        )

    # 3) Validate LINK_PLAN structure (must be a dict with a non-empty 'plan' list)
    if not isinstance(link_plan, dict) or "plan" not in link_plan or not isinstance(link_plan["plan"], list):
        return _unchanged_prompt()
    if len(link_plan["plan"]) == 0:
        return _unchanged_prompt()

    # 4) Normal case: usable plan -> apply it
    return (
        f"{base}\n\n"
        "Apply the provided LINK_PLAN to insert internal links.\n"
        "Never alter headings or the first paragraph; preserve HTML structure; output pure HTML only.\n\n"
        "Inputs:\n"
        f"- LINK_PLAN = {json.dumps(link_plan, ensure_ascii=False)}\n"
        f"- KEYPHRASE = {json.dumps(keyphrase or '', ensure_ascii=False)}\n"
        "- ARTICLE_HTML:\n"
        "<BEGIN_HTML>\n"
        f"{article_html}\n"
        "</END_HTML>\n"
    )
