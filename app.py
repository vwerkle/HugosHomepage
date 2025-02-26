from flask import Flask, render_template, request, redirect,url_for
import sys
import json
app = Flask(__name__)






@app.route("/")
def home():
    print("test")
    return render_template('home.html')


@app.route("/recipes")
def recipes():
    recipesList = make_json()
    print(recipesList)
    #print (recipesList.join())
    return render_template('recipes.html',recipes=recipesList)

@app.route('/recipe/<int:recipe_id>')
def recipe(recipe_id):
    recipe=next((r for r in recipesList if r['id']==recipe_id),None)
    if recipe:
        return render_template('recipe.html',recipe=recipe)
    else:
        return "Recipe not found", 404
    

def make_json():
    with open('Recipes.txt','r') as file:
        lines=file.readlines()
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
    #print(recipes_json)

    with open('recipes.json','w') as jsonfile:
        jsonfile.write(recipes_json)
    with open('recipes.json','r') as jfile:
        recipes_json=json.load(jfile)

    return recipes_json

if __name__ == '__main__':
    print("hello",file=sys.stdout)
    app.run(debug=True)
