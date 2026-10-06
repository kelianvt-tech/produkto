from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

# US and Canada NPA area codes mapped to IANA timezone names.
# Default fallback is America/New_York (Eastern).
AREA_CODE_TIMEZONES: dict[str, str] = {
    # Eastern (America/New_York)
    "201": "America/New_York", "202": "America/New_York", "203": "America/New_York",
    "207": "America/New_York", "212": "America/New_York", "215": "America/New_York",
    "216": "America/New_York", "227": "America/New_York", "231": "America/New_York",
    "234": "America/New_York", "239": "America/New_York", "240": "America/New_York",
    "248": "America/New_York", "252": "America/New_York", "267": "America/New_York",
    "269": "America/New_York", "272": "America/New_York", "276": "America/New_York",
    "301": "America/New_York", "302": "America/New_York", "304": "America/New_York",
    "305": "America/New_York", "313": "America/New_York", "315": "America/New_York",
    "321": "America/New_York", "330": "America/New_York", "336": "America/New_York",
    "339": "America/New_York", "347": "America/New_York", "351": "America/New_York",
    "352": "America/New_York", "380": "America/New_York", "386": "America/New_York",
    "401": "America/New_York", "404": "America/New_York", "407": "America/New_York",
    "410": "America/New_York", "412": "America/New_York", "413": "America/New_York",
    "419": "America/New_York", "434": "America/New_York", "440": "America/New_York",
    "443": "America/New_York", "445": "America/New_York", "470": "America/New_York",
    "475": "America/New_York", "484": "America/New_York", "508": "America/New_York",
    "513": "America/New_York", "516": "America/New_York", "518": "America/New_York",
    "540": "America/New_York", "551": "America/New_York", "561": "America/New_York",
    "567": "America/New_York", "570": "America/New_York", "585": "America/New_York",
    "603": "America/New_York", "607": "America/New_York", "609": "America/New_York",
    "610": "America/New_York", "614": "America/New_York", "617": "America/New_York",
    "631": "America/New_York", "646": "America/New_York", "678": "America/New_York",
    "681": "America/New_York", "689": "America/New_York", "703": "America/New_York",
    "704": "America/New_York", "706": "America/New_York", "716": "America/New_York",
    "717": "America/New_York", "718": "America/New_York", "724": "America/New_York",
    "727": "America/New_York", "732": "America/New_York", "740": "America/New_York",
    "754": "America/New_York", "757": "America/New_York", "770": "America/New_York",
    "772": "America/New_York", "774": "America/New_York", "781": "America/New_York",
    "786": "America/New_York", "802": "America/New_York", "803": "America/New_York",
    "804": "America/New_York", "810": "America/New_York", "813": "America/New_York",
    "814": "America/New_York", "828": "America/New_York", "838": "America/New_York",
    "843": "America/New_York", "845": "America/New_York", "848": "America/New_York",
    "854": "America/New_York", "856": "America/New_York", "857": "America/New_York",
    "860": "America/New_York", "862": "America/New_York", "864": "America/New_York",
    "865": "America/New_York", "904": "America/New_York", "908": "America/New_York",
    "910": "America/New_York", "912": "America/New_York", "914": "America/New_York",
    "917": "America/New_York", "919": "America/New_York", "929": "America/New_York",
    "937": "America/New_York", "941": "America/New_York", "947": "America/New_York",
    "959": "America/New_York", "973": "America/New_York", "978": "America/New_York",
    "980": "America/New_York", "984": "America/New_York", "989": "America/New_York",

    # Central (America/Chicago)
    "205": "America/Chicago", "210": "America/Chicago", "214": "America/Chicago",
    "217": "America/Chicago", "218": "America/Chicago", "219": "America/Chicago",
    "224": "America/Chicago", "225": "America/Chicago", "228": "America/Chicago",
    "251": "America/Chicago", "256": "America/Chicago", "260": "America/Chicago",
    "262": "America/Chicago", "270": "America/Chicago", "281": "America/Chicago",
    "308": "America/Chicago", "309": "America/Chicago", "312": "America/Chicago",
    "314": "America/Chicago", "316": "America/Chicago", "318": "America/Chicago",
    "319": "America/Chicago", "320": "America/Chicago", "325": "America/Chicago",
    "331": "America/Chicago", "334": "America/Chicago", "337": "America/Chicago",
    "346": "America/Chicago", "361": "America/Chicago", "402": "America/Chicago",
    "405": "America/Chicago", "409": "America/Chicago", "414": "America/Chicago",
    "417": "America/Chicago", "430": "America/Chicago", "432": "America/Chicago",
    "469": "America/Chicago", "479": "America/Chicago", "501": "America/Chicago",
    "504": "America/Chicago", "507": "America/Chicago", "512": "America/Chicago",
    "515": "America/Chicago", "531": "America/Chicago", "534": "America/Chicago",
    "539": "America/Chicago", "563": "America/Chicago", "573": "America/Chicago",
    "601": "America/Chicago", "605": "America/Chicago", "608": "America/Chicago",
    "612": "America/Chicago", "615": "America/Chicago", "618": "America/Chicago",
    "620": "America/Chicago", "630": "America/Chicago", "636": "America/Chicago",
    "641": "America/Chicago", "651": "America/Chicago", "660": "America/Chicago",
    "662": "America/Chicago", "682": "America/Chicago", "701": "America/Chicago",
    "708": "America/Chicago", "712": "America/Chicago", "713": "America/Chicago",
    "715": "America/Chicago", "731": "America/Chicago", "737": "America/Chicago",
    "763": "America/Chicago", "765": "America/Chicago", "769": "America/Chicago",
    "773": "America/Chicago", "779": "America/Chicago", "806": "America/Chicago",
    "812": "America/Chicago", "815": "America/Chicago", "816": "America/Chicago",
    "817": "America/Chicago", "830": "America/Chicago", "832": "America/Chicago",
    "847": "America/Chicago", "850": "America/Chicago", "870": "America/Chicago",
    "901": "America/Chicago", "903": "America/Chicago", "913": "America/Chicago",
    "915": "America/Chicago", "918": "America/Chicago", "920": "America/Chicago",
    "931": "America/Chicago", "936": "America/Chicago", "940": "America/Chicago",
    "952": "America/Chicago", "956": "America/Chicago", "972": "America/Chicago",
    "979": "America/Chicago", "985": "America/Chicago",

    # Mountain (America/Denver)
    "208": "America/Denver", "303": "America/Denver", "307": "America/Denver",
    "385": "America/Denver", "406": "America/Denver", "435": "America/Denver",
    "505": "America/Denver", "575": "America/Denver", "719": "America/Denver",
    "720": "America/Denver", "801": "America/Denver", "970": "America/Denver",

    # Arizona (America/Phoenix - Mountain Standard, No DST)
    "480": "America/Phoenix", "520": "America/Phoenix", "602": "America/Phoenix",
    "623": "America/Phoenix", "928": "America/Phoenix",

    # Pacific (America/Los_Angeles)
    "206": "America/Los_Angeles", "209": "America/Los_Angeles", "213": "America/Los_Angeles",
    "253": "America/Los_Angeles", "310": "America/Los_Angeles", "323": "America/Los_Angeles",
    "360": "America/Los_Angeles", "408": "America/Los_Angeles", "415": "America/Los_Angeles",
    "424": "America/Los_Angeles", "425": "America/Los_Angeles", "442": "America/Los_Angeles",
    "503": "America/Los_Angeles", "509": "America/Los_Angeles", "510": "America/Los_Angeles",
    "530": "America/Los_Angeles", "541": "America/Los_Angeles", "559": "America/Los_Angeles",
    "562": "America/Los_Angeles", "564": "America/Los_Angeles", "619": "America/Los_Angeles",
    "626": "America/Los_Angeles", "628": "America/Los_Angeles", "650": "America/Los_Angeles",
    "657": "America/Los_Angeles", "661": "America/Los_Angeles", "669": "America/Los_Angeles",
    "702": "America/Los_Angeles", "707": "America/Los_Angeles", "714": "America/Los_Angeles",
    "725": "America/Los_Angeles", "747": "America/Los_Angeles", "760": "America/Los_Angeles",
    "775": "America/Los_Angeles", "805": "America/Los_Angeles", "818": "America/Los_Angeles",
    "820": "America/Los_Angeles", "831": "America/Los_Angeles", "858": "America/Los_Angeles",
    "909": "America/Los_Angeles", "916": "America/Los_Angeles", "925": "America/Los_Angeles",
    "949": "America/Los_Angeles", "951": "America/Los_Angeles", "971": "America/Los_Angeles",

    # Alaska & Hawaii
    "907": "America/Anchorage",
    "808": "Pacific/Honolulu",
}


