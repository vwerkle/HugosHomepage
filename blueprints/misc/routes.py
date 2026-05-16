from flask import Blueprint, render_template, json, request, jsonify, url_for
import os
import random
import requests as req

misc_bp = Blueprint('misc', __name__)
locations = {"Fairmount","Fishtown","Rittenhouse","Center City","West Philly","NoLibs","South Philly","Fitler Square"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '..', '..', 'data', 'misc')

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


@misc_bp.route("/recipes")
def recipes():
    recipesList = make_json_recipes()
    return render_template('misc/recipes2.html', recipes=recipesList)

@misc_bp.route("/recipes3")
def recipes3():
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
                           recipes=sorted_recipes,
                           cats=cats)

@misc_bp.route("/restaurants")
def restaurants():
    restList = make_json_restaurants()
    sorted_rest = sorted(restList.values(),key=lambda x: x['rating'],reverse=True)
    tags = sorted(set(tag for rest in sorted_rest for tag in rest['tags']) - set(locations))
    return render_template('misc/restaurants.html',restaurants=sorted_rest,tags=tags,locationfilters=locations)


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