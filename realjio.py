import sys
import os
import requests
import re
from urllib.parse import urljoin
from typing import Optional, Tuple, Set, Dict, Any


def clean_phone_number(number: str) -> str:
    clean_number = "".join(filter(str.isdigit, str(number)))

    if len(clean_number) > 10 and clean_number.startswith("91"):
        clean_number = clean_number[-10:]

    return clean_number


def check_jio_number(number: str) -> bool:
    clean_num = clean_phone_number(number)
    if len(clean_num) != 10 or not re.match(r'^[6-9]\d{9}$', clean_num):
        return False

    url = (
        "https://www.jio.com/api/jio-recharge-service/"
        f"recharge/mobility/number/{clean_num}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.jio.com/"
    }

    try:
        res = requests.get(url, headers=headers, timeout=5)

        if res.status_code == 200:
            return True
        elif res.status_code in {429, 403}:
            # Rate limited or CAPTCHA required on recharge-service; fail open so sendOtp validates
            return True
        else:
            try:
                err = res.json()
                err_msg = err.get("errorMessage") or ""
                if err_msg in {"NOT_SUBSCRIBED_USER", "INVALID_JIONUMBER_ERROR"}:
                    return False
                if "CAPTCHA" in err_msg.upper():
                    return True
            except Exception:
                pass
            return True

    except Exception:
        return True


def looks_like_claim_link(url: str) -> bool:
    """
    Accept ONLY authentic Google Gemini activation and subscription URLs.
    Never accept internal Next.js assets, CSS class names, or Jio portal pages.
    """
    if not url or not isinstance(url, str):
        return False

    value = url.strip()
    lower_val = value.lower()

    # Must be a valid HTTP/HTTPS URL
    if not (lower_val.startswith("http://") or lower_val.startswith("https://")):
        return False

    # Block any static assets, webpack chunks, scripts, stylesheets, images, CSS class names
    blocked_patterns = (
        "_next", "static/chunks", ".js", ".css", ".png", ".svg", ".json",
        ".jpg", ".jpeg", ".woff", ".map", "activatebtn", "landing_",
        "selfcare/googleai", "selfcare/login", "retailer-portal", "jiocommon"
    )
    if any(bp in lower_val for bp in blocked_patterns):
        return False

    # 1. Primary authentic Google activation endpoints
    if "serviceactivation.google.com" in lower_val or "google.com/subscription" in lower_val:
        return True

    # 2. Direct OTT redirection URLs returned by Jio that lead to Gemini activation
    if "tiny.jio.com" in lower_val and any(x in lower_val for x in ("gemini", "googleai", "google", "activation")):
        return True

    return False


def find_direct_gemini_claim_link(session: requests.Session, first_response=None) -> Optional[str]:
    """
    Fallback scanner: searches through authenticated session pages and redirects
    for genuine Google Gemini activation links (serviceactivation.google.com).
    """
    candidates = set()

    # 1. Check redirect history of first response
    if first_response is not None:
        if looks_like_claim_link(first_response.url):
            return first_response.url
        for item in first_response.history:
            location = item.headers.get("Location")
            if location and looks_like_claim_link(location):
                return location

    # 2. Scan Google AI selfcare page for explicit Google activation URLs
    try:
        google_ai = session.get(
            "https://www.jio.com/selfcare/googleai/",
            timeout=15,
            allow_redirects=True,
        )
        if google_ai.status_code == 200:
            if looks_like_claim_link(google_ai.url):
                return google_ai.url
            
            # Find full explicit Google activation URLs in page HTML
            found_urls = re.findall(
                r'https?://(?:serviceactivation\.google\.com|www\.google\.com/subscription|google\.com/subscription)[^\s"\'<>]+',
                google_ai.text,
                re.I
            )
            for u in found_urls:
                clean_u = u.replace("\\/", "/").rstrip('",\';\\')
                if looks_like_claim_link(clean_u):
                    candidates.add(clean_u)
    except requests.RequestException:
        pass

    # 3. Check tiny.jio.com redirects
    for landing_url in ("https://tiny.jio.com/loginrecharge", "https://tiny.jio.com/loginirecharge"):
        try:
            page = session.get(landing_url, timeout=12, allow_redirects=True)
            if looks_like_claim_link(page.url):
                return page.url
            found_urls = re.findall(
                r'https?://(?:serviceactivation\.google\.com|www\.google\.com/subscription|google\.com/subscription)[^\s"\'<>]+',
                page.text,
                re.I
            )
            for u in found_urls:
                clean_u = u.replace("\\/", "/").rstrip('",\';\\')
                if looks_like_claim_link(clean_u):
                    candidates.add(clean_u)
        except Exception:
            pass

    for match in candidates:
        if looks_like_claim_link(match):
            return match

    return None


