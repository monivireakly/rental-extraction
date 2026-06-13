import asyncio
import hashlib
import logging
import uuid
from datetime import timedelta
from functools import partial

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from . import db
from . import extractor
from . import crawler
from . import normalizer
from .config import settings

logger = logging.getLogger(__name__)


def _md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _format_reply(data, needs_review):
    rent = f"${data.get('rent_usd')}" if data.get("rent_usd") is not None else "—"
    elec = f"${data.get('electricity_per_kwh')}/kWh" if data.get("electricity_per_kwh") is not None else "—"
    water = f"${data.get('water_per_m3')}/m³" if data.get("water_per_m3") is not None else "—"
    mgmt = f"${data.get('management_fee_usd')}" if data.get("management_fee_usd") is not None else "—"
    confidence = data.get("extraction_confidence", 0)

    prop = data.get("property_name") or "Unknown"
    borey = data.get("borey_name") or ""
    location = data.get("district") or data.get("landmark") or "Location unknown"
    room = data.get("room_type") or "?"
    furnished = data.get("furnished_status") or "?"

    review_line = "\n⚠️ Flagged for review" if needs_review else ""

    return (
        f"✅ Saved\n\n"
        f"🏠 {prop} {borey}\n"
        f"📍 {location}\n"
        f"🛏 {room} | {furnished}\n\n"
        f"💵 Rent:        {rent}\n"
        f"⚡ Electric:    {elec}\n"
        f"💧 Water:       {water}\n"
        f"🏢 Management:  {mgmt}\n\n"
        f"🎯 Confidence: {confidence}"
        f"{review_line}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me any Phnom Penh rental listing text and I'll extract and save the details."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text
    listing_hash = _md5(raw_text)

    logger.info("Received message, hash=%s", listing_hash)

    if db.listing_exists(listing_hash):
        logger.info("Duplicate listing detected: %s", listing_hash)
        await update.message.reply_text("⚠️ Duplicate listing — already in database.")
        return

    db.insert_raw_listing(listing_hash, raw_text)

    # Only catch extraction/parse failures here, not Telegram send errors.
    try:
        data = extractor.extract_listing(raw_text)
        listing_id = str(uuid.uuid4())
        needs_review = bool(data.get("needs_review", False))
        db.insert_listing(listing_id, listing_hash, data)
        logger.info("Extraction success, listing_id=%s", listing_id)
        reply = _format_reply(data, needs_review)
    except Exception as e:
        logger.error("Extraction failed for hash=%s: %s", listing_hash, e)
        db.increment_extraction_attempts(listing_hash)
        attempts = db.get_extraction_attempts(listing_hash)
        if attempts >= 3:
            db.mark_needs_review(listing_hash)
            logger.warning("Marking hash=%s for review after %d attempts", listing_hash, attempts)
        reply = "❌ Extraction failed. Saved raw. Will retry."

    try:
        await update.message.reply_text(reply)
    except TelegramError as e:
        logger.warning("Could not send reply (hash=%s): %s", listing_hash, e)


async def crawl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /crawl                  — all channels from .env, 1 page each
    /crawl 5                — all channels, 5 pages each
    /crawl channelname      — one channel, 1 page
    /crawl channelname 5    — one channel, 5 pages
    """
    args = context.args
    target_channel = None
    pages = 1

    if len(args) >= 1:
        if args[0].lstrip("-").isdigit():
            pages = max(1, min(int(args[0]), 20))
        else:
            target_channel = args[0].lstrip("@")
            if len(args) >= 2 and args[1].lstrip("-").isdigit():
                pages = max(1, min(int(args[1]), 20))

    if target_channel:
        channels = [{"username": target_channel, "pages": pages}]
    else:
        channels = crawler.get_channels()
    channel_list = "  ".join(f"@{c['username']}" for c in channels)
    msg = await update.message.reply_text(
        f"🔄 Crawling {channel_list}..."
    )

    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            None, partial(crawler.crawl_all, channels, pages)
        )
        lines = ["✅ Crawl complete\n"]
        total_p = total_s = total_f = 0
        ch_pages = {c["username"]: c["pages"] for c in channels}
        for r in results:
            p = ch_pages.get(r["channel"], "?")
            lines.append(
                f"@{r['channel']} ({p}p)\n"
                f"  📥 {r['processed']} extracted  "
                f"⏭ {r['skipped']} skipped  "
                f"❌ {r['failed']} failed"
            )
            total_p += r["processed"]
            total_s += r["skipped"]
            total_f += r["failed"]
        if len(results) > 1:
            lines.append(f"\nTotal: {total_p} extracted  {total_s} skipped  {total_f} failed")
        await msg.edit_text("\n".join(lines))
    except Exception as e:
        logger.error("Crawl command failed: %s", e)
        await msg.edit_text(f"❌ Crawl failed: {e}")


async def fixcity_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /fixcity        — dry-run, show how many would be corrected
    /fixcity apply  — apply corrections to the database
    """
    apply = len(context.args) > 0 and context.args[0].lower() == "apply"
    loop = asyncio.get_event_loop()
    try:
        count = await loop.run_in_executor(None, lambda: normalizer.fix_city(apply=apply))
        if apply:
            await update.message.reply_text(
                f"✅ City fix applied — {count} listing(s) updated to Siem Reap."
                if count else "✅ No city corrections needed."
            )
        else:
            await update.message.reply_text(
                f"🔍 Dry run — {count} listing(s) would be updated to Siem Reap.\n"
                f"Run /fixcity apply to write changes."
                if count else "✅ No city corrections needed."
            )
    except Exception as e:
        logger.error("fixcity failed: %s", e)
        await update.message.reply_text(f"❌ Fix failed: {e}")


async def _scheduled_crawl(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Scheduled crawl starting (every %dh)...", settings.crawl_interval_hours)
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(
            None, partial(crawler.crawl_all, max_pages=settings.crawl_pages_per_run)
        )
        total = sum(r["processed"] for r in results)
        skipped = sum(r["skipped"] for r in results)
        logger.info("Scheduled crawl done: %d extracted, %d skipped", total, skipped)
    except Exception as e:
        logger.error("Scheduled crawl failed: %s", e)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning("Telegram error: %s", context.error)


def start_bot():
    db.init_db()
    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("crawl", crawl_command))
    app.add_handler(CommandHandler("fixcity", fixcity_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    app.job_queue.run_repeating(
        _scheduled_crawl,
        interval=timedelta(hours=settings.crawl_interval_hours),
        first=timedelta(seconds=30),
        name="scheduled_crawl",
    )
    logger.info(
        "Bot starting — auto-crawl every %dh (%d pages/run)",
        settings.crawl_interval_hours,
        settings.crawl_pages_per_run,
    )
    app.run_polling()
