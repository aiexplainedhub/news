import time, random, os
from pathlib import Path
import pyautogui, pyperclip
from .screenshot import take_screenshot

def _paste(text: str):
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")

def image_downloader(ctx):
    debug_folder = ctx.screenshots_dir / "image_downloader"
    debug_folder.mkdir(parents=True, exist_ok=True)
    take_screenshot(ctx.region, debug_folder)

    def attempt_download():
        print("🖼️ Attempting to download image...")
        pyautogui.hotkey('ctrl', 'shift', 'J')  # Open save dialog (adjust for your env)
        time.sleep(1)
        pyautogui.moveTo(2400, 570, duration=1.0)
        time.sleep(0.8)
        pyautogui.click()
        time.sleep(0.3)
        #write allow pasting
        for char in "allow pasting":
            pyautogui.write(char)
            time.sleep(0.1)
        pyautogui.press('enter')
        time.sleep(0.8)

        # Paste the helper text
        helper_path = Path(__file__).resolve().parents[1] / "assets" / "image_downloader_helper.txt"
        content = helper_path.read_text(encoding="utf-8") if helper_path.exists() else ""
        _paste(content)
        time.sleep(0.8)
        pyautogui.press('enter')
        time.sleep(0.8)
        pyautogui.moveTo(1300, 570, duration=1.0)
        time.sleep(0.8)
        take_screenshot(ctx.region, debug_folder)
        pyautogui.rightClick()
        time.sleep(0.8)
        take_screenshot(ctx.region, debug_folder)
        pyautogui.press('down', presses=2)
        time.sleep(0.6)
        take_screenshot(ctx.region, debug_folder)
        pyautogui.press('enter')
        take_screenshot(ctx.region, debug_folder)
        time.sleep(0.4)
        folder = f"/app/screenshots/generated_images/{ctx.article_id}"
        _paste(folder)
        take_screenshot(ctx.region, debug_folder)
        time.sleep(0.4)
        pyautogui.press('enter')
        take_screenshot(ctx.region, debug_folder)
        time.sleep(0.4)

    attempt_download()
    print(f"✅ Image expected at: /app/screenshots/generated_images/{ctx.article_id}.png")
