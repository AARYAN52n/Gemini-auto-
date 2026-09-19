"""
Jio Gemini Auto Claimer & Multi-User Firebase Link Delivery System.
Entrypoint module supporting direct execution via `python jio.py` or `python gemini_claimer.py`.
"""
import sys
import asyncio
from gemini_claimer import main, logger

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    logger.info("Starting Jio Gemini Auto Claimer System via jio.py...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Process stopped.")