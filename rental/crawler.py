"""
Crawl a public Telegram channel via its web preview (t.me/s/<channel>).
No API credentials required — works on any public channel.

Usage:
    python -m rental.crawler [--channel channelname] [--pages 5]
"""

import argparse
import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

_KH_TZ = timezone(timedelta(hours=7))


def _to_cambodia_time(dt_str):
    """Convert an ISO datetime string (any tz) to Cambodia local time string."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_KH_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str

import requests
from bs4 import BeautifulSoup

from . import db
from . import extractor
from .config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_channels():
    """Merge env channels into DB, then return all active channels with stored page depth."""
    for ch in settings.channels:
        db.register_channel(ch)
    return db.get_active_channels()  # [{"username": ..., "pages": ...}]


def _md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def fetch_messages(channel, before_id=None):
    """Fetch one page of messages. Returns (messages, oldest_msg_id)."""
    url = f"https://t.me/s/{channel}"
    if before_id:
        url += f"?before={before_id}"

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    posts = soup.select(".tgme_widget_message")

    messages = []
    oldest_id = None

    for post in posts:
        msg_id_attr = post.get("data-post", "")
        try:
            msg_id = int(msg_id_attr.split("/")[-1])
        except (ValueError, IndexError):
            continue

        text_el = post.select_one(".tgme_widget_message_text")
        if not text_el:
            continue

        text = text_el.get_text(separator="\n").strip()
        if not text:
            continue

        time_el = post.select_one("time")
        posted_at = _to_cambodia_time(time_el.get("datetime")) if time_el else None

        messages.append({"id": msg_id, "text": text, "posted_at": posted_at})
        if oldest_id is None or msg_id < oldest_id:
            oldest_id = msg_id

    return messages, oldest_id


def crawl_channel(channel, max_pages=5):
    """Crawl a single channel. Returns a stats dict."""
    db.init_db()

    processed = skipped = failed = 0
    before_id = None

    for page in range(1, max_pages + 1):
        logger.info("Fetching page %d/%d (channel=%s)...", page, max_pages, channel)

        try:
            messages, oldest_id = fetch_messages(channel, before_id)
        except Exception as e:
            logger.error("Failed to fetch page %d: %s", page, e)
            break

        if not messages:
            logger.info("No more messages in @%s.", channel)
            break

        for msg in reversed(messages):
            raw_text = msg["text"]
            listing_hash = _md5(raw_text)

            if db.listing_exists(listing_hash):
                logger.info("Skip duplicate msg_id=%s", msg["id"])
                skipped += 1
                continue

            posted_at = msg.get("posted_at")
            db.insert_raw_listing(listing_hash, raw_text, posted_at=posted_at)

            try:
                data = extractor.extract_listing(raw_text)
                listing_id = str(uuid.uuid4())
                db.insert_listing(listing_id, listing_hash, data, posted_at=posted_at)
                logger.info(
                    "Extracted msg_id=%s → %s | confidence=%.2f",
                    msg["id"],
                    data.get("property_name") or "unknown",
                    data.get("extraction_confidence", 0),
                )
                processed += 1
            except Exception as e:
                logger.error("Extraction failed msg_id=%s: %s", msg["id"], e)
                db.increment_extraction_attempts(listing_hash)
                attempts = db.get_extraction_attempts(listing_hash)
                if attempts >= 3:
                    db.mark_needs_review(listing_hash)
                failed += 1

            time.sleep(1)

        before_id = oldest_id
        time.sleep(2)

    db.update_channel_stats(channel, processed, skipped, failed, pages=max_pages)
    return {"channel": channel, "processed": processed, "skipped": skipped, "failed": failed}


def crawl_all(channels=None, max_pages=None):
    """Crawl all channels using per-channel stored page depth."""
    channel_configs = channels or get_channels()
    results = []
    for entry in channel_configs:
        if isinstance(entry, dict):
            channel = entry["username"]
            pages = max_pages or entry.get("pages", settings.crawl_pages_per_run)
        else:
            channel = entry
            pages = max_pages or settings.crawl_pages_per_run
        logger.info("=== Starting crawl: @%s (%d pages) ===", channel, pages)
        stats = crawl_channel(channel, pages)
        results.append(stats)
    return results


def main():
    parser = argparse.ArgumentParser(description="Crawl public Telegram channels for rental listings.")
    parser.add_argument("--channel", default=None, help="Single channel to crawl (default: all from TELEGRAM_CHANNELS)")
    parser.add_argument("--pages", type=int, default=5, help="Pages per channel (default 5, ~20 msgs each)")
    args = parser.parse_args()

    if args.channel:
        crawl_channel(args.channel.lstrip("@"), args.pages)
    else:
        crawl_all(max_pages=args.pages)


if __name__ == "__main__":
    main()
