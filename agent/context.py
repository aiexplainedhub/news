from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass
class Context:
    article_id: str
    base_dir: Path
    region: dict

    @property
    def screenshots_dir(self) -> Path:
        p = self.base_dir / "screenshots" / self.article_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def article_dir(self) -> Path:
        p = self.base_dir / "article_content" / self.article_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    def new(base_dir: str, region: dict) -> "Context":
        aid = datetime.now().strftime("article_%Y%m%d_%H%M%S_%f")[:-3]
        return Context(article_id=aid, base_dir=Path(base_dir), region=region)
