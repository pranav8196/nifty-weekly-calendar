import os
import time
import requests
from datetime import datetime, date, time as dtime, timezone, timedelta

# -------------------------------------------------------------------
# TIMEZONE (IST)
# -------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))

# -------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------
IV_SPREAD_THRESHOLD = 20.0  # percent; alert when |spread| >= this

# Pairs: (left_W_index, right_W_index) — left is far, right is near
# Formula: (left_iv - right_iv) / right_iv * 100
# All 10 pairs in defined order: W2W1 W3W1 W3W2 W4W2 W4W3 W4W1 W5W1 W5W2 W5W3 W5W4
PAIRS = [
    (2, 1),
    (3, 1),
    (3, 2),
    (4, 2),
    (4, 3),
    (4, 1),
    (5, 1),
    (5, 2),
    (5, 3),
    (5, 4),
]

CHECK_SLOTS = [dtime(9, 30), dtime(10, 0), dtime(10, 30), dtime(11, 0)]

# ---------- NSE Weekly Expiries (hardcoded fallback) ----------
WEEKLY_EXPIRIES = [
    "10-Mar-2026", "17-Mar-2026", "24-Mar-2026", "30-Mar-2026",
    "07-Apr-2026", "13-Apr-2026", "21-Apr-2026", "28-Apr-2026",
    "05-May-2026", "12-May-2026", "19-May-2026", "26-May-2026",
    "02-Jun-2026", "09-Jun-2026", "16-Jun-2026", "23-Jun-2026",
    "30-Jun-2026", "07-Jul-2026", "14-Jul-2026", "21-Jul-2026",
    "28-Jul-2026", "04-Aug-2026", "11-Aug-2026", "18-Aug-2026",
    "25-Aug-2026", "01-Sep-2026", "08-Sep-2026", "15-Sep-2026",
    "22-Sep-2026", "29-Sep-2026", "06-Oct-2026", "13-Oct-2026",
    "19-Oct-2026", "27-Oct-2026", "03-Nov-2026", "09-Nov-2026",
    "17-Nov-2026", "23-Nov-2026", "01-Dec-2026", "08-Dec-2026",
    "15-Dec-2026", "22-Dec-2026", "29-Dec-2026",
]

# ---------- NSE Market Holidays 2026 ----------
MARKET_HOLIDAYS = {
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}

# ---------- Telegram ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------- NSE ----------
NSE_BASE_URL = "https://www.nseindia.com/api/option-chain-v3"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
    "Origin": "https://www.nseindia.com",
}

_session = None


# -------------------------------------------------------------------
# SESSION FACTORY
# -------------------------------------------------------------------

def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


# -------------------------------------------------------------------
# TELEGRAM
# -------------------------------------------------------------------

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram] Not configured — skipping. Message:\n{message}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        resp = requests.post(url, json=payload, timeout=10)
        print(f"[Telegram] Status: {resp.status_code}")
    except Exception as e:
        print(f"[Telegram] Error: {e}")


# -------------------------------------------------------------------
# NSE API
# -------------------------------------------------------------------

