Normalise district names, room types, and furnished status in the listings database.

Usage:
  /normalize         — dry-run: show what would change, ask for confirmation
  /normalize apply   — apply changes directly without prompting

Arguments: $ARGUMENTS

Steps:
1. Always run a dry-run first:
   `python3 -m rental.normalizer`
2. Parse the output and summarise:
   - How many rows need updating
   - Which fields are affected (district / room_type / furnished_status)
   - Show a condensed table of unique mappings (old → new), not every row
3. If $ARGUMENTS contains "apply" OR the dry-run shows changes:
   - If "apply" was passed: proceed immediately
   - Otherwise: ask the user "Apply these N changes to the database? (yes/no)"
4. On confirmation (or if "apply" was passed):
   `python3 -m rental.normalizer --apply`
   Report "✅ Applied N updates."
5. If already clean ("nothing to normalise"), report that and stop.
