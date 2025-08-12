# Modular Agent Refactor

This is a modularized version of your `agent.py`. It separates GUI automation, vision, parsing,
and WordPress publishing. Secrets are loaded from environment variables.

## Quick start

1) Create and populate a `.env` file (do NOT commit it):
   ```env
   DISPLAY=:1
   WP_SITE_URL=https://squarereporter.com
   WP_USER=admin
   WP_APP_PASSWORD=YOUR_APP_PASSWORD
   DEFAULT_IMAGE_URL=https://yourdomain.com/default-image.jpg
   ```

2) Install deps (ideally in a virtualenv / container):
   ```bash
   pip install -r agent/requirements.txt
   ```

3) Put your YOLO weights at `runs/detect/train10/weights/best.pt`
   (or change the path in `vision/detector.py`).

4) Provide `agent/data/trending_topics.json`. Example:
   ```json
   {
     "World": ["Global tourism trends 2025"],
     "Tech": ["AI safety debate heats up"]
   }
   ```

5) Run:
   ```bash
   python -m agent.main
   ```

## Notes

- Replace hard-coded coordinates / timings in `gui/flows.py` if your window layout differs.
- The login flow was removed by default (your original was commented), add it back in `gui/flows.py` if needed.
- Image downloader flow is provided in `gui/downloader.py`, expects helper text in `agent/assets/image_downloader_helper.txt`.
