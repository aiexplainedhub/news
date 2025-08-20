import os, time
os.environ.setdefault("DISPLAY", ":1")
import pyautogui
pyautogui.FAILSAFE = False

from pathlib import Path
from .config import Settings
from .context import Context
from .logging_setup import setup_logging
from .pipeline.topics import load_trending_topics
from .pipeline.agents import generate_agents_for_topic
from .vision.detector import Detector
from .gui.flows import run_agent, automate_text_capture, reset_interface
from .parsing.blocks import extract_and_save_blocks
from .parsing.preprocess import preprocess_article
from .wordpress.publish import publish_article_html_auto
from .gui.flows import run_agent, automate_text_capture, reset_interface, wait_for_ready
from .gui.downloader import image_downloader
import json
from .pipeline.related import (
    find_related_articles,
    build_internal_links_identifier_prompt,
    build_internal_links_publisher_prompt,
)
def set_agent_prompt(agents_list, name: str, prompt: str):
    """Upsert the agent's prompt in agents_list."""
    for a in agents_list:
        if a.get("name") == name:
            a["prompt"] = prompt
            return
    agents_list.append({"name": name, "prompt": prompt})
def parse_ai_response(ctx, agents_list):
    input_txt = ctx.screenshots_dir / f"{ctx.article_id}.txt"
    if not input_txt.exists():
        print(f"❌ Input file not found: {input_txt}")
        return
    content = input_txt.read_text(encoding="utf-8").replace("\r\n", "\n")
    extract_and_save_blocks(content, agents_list, ctx.article_dir)

def run():
    setup_logging()
    settings = Settings.default()

    topics_path = Path(__file__).resolve().parents[0] / "data" / "trending_topics.json"
    if not topics_path.exists():
        print(f"⚠️ No trending_topics.json found at {topics_path}. Create one to proceed.")
        return
    trending_topics = load_trending_topics(topics_path)

    detector = Detector(settings.weights_path)

    for category, topics in trending_topics.items():
        for topic in topics:
            ctx = Context.new(base_dir=".", region=settings.screen_region)
            print(f"🔄 Processing article: {topic}  |  ARTICLE_ID={ctx.article_id}")

            agents_list = generate_agents_for_topic(topic)
            published = False
            # ✅ Reset interface before starting agents
            reset_interface(ctx)
            time.sleep(5)
            for agent in list(agents_list):
                ok = run_agent(ctx, detector, agent)
                if agent["name"] == "seo_optimizer" and ok:
                    published = True
                    break

            if published:
                # ✅ Ensure UI is back to ready state before copying text
                # wait_for_ready(
                #     ctx, detector,
                #     folder=ctx.screenshots_dir / "pre_capture_wait",
                #     poll_seconds=5,
                #     timeout_seconds=600,
                #     conf=0.6
                # )
                time.sleep(5)
                automate_text_capture(ctx)
                parse_ai_response(ctx, agents_list)
                
                
                # Run article similarity check
                print("🔍 Checking for similar articles...")
                related_out = find_related_articles(ctx.article_id, ctx.article_dir)
                print("   → Similar:", json.dumps(related_out["related"], ensure_ascii=False))

                # Build and run internal_links_identifier
                print("🔗 Identifying internal links (planning)...")
                identifier_prompt = build_internal_links_identifier_prompt(agents_list, ctx.article_dir)
                
                run_agent(ctx, detector, {"name": "internal_links_identifier", "prompt": identifier_prompt})
                set_agent_prompt(agents_list, "internal_links_identifier", identifier_prompt)

                # Capture & parse the plan output into files
                time.sleep(2)
                automate_text_capture(ctx)
                parse_ai_response(ctx,agents_list)

                # Build and run internal_links_publisher
                print("🔗 Publishing internal links (applying plan)...")
                publisher_prompt = build_internal_links_publisher_prompt(agents_list, ctx.article_dir)
                run_agent(ctx, detector, {"name": "internal_links_publisher", "prompt": publisher_prompt})
                set_agent_prompt(agents_list, "internal_links_publisher", publisher_prompt)
                #Generating image prompt
                print("🖼️ Generating article image prompt...")
                run_agent(ctx, detector, {"name": "article_image_generator", "prompt": "Give me a prompt for a dall e model to generate an image for this article. output only the prompt without any additional text or explanation."})    
                # Capture & parse the applied HTML (optional, if your publisher outputs HTML to UI)
                time.sleep(3)
                automate_text_capture(ctx)
                parse_ai_response(ctx, agents_list)
                #Run article image generator
                print("🖼️ Generating article image...")
                reset_interface(ctx)
                time.sleep(2)
                image_prompt_path = ctx.article_dir / "article_image_generator.txt"
                if image_prompt_path.exists():
                    image_prompt = "Generate this realistic image : " + image_prompt_path.read_text(encoding="utf-8").strip()
                else:
                    image_prompt = "Fallback prompt."
                    #continue  # Skip if no image prompt file found
                # Re-run image agent with composed prompt (optional UI step)
                run_agent(ctx, detector, {"name": "article_image_generator", "prompt": image_prompt})

                # Download image
                print("🖼️ Image generation complete. Downloading image...")
                image_downloader(ctx)

                # Publish
                html_content = preprocess_article(ctx.article_dir, ctx.article_id)
                result = publish_article_html_auto(
                    html_content=html_content,
                    site_url=settings.wp_site_url,
                    username=settings.wp_user,
                    app_password=settings.wp_app_password,
                    article_id=ctx.article_id,
                    local_image_dir=Path("screenshots/generated_images"),
                    default_image_url=settings.default_image_url
                )
                print(f"✅ Draft created. Post ID: {result['id']}  |  Title: {result['title']}  |  Link: {result['link']}")

            # Prepare for next article
            pyautogui.hotkey('ctrl', 't')
            time.sleep(1)
            pyautogui.typewrite('chatgpt.com')
            time.sleep(0.5)
            pyautogui.press('enter')
            reset_interface(ctx)
            time.sleep(3)

    # Shutdown
    pyautogui.hotkey('alt', 'f4')

if __name__ == "__main__":
    run()
