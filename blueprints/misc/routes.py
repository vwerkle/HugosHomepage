from flask import Blueprint, render_template, json
import os

misc_bp = Blueprint('misc', __name__)
locations = {"Fairmount","Fishtown","Rittenhouse","Center City","West Philly","NoLibs","South Philly","Fitler Square"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '..', '..', 'data', 'misc')

@misc_bp.route("/recipes")
def recipes():
    recipesList = make_json_recipes()
    return render_template('misc/recipes2.html', recipes=recipesList)

@misc_bp.route("/restaurants")
def restaurants():
    restList = make_json_restaurants()
    sorted_rest = sorted(restList.values(),key=lambda x: x['rating'],reverse=True)
    tags = sorted(set(tag for rest in sorted_rest for tag in rest['tags']) - set(locations))
    return render_template('misc/restaurants.html',restaurants=sorted_rest,tags=tags,locationfilters=locations)


def make_json_recipes():
    with open('data/misc/Recipes.txt','r') as file:
        lines=file.readlines()
        #print(lines)
    recipesList = {}
    current_cat=""
    current_subcat=""
    current_rec={}

    for line in lines:
        line=line.strip()
        if line=="":
            continue
        elif line[0]=='-':
            current_cat=line[1:]
            recipesList[current_cat]={}
            #print(current_cat)
        elif line[0]=='+':
            current_subcat=line[1:]
            recipesList[current_cat][current_subcat]=[]
        elif not current_rec:
            current_rec['title']=line
        elif 'notes'not in current_rec:
            current_rec['notes']=line
        elif 'image' not in current_rec:
            current_rec['image']=line
        elif 'date'not in current_rec:
            current_rec['date']=line
            recipesList[current_cat][current_subcat].append(current_rec)
            current_rec={}
    
    recipes_json=json.dumps(recipesList, indent=4)

    with open('data/misc/recipes.json','w') as jsonfile:
        jsonfile.write(recipes_json)

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