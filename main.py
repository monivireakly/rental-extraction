import logging

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

from rental.bot import start_bot

if __name__ == "__main__":
    start_bot()
