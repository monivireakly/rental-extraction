Manage and inspect the registered Telegram channels.

Usage:
  /channels                        — list all registered channels with stats
  /channels add @channelname       — register a new channel
  /channels pause @channelname     — mark a channel inactive (skipped in crawls)
  /channels resume @channelname    — re-activate a paused channel

Arguments: $ARGUMENTS

Steps:

No args — list all channels:
  Run this SQL against the database:
  ```sql
  SELECT username, added_at, last_crawled_at,
         total_crawls, total_extracted, is_active
  FROM channels ORDER BY total_extracted DESC;
  ```
  Format as a markdown table with columns:
  Channel | Added | Last Crawled | Crawls | Extracted | Status

"add @channelname":
  1. Strip the @ from the channel name
  2. Run: `python3 -c "from rental.db import register_channel; register_channel('channelname')"`
  3. Confirm: "✅ @channelname registered. Run /crawl channelname to pull listings."

"pause @channelname":
  1. Run: `python3 -c "from rental.db import set_channel_active; set_channel_active('channelname', False)"`
  2. Confirm: "⏸ @channelname paused — will be skipped in scheduled crawls."

"resume @channelname":
  1. Run: `python3 -c "from rental.db import set_channel_active; set_channel_active('channelname', True)"`
  2. Confirm: "▶️ @channelname resumed."
