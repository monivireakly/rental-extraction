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
import logging
import re
import time

import anthropic

from . import db
from .config import settings
from .prompts.research import RESEARCH_PROMPT

logger = logging.getLogger(__name__)

_client = None

# ── Tool definitions ──────────────────────────────────────────────────────────

_RESEARCH_TOOL = {
    "name": "research_building",
    "description": "Return a structured property profile for the given Phnom Penh building.",
    "input_schema": {
        "type": "object",
        "properties": {
            "year_built":          {"type": ["integer", "null"]},
            "developer":           {"type": ["string", "null"]},
            "total_floors":        {"type": ["integer", "null"]},
            "total_units":         {"type": ["integer", "null"]},
            "building_type": {
                "type": ["string", "null"],
                "enum": ["Condo", "Serviced Apartment", "Borey", "Villa", "Commercial", None],
            },
            "amenities_summary":   {"type": ["string", "null"]},
            "description":         {"type": "string"},
            "research_confidence": {"type": "number"},
        },
        "required": ["description", "research_confidence"],
    },
}

# Cached block — avoids re-tokenising the research prompt on every call (~80% token savings).
_RESEARCH_SYSTEM = [
    {
        "type": "text",
        "text": RESEARCH_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]

_CLASSIFY_TOOL = {
    "name": "classify_property",
    "description": "Classify a Phnom Penh property name into the correct property type.",
    "input_schema": {
        "type": "object",
        "properties": {
            "property_type": {
                "type": "string",
                "enum": ["Apartment", "Condo", "Service Apartment", "Borey", "Villa", "Shophouse", "Studio"],
            },
        },
        "required": ["property_type"],
    },
}

_CLASSIFY_SYSTEM_BLOCK = [
    {
        "type": "text",
        "text": (
            "You are a Cambodia real estate property type classifier. "
            "Given a property name, classify it into exactly one property type. "
            "Rules: Most named residential towers in Phnom Penh are Condo or Apartment. "
            "Use Borey only if the word Borey appears or it is clearly a gated housing estate. "
            "Use Apartment for mid-rise rentals and named residences without condo branding. "
            "Use Condo for high-rise units sold or rented with strata title."
        ),
        "cache_control": {"type": "ephemeral"},
    }
]

# ── Helpers ───────────────────────────────────────────────────────────────────

# Maps property_profiles.building_type → listings.property_type canonical values
_BUILDING_TYPE_MAP = {
    "condo":               "Condo",
    "condominium":         "Condo",
    "apartment":           "Apartment",
    "serviced apartment":  "Service Apartment",
    "service apartment":   "Service Apartment",
    "borey":               "Borey",
    "villa":               "Villa",
    "shophouse":           "Shophouse",
    "studio":              "Studio",
}

# Whole-word keyword patterns applied to property_name when no profile exists
_NAME_KEYWORDS = [
    (r"\bborey\b",        "Borey"),
    (r"\bvilla\b",        "Villa"),
    (r"\bshophouse\b",    "Shophouse"),
    (r"\bserviced?\b",    "Service Apartment"),
    (r"\bcondo\b",        "Condo"),
    (r"\bcondominium\b",  "Condo"),
    (r"\bstudio\b",       "Studio"),
]


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


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
        max_tokens=1024,
        system=_RESEARCH_SYSTEM,
        tools=[_RESEARCH_TOOL],
        tool_choice={"type": "tool", "name": "research_building"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_block = next(
        (b for b in message.content if b.type == "tool_use"),
        None,
    )
    if tool_block is None:
        raise ValueError(f"No tool_use block in response: {message.content}")

    data = tool_block.input
    logger.info(
        "Research done — %s | confidence=%.2f | cache_tokens=%s",
        property_name,
        data.get("research_confidence", 0),
        getattr(message.usage, "cache_read_input_tokens", 0),
    )
    return data


def _classify_by_name(name):
    lower = name.lower()
    for pattern, ptype in _NAME_KEYWORDS:
        if re.search(pattern, lower):
            return ptype
    return None


def _classify_via_claude(name):
    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=20,
        system=_CLASSIFY_SYSTEM_BLOCK,
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_property"},
        messages=[{"role": "user", "content": name}],
    )
    tool_block = next(
        (b for b in message.content if b.type == "tool_use"),
        None,
    )
    if tool_block is None:
        return "Apartment"
    return tool_block.input.get("property_type", "Apartment")


def backfill_property_type(dry_run=False):
    """Fill property_type for all listings where it is NULL."""
    db.init_db()
    rows = db.get_properties_missing_type()

    if not rows:
        print("✅ No listings with missing property_type.")
        return

    from_profile = from_keyword = from_claude = 0

    for row in rows:
        name     = row["property_name"]
        district = row["district"]
        btype    = row["building_type"]
        count    = row["listing_count"]
        source   = None
        ptype    = None

        # 1. Use existing profile building_type
        if btype:
            ptype = _BUILDING_TYPE_MAP.get(btype.lower().strip())
            if ptype:
                source = "profile"

        # 2. Keyword match on name
        if not source:
            ptype = _classify_by_name(name)
            if ptype:
                source = "keyword"

        # 3. Ask Claude
        if not source:
            try:
                ptype = _classify_via_claude(name)
                source = "claude"
                time.sleep(0.3)
            except Exception as e:
                logger.error("Claude classify failed for %s: %s", name, e)
                ptype = "Apartment"
                source = "fallback"

        tag = f"[{source}]"
        print(f"  {tag:10s} {name:40s} → {ptype}  ({count} rows)")

        if not dry_run:
            updated = db.bulk_update_property_type(name, ptype)
            building_key = db.make_building_key(name, district)
            db.upsert_profile_building_type(building_key, ptype)
            if source == "profile":
                from_profile += updated
            elif source == "keyword":
                from_keyword += updated
            else:
                from_claude += updated

    if not dry_run:
        total = from_profile + from_keyword + from_claude
        print(f"\n✅ Updated {total} row(s)  —  profile:{from_profile}  keyword:{from_keyword}  claude:{from_claude}")
    else:
        print("\nDry run — pass --backfill to apply.")


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
    parser.add_argument("--backfill", action="store_true", help="Backfill property_type for listings where it is NULL")
    args = parser.parse_args()

    if args.backfill:
        backfill_property_type(dry_run=args.dry_run)
    else:
        run(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
