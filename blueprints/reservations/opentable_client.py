import json
import os
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join('data', 'reservations', 'config.json')
SESSION_PATH = os.path.join('data', 'reservations', 'opentable_session.json')

OPENTABLE_BASE = "https://www.opentable.com"
PHILLY_METRO_ID = 13  # confirmed from OT's own search page links (was 4, wrong)
PHILLY_LAT = 39.9526
PHILLY_LON = -75.1652


def _load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)['opentable']


def is_configured():
    try:
        cfg = _load_config()
        return bool(cfg.get('email') and cfg.get('password'))
    except Exception:
        return False


def _load_storage_state():
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH) as f:
            return json.load(f)
    return None


def _save_storage_state(context):
    state = context.storage_state()
    with open(SESSION_PATH, 'w') as f:
        json.dump(state, f)


def _get_browser_context():
    """
    Return (playwright, browser, context) using camoufox — a patched Firefox build
    that spoofs canvas, WebGL, audio, and navigator fingerprints to bypass Akamai
    Bot Manager (which blocks plain headless Firefox on OpenTable).
    """
    from playwright.sync_api import sync_playwright
    from camoufox.sync_api import NewBrowser

    pw = sync_playwright().start()
    # NewBrowser uses camoufox's own patched Firefox executable — PLAYWRIGHT_BROWSERS_PATH
    # is irrelevant here. os='windows' makes it fingerprint as a Windows desktop browser.
    browser = NewBrowser(pw, headless=True, os='windows')
    storage_state = _load_storage_state()
    context = browser.new_context(
        storage_state=storage_state if storage_state else None,
        locale='en-US',
        timezone_id='America/New_York',
    )
    return pw, browser, context


def search_philly_venues():
    """
    Return Philadelphia OpenTable venues by scraping RestaurantCard DOM elements.
    OT changed from numeric IDs (/restaurant/profile/123) to slugs (/r/slug).
    Warm up on homepage first — direct hits are Cloudflare-blocked.
    """
    pw, browser, context = _get_browser_context()
    venues = []

    try:
        page = context.new_page()

        # Step 1: warm up session on homepage (required to pass Cloudflare JS challenge)
        page.goto(OPENTABLE_BASE, wait_until='networkidle', timeout=40000)
        page.wait_for_timeout(3000)  # give CF challenge time to complete
        _save_storage_state(context)  # persist cf_clearance cookie for next run

        # Step 2: navigate to Philly search
        search_url = (
            f"{OPENTABLE_BASE}/s?covers=2"
            f"&metroId={PHILLY_METRO_ID}"
            f"&latitude={PHILLY_LAT}"
            f"&longitude={PHILLY_LON}"
            f"&term=philadelphia"
        )
        page.goto(search_url, wait_until='networkidle', timeout=40000)
        page.wait_for_timeout(3000)

        # If Cloudflare blocked us, retry the homepage warmup and try again
        if 'Access Denied' in page.title() or 'access denied' in page.title().lower():
            logger.warning("[OT] Access Denied on search — retrying CF warmup")
            page.goto(OPENTABLE_BASE, wait_until='networkidle', timeout=40000)
            page.wait_for_timeout(5000)
            _save_storage_state(context)
            page.goto(search_url, wait_until='networkidle', timeout=40000)
            page.wait_for_timeout(3000)

        if 'Access Denied' in page.title():
            raise Exception("Cloudflare blocked OpenTable access — try again later")

        # Scroll several times to trigger lazy loading of more restaurant cards
        for _ in range(5):
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(1500)

        # Extract restaurants from the Apollo/GQL JSON blob embedded in the page.
        # OT embeds full restaurant data (name, slug, neighborhood) in a <script> tag —
        # much more reliable than DOM scraping of obfuscated class names.
        html = page.content()
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        target_script = None
        for s in scripts:
            if '"restaurants"' in s and '"profileLink"' in s:
                target_script = s
                break

        if target_script:
            seen_ids = set()
            positions = [m.start() for m in re.finditer(r'"restaurantId":', target_script)]
            for pos in positions:
                chunk = target_script[pos:pos + 800]
                rid_m = re.search(r'"restaurantId":(\d+)', chunk)
                name_m = re.search(r'"name":"([^"]+)"', chunk)
                link_m = re.search(r'"link":"(https://www\.opentable\.com/[^"#]+)"', chunk)
                nbhd_m = re.search(r'"neighborhood":\{"name":"([^"]*)"', chunk)
                if rid_m and name_m and link_m:
                    rid = rid_m.group(1)
                    if rid in seen_ids:
                        continue
                    seen_ids.add(rid)
                    url = link_m.group(1)
                    path = url.replace('https://www.opentable.com/', '')
                    venues.append({
                        'name': name_m.group(1),
                        'venue_id': path,
                        'platform': 'opentable',
                        'neighborhood': nbhd_m.group(1) if nbhd_m else '',
                    })

        if not venues:
            raise Exception("0 venues found — OpenTable page may not have rendered restaurant data")

        logger.info(f"OpenTable: found {len(venues)} Philly venues")
    except Exception as e:
        logger.error(f"OpenTable venue search error: {e}")
        raise
    finally:
        browser.close()
        pw.stop()

    return venues


