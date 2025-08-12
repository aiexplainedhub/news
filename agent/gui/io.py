import pyperclip, pyautogui, time, random

# Use xclip for clipboard operations (Linux/Xvfb)
try:
    pyperclip.set_clipboard("xclip")
except Exception:
    pass

def human_type(text: str, min_delay=0, max_delay=0):
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    if min_delay or max_delay:
        time.sleep(random.uniform(min_delay, max_delay))
