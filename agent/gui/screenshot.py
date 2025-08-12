import mss, mss.tools
from PIL import Image, ImageDraw
from datetime import datetime
from pathlib import Path
import pyautogui

def take_screenshot(region: dict, folder: str | Path) -> str:
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = folder / f"screenshot_{ts}.png"

    with mss.mss() as sct:
        sct_img = sct.grab(region)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(path))

    cx, cy = pyautogui.position()
    # Translate to region space
    rel_x, rel_y = cx - region["left"], cy - region["top"]
    draw_cursor_on_image(str(path), rel_x, rel_y)
    return str(path)

def draw_cursor_on_image(path: str, cx: int, cy: int):
    try:
        with Image.open(path) as im:
            w, h = im.size
            # clamp so we don't draw out of bounds
            cx = max(0, min(cx, w - 1))
            cy = max(0, min(cy, h - 1))
            draw = ImageDraw.Draw(im)
            draw.line((cx - 10, cy, cx + 10, cy), fill="red", width=2)
            draw.line((cx, cy - 10, cx, cy + 10), fill="red", width=2)
            im.save(path)
    except Exception as e:
        print(f"⚠️ cursor paint failed: {e}")
