from flask import Blueprint, render_template, json, request, jsonify, url_for, session, redirect
import os
import csv
import random
import requests as req
from werkzeug.utils import secure_filename
from datetime import datetime

misc_bp = Blueprint('misc', __name__)

ALLOWED_IMG = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

def is_admin():
    return session.get('user') == 'hugo'

def _allowed_img(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMG
locations = {"Fairmount","Fishtown","Rittenhouse","Center City","West Philly","NoLibs","South Philly","Fitler Square"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '..', '..', 'data', 'misc')

BELI_BASE_URL = "https://backoffice-service-split-t57o3dxfca-nn.a.run.app"
BELI_CONFIG_PATH = r"C:\Users\vince\beli-export\beli_config.json"
BELI_CSV_PATH = os.path.join(DATA_PATH, 'beli_restaurants.csv')
PRICE_LABELS = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}

# --- Dish Finder API Keys ---
SERPER_API_KEY = "0464577025b6c548601b923324dce3b18c9edb6d"

# Approximate center coordinates for each Philly neighborhood tag
NEIGHBORHOOD_COORDS = {
    "Fishtown":      (39.9727, -75.1337),
    "Fairmount":     (39.9676, -75.1726),
    "Center City":   (39.9526, -75.1652),
    "Rittenhouse":   (39.9496, -75.1727),
    "NoLibs":        (39.9609, -75.1410),
    "South Philly":  (39.9179, -75.1635),
    "West Philly":   (39.9526, -75.2090),
    "Fitler Square": (39.9457, -75.1800),
}

@misc_bp.route("/dish-finder")
def dish_finder():
    return render_template('misc/dish_image_finder.html')

@misc_bp.route("/api/dish-images", methods=["POST"])
def dish_images():
    data = request.get_json()
    restaurant_name = data.get("restaurant", "").strip()
    dish_query      = data.get("dish", "").strip()
    location        = data.get("location", "Philadelphia").strip() or "Philadelphia"
    if not restaurant_name or not dish_query:
        return jsonify({"error": "Missing fields"}), 400
    google_results = _search_images(restaurant_name, dish_query, location)
    return jsonify({
        "google": google_results,
        "query":  f"{dish_query} at {restaurant_name}"
    })

def _search_images(restaurant_name, dish, location="Philadelphia"):
    query = f'"{restaurant_name}" {dish} {location}'
    resp = req.post(
        "https://google.serper.dev/images",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": 10},
        timeout=8
    )
    resp.raise_for_status()
    return [
        {
            "url":         item.get("imageUrl", ""),
            "title":       item.get("title", ""),
            "source_page": item.get("link", ""),
        }
        for item in resp.json().get("images", [])
    ]


@misc_bp.route("/landing")
def landing():
    nested = make_json_recipes()
    flat = []
    for cat, subcats in nested.items():
        for subcat, recipe_list in subcats.items():
            for recipe in recipe_list:
                flat.append({**recipe, 'category': cat, 'subcategory': subcat})
    tier1 = [r for r in flat if r.get('tier') == 1 and r.get('image')]
    pool = tier1 if tier1 else [r for r in flat if r.get('image')]
    featured_image = ''
    if pool:
        pick = random.choice(pool)
        featured_image = url_for('static', filename=pick['image'])
    return render_template('landing.html', featured_image=featured_image)


@misc_bp.route('/admin/login', methods=['POST'])
def admin_login():
    name = request.form.get('name', '').strip()
    pw = request.form.get('password', '')
    next_url = request.form.get('next', '/')
    if not next_url.startswith('/'):
        next_url = '/'
    try:
        with open('data/madness/users.json') as f:
            users = json.load(f)
        if name in users and users[name]['password'] == pw:
            session['user'] = name
    except Exception:
        pass
    return redirect(next_url)

@misc_bp.route('/admin/logout')
def admin_logout():
    session.pop('user', None)
    next_url = request.args.get('next', '/')
    if not next_url.startswith('/'):
        next_url = '/'
    return redirect(next_url)


def _insert_recipe_txt(category, subcategory, title, notes, image_filename, date_str, tier='3'):
    with open('data/misc/Recipes.txt', 'r') as f:
        lines = f.readlines()

    in_target_cat = False
    insert_idx = None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith('-'):
            in_target_cat = (s[1:].strip() == category)
        elif s.startswith('+') and in_target_cat:
            if s[1:].strip() == subcategory:
                insert_idx = i + 1
                break

    if insert_idx is None:
        return False

    indent = '        '
    new_lines = [
        '\n',
        f'{indent}{title}\n',
        f'{indent}{notes}\n',
        f'{indent}{image_filename}\n',
        f'{indent}{date_str}\n',
        f'{indent}>{tier}\n',
    ]
    lines = lines[:insert_idx] + new_lines + lines[insert_idx:]
    with open('data/misc/Recipes.txt', 'w') as f:
        f.writelines(lines)
    return True


