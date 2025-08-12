import json
from pathlib import Path

def load_trending_topics(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