def fetch_option_chain(expiry_str: str | None = None) -> dict | None:
    """Fetch NSE option chain. If expiry_str given, fetch per-expiry data."""
    session = get_session()
    url = f"{NSE_BASE_URL}?type=Indices&symbol=NIFTY"
    if expiry_str:
        url += f"&expiry={expiry_str}"

    for attempt in range(3):
        try:
            warmup = session.get("https://www.nseindia.com", timeout=5)
            print(f"  Warmup: {warmup.status_code}")
            resp = session.get(url, timeout=10)
            print(f"  NSE [{expiry_str or 'base'}]: {resp.status_code} (attempt {attempt + 1})")
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or not data:
                print(f"  NSE returned empty JSON for expiry={expiry_str}")
                return None
            return data
        except Exception as e:
            print(f"  Error fetching chain (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                print("  Retrying in 5s...")
                time.sleep(5)
    return None


def get_expiry_list(data: dict) -> list[date]:
    """Parse records.expiryDates → sorted list of date objects."""
    raw = data.get("records", {}).get("expiryDates", [])
    dates = []
    for s in raw:
        try:
            dates.append(datetime.strptime(s, "%d-%b-%Y").date())
        except Exception:
            continue
    return sorted(dates)


def get_expiry_dates_from_hardcoded(today: date) -> list[date]:
    """Return hardcoded expiry dates on or after today, as sorted date objects."""
    dates = []
    for s in WEEKLY_EXPIRIES:
        try:
            d = datetime.strptime(s, "%d-%b-%Y").date()
            if d >= today:
                dates.append(d)
        except Exception:
            continue
    return sorted(dates)


def get_spot_price(data: dict) -> float | None:
    return data.get("records", {}).get("underlyingValue")


# -------------------------------------------------------------------
# W-CYCLE LOGIC
# -------------------------------------------------------------------

def get_reference_tuesday(today: date) -> date:
    """
    Return the reference Tuesday for W-cycle calculation:
      Mon (wd=0): today + 1
      Tue (wd=1): today
      Wed (wd=2): today + 6
      Thu (wd=3): today + 5
      Fri (wd=4): today + 4
    """
    wd = today.weekday()
    if wd == 0:
        return today + timedelta(days=1)
    elif wd == 1:
        return today
    elif wd == 2:
        return today + timedelta(days=6)
    elif wd == 3:
        return today + timedelta(days=5)
    else:  # Friday
        return today + timedelta(days=4)


def get_w_expiries(today: date, expiry_dates: list[date]) -> dict[int, date]:
    """
    Returns {1: W1_date, 2: W2_date, ..., 5: W5_date} from NSE expiry list.
    W1 = first NSE expiry >= reference_tuesday + 7
    W2–W5 = next 4 consecutive expiries.
    """
    ref_tue = get_reference_tuesday(today)
    cutoff = ref_tue + timedelta(days=7)

    future = [d for d in expiry_dates if d >= cutoff]
    w_map = {}
    for i, d in enumerate(future[:5], start=1):
        w_map[i] = d
    return w_map


# -------------------------------------------------------------------
# ATM & PE IV
# -------------------------------------------------------------------

def find_atm_strike(spot: float, strikes: list[int]) -> int:
    return min(strikes, key=lambda s: abs(s - spot))


def get_pe_iv_at_atm(expiry_str: str, spot: float) -> float | None:
    """
    Fetch per-expiry chain, find ATM, return PE IV.
    Fallback order: ATM±50, ATM±100, then CE IV at ATM.
    Returns None if all fallbacks fail.
    """
    data = fetch_option_chain(expiry_str)
    if data is None:
        print(f"  [{expiry_str}] Failed to fetch chain.")
        return None

    records_data = data.get("records", {}).get("data", [])
    if not records_data:
        print(f"  [{expiry_str}] Empty records.data.")
        return None

    # Build {strike: {CE: iv, PE: iv}} map
    iv_map: dict[int, dict[str, float]] = {}
    for item in records_data:
        strike = item.get("strikePrice")
        if strike is None:
            continue
        iv_map.setdefault(strike, {})
        ce = item.get("CE")
        pe = item.get("PE")
        if ce and ce.get("impliedVolatility"):
            iv_map[strike]["CE"] = float(ce["impliedVolatility"])
        if pe and pe.get("impliedVolatility"):
            iv_map[strike]["PE"] = float(pe["impliedVolatility"])

    all_strikes = sorted(iv_map.keys())
    if not all_strikes:
        print(f"  [{expiry_str}] No strikes in IV map.")
        return None

    atm = find_atm_strike(spot, all_strikes)
    print(f"  [{expiry_str}] Spot={spot}, ATM={atm}")

    # Try ATM, ATM±50, ATM±100 for PE IV
    for offset in (0, 50, -50, 100, -100):
        candidate = atm + offset
        pe_iv = iv_map.get(candidate, {}).get("PE")
        if pe_iv and pe_iv > 0:
            print(f"  [{expiry_str}] PE IV at {candidate} (offset {offset}): {pe_iv}")
            return pe_iv

    # Final fallback: CE IV at ATM
    ce_iv = iv_map.get(atm, {}).get("CE")
    if ce_iv and ce_iv > 0:
        print(f"  [{expiry_str}] PE IV unavailable; using CE IV fallback at ATM {atm}: {ce_iv}")
        return ce_iv

    print(f"  [{expiry_str}] No usable IV found.")
    return None


# -------------------------------------------------------------------
# SPREAD COMPUTATION & ALERT LOGIC
# -------------------------------------------------------------------

def compute_spread_pct(left_iv: float, right_iv: float) -> float:
    """(left_iv - right_iv) / right_iv * 100"""
    return (left_iv - right_iv) / right_iv * 100.0


def expiry_label(d: date) -> str:
    return d.strftime("%-d-%b")  # e.g. "17-Mar"


def check_all_pairs(
    iv_map: dict[int, float],
    w_map: dict[int, date],
    spot: float,
    atm: int,
    slot_label: str,
) -> str | None:
    """
    Check all 10 pairs. Return consolidated Telegram message if any qualify, else None.
    """
    now_ist = datetime.now(IST)
    spot_fmt = f"{spot:,.0f}"
    atm_fmt = str(atm)

    lines = [
        f"*NIFTY Calendar Strategy — IV Spread Alert | {slot_label} IST*",
        f"Spot: {spot_fmt} | ATM: {atm_fmt}",
        "",
    ]

    any_alert = False

    for left_w, right_w in PAIRS:
        if left_w not in w_map or right_w not in w_map:
            print(f"  Pair W{left_w}/W{right_w}: missing expiry, skipping.")
            continue
        if left_w not in iv_map or right_w not in iv_map:
            print(f"  Pair W{left_w}/W{right_w}: missing IV, skipping.")
            continue

        left_iv = iv_map[left_w]
        right_iv = iv_map[right_w]

        if right_iv <= 0:
            print(f"  Pair W{left_w}/W{right_w}: right_iv={right_iv} <= 0, skipping.")
            continue

        spread = compute_spread_pct(left_iv, right_iv)
        left_date = w_map[left_w]
        right_date = w_map[right_w]
        left_label = expiry_label(left_date)
        right_label = expiry_label(right_date)

        print(
            f"  W{left_w}({left_label}) IV={left_iv:.2f}% vs "
            f"W{right_w}({right_label}) IV={right_iv:.2f}% → spread={spread:+.1f}%"
        )

        if spread >= IV_SPREAD_THRESHOLD:
            any_alert = True
            lines.append(
                f"W{left_w} ({left_label}) IV is {spread:.1f}% higher than W{right_w} ({right_label})"
            )
            lines.append(f"Long Calendar: Long W{left_w}, Short W{right_w}")
            lines.append("")
        elif spread <= -IV_SPREAD_THRESHOLD:
            any_alert = True
            abs_spread = abs(spread)
            lines.append(
                f"W{left_w} ({left_label}) IV is -{abs_spread:.1f}% lower than W{right_w} ({right_label})"
            )
            lines.append(f"Short Calendar: Short W{left_w}, Long W{right_w}")
            lines.append("")

    if not any_alert:
        return None

    # Remove trailing blank line
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# -------------------------------------------------------------------
# SLOT ORCHESTRATION
# -------------------------------------------------------------------

def collect_ivs_for_slot(today: date) -> tuple[dict[int, float], dict[int, date], float | None, int | None]:
    """
    Fetch base chain to get expiries + spot, then fetch per-expiry IV for W1–W5.
    Returns (iv_map, w_map, spot, atm).
    """
    print(f"\n[collect_ivs] Fetching base chain...")
    base_data = fetch_option_chain()

    expiry_dates = get_expiry_list(base_data) if base_data else []
    spot = get_spot_price(base_data) if base_data else None

    if not expiry_dates:
        print("[collect_ivs] No expiry dates from base chain — using hardcoded list.")
        expiry_dates = get_expiry_dates_from_hardcoded(today)

    print(f"[collect_ivs] Expiries ({len(expiry_dates)}): {expiry_dates[:6]}")
    print(f"[collect_ivs] Spot: {spot}")

    if not expiry_dates:
        print("[collect_ivs] No expiry dates available.")
        return {}, {}, None, None

    w_map = get_w_expiries(today, expiry_dates)
    print(f"[collect_ivs] W-map: { {k: v.isoformat() for k, v in w_map.items()} }")

    if not w_map:
        print("[collect_ivs] No W expiries found.")
        return {}, {}, spot, None

    # If base chain failed to give spot, fetch it from the nearest W expiry
    if spot is None:
        for w_idx in sorted(w_map.keys()):
            fallback_exp = w_map[w_idx].strftime("%d-%b-%Y")
            print(f"[collect_ivs] Fetching spot from W{w_idx} chain ({fallback_exp})...")
            fallback_data = fetch_option_chain(fallback_exp)
            if fallback_data:
                spot = get_spot_price(fallback_data)
                if spot:
                    print(f"[collect_ivs] Got spot={spot} from W{w_idx} chain.")
                    break
            time.sleep(1.5)

    if spot is None:
        print("[collect_ivs] Could not determine spot price.")
        return {}, {}, None, None

    # Compute ATM from base chain (for display only)
    atm = None
    if base_data:
        all_strikes_base = sorted(set(
            item["strikePrice"]
            for item in base_data.get("records", {}).get("data", [])
            if "strikePrice" in item
        ))
        atm = find_atm_strike(spot, all_strikes_base) if all_strikes_base else None

    # Fetch per-expiry IV
    iv_map: dict[int, float] = {}
    for w_idx, exp_date in sorted(w_map.items()):
        exp_str = exp_date.strftime("%d-%b-%Y")
        print(f"\n[collect_ivs] Fetching IV for W{w_idx} ({exp_str})...")
        iv = get_pe_iv_at_atm(exp_str, spot)
        if iv is not None:
            iv_map[w_idx] = iv
        time.sleep(1.5)  # rate limiting between expiry calls

    print(f"\n[collect_ivs] IV map: { {f'W{k}': f'{v:.2f}%' for k, v in iv_map.items()} }")
    return iv_map, w_map, spot, atm


# -------------------------------------------------------------------
# TIMING
# -------------------------------------------------------------------

def seconds_until(target: dtime) -> float:
    """Seconds until target IST time. Returns 0 if already past."""
    now = datetime.now(IST)
    target_dt = datetime.combine(now.date(), target, tzinfo=IST)
    diff = (target_dt - now).total_seconds()
    return max(0.0, diff)


# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------

def main():
    now_ist = datetime.now(IST)
    today = now_ist.date()
    today_str = today.isoformat()

    print(f"=== NIFTY IV Monitor Starting | {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST ===")

    # Holiday check
    holiday_name = MARKET_HOLIDAYS.get(today_str)
    if holiday_name:
        msg = (
            f"*NIFTY Calendar Strategy — Market Holiday*\n"
            f"Date    : {today_str}\n"
            f"Holiday : {holiday_name}\n"
            f"NSE is closed today. No monitoring."
        )
        send_telegram(msg)
        print(f"Market holiday: {holiday_name}. Exiting.")
        return

    # Startup ping
    slots_str = ", ".join(s.strftime("%H:%M") for s in CHECK_SLOTS)
    send_telegram(
        f"*NIFTY Calendar Strategy — IV Monitor Starting*\n"
        f"Date: {today_str} | Time: {now_ist.strftime('%H:%M')} IST\n"
        f"Slots: {slots_str} IST"
    )

    # Run each slot
    for slot in CHECK_SLOTS:
        wait = seconds_until(slot)
        slot_label = slot.strftime("%H:%M")
        if wait > 0:
            print(f"\n[main] Sleeping {wait:.0f}s until {slot_label} IST slot...")
            time.sleep(wait)
        else:
            print(f"\n[main] Already past {slot_label} — running immediately.")

        print(f"\n[main] === Slot {slot_label} IST ===")
        now_ist = datetime.now(IST)

        iv_map, w_map, spot, atm = collect_ivs_for_slot(today)

        if not iv_map or spot is None:
            err_msg = f"*NIFTY Calendar Strategy — Slot {slot_label}*\nData fetch failed. Check NSE connectivity."
            send_telegram(err_msg)
            print(f"[main] Slot {slot_label}: data fetch failed, sent error message.")
            continue

        msg = check_all_pairs(iv_map, w_map, spot, atm, slot_label)
        if msg:
            send_telegram(msg)
            print(f"[main] Slot {slot_label}: alert sent.")
        else:
            print(f"[main] Slot {slot_label}: no pairs crossed threshold — silence.")

    # Session complete
    send_telegram(
        f"*NIFTY Calendar Strategy — Session Complete*\n"
        f"Date: {today_str} | All {len(CHECK_SLOTS)} slots checked."
    )
    print("=== Session complete ===")


if __name__ == "__main__":
    main()
