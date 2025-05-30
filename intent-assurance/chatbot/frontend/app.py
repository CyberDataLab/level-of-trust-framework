from flask import Flask, render_template, redirect, url_for, request
from flask_cors import CORS
import requests
import json
from forms import LoginForm
from pymongo import MongoClient

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'your_secret_key_here'
CORS(app, resources={r"/*": {"origins": "*"}})

client = MongoClient("mongodb://172.17.0.2:27017/") #Chequear cada vez que se lanza 172.17.0.3
db = client["example_database"]
users_collection = db["users"]
ns_collection = db["wef_entities"]
current_user = None

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    global current_user
    form = LoginForm()
    if form.validate_on_submit():
        current_user = form.username.data
        password = form.password.data
        return redirect(url_for('dashboard'))
    return render_template('login.html', form=form)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if current_user is None:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/signTLA', methods=['POST'])
def signTLA():
    global current_user
    global ns_collection
    global users_collection
    data = request.get_json(force=True, silent=True) or []

    if current_user is None:
        return json.dumps({"error": "Not logged in"}), 401, {'Content-Type': 'application/json'}
    if not data:
        return json.dumps({"error": "No data provided"}), 400, {'Content-Type': 'application/json'}
    
    user_data = users_collection.find_one({"id": current_user})
    print("DEBUG: current_user =", current_user)
    print("DEBUG: user_data =", user_data)
    tla_list = user_data.get("tlas", []) if user_data else []
    last_id = int(tla_list[-1]["id"]) if tla_list else 0
    related_ns = []
    for entity in data:
        resource = entity.get("resource")
        if resource is not None:
            related_ns.append(resource)
    new_tla = {
        "id": str(last_id + 1),
        "related-ns": related_ns
    }
    tla_list.append(new_tla)
    if user_data:
        users_collection.update_one({"id": current_user}, {"$set": {"tlas": tla_list}})
    result = {
        "levelOfTrust": user_data.get("levelOfTrust") if user_data else None,
        "data": data
    }

    return json.dumps(result), 200, {'Content-Type': 'application/json'}

@app.route('/debug')
def debug():
    url = "http://localhost:5005/webhooks/rest/webhook"
    headers = {"Content-Type": "application/json"}
    data = {"message": "start over"}

    response = requests.post(url, headers=headers, json=data)
    return json.dumps(response.json(), indent=4)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')