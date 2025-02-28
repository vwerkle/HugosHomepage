from flask import Flask, render_template, request, redirect,url_for
import sys
import json
app = Flask(__name__)

locations = {"Fairmount","Fishtown","Rittenhouse","Center City","West Philly","NoLibs","South Philly"}




@app.route("/")
def home():
    print("test")
    return render_template('home.html')


@app.route("/recipes")
def recipes():
    recipesList = make_json_recipes()
    #print(recipesList)
    #print (recipesList.join())
    return render_template('recipes.html',recipes=recipesList)

@app.route("/restaurants")
def restaurants():
    restList = make_json_restaurants()
    sorted_rest = sorted(restList.values(),key=lambda x: x['rating'],reverse=True)
    tags = sorted(set(tag for rest in sorted_rest for tag in rest['tags']) - set(locations))
    return render_template('restaurants.html',restaurants=sorted_rest,tags=tags,locationfilters=locations)

@app.route('/recipe/<int:recipe_id>')
def recipe(recipe_id):
    recipe=next((r for r in recipesList if r['id']==recipe_id),None)
    if recipe:
        return render_template('recipe.html',recipe=recipe)
    else:
        return "Recipe not found", 404
    

def make_json_recipes():
    with open('Recipes.txt','r') as file:
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

    with open('recipes.json','w') as jsonfile:
        jsonfile.write(recipes_json)

    return recipes_json

def make_json_restaurants():
    with open('Restaurants.txt', 'r') as file:
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

    with open('restaurants.json','w') as jsonfile:
        jsonfile.write(restaurants_json)

    return restaurants


if __name__ == '__main__':
    print("hello")
    #print("hello",file=sys.stdout)
    #app.run(debug=True)