@misc_bp.route('/recipes/add', methods=['POST'])
def recipes_add():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    title = request.form.get('title', '').strip()
    notes = request.form.get('notes', '').strip()
    link  = request.form.get('link', '').strip()
    category    = request.form.get('category', '').strip()
    subcategory = request.form.get('subcategory', '').strip()

    if not title or not category or not subcategory:
        return jsonify({'error': 'Missing required fields'}), 400

    image_filename = ''
    f_img = request.files.get('image')
    if f_img and f_img.filename and _allowed_img(f_img.filename):
        filename = secure_filename(f_img.filename)
        f_img.save(os.path.join('static', filename))
        image_filename = filename

    if link and notes:
        final_notes = f'<a href="{link}" target="_blank">Recipe &rarr;</a><br>{notes}'
    elif link:
        final_notes = f'<a href="{link}" target="_blank">Recipe &rarr;</a>'
    else:
        final_notes = notes

    date_str = request.form.get('date', '').strip() or datetime.now().strftime('%m/%d/%Y')
    tier = request.form.get('tier', '3').strip()
    if tier not in ('1', '2', '3'):
        tier = '3'

    ok = _insert_recipe_txt(category, subcategory, title, final_notes, image_filename, date_str, tier)
    if not ok:
        return jsonify({'error': 'Category/subcategory not found'}), 404
    return jsonify({'ok': True})


@misc_bp.route("/recipes")
def recipes():
    nested = make_json_recipes()
    flat = []
    for cat, subcats in nested.items():
        for subcat, recipe_list in subcats.items():
            for recipe in recipe_list:
                flat.append({**recipe, 'category': cat, 'subcategory': subcat})
    by_tier = {}
    for r in flat:
        by_tier.setdefault(r.get('tier', 3), []).append(r)
    for bucket in by_tier.values():
        random.shuffle(bucket)
    sorted_recipes = by_tier.get(1, []) + by_tier.get(2, []) + by_tier.get(3, [])
    cats = {cat: list(subcats.keys()) for cat, subcats in nested.items()}
    return render_template('misc/recipes3.html',
                           recipes=sorted_recipes, cats=cats, is_admin=is_admin())

@misc_bp.route("/recipes3")
def recipes3():
    return redirect(url_for('misc.recipes'))

def _score_to_stars(score):
    s = round(score / 2)
    return max(1, min(5, s))

def load_beli_restaurants():
    path = os.path.join(DATA_PATH, 'beli_restaurants.csv')
    restaurants = []
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            score = float(row['score'] or 0)
            price_str = row['price'] or ''
            cuisines = [c.strip() for c in (row['cuisine'] or '').split(',') if c.strip()]
            city = row['city'] or ''
            is_philly = 'philadelphia' in city.lower()
            restaurants.append({
                'rank': int(row['rank'] or 0),
                'score': score,
                'stars': _score_to_stars(score),
                'name': row['name'],
                'cuisine': cuisines,
                'city': city,
                'neighborhood': row.get('neighborhood', ''),
                'country': row['country'],
                'price': len(price_str),
                'price_str': price_str,
                'website': row['website'],
                'is_philly': is_philly,
            })
    return restaurants

@misc_bp.route("/restaurants")
def restaurants():
    rests = load_beli_restaurants()
    all_cuisines = sorted(set(c for r in rests for c in r['cuisine']))
    return render_template('misc/restaurants.html', restaurants=rests, all_cuisines=all_cuisines, is_admin=is_admin())

