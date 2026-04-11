from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
import os
import traceback
import requests
import re
import json
import bcrypt
from datetime import datetime
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-here-change-it")
CORS(app)

# API 1: Groq for recipe generation
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# API 2: Pexels for images
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# Users data file
USERS_FILE = "users.json"
HISTORY_FILE = "history.json"

def load_users():
    """Load users from JSON file"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    """Save users to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def load_history():
    """Load chat history from JSON file"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_history(history):
    """Save chat history to JSON file"""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)

def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Please login first', 'redirect': '/login'}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_dish_image_pexels(dish_name):
    """Pexels API se exact dish ki photo lao"""
    try:
        if not PEXELS_API_KEY:
            return None
            
        search_query = f"{dish_name} food"
        
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {
            "query": search_query,
            "per_page": 1,
            "orientation": "landscape"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("photos") and len(data["photos"]) > 0:
                return data["photos"][0]["src"]["large"]
        return None
        
    except Exception as e:
        print(f"Image fetch error: {e}")
        return None

@app.route('/')
def home():
    if 'user_id' in session:
        return render_template('index.html', username=session.get('username'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        users = load_users()
        
        if email not in users:
            return jsonify({'success': False, 'error': 'Email not found! Sign up first.'}), 401
        
        user = users[email]
        if bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            session['user_id'] = email
            session['username'] = user['username']
            return jsonify({'success': True, 'redirect': '/'})
        else:
            return jsonify({'success': False, 'error': 'Wrong password!'}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not email or not password:
            return jsonify({'success': False, 'error': 'All fields required!'}), 400
        
        users = load_users()
        
        if email in users:
            return jsonify({'success': False, 'error': 'Email already registered!'}), 400
        
        # Hash password
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        users[email] = {
            'username': username,
            'email': email,
            'password': hashed.decode('utf-8'),
            'created_at': datetime.now().isoformat()
        }
        
        save_users(users)
        
        return jsonify({'success': True, 'redirect': '/login'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/get_recipe', methods=['POST'])
@login_required
def get_recipe():
    try:
        data = request.get_json()
        user_input = data.get('ingredients', '').strip()
        
        if not user_input:
            return jsonify({'success': False, 'error': 'Please enter dish name!'}), 400
        
        print(f"User: {session['username']} | Request: {user_input}")
        
        # Generate recipe
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": """You are an expert chef. 
                CRITICAL RULES:
                1. ONLY make what the user asks for
                2. If user asks for "plain dosa", give PLAIN DOSA recipe
                3. Follow EXACTLY what user requests"""},
                
                {"role": "user", "content": f"""Make EXACTLY this dish: {user_input}

Follow this EXACT format:

Recipe Name: [exact dish name]

Ingredients:
- ingredient 1 with quantity
- ingredient 2 with quantity

Instructions:
1. First step
2. Second step
3. Third step

Tips: One helpful tip

Time: X minutes
Serves: X people"""}
            ]
        )
        
        recipe_text = response.choices[0].message.content
        
        # Extract dish name
        dish_match = re.search(r'Recipe Name:\s*(.+?)(?:\n|$)', recipe_text, re.IGNORECASE)
        dish_name = dish_match.group(1).strip() if dish_match else user_input
        
        # Get image
        image_url = get_dish_image_pexels(dish_name)
        
        # Save to history
        history = load_history()
        user_email = session['user_id']
        
        if user_email not in history:
            history[user_email] = []
        
        history[user_email].insert(0, {
            'id': datetime.now().timestamp(),
            'query': user_input,
            'recipe': recipe_text,
            'dish_name': dish_name,
            'image_url': image_url,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 50 chats per user
        if len(history[user_email]) > 50:
            history[user_email] = history[user_email][:50]
        
        save_history(history)
        
        return jsonify({
            'success': True,
            'recipe': recipe_text,
            'dish_name': dish_name,
            'image_url': image_url
        })
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_history', methods=['GET'])
@login_required
def get_history():
    try:
        history = load_history()
        user_email = session['user_id']
        
        user_history = history.get(user_email, [])
        
        return jsonify({
            'success': True,
            'history': user_history
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    try:
        history = load_history()
        user_email = session['user_id']
        
        history[user_email] = []
        save_history(history)
        
        return jsonify({'success': True, 'message': 'History cleared!'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/suggest_ideas', methods=['GET'])
@login_required
def suggest_ideas():
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful recipe assistant."},
                {"role": "user", "content": "List 10 popular dishes people love to cook at home. Format each as: • Dish Name"}
            ]
        )
        
        suggestions = response.choices[0].message.content
        
        return jsonify({'success': True, 'suggestions': suggestions})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 AI Recipe Generator Starting...")
    print("🔐 Login System Enabled")
    print(f"📸 Pexels API: {'✓ Configured' if PEXELS_API_KEY else '✗ Missing'}")
    print("🌐 Server: http://localhost:8080")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=8080)