"""
Property research agent — enriches each unique building with a structured profile
and a distinct description, stored in property_profiles.

For each unresearched building it:
  1. Collects up to 5 sample listing texts from the DB
  2. Calls Claude with the research prompt
  3. Stores the result in property_profiles (upsert)

Usage:
    python -m rental.researcher              # research all pending buildings
    python -m rental.researcher --limit 10  # cap at N buildings
    python -m rental.researcher --dry-run   # show what would be researched
"""

import argparse
import json
import logging
import time

import anthropic

from . import db
from .config import settings
from .prompts.research import RESEARCH_PROMPT

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0].strip()
    return text


def research_building(property_name, district, samples):
    """Call Claude to produce a property profile. Returns parsed dict."""
    sample_block = "\n".join(f"- {s[:300]}" for s in samples)
    user_message = (
        f"<property>\n"
        f"Name: {property_name}\n"
        f"District: {district or 'Unknown'}\n"
        f"Listings:\n{sample_block}\n"
        f"</property>"
    )

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        system=RESEARCH_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = _strip_fences(message.content[0].text)
    logger.debug("Research response: %s", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed for %s: %s", property_name, e)
        raise


def run(limit=None, dry_run=False):
    db.init_db()

    buildings = db.get_unresearched_buildings()
    if limit:
        buildings = buildings[:limit]

    if not buildings:
        print("✅ All buildings already have profiles.")
        return

    print(f"{'DRY RUN — ' if dry_run else ''}{len(buildings)} building(s) to research:\n")

    done = failed = 0

    for b in buildings:
        name = b["property_name"]
        district = b["district"]
        building_key = b["building_key"]
        listing_count = b["listing_count"]

        print(f"  {name or '(unknown)'} / {district or '?'}  ({listing_count} listing(s))")

        if dry_run:
            continue

        samples = db.get_listing_samples(name, district)

        try:
            data = research_building(name, district, samples)
            db.insert_property_profile(
                building_key=building_key,
                canonical_listing_id=b["canonical_listing_id"],
                data=data,
            )
            print(
                f"    ✅ {data.get('building_type') or '?'} | "
                f"built {data.get('year_built') or '?'} | "
                f"dev: {data.get('developer') or '?'} | "
                f"confidence: {data.get('research_confidence', 0):.2f}"
            )
            done += 1
        except Exception as e:
            logger.error("Research failed for %s: %s", name, e)
            print(f"    ❌ Failed: {e}")
            failed += 1

        time.sleep(0.5)  # gentle rate limit

    if not dry_run:
        print(f"\nDone. ✅ {done} researched  ❌ {failed} failed")


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description="Research and enrich property profiles.")
    parser.add_argument("--limit", type=int, default=None, help="Max buildings to research")
    parser.add_argument("--dry-run", action="store_true", help="Show pending buildings without calling Claude")
    args = parser.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
