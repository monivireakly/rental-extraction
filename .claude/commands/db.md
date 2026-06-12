Inspect the listings database and report a quick health summary.

Usage:
  /db                — overall stats
  /db district       — breakdown by district
  /db rent           — rent statistics by room type
  /db review         — listings flagged for review

Arguments: $ARGUMENTS

Steps:
1. Connect to the database at the path in DATABASE_PATH env (default: ./data/listings.db)
2. Run queries based on $ARGUMENTS:

   No args — overall health:
   ```sql
   SELECT COUNT(*) FROM raw_listings;
   SELECT COUNT(*), SUM(is_processed), SUM(extraction_attempts >= 3) FROM raw_listings;
   SELECT COUNT(*) FROM listings;
   SELECT COUNT(*) FROM listings WHERE needs_review = 1;
   ```

   "district" — top districts:
   ```sql
   SELECT district, COUNT(*) as n, ROUND(AVG(rent_usd),0) as avg_rent
   FROM listings WHERE district IS NOT NULL
   GROUP BY district ORDER BY n DESC LIMIT 15;
   ```

   "rent" — rent by room type:
   ```sql
   SELECT room_type, COUNT(*) as n,
          ROUND(MIN(rent_usd),0) as min,
          ROUND(AVG(rent_usd),0) as avg,
          ROUND(MAX(rent_usd),0) as max
   FROM listings WHERE rent_usd IS NOT NULL
   GROUP BY room_type ORDER BY avg;
   ```

   "review" — flagged listings:
   ```sql
   SELECT l.id, r.raw_text, l.extraction_confidence
   FROM listings l JOIN raw_listings r ON l.listing_hash = r.listing_hash
   WHERE l.needs_review = 1 LIMIT 10;
   ```

3. Format results as a clean markdown table and print them.
4. Suggest next steps based on what you find (e.g. run /normalize if dirty data, /insights to visualise).
