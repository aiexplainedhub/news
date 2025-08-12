# Create a lightweight Yoast SEO smoke test script and an optional MU-plugin file for convenience.
# These files will be available for the user to download and run locally / upload to WordPress.

from pathlib import Path

base_dir = Path.cwd()
base_dir.mkdir(parents=True, exist_ok=True)

# 1) Python smoke test script
py_code = r'''#!/usr/bin/env python3
"""
Yoast SEO REST Smoke Test
-------------------------
Quickly verify you can set Yoast SEO fields (focus keyphrase, title, meta description) via WordPress REST
without running your full publishing pipeline.

USAGE EXAMPLES
--------------
# Using CLI flags
python yoast_smoke_test.py --base https://your-site.com --user admin --app-pass ABCD EFGH IJKL MNOP QRST UVWX
# (Application Passwords include spaces; wrap the whole value in quotes if your shell splits words)

# Publish instead of draft
python yoast_smoke_test.py --base https://your-site.com --user admin --app-pass "xxxx xxxx xxxx xxxx xxxx xxxx" --publish

# Clean up (delete the post after the test)
python yoast_smoke_test.py --base https://your-site.com --user admin --app-pass "xxxx xxxx xxxx xxxx xxxx xxxx" --cleanup

# Override Yoast fields
python yoast_smoke_test.py --base https://your-site.com --user admin --app-pass "xxxx" \
  --keyphrase "EU AI Act timeline" \
  --seo-title "EU AI Act Timeline: What Changes in 2025" \
  --meta-desc "Understand the EU AI Act timeline, key milestones, and compliance deadlines for 2025."

REQUIREMENTS
------------
- WordPress 5.6+ with Application Passwords (or use JWT headers; adapt code).
- Yoast SEO plugin installed and active.
- MU-plugin that exposes Yoast meta keys to REST (see 'yoast-rest-bridge.php' provided alongside this script).
  Keys registered: _yoast_wpseo_focuskw, _yoast_wpseo_title, _yoast_wpseo_metadesc, _yoast_wpseo_canonical.

WHAT IT DOES
------------
1) Creates a draft post with a unique slug (or publishes if --publish is passed).
2) Sets Yoast focus keyphrase, SEO title, and meta description via the /wp/v2/posts endpoint.
3) Reads the post back to confirm the meta stored correctly.
4) Tries Yoast's head endpoint (/yoast/v1/get_head?url=...) and prints the detected <title> and meta description.
5) Optionally deletes the test post at the end (--cleanup).
"""

import argparse
import json
import sys
import time
import random
import string
from typing import Dict, Any, Tuple
from urllib.parse import urlencode, quote
import requests


def rand_suffix(n: int = 6) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Yoast SEO REST Smoke Test")
    p.add_argument("--base", required=True, help="Base site URL, e.g., https://example.com")
    p.add_argument("--user", required=True, help="WP username (with permissions to create/edit posts)")
    p.add_argument("--app-pass", required=True, help="WordPress Application Password for the user")
    p.add_argument("--post-type", default="post", help="Post type (default: post)")
    p.add_argument("--publish", action="store_true", help="Publish instead of draft")
    p.add_argument("--cleanup", action="store_true", help="Delete the test post at the end")
    p.add_argument("--keyphrase", default="Yoast REST smoke test", help="Focus keyphrase")
    p.add_argument("--seo-title", default="", help="Yoast SEO title (leave empty to auto-generate)")
    p.add_argument("--meta-desc", default="", help="Yoast meta description (leave empty to auto-generate)")
    return p.parse_args()


def build_urls(base: str, post_type: str) -> Tuple[str, str]:
    base = base.rstrip("/")
    posts = f"{base}/wp-json/wp/v2/{post_type}s" if not base.endswith("/wp-json") else base
    yoast_head = f"{base}/wp-json/yoast/v1/get_head"
    # WP core uses /wp-json/wp/v2/posts; for CPTs replace accordingly
    if post_type == "post":
        endpoint = f"{base}/wp-json/wp/v2/posts"
    else:
        endpoint = f"{base}/wp-json/wp/v2/{post_type}"
    return endpoint, yoast_head


def short_desc(text: str, max_len: int = 155) -> str:
    text = ' '.join(text.split())
    if len(text) <= max_len:
        return text
    # Try to cut at last space before max_len
    cut = text[:max_len].rsplit(' ', 1)[0]
    return cut if cut else text[:max_len]


def create_test_post(endpoint: str, auth: Tuple[str, str], status: str, title: str, content: str, slug: str,
                     yoast_meta: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "status": status,
        "title": title,
        "content": content,
        "slug": slug,
        "meta": yoast_meta
    }
    r = requests.post(endpoint, json=payload, auth=auth, timeout=30)
    try:
        r.raise_for_status()
    except Exception as e:
        print("POST failed:", r.status_code, r.text, file=sys.stderr)
        raise
    return r.json()


def update_post(endpoint: str, post_id: int, auth: Tuple[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{endpoint}/{post_id}", json=data, auth=auth, timeout=30)
    try:
        r.raise_for_status()
    except Exception as e:
        print("POST (update) failed:", r.status_code, r.text, file=sys.stderr)
        raise
    return r.json()


def get_post(endpoint: str, post_id: int, auth: Tuple[str, str]) -> Dict[str, Any]:
    r = requests.get(f"{endpoint}/{post_id}", params={"_fields": "id,slug,status,link,meta,title"}, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()


def delete_post(endpoint: str, post_id: int, auth: Tuple[str, str]) -> Dict[str, Any]:
    r = requests.delete(f"{endpoint}/{post_id}", params={"force": "true"}, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_yoast_head(yoast_head_endpoint: str, public_url: str) -> Dict[str, Any]:
    params = {"url": public_url}
    r = requests.get(yoast_head_endpoint, params=params, timeout=30)
    if r.status_code != 200:
        return {"error": f"Yoast head endpoint returned {r.status_code}", "body": r.text}
    try:
        return r.json()
    except Exception:
        return {"raw": r.text}


def main():
    args = parse_args()
    endpoint, yoast_head_endpoint = build_urls(args.base, args.post_type)

    status = "publish" if args.publish else "draft"
    suffix = rand_suffix()
    title = args.seo_title or f"Yoast REST Smoke Test {suffix}"
    slug = "yoast-rest-smoke-test-" + suffix
    content = (
        f"<p>This is an automated smoke test post created at {time.strftime('%Y-%m-%d %H:%M:%S')}.</p>"
        f"<p>It verifies REST writes to Yoast SEO meta keys.</p>"
    )
    keyphrase = args.keyphrase
    meta_desc = args.meta_desc or short_desc(
        f"{keyphrase} — Automated test to verify Yoast SEO meta writes via REST. "
        f"Ensures focus keyphrase, SEO title, and meta description are stored and rendered correctly."
    )

    yoast_meta = {
        "_yoast_wpseo_focuskw": keyphrase,
        "_yoast_wpseo_title": title,
        "_yoast_wpseo_metadesc": meta_desc
    }

    auth = (args.user, args.app_pass)

    print("== Creating test post ==")
    try:
        created = create_test_post(endpoint, auth, status, title, content, slug, yoast_meta)
    except Exception:
        print("\nHINT: If the error mentions 'meta' or unknown keys, make sure the MU-plugin "
              "'yoast-rest-bridge.php' is installed to expose Yoast keys to REST.", file=sys.stderr)
        sys.exit(1)

    post_id = created.get("id")
    link = created.get("link")
    print(f"Created post ID: {post_id}")
    print(f"Link: {link}")
    print(f"Status: {created.get('status')}")
    print()

    # Read back meta
    print("== Verifying stored meta ==")
    got = get_post(endpoint, post_id, auth)
    meta = got.get("meta", {})
    for k in ("_yoast_wpseo_focuskw", "_yoast_wpseo_title", "_yoast_wpseo_metadesc"):
        print(f"{k}: {meta.get(k)!r}")
    print()

    # Try Yoast head endpoint (may fail if site is private/staging)
    if link:
        print("== Fetching Yoast head (rendered SEO) ==")
        head = fetch_yoast_head(yoast_head_endpoint, link)
        if "json" in head or isinstance(head, dict):
            # Yoast returns JSON with 'json' key containing title, description, robots, etc. in some versions.
            # We'll try to print reasonable fields if present.
            if isinstance(head, dict) and "json" in head:
                yo = head["json"]
            else:
                yo = head

            title_val = None
            desc_val = None
            if isinstance(yo, dict):
                title_val = yo.get("title") or yo.get("og_title") or yo.get("twitter_title")
                desc_val  = yo.get("description") or yo.get("og_description") or yo.get("twitter_description")

            print("Rendered <title>:", repr(title_val))
            print("Rendered meta description:", repr(desc_val))
        else:
            print("Yoast head raw response:", str(head)[:300], "...")
        print()

    if args.cleanup:
        print("== Cleaning up (deleting post) ==")
        deleted = delete_post(endpoint, post_id, auth)
        print(f"Deleted post ID: {deleted.get('id')} (trashed: {deleted.get('deleted', True)})")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
(base_dir / "yoast_smoke_test.py").write_text(py_code, encoding="utf-8")


# 2) Optional MU-plugin file to expose Yoast meta to REST
mu_plugin = r'''<?php
/**
 * Plugin Name: Yoast REST Bridge
 * Description: Expose key Yoast SEO meta keys for REST writes.
 */

add_action('init', function () {
    $post_types = get_post_types(['public' => true], 'names');

    $yoast_keys = [
        '_yoast_wpseo_focuskw'   => 'string',
        '_yoast_wpseo_metadesc'  => 'string',
        '_yoast_wpseo_title'     => 'string',
        '_yoast_wpseo_canonical' => 'string',
    ];

    foreach ($post_types as $type) {
        foreach ($yoast_keys as $key => $type_def) {
            register_post_meta($type, $key, [
                'type'          => $type_def,
                'single'        => true,
                'show_in_rest'  => true,
                'auth_callback' => function() { return current_user_can('edit_posts'); },
            ]);
        }
    }
});
'''
(base_dir / "yoast-rest-bridge.php").write_text(mu_plugin, encoding="utf-8")

str(base_dir), [p.name for p in base_dir.iterdir() if p.name.startswith("yoast")]
