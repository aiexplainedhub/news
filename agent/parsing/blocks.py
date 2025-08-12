import re
from pathlib import Path

def _next_block(text: str, start_pos: int = 0):
    x = re.search(r"ChatGPT said\s*:\s*", text[start_pos:], flags=re.IGNORECASE)
    if not x: return None, start_pos
    block_start = start_pos + x.end()
    y = re.search(r"\byou said\s*:", text[block_start:], flags=re.IGNORECASE)
    block_end = block_start + (y.start() if y else len(text))
    return text[block_start:block_end].strip(), block_end

def extract_and_save_blocks(content: str, agents_list: list[dict], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    footer = "No file chosenNo file chosen\nChatGPT can make mistakes. Check important info. See Cookie Preferences."
    content = content.replace(footer, "").rstrip()
    skipped, cursor = _next_block(content, 0)
    if skipped is None:
        print("⚠️ no blocks found"); return
    for agent in agents_list:
        block_text, cursor = _next_block(content, cursor)
        if block_text is None: break
        (out_dir / f"{agent['name']}.txt").write_text(block_text, encoding="utf-8")