def find_restaurant_slug(name):
    """
    Search OpenTable for a restaurant by name and return its slug path (e.g. 'r/mawn-philadelphia').
    Used when the user enters a free-text restaurant name instead of picking from the dropdown.
    Returns the slug string, or raises if not found.
    """
    pw, browser, context = _get_browser_context()
    try:
        page = context.new_page()
        page.goto(OPENTABLE_BASE, wait_until='networkidle', timeout=40000)
        page.wait_for_timeout(2000)

        search_url = (
            f"{OPENTABLE_BASE}/s?covers=2&metroId={PHILLY_METRO_ID}"
            f"&latitude={PHILLY_LAT}&longitude={PHILLY_LON}"
            f"&term={name}"
        )
        page.goto(search_url, wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(3000)

        html = page.content()
        # Extract the first restaurant slug from the embedded JSON
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        for s in scripts:
            if '"profileLink"' in s:
                link_m = re.search(r'"link":"(https://www\.opentable\.com/[^"#]+)"', s)
                if link_m:
                    slug = link_m.group(1).replace('https://www.opentable.com/', '')
                    logger.info(f"Resolved '{name}' to slug '{slug}'")
                    _save_storage_state(context)
                    return slug

        raise Exception(f"Could not find OpenTable restaurant matching '{name}'")
    finally:
        browser.close()
        pw.stop()


def get_availability(restaurant_id, date, party_size, min_time, max_time):
    """
    Get available time slots by navigating to the restaurant page.
    restaurant_id is now a slug path like 'r/fogo-de-chao...' or 'el-vez'.
    Intercepts the RestaurantsAvailability GQL response.
    date: 'YYYY-MM-DD', min/max_time: 'HH:MM' (24h)
    Returns list of {time, display_time, slot_hash}
    """
    pw, browser, context = _get_browser_context()
    slots = []
    captured_slots = []

    try:
        page = context.new_page()

        def on_response(response):
            url = response.url
            if 'fe/gql' in url and 'RestaurantsAvailability' in url:
                try:
                    body = response.json()
                    _parse_gql_availability(body, captured_slots, date, min_time)
                except Exception:
                    pass
            elif any(k in url for k in ['availability', 'timeslots']):
                try:
                    body = response.json()
                    _parse_legacy_availability(body, captured_slots)
                except Exception:
                    pass

        page.on('response', on_response)

        url = (
            f"{OPENTABLE_BASE}/{restaurant_id}"
            f"?covers={party_size}&dateTime={date}T{min_time}"
        )
        page.goto(url, wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(3000)

        if captured_slots:
            slots = [s for s in captured_slots if min_time <= s['time'] <= max_time]
        else:
            slots = _scrape_time_buttons(page, min_time, max_time)

    except Exception as e:
        logger.error(f"OpenTable availability error for {restaurant_id}: {e}")
    finally:
        browser.close()
        pw.stop()

    return slots


def _parse_gql_availability(body, out_slots, requested_date, requested_time):
    """
    Parse the RestaurantsAvailability GQL response.
    Slots use timeOffsetMinutes relative to the requested dateTime.
    """
    try:
        avail_list = body.get('data', {}).get('availability', [])
        req_dt = datetime.strptime(f"{requested_date}T{requested_time}", '%Y-%m-%dT%H:%M')
        for rest_avail in avail_list:
            for day in rest_avail.get('availabilityDays', []):
                for slot in day.get('slots', []):
                    if not slot.get('isAvailable', True):
                        continue
                    offset = slot.get('timeOffsetMinutes', 0)
                    slot_hash = str(slot.get('slotHash', ''))
                    actual_dt = req_dt + timedelta(minutes=offset)
                    t24 = actual_dt.strftime('%H:%M')
                    out_slots.append({
                        'time': t24,
                        'display_time': actual_dt.strftime('%I:%M %p').lstrip('0'),
                        'slot_hash': slot_hash,
                    })
    except Exception as e:
        logger.error(f"Error parsing GQL availability: {e}")


def _parse_legacy_availability(body, out_slots):
    """Recursively find time slot data in older OpenTable API responses."""
    def _walk(obj):
        if isinstance(obj, list):
            for item in obj:
                _walk(item)
        elif isinstance(obj, dict):
            time_val = obj.get('timeOffered') or obj.get('time') or obj.get('startTime')
            slot_hash = obj.get('slotHash') or obj.get('hash') or obj.get('slotId') or ''
            if time_val and isinstance(time_val, str):
                try:
                    if 'T' in time_val:
                        t24 = datetime.fromisoformat(time_val).strftime('%H:%M')
                    elif ':' in time_val:
                        t24 = time_val[:5]
                    else:
                        return
                    out_slots.append({
                        'time': t24,
                        'display_time': datetime.strptime(t24, '%H:%M').strftime('%I:%M %p').lstrip('0'),
                        'slot_hash': str(slot_hash),
                    })
                except Exception:
                    pass
                return
            for v in obj.values():
                _walk(v)
    _walk(body)


def _scrape_time_buttons(page, min_time, max_time):
    """DOM fallback: find clickable time buttons and parse their text."""
    slots = []
    selectors = [
        '[data-test="time-button"]',
        '[data-test="timeslot-button"]',
        'button[aria-label*="PM"]',
        'button[aria-label*="AM"]',
        '[class*="timeslot"] button',
        '[class*="TimeSlot"] button',
    ]
    buttons = []
    for sel in selectors:
        buttons = page.query_selector_all(sel)
        if buttons:
            break

    for btn in buttons:
        label = btn.get_attribute('aria-label') or btn.inner_text().strip()
        slot_hash = btn.get_attribute('data-hash') or btn.get_attribute('data-slot-hash') or ''
        match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', label, re.IGNORECASE)
        if match:
            try:
                t = datetime.strptime(match.group(1).strip(), '%I:%M %p')
                t24 = t.strftime('%H:%M')
                if min_time <= t24 <= max_time:
                    slots.append({
                        'time': t24,
                        'display_time': match.group(1).strip(),
                        'slot_hash': slot_hash,
                    })
            except ValueError:
                pass
    return slots


def _login_if_needed(page, context):
    """Log in if not already authenticated; save session cookie after."""
    content = page.content()
    if 'sign-in' not in page.url and 'Log in' not in content and 'Sign in' not in content:
        return True

    cfg = _load_config()
    page.goto("https://www.opentable.com/login", wait_until='networkidle', timeout=30000)
    page.fill('input[type="email"], input[name="email"]', cfg['email'])
    page.click('button[type="submit"], [data-test="continue-button"]')
    page.wait_for_timeout(1500)

    try:
        page.fill('input[type="password"], input[name="password"]', cfg['password'])
        page.click('button[type="submit"], [data-test="sign-in-button"]')
    except Exception:
        pass

    try:
        page.wait_for_url(lambda url: 'login' not in url and 'sign-in' not in url, timeout=20000)
        _save_storage_state(context)
        return True
    except Exception as e:
        logger.error(f"OpenTable login failed: {e}")
        return False


def book_slot(restaurant_id, date, slot_time, party_size):
    """
    Book via Playwright: navigate to restaurant page (slug URL), click time slot, confirm.
    restaurant_id is a slug path like 'r/fogo-de-chao...' or 'el-vez'.
    Returns (success: bool, detail: str)
    """
    pw, browser, context = _get_browser_context()
    try:
        page = context.new_page()

        page.goto(OPENTABLE_BASE, wait_until='domcontentloaded', timeout=20000)
        _login_if_needed(page, context)

        url = (
            f"{OPENTABLE_BASE}/{restaurant_id}"
            f"?covers={party_size}&dateTime={date}T{slot_time}"
        )
        page.goto(url, wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(1500)

        display_time = datetime.strptime(slot_time, '%H:%M').strftime('%I:%M %p').lstrip('0')
        selectors = [
            f'[data-test="time-button"]:has-text("{display_time}")',
            f'[data-test="timeslot-button"]:has-text("{display_time}")',
            f'button:has-text("{display_time}")',
        ]
        clicked = False
        for sel in selectors:
            try:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            fallback = page.query_selector('[data-test="time-button"], [data-test="timeslot-button"]')
            if fallback:
                fallback.click()
                clicked = True

        if not clicked:
            return False, f"Could not find time slot for {display_time}"

        page.wait_for_timeout(2000)

        confirm_selectors = [
            '[data-test="complete-button"]',
            '[data-test="confirm-button"]',
            'button:has-text("Complete reservation")',
            'button:has-text("Confirm")',
            'button[type="submit"]',
        ]
        confirmed = False
        for sel in confirm_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    confirmed = True
                    break
            except Exception:
                pass

        if confirmed:
            page.wait_for_timeout(3000)
            if 'confirmation' in page.url or 'success' in page.url or 'thankyou' in page.url:
                return True, "Booked via OpenTable"
            return True, "Booking submitted (verify in OpenTable app)"

        return False, "Could not find confirm button"

    except Exception as e:
        logger.error(f"OpenTable book_slot error for {restaurant_id}: {e}")
        return False, str(e)
    finally:
        browser.close()
        pw.stop()
