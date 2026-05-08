import json, os, re
from camoufox.sync_api import NewBrowser
from playwright.sync_api import sync_playwright

SESSION_PATH = os.path.join('data', 'reservations', 'opentable_session.json')
storage_state = json.load(open(SESSION_PATH)) if os.path.exists(SESSION_PATH) else None

pw = sync_playwright().start()
browser = NewBrowser(pw, headless=True, os='windows')
context = browser.new_context(storage_state=storage_state, locale='en-US', timezone_id='America/New_York')
page = context.new_page()
page.goto('https://www.opentable.com', wait_until='networkidle', timeout=40000)
page.wait_for_timeout(2000)

def search_restaurant(term):
    url = f'https://www.opentable.com/s?covers=2&term={term}&metroId=13&latitude=39.9526&longitude=-75.1652'
    page.goto(url, wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(3000)
    html = page.content()
    # Check for restaurant slugs
    links = re.findall(r'"link":"(https://www\.opentable\.com/[^"#]+)"', html)
    names = re.findall(r'"name":"([^"]+)"', html)
    print(f"\nSearch '{term}':")
    print(f"  Links: {links[:5]}")
    # Also check DOM
    a_links = page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h.includes('/r/') || h.includes('opentable.com/'))")
    rest_links = [l for l in a_links if '/r/' in l or ('opentable.com/' in l and l.count('/') == 4)]
    print(f"  DOM restaurant links: {rest_links[:5]}")

search_restaurant('mawn philadelphia')
search_restaurant('sao vietnamese philadelphia')
search_restaurant('sao philadelphia')

# Also try: multiple neighborhood searches to get more restaurants total
# Search for neighborhoods we know
print("\n\nNow trying neighborhood-based searches to expand list...")
neighborhoods = ['fishtown', 'south philly', 'west philadelphia', 'northern liberties', 'old city']
all_venues = {}
for nbhd in neighborhoods:
    url = f'https://www.opentable.com/s?covers=2&term={nbhd}+philadelphia&metroId=13&latitude=39.9526&longitude=-75.1652'
    page.goto(url, wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(3000)
    html = page.content()
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for s in scripts:
        if '"restaurants"' in s and '"profileLink"' in s:
            positions = [m.start() for m in re.finditer(r'"restaurantId":', s)]
            for pos in positions:
                chunk = s[pos:pos + 800]
                rid_m = re.search(r'"restaurantId":(\d+)', chunk)
                name_m = re.search(r'"name":"([^"]+)"', chunk)
                link_m = re.search(r'"link":"(https://www\.opentable\.com/[^"#]+)"', chunk)
                nbhd_m = re.search(r'"neighborhood":\{"name":"([^"]*)"', chunk)
                if rid_m and name_m and link_m:
                    rid = rid_m.group(1)
                    if rid not in all_venues:
                        url2 = link_m.group(1).replace('https://www.opentable.com/', '')
                        all_venues[rid] = {'name': name_m.group(1), 'venue_id': url2, 'neighborhood': nbhd_m.group(1) if nbhd_m else ''}
            print(f"  {nbhd}: total unique so far = {len(all_venues)}")
            break

browser.close()
pw.stop()