@misc_bp.route("/restaurants/refresh", methods=["POST"])
def restaurants_refresh():
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        import base64
        # Load stored config
        with open(BELI_CONFIG_PATH, encoding='utf-8') as f:
            config = json.load(f)
        refresh_token = config.get("refresh_token", "")
        if not refresh_token:
            return jsonify({"error": "No refresh token in beli_config.json"}), 500

        # Get a fresh access token
        r = req.post(f"{BELI_BASE_URL}/api/token/refresh/", json={"refresh": refresh_token}, timeout=10)
        if r.status_code != 200:
            return jsonify({"error": f"Token refresh failed ({r.status_code})"}), 500
        access_token = r.json()["access"]

        # Decode user_id from JWT payload
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        user_id = json.loads(base64.urlsafe_b64decode(payload))["user_id"]

        # Save updated token back to config
        config["access_token"] = access_token
        with open(BELI_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        # Fetch rankings
        headers = {"Authorization": f"Bearer {access_token}", "User-Agent": "Beli/9.0.8 CFNetwork/1474 Darwin/23.0.0"}
        r = req.get(f"{BELI_BASE_URL}/api/get-ranking/?user={user_id}&category=ALL", headers=headers, timeout=15)
        r.raise_for_status()
        rankings = r.json()

        # Write CSV
        fields = ["rank", "score", "name", "category", "cuisine", "city", "neighborhood",
                  "country", "price", "website", "phone", "last_visit", "ranked_on", "lat", "lng", "google_place_id"]
        rows = []
        cat_labels = {"RES": "Restaurant", "BAR": "Bar", "COF": "Coffee", "BAK": "Bakery", "DES": "Dessert"}
        for cat, entries in rankings.items():
            sorted_entries = sorted(entries, key=lambda e: e.get("score", 0), reverse=True)
            for i, entry in enumerate(sorted_entries, 1):
                biz = entry.get("business", {})
                price_raw = biz.get("price")
                visit_dates = entry.get("visit_dates", [])
                cuisines = biz.get("cuisines", [])
                rows.append({
                    "rank": i,
                    "score": round(entry.get("score", 0), 2),
                    "name": biz.get("name", ""),
                    "category": cat_labels.get(cat, cat),
                    "cuisine": ", ".join(cuisines),
                    "city": biz.get("city", ""),
                    "neighborhood": biz.get("neighborhood") or "",
                    "country": biz.get("country", ""),
                    "price": PRICE_LABELS.get(price_raw, ""),
                    "website": biz.get("website") or "",
                    "phone": biz.get("phone_number") or "",
                    "last_visit": visit_dates[-1] if visit_dates else "",
                    "ranked_on": (entry.get("created_dt", "") or "")[:10],
                    "lat": biz.get("lat", ""),
                    "lng": biz.get("lng", ""),
                    "google_place_id": biz.get("place_id", ""),
                })

        with open(BELI_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        return jsonify({"ok": True, "count": len(rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def make_json_recipes():
    with open('data/misc/Recipes.txt', 'r') as f:
        lines = f.readlines()

    recipesList = {}
    current_cat = ""
    current_subcat = ""
    current_rec = {}

    def flush():
        if current_rec.get('title') and current_cat and current_subcat:
            current_rec.setdefault('tags', [])
            current_rec.setdefault('tier', 3)
            recipesList[current_cat][current_subcat].append(dict(current_rec))
            current_rec.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith('-'):
            flush()
            current_cat = line[1:].strip()
            recipesList[current_cat] = {}
        elif line.startswith('+'):
            flush()
            current_subcat = line[1:].strip()
            recipesList[current_cat][current_subcat] = []
        elif line.startswith('#'):
            current_rec['tags'] = [t.strip() for t in line[1:].split(',') if t.strip()]
        elif line.startswith('>'):
            try:
                current_rec['tier'] = int(line[1:].strip())
            except ValueError:
                current_rec['tier'] = 3
        elif 'title' not in current_rec:
            current_rec['title'] = line
        elif 'notes' not in current_rec:
            current_rec['notes'] = line
        elif 'image' not in current_rec:
            current_rec['image'] = line
        elif 'date' not in current_rec:
            current_rec['date'] = line
        else:
            flush()
            current_rec['title'] = line

    flush()

    with open('data/misc/recipes.json', 'w') as f:
        f.write(json.dumps(recipesList, indent=4))

    return recipesList

def make_json_restaurants():
    with open(os.path.join(DATA_PATH, 'Restaurants.txt'), 'r') as file:
        lines=file.readlines()
    restaurants = {}
    current_rest={}
    for line in lines:
        line= line.strip()
        if line=="":
            continue
        elif not current_rest:
            current_rest['name']=line
        elif 'rating'not in current_rest:
            current_rest['rating']=float(line)
        elif 'price'not in current_rest:
            current_rest['price']=int(line)
        elif 'html'not in current_rest:
            current_rest['html']=line
        elif 'tags'not in current_rest:
            current_rest['tags']=line.split(',')
            #print(current_rest['tags'])
            restaurants[current_rest['name']]=current_rest
            current_rest={}
    restaurants_json=json.dumps(restaurants, indent=4)

    with open('data/misc/restaurants.json','w') as jsonfile:
        jsonfile.write(restaurants_json)

    return restaurants