import hashlib
import logging
import os
import uuid

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

import db
import extractor

load_dotenv()
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
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

    try:
        data = extractor.extract_listing(raw_text)
        listing_id = str(uuid.uuid4())
        needs_review = bool(data.get("needs_review", False))
        db.insert_listing(listing_id, listing_hash, data)
        logger.info("Extraction success, listing_id=%s", listing_id)
        await update.message.reply_text(_format_reply(data, needs_review))

    except Exception as e:
        logger.error("Extraction failed for hash=%s: %s", listing_hash, e)
        db.increment_extraction_attempts(listing_hash)
        attempts = db.get_extraction_attempts(listing_hash)
        if attempts >= 3:
            db.mark_needs_review(listing_hash)
            logger.warning("Marking hash=%s for review after %d attempts", listing_hash, attempts)
        await update.message.reply_text("❌ Extraction failed. Saved raw. Will retry.")


def main():
    db.init_db()
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