class JioDirectClaimer:
    """
    Direct in-house Jio API client for:
    1. Validating Jio numbers
    2. Sending OTPs
    3. Validating OTPs
    4. Fetching Google Gemini activation URLs directly from Jio's OTT service APIs.
    """

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.jio.com",
        "Referer": "https://www.jio.com/selfcare/login/",
    }

    def __init__(self, phone: str):
        self.phone = clean_phone_number(phone)
        self.session = requests.Session()
        self.session.headers.update(self.BASE_HEADERS)
        self.is_logged_in = False

    def is_valid_jio(self) -> bool:
        return check_jio_number(self.phone)

    def send_otp(self) -> Tuple[bool, str]:
        """Sends OTP to the mobile number via Jio's login API."""
        url = "https://www.jio.com/api/jio-login-service/login/sendOtp"
        payload = {
            "mobileNumber": self.phone,
            "loginFlowType": "MOBILE",
            "alternateNumber": ""
        }

        try:
            res = self.session.post(url, json=payload, timeout=12)
            if res.status_code == 200:
                return True, "OTP sent successfully"
            
            err_msg = "Failed to send OTP"
            try:
                data = res.json()
                err_msg = data.get("errorMessage") or str(data)
            except Exception:
                err_msg = res.text[:200]
            
            if res.status_code == 429 or "CAPTCHA" in err_msg.upper():
                return False, "CAPTCHA_REQUIRED"
            if "SEND_OTP_CURRENTLY_LOCKED" in err_msg:
                return True, "SEND_OTP_CURRENTLY_LOCKED"
            if any(k in err_msg for k in ["INVALID_JIONUMBER", "NOT_SUBSCRIBED"]):
                return False, "INVALID_JIONUMBER"
            
            return False, err_msg
        except Exception as e:
            return False, f"Network error sending OTP: {e}"

    def validate_otp(self, otp: str) -> Tuple[bool, str]:
        """Validates OTP code with Jio login service."""
        clean_otp = str(otp).strip()
        url = "https://www.jio.com/api/jio-login-service/login/validateOtp"
        payload = {"otp": clean_otp}

        try:
            res = self.session.post(url, json=payload, timeout=12)
            if res.status_code == 200:
                self.is_logged_in = True
                return True, "OTP validated successfully"
            
            err_msg = "OTP validation failed"
            try:
                data = res.json()
                err_msg = data.get("errorMessage") or str(data)
            except Exception:
                err_msg = res.text[:200]

            return False, err_msg
        except Exception as e:
            return False, f"Network error validating OTP: {e}"

    def claim_gemini(self) -> Tuple[str, Optional[str], str]:
        """
        Directly claims Google Gemini activation link using Jio's OTT endpoints:
        - Checks /api/jio-ott-service/ott/subscription/activate/Z0241
        - Requests /api/jio-ott-service/ott/subscription/google-ai
        - Submits /api/jio-ott-service/ott/subscription/submit
        - Fallback scans authenticated pages if required.

        Returns: (status, link, details)
          - ('SUCCESS', link, message)
          - ('ALREADY_USED', None, message)
          - ('NO_OFFER', None, message)
          - ('ERROR', None, message)
        """
        if not self.is_logged_in:
            return "ERROR", None, "Session is not authenticated"

        ott_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.jio.com",
            "Referer": "https://www.jio.com/selfcare/googleai/",
        }

        already_claimed = False

        # 1. Check activation status / eligibility
        try:
            check_res = self.session.get(
                "https://www.jio.com/api/jio-ott-service/ott/subscription/activate/Z0241",
                headers=ott_headers,
                timeout=15
            )
            if check_res.status_code == 200:
                try:
                    c_data = check_res.json()
                    err = c_data.get("errorMessage") or ""
                    if err == "GOOGLE_AI_SUBSCRIPTION_ALREADY_EXISTS":
                        already_claimed = True
                except Exception:
                    pass
        except Exception as e:
            pass

        # 2. Directly request Google AI claim link
        try:
            claim_res = self.session.get(
                "https://www.jio.com/api/jio-ott-service/ott/subscription/google-ai",
                headers=ott_headers,
                timeout=15
            )
            if claim_res.status_code == 200:
                try:
                    data = claim_res.json()
                    redirect_url = data.get("redirectionURL") or data.get("redirectUrl") or data.get("url")
                    if redirect_url and looks_like_claim_link(redirect_url):
                        # Submit claim confirmation
                        try:
                            self.session.get(
                                "https://www.jio.com/api/jio-ott-service/ott/subscription/submit",
                                headers=ott_headers,
                                timeout=10
                            )
                        except Exception:
                            pass
                        status_label = "ALREADY_CLAIMED" if already_claimed else "SUCCESS"
                        return status_label, redirect_url, "Direct OTT API claimed successfully"
                except Exception:
                    pass
            elif claim_res.status_code == 400:
                try:
                    err_json = claim_res.json()
                    err_msg = err_json.get("errorMessage", "")
                    if "already" in err_msg.lower():
                        already_claimed = True
                except Exception:
                    pass
        except Exception as e:
            pass

        # 3. Authenticated session navigation fallback
        response_for_scan = None
        for landing_url in ("https://www.jio.com/selfcare/googleai/", "https://tiny.jio.com/loginrecharge", "https://tiny.jio.com/loginirecharge"):
            try:
                page = self.session.get(landing_url, timeout=15, allow_redirects=True)
                if page.status_code == 200:
                    response_for_scan = page
                    break
            except Exception:
                pass

        direct_link = find_direct_gemini_claim_link(self.session, response_for_scan)
        if direct_link:
            status_label = "ALREADY_CLAIMED" if already_claimed else "SUCCESS"
            return status_label, direct_link, "Claim link captured via authenticated portal scan"

        if already_claimed:
            return "ALREADY_CLAIMED", None, "Google AI subscription already claimed / exists"

        return "NO_OFFER", None, "No active Google AI entitlement found on this Jio account"


