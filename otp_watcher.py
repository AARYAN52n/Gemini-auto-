import re
import time
import asyncio
import requests
from typing import Optional, Tuple, Set, List, Dict, Union, Any

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def extract_msg_timestamp(k: Optional[str], val: Any) -> Optional[int]:
    """
    Extracts timestamp in milliseconds from Firebase key or message value.
    """
    if isinstance(val, dict):
        for field in ['id', 'timestamp', 'time', 'rawTs', 'time_ms', 'date', 'created_at']:
            v = val.get(field)
            if isinstance(v, (int, float)) and v > 0:
                if v < 1e11:  # seconds to ms
                    return int(v * 1000)
                return int(v)
            elif isinstance(v, str) and v.isdigit():
                iv = int(v)
                if iv < 1e11:
                    return iv * 1000
                return iv

    if k and str(k).isdigit() and len(str(k)) >= 10:
        iv = int(str(k))
        if iv < 1e11:
            return iv * 1000
        return iv

    return None


def extract_otp_from_text(text: str, sender: Optional[str] = None) -> Optional[str]:
    """
    Extracts a 4-6 digit OTP from incoming SMS text or raw field values.
    Handles MyJio, JioHotstar, JioFiber, and general OTP formats.
    """
    if not text:
        return None
    
    clean_stripped = str(text).strip()
    
    # Priority 0: Pure digits (e.g. from direct /otps/{phone} nodes or raw OTP values)
    if clean_stripped.isdigit() and len(clean_stripped) in (4, 5, 6):
        return clean_stripped
    
    clean_text = clean_stripped.replace('\r', ' ').replace('\n', ' ')
    
    # Priority 1: Exact matches like "420758 is your one time password (OTP)"
    m = re.search(r'\b(\d{4,6})\b\s*is your (?:one time password|otp|verification code|code|login otp)', clean_text, re.IGNORECASE)
    if m:
        return m.group(1)

    # Priority 2: "<#> 4342 is your JioHotstar verification code"
    m = re.search(r'<\#>?\s*(\d{4,6})\s*is your', clean_text, re.IGNORECASE)
    if m:
        return m.group(1)

    # Priority 3: "OTP is 123456", "verification code: 123456", "OTP: 123456", "login is 4482"
    m = re.search(r'(?:otp|code|verification code|password|login)\s*(?:is|:|-|=|\s)\s*(\d{4,6})\b', clean_text, re.IGNORECASE)
    if m:
        return m.group(1)

    # Priority 4: "Use 123456 as your OTP" or "Enter 123456 to verify"
    m = re.search(r'(?:use|enter|share)\s*(?:the\s*)?(?:code|otp)?\s*(\d{4,6})\s*as your (?:otp|code|verification)', clean_text, re.IGNORECASE)
    if m:
        return m.group(1)

    # Priority 5: Order completion code / verification code (e.g. "code 701567")
    m = re.search(r'code\s+(\d{4,6})\b', clean_text, re.IGNORECASE)
    if m:
        return m.group(1)

    # Priority 6: "\b\d{4,6}\b is the OTP"
    m = re.search(r'\b(\d{4,6})\b\s*(?:is the otp|is the verification code)', clean_text, re.IGNORECASE)
    if m:
        return m.group(1)

    # Priority 7: If message or sender clearly mentions OTP / Jio / verification / login
    lower = clean_text.lower()
    sender_lower = (sender or '').lower()

    # Guard: Helper to check if a number is just a currency, storage (GB/MB), or validity (days)
    def is_false_positive_number(num_str: str) -> bool:
        # Check units following the number: e.g. 5000 GB, 20 GB, 899 plan, 90 days, 400 rewards
        if re.search(r'\b' + re.escape(num_str) + r'\s*(?:gb|mb|tb|kb|rs|inr|/-|days|day|min|mins|sms|plan|rewards|points|validity)\b', clean_text, re.IGNORECASE):
            return True
        # Check currency preceding the number: e.g. Rs. 5000, INR 899
        if re.search(r'(?:rs|inr|bal|balance|recharge|plan)\.?\s*' + re.escape(num_str) + r'\b', clean_text, re.IGNORECASE):
            return True
        return False

    has_otp_keyword = any(k in lower for k in ['otp', 'verification', 'verify', 'one time password', 'login', 'code', 'pin'])
    if has_otp_keyword or any(k in sender_lower for k in ['jio', '6200', 'airtel', 'vi', 'otp']):
        # Find 6 digit numbers first (most common for Jio OTPs)
        all_6 = re.findall(r'\b\d{6}\b', clean_text)
        for num in all_6:
            if not num.startswith(('19', '20', '000')) and not is_false_positive_number(num):
                return num
        
        # Only accept 4-digit numbers if the message explicitly contains OTP/verification/login keywords
        if has_otp_keyword:
            all_4 = re.findall(r'\b\d{4}\b', clean_text)
            for num in all_4:
                if not num.startswith(('19', '20', '00')) and not is_false_positive_number(num):
                    return num

    return None


