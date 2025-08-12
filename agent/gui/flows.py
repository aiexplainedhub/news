import time, os
from pathlib import Path
import pyautogui
from .screenshot import take_screenshot
from .io import human_type
import pyperclip
import cv2
import json

READY_LABELS = ("ready_button", "start_button")

def _collect_detections(results, model, conf=0.6):
    by_class = {}
    if not results:
        return by_class
    for r in results:
        # guard: some results may have no boxes
        boxes = getattr(r, "boxes", None)
        if not boxes:
            continue
        for b in boxes:
            c = float(b.conf[0])
            if c < conf:
                continue
            cls = model.names[int(b.cls[0])]
            x, y, w, h = b.xywh[0].tolist()
            by_class.setdefault(cls, []).append({
                "center_x": int(x),
                "center_y": int(y),
                "width": int(w),
                "height": int(h),
                "conf": c,
            })
    return by_class

def _pick_input_zone(dets: dict):
    """Prefer the input_zone with the largest center_y (closest to bottom)."""
    zs = dets.get("input_zone") or dets.get("input_zones")  # just in case
    if not zs:
        return None
    return max(zs, key=lambda d: d["center_y"])

def _found_ready(results, model, conf, labels):
    if not results:
        return False
    for r in results:
        boxes = getattr(r, "boxes", None)
        if not boxes:
            continue
        for b in boxes:
            if float(b.conf[0]) >= conf and model.names[int(b.cls[0])] in labels:
                return True
    return False

