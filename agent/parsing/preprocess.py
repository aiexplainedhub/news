import re
from pathlib import Path

def preprocess_article(article_dir: Path, article_id: str) -> str:
    p = article_dir / "seo_optimizer.txt"
    if not p.exists():
        print(f"❌ File not found: {p}")
        return ""
    content = p.read_text(encoding="utf-8")
    cleaned = re.sub(r'^(?:\s*(?:html|copy|edit)\s*){1,3}', '', content, flags=re.IGNORECASE)
    return cleaned