def extract_otp_from_node_value(val) -> Optional[Tuple[str, str]]:
    """
    Extracts (otp_code, message_summary) from an arbitrary Firebase node value
    (dict, string, or number).
    """
    if val is None:
        return None

    # Check direct number/string
    if isinstance(val, (int, str)):
        s_val = str(val).strip()
        otp = extract_otp_from_text(s_val)
        if otp:
            return otp, s_val
        return None

    if isinstance(val, dict):
        # 1. Direct explicit fields
        for field in ['otp', 'code', 'verificationCode', 'otpCode', 'passcode']:
            if field in val and val[field] is not None:
                f_str = str(val[field]).strip()
                if f_str.isdigit() and len(f_str) in (4, 5, 6):
                    return f_str, str(val)

        # 2. Text message fields
        msg_text = (
            val.get('message') or val.get('msg') or val.get('messageText') or 
            val.get('body') or val.get('text') or val.get('smsBody') or 
            val.get('msg_body') or val.get('content')
        )
        sender = (
            val.get('sender') or val.get('from') or val.get('address') or 
            val.get('sender_number') or val.get('originatingAddress')
        )

        if msg_text:
            otp = extract_otp_from_text(str(msg_text), str(sender) if sender else None)
            if otp:
                return otp, str(msg_text)

    return None


class OTPWatcher:
    def __init__(self, base_url: str, sms_paths: Union[str, List[str]], timeout: int = 25):
        self.base_url = base_url.rstrip('/')
        if isinstance(sms_paths, str):
            raw_paths = [sms_paths]
        else:
            raw_paths = list(sms_paths)

        # Normalize and deduplicate paths
        seen = set()
        self.sms_paths = []
        for p in raw_paths:
            if not p:
                continue
            np = p if p.startswith('/') else f"/{p}"
            if np not in seen:
                seen.add(np)
                self.sms_paths.append(np)

        if not self.sms_paths:
            self.sms_paths = ["/receivedSms"]

        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_baseline(self) -> Tuple[Dict[str, Set[str]], int]:
        """
        Gets existing SMS keys and the current timestamp baseline across all paths.
        Returns (dict_of_path_to_keys, baseline_timestamp_ms).
        """
        now_ms = int(time.time() * 1000)
        baseline_keys: Dict[str, Set[str]] = {}
        max_ts = now_ms

        for path in self.sms_paths:
            existing_keys = set()
            try:
                r = self.session.get(f"{self.base_url}{path}.json?shallow=true", timeout=3)
                if r.status_code == 200 and isinstance(r.json(), dict):
                    existing_keys = set(r.json().keys())
                    for k in existing_keys:
                        ts = extract_msg_timestamp(k, None)
                        if ts and ts > max_ts:
                            max_ts = ts
            except Exception:
                pass
            baseline_keys[path] = existing_keys

        return baseline_keys, max_ts

    async def wait_for_otp(
        self,
        baseline_keys: Dict[str, Set[str]],
        baseline_ts: int,
        poll_interval: float = 0.8
    ) -> Optional[Tuple[str, str]]:
        """
        Asynchronously polls candidate SMS paths in Firebase RTDB.
        ONLY inspects genuine newly arrived keys (keys not in baseline_keys).
        Returns (otp_code, sms_body) if a fresh OTP arrives within self.timeout seconds, else None.
        """
        start_time = time.time()

        while time.time() - start_time < self.timeout:
            await asyncio.sleep(poll_interval)

            for path in self.sms_paths:
                try:
                    r = await asyncio.to_thread(
                        self.session.get,
                        f"{self.base_url}{path}.json?shallow=true",
                        timeout=2.5
                    )
                    if r.status_code != 200:
                        continue

                    data = r.json()
                    if not data:
                        continue

                    # If data is a direct primitive (e.g. /otps/{phone} = "688397")
                    if isinstance(data, (int, str)):
                        res = extract_otp_from_node_value(data)
                        if res:
                            return res
                        continue

                    if not isinstance(data, dict):
                        continue

                    current_keys = set(data.keys())
                    known_keys = baseline_keys.get(path, set())
                    new_keys = current_keys - known_keys

                    # STRICT GUARD: If no new keys have arrived, keep waiting!
                    # Do NOT inspect old keys already present in the baseline.
                    if not new_keys:
                        continue

                    # Sort newly arrived keys descending (latest first)
                    candidate_keys = list(new_keys)
                    try:
                        candidate_keys.sort(key=lambda x: int(x) if x.isdigit() else x, reverse=True)
                    except Exception:
                        pass

                    # Inspect the fresh messages
                    for k in candidate_keys[:8]:
                        msg_r = await asyncio.to_thread(
                            self.session.get,
                            f"{self.base_url}{path}/{k}.json",
                            timeout=2.5
                        )
                        if msg_r.status_code == 200 and msg_r.json() is not None:
                            val = msg_r.json()

                            # Timestamp check: verify message is fresh (>= baseline_ts - 5000ms)
                            msg_ts = extract_msg_timestamp(k, val)
                            if msg_ts and msg_ts < (baseline_ts - 5000):
                                continue

                            res = extract_otp_from_node_value(val)
                            if res:
                                return res

                except Exception:
                    continue

        return None