def get_area_code(phone: str) -> str:
    """Extract 3-digit North American area code from a phone number."""
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("1") and len(digits) >= 11:
        return digits[1:4]
    if len(digits) == 10:
        return digits[:3]
    return ""


def get_timezone_for_phone(phone: str, default: str = "America/New_York") -> str:
    """Resolve prospect's local timezone based on phone area code."""
    npa = get_area_code(phone)
    return AREA_CODE_TIMEZONES.get(npa, default)


TZ_SHORT_CODES: dict[str, str] = {
    "America/New_York": "ET",
    "America/Chicago": "CT",
    "America/Denver": "MT",
    "America/Los_Angeles": "PT",
    "America/Phoenix": "MST",
    "America/Anchorage": "AKT",
    "Pacific/Honolulu": "HT",
}


def get_contact_local_time(phone: str, ref_dt: datetime | None = None) -> dict[str, Any]:
    """Calculate prospect local time, wave tier, and safe calling hours status."""
    tz_name = get_timezone_for_phone(phone)
    tz_code = TZ_SHORT_CODES.get(tz_name, "US")

    now_utc = ref_dt if ref_dt is not None else datetime.now(ZoneInfo("UTC"))
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))

    local_dt = now_utc.astimezone(ZoneInfo(tz_name))
    hour_decimal = local_dt.hour + (local_dt.minute / 60.0)

    # Safe Calling Window: 08:30 to 17:30 local time
    can_call = 8.5 <= hour_decimal <= 17.5

    # Wave classification: Prime vs Acceptable vs Off Hours
    if can_call:
        # Prime morning: 9:00am - 12:00pm, Prime afternoon: 1:30pm - 5:00pm
        if (9.0 <= hour_decimal <= 12.0) or (13.5 <= hour_decimal <= 17.0):
            wave_status = "prime"
            wave_score = 1
            notice = "Prime calling window"
        else:
            wave_status = "acceptable"
            wave_score = 2
            notice = "Acceptable window (early morning or lunch)"
    else:
        wave_status = "off_hours"
        wave_score = 3
        if hour_decimal < 8.5:
            notice = "Too early (before 8:30 AM local)"
        else:
            notice = "Too late (after 5:30 PM local)"

    formatted_time = local_dt.strftime("%I:%M %p").lstrip("0")

    return {
        "phone": phone,
        "tz_name": tz_name,
        "tz_code": tz_code,
        "local_time_str": formatted_time,
        "hour_decimal": round(hour_decimal, 2),
        "wave_status": wave_status,
        "wave_score": wave_score,
        "can_call": can_call,
        "badge_text": f"{tz_code} · {formatted_time}",
        "notice": notice,
    }


def sort_queue_by_timezone_wave(
    contacts: list[dict[str, Any]],
    safe_hours_only: bool = False,
    ref_dt: datetime | None = None,
) -> list[dict[str, Any]]:
    """Sort contacts prioritizing active prime-time wave windows and enforce safe hours."""
    scored: list[tuple[int, float, dict[str, Any]]] = []

    for contact in contacts:
        phone = str(contact.get("phone") or "")
        tz_info = get_contact_local_time(phone, ref_dt=ref_dt)
        # Attach tz_info into the contact dict
        contact_copy = dict(contact)
        contact_copy["timezone_info"] = tz_info

        if safe_hours_only and not tz_info["can_call"]:
            continue

        # Sort key:
        # Primary: can_call (0 for True, 1 for False)
        # Secondary: wave_score (1=prime, 2=acceptable, 3=off_hours)
        # Tertiary: distance from optimal peak hour (10:30 AM or 2:30 PM)
        can_call_key = 0 if tz_info["can_call"] else 1
        wave_score = tz_info["wave_score"]
        h = tz_info["hour_decimal"]
        dist = min(abs(h - 10.5), abs(h - 14.5))

        scored.append((can_call_key, wave_score * 100 + dist, contact_copy))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored]