def _save_annotated(path:str, results, dets:dict=None):
    """
    Save annotated image(s) next to `path` as *_ann.png.
    Also saves detections JSON as *_dets.json if provided.
    """
    base = Path(path)
    if results:
        for i, r in enumerate(results):
            try:
                ann = r.plot()  # numpy image (BGR)
                out = base.with_name(f"{base.stem}_ann{i}.png")
                cv2.imwrite(str(out), ann)
            except Exception as e:
                print(f"⚠️ annotate single frame failed: {e}")
    if dets is not None:
        try:
            (base.with_name(f"{base.stem}_dets.json")).write_text(
                json.dumps(dets, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"⚠️ write dets.json failed: {e}")

def wait_for_ready(ctx, detector, *, folder, poll_seconds=10, timeout_seconds=600,
                   conf=0.6, labels=READY_LABELS, cooldown_seconds=10,
                   assume_ready_after=600, save_ann=True):
    """
    Wait until a ready/start button appears (>= conf).
    If not seen within `assume_ready_after` seconds, ASSUME ready and return True.
    If not seen within `timeout_seconds`, give up and return False.

    - `assume_ready_after=None` disables the soft-timeout behavior.
    - `cooldown_seconds` avoids immediate re-detection on the next agent.
    - If `save_ann` is True, every poll saves *_ann*.png (and dets.json when available).
    """
    start = time.time()
    while True:
        path = take_screenshot(ctx.region, folder)
        results = detector.raw(path)

        if save_ann:
            try:
                # store a quick snapshot of detections too
                dets = _collect_detections(results, detector.model, conf=conf)
                _save_annotated(path, results, dets)
            except Exception as e:
                print(f"⚠️ annotate failed: {e}")

        if _found_ready(results, detector.model, conf, labels):
            print("✅ Successful: ready/start button appeared again.")
            time.sleep(cooldown_seconds)
            return True

        elapsed = time.time() - start

        # Soft timeout → treat as success
        if assume_ready_after is not None and elapsed >= assume_ready_after:
            print(f"⚠️ Assumed ready after {assume_ready_after}s without detection.")
            time.sleep(cooldown_seconds)
            return True

        # Hard timeout → real failure
        if timeout_seconds is not None and elapsed >= timeout_seconds:
            print("⏰ Timeout waiting for ready/start button.")
            return False

        print(f"⏳ Not ready yet... waiting {poll_seconds}s")
        time.sleep(poll_seconds)

def run_agent(ctx, detector, agent, timeout_seconds=600, conf=0.6,
              fallback_click=(1300, 1100), scroll_attempts=2, scroll_amount=600):
    folder = ctx.screenshots_dir / agent["name"]
    folder.mkdir(parents=True, exist_ok=True)

    # 1) Always wait until ready first (save annotated frames)
    if not wait_for_ready(ctx, detector, folder=folder, poll_seconds=10,
                          timeout_seconds=timeout_seconds, conf=conf,
                          assume_ready_after=600, save_ann=True):
        print(f"⏰ Timeout: '{agent['name']}' never reached ready state.")
        return False

    # 2) Try to detect input_zone; if not found, scroll up a bit and retry
    input_xy = None
    for attempt in range(scroll_attempts + 1):  # initial + N scroll retries
        fp = take_screenshot(ctx.region, folder)
        results = detector.raw(fp)

        # SAVE ANNOTATED on every YOLO call in this loop
        try:
            dets = _collect_detections(results, detector.model, conf=conf)
            _save_annotated(fp, results, dets)
        except Exception as e:
            print(f"⚠️ annotate/save failed: {e}")
            dets = {}

        choice = _pick_input_zone(dets)
        if choice:
            input_xy = (choice["center_x"], choice["center_y"])
            break

        if attempt < scroll_attempts:
            print(f"⚠️ '{agent['name']}' input zone not detected — scrolling up and retrying ({attempt+1}/{scroll_attempts})...")
            pyautogui.scroll(scroll_amount)  # positive = up
            time.sleep(0.4)

    # 3) Focus input
    if input_xy:
        pyautogui.moveTo(*input_xy, duration=0.3)
        pyautogui.click()
    else:
        print(f"⚠️ '{agent['name']}' input zone still not detected after scroll retries — using fallback click.")
        pyautogui.moveTo(*fallback_click, duration=0.3)
        pyautogui.click()
        time.sleep(0.2)

    # 4) Type + submit
    human_type(agent["prompt"])
    time.sleep(0.2)
    pyautogui.press("enter")

    # 5) Wait until ready appears again (submission completed) — save annotated frames
    return wait_for_ready(ctx, detector, folder=folder, poll_seconds=10,
                          timeout_seconds=timeout_seconds, conf=conf,
                          assume_ready_after=600, save_ann=True)

def automate_text_capture(ctx):
    """
    Simple capture:
    1. Click to focus page
    2. Select all
    3. Copy
    4. Save text + annotated screenshots
    """
    print("🖱️ Move your mouse to the target browser area. Starting in 3 seconds...")
    time.sleep(3)

    # 1️⃣ Click to make sure page is focused
    pyautogui.moveTo(1250, 650, duration=0.5)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(0.2)

    region = {"top": 0, "left": 0, "width": 2560, "height": 1440}
    base_folder = ctx.screenshots_dir
    Path(base_folder).mkdir(parents=True, exist_ok=True)

    # 2️⃣ Select all
    print("➡️ Selecting all text")
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.5)
    take_screenshot(region, base_folder)

    # 3️⃣ Copy
    print("➡️ Copying selection")
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(0.6)
    take_screenshot(region, base_folder)

    # 4️⃣ Save text
    text = pyperclip.paste()
    out_path = Path(base_folder) / f"{ctx.article_id}.txt"
    out_path.write_text(text, encoding='utf-8')
    print(f"✅ Text copied and saved to {out_path}")

def reset_interface(ctx):
    folder = ctx.screenshots_dir / "reset_interface"
    folder.mkdir(parents=True, exist_ok=True)

    time.sleep(2)
    pyautogui.press('f5')
    time.sleep(1)
    pyautogui.hotkey('ctrl', 'shift', 'o')
    time.sleep(1)
    take_screenshot(ctx.region, folder)

    take_screenshot(ctx.region, folder)

    # Bootstrap conversation
    human_type("Hello", min_delay=0.05, max_delay=0.15)
    pyautogui.press('enter')
    time.sleep(0.4)
    take_screenshot(ctx.region, folder)

    # Optional: click somewhere safe to close menus, etc.
    pyautogui.moveTo(2040, 1280, duration=0.02)
    pyautogui.click()
    time.sleep(0.1)
    take_screenshot(ctx.region, folder)
