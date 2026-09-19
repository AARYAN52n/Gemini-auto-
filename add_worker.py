"""
Utility to log in additional Telegram worker accounts for parallel link claiming.
Saves session files into the 'sessions/' directory.
"""
import os
import sys
import asyncio
from telethon import TelegramClient

sys.stdout.reconfigure(encoding='utf-8')

API_ID = 33316824
API_HASH = "f24ba90df909312f3368a3ee2f68487b"
SESSIONS_DIR = "sessions"

async def add_worker():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    print("=" * 60)
    print("🤖 Telegram Worker Account Login Utility")
    print("=" * 60)
    print("Is utility se aap naye Telegram accounts add kar sakte hain.")
    print("Har naya account parallel worker ban kar fast speed me links claim karega!\n")

    phone = input("👉 Enter Phone Number (with country code, e.g. +919876543210): ").strip()
    if not phone:
        print("❌ Phone number cannot be empty.")
        return

    clean_name = phone.replace("+", "").replace(" ", "").replace("-", "")
    session_path = os.path.join(SESSIONS_DIR, f"worker_{clean_name}")

    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"\n✅ Ye account pehle se logged in hai: {me.first_name} (ID: {me.id})")
        print(f"📁 Session saved at: {session_path}.session")
        await client.disconnect()
        return

    print(f"\n📲 Sending login code to {phone}...")
    await client.send_code_request(phone)

    code = input("👉 Enter Telegram Login Code received via SMS/Telegram: ").strip()
    try:
        await client.sign_in(phone, code)
    except Exception as e:
        if "Two-steps verification" in str(e) or "SessionPasswordNeededError" in type(e).__name__:
            pwd = input("👉 Enter 2FA Password: ").strip()
            await client.sign_in(password=pwd)
        else:
            print(f"❌ Login failed: {e}")
            await client.disconnect()
            return

    me = await client.get_me()
    print(f"\n🎉 SUCCESS! Logged in as: {me.first_name} (ID: {me.id})")
    print(f"📁 Session successfully saved: {session_path}.session")
    print("⚡ Jab aap `python gemini_claimer.py` run karenge, ye account automatically parallel worker ki tarah kaam karega!")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(add_worker())
