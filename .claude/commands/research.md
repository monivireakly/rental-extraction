Run the property research agent to enrich buildings with structured profiles and descriptions.

Usage:
  /research              — research all pending buildings
  /research 10           — research up to 10 buildings
  /research dry-run      — show what would be researched without calling Claude

Arguments: $ARGUMENTS

Steps:
1. Parse $ARGUMENTS:
   - "dry-run": show pending buildings only
   - a number: use as --limit
   - empty: research all pending

2. First always do a dry-run to show the user what will be researched:
   `python3 -m rental.researcher --dry-run`
   Report: how many buildings are pending, list them with listing counts.

3. If $ARGUMENTS is "dry-run", stop here.

4. Otherwise run the research:
   - With limit: `python3 -m rental.researcher --limit <n>`
   - All:        `python3 -m rental.researcher`

5. Stream and report the output:
   - For each building: name, type, year built, developer, confidence
   - Final summary: N researched, N failed

6. After completion, suggest running /insights to regenerate the dashboard
   or /db to check the property_profiles table.