def get_valid_jio_number():
    while True:
        try:
            phone_number = input("\nEnter your Jio mobile number (or q to quit): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return None

        if phone_number.lower() in {"q", "quit", "exit"}:
            return None

        clean_num = clean_phone_number(phone_number)

        if len(clean_num) != 10:
            print(f"[-] '{phone_number}' is not a valid 10-digit Indian number.")
            continue

        if not check_jio_number(clean_num):
            print(f"[-] {clean_num} is not a registered Jio number.")
            print("[*] Enter another number; no restart is needed.")
            continue

        return clean_num


def print_request_diagnostics(res, session):
    print("\n" + "=" * 60)
    print("REQUEST DIAGNOSTICS")
    print("=" * 60)
    print("\n[FINAL URL]")
    print(res.url)

    print("\n[REDIRECT HISTORY]")
    if not res.history:
        print("No redirects.")
    else:
        for index, redirect in enumerate(res.history, 1):
            print(f"{index}. {redirect.status_code} {redirect.url}")
            location = redirect.headers.get("Location")
            if location:
                print(f"   -> {location}")

    print("\n[RESPONSE INFO]")
    print("Status:", res.status_code)
    print("Content-Type:", res.headers.get("Content-Type"))

    print("\n[SESSION COOKIES]")
    if not session.cookies:
        print("No cookies stored.")
    else:
        for cookie in session.cookies:
            value = cookie.value
            safe_value = value[:6] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"{cookie.name}={safe_value} | domain={cookie.domain}")

    print("=" * 60)


def main():
    queued_number = sys.argv[1] if len(sys.argv) > 1 else None

    while True:
        if queued_number is not None:
            clean_num = clean_phone_number(queued_number)
            queued_number = None
            if len(clean_num) != 10 or not check_jio_number(clean_num):
                print("[-] Supplied number is invalid/not registered with Jio.")
                clean_num = get_valid_jio_number()
        else:
            clean_num = get_valid_jio_number()

        if clean_num is None:
            return

        print(f"\n[+] Processing Jio number: {clean_num}")
        claimer = JioDirectClaimer(clean_num)

        print("[*] Sending OTP via Jio Official Login API...")
        ok, msg = claimer.send_otp()
        if not ok:
            print(f"[-] Failed to send OTP: {msg}")
            print("[*] Try another number.")
            continue

        print("[+] OTP sent successfully to mobile!")

        try:
            otp = input("\nPlease enter the OTP sent to your phone: ").strip()
        except (KeyboardInterrupt, EOFError):
            return

        print("\n[*] Verifying OTP via Jio API...")
        ok, msg = claimer.validate_otp(otp)
        if not ok:
            print(f"[-] Verification failed: {msg}")
            print("[*] Try another number.")
            continue

        print("[+] OTP verified successfully! Logged in to Jio Selfcare.")
        print("[*] Claiming Google Gemini offer directly from Jio OTT Service...")

        status, link, details = claimer.claim_gemini()

        print("\n" + "=" * 60)
        print("CLAIM RESULT")
        print("=" * 60)
        print(f"Status:  {status}")
        print(f"Details: {details}")
        if status == "SUCCESS" and link:
            print(f"\n🎉 GEMINI ACTIVATION LINK:\n{link}\n")
        elif status == "ALREADY_USED":
            print("\n⚠️ This number's Google AI subscription is ALREADY CLAIMED.")
        elif status == "NO_OFFER":
            print("\nℹ️ This number is not eligible or has no Google AI offer.")
        print("=" * 60)

        again = input("\nTry another Jio number? [Y/n]: ").strip().lower()
        if again in {"n", "no"}:
            return


if __name__ == "__main__":
    if os.name == "nt":
        os.system("color")
    main()