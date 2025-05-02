from flask import Flask, render_template, request, redirect, url_for
import requests
import json
from forms import LoginForm

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'your_secret_key_here'

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        return redirect(url_for('dashboard'))
    return render_template('login.html', form=form)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    return render_template('dashboard.html')

@app.route('/debug')
def debug():
    url = "http://localhost:5005/webhooks/rest/webhook"
    headers = {"Content-Type": "application/json"}
    data = {"message": "start over"}

    response = requests.post(url, headers=headers, json=data)
    return json.dumps(response.json(), indent=4)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')