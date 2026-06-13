Manage the extraction prompt and city classification rules.

Usage:
  /prompt                  — show the current extraction prompt
  /prompt fixcity          — dry-run city corrections on existing listings
  /prompt fixcity apply    — apply city corrections to the database
  /prompt test <text>      — run extraction on a raw listing text snippet

Arguments: $ARGUMENTS

Steps:

No args — show current prompt:
  Read and print the contents of `rental/prompts/extraction.py`.
  Highlight the city detection rule.

"fixcity" (dry-run):
  Run: `python3 -m rental.normalizer --fixcity`
  Or call fix_city() directly:
  ```
  python3 -c "from rental.normalizer import fix_city; fix_city(apply=False)"
  ```
  Report how many listings would be updated.

"fixcity apply":
  Run: `python3 -c "from rental.normalizer import fix_city; fix_city(apply=True)"`
  Report how many listings were updated to Siem Reap.

"test <text>":
  Run extraction on the provided text:
  ```
  python3 -c "
  from rental.extractor import extract_listing
  import json
  result = extract_listing('<paste text here>')
  print(json.dumps(result, indent=2))
  "
  ```
  Show the full JSON output, highlighting city, district, landmark, and extraction_confidence.

Siem Reap detection terms (defined in SIEM_REAP_TERMS in normalizer.py):
  Pub Street, Angkor Market, Angkor Supermarket, Sala Kamreuk,
  Deum Kralanh, Taphul, Bakheng, Heritage Walk, Wat Bo,
  Svay Dangkum, Slor Kram

Phnom Penh exclusions (override SR match):
  Wat Botum, Chakto Mukh
