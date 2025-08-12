from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    display: str = os.getenv("DISPLAY", ":1")
    wp_site_url: str = os.getenv("WP_SITE_URL", "")
    wp_user: str = os.getenv("WP_USER", "")
    wp_app_password: str = os.getenv("WP_APP_PASSWORD", "")
    default_image_url: str = os.getenv("DEFAULT_IMAGE_URL", "https://yourdomain.com/default-image.jpg")
    weights_path: str = os.getenv("YOLO_WEIGHTS", "models/best.pt")

    # 1440p default
    screen_region: dict = None

    @staticmethod
    def default():
        return Settings(
            screen_region={"left": 0, "top": 0, "width": 2560, "height": 1440}
        )
