Generate the visual insights dashboard from the current listings database.

Usage:
  /insights

Steps:
1. Run: `python3 -m rental.insights`
2. Read the saved image at `data/insights.png` and display it inline.
3. After displaying, summarise the key numbers pulled from the database:
   - Total listings
   - Top district by volume
   - Most common room type
   - Median and average rent
   - Extraction confidence breakdown (high / medium / low)
4. Note the output path: `data/insights.png`
