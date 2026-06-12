Start the Telegram rental extraction bot.

Usage:
  /bot

Steps:
1. Check that required environment variables are set:
   - Read `.env` (or check os.environ) for TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY
   - If either is missing or still set to the placeholder value, stop and tell the user which variable to fill in
2. Check the database exists and is initialised:
   - If `data/listings.db` does not exist, note that it will be created on first run
3. Run the bot in the background:
   `python3 main.py`
   Use run_in_background=true so the session stays interactive
4. Confirm: "Bot is running. Send any rental listing text to your bot, or type /crawl to pull from channels."
5. Remind the user to press Ctrl+C (or stop the background process) to shut it down.
