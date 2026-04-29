from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
import os
import requests
import re
import json

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "flavorax-secret-key")
CORS(app)

# Groq Client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Languages 
LANGUAGES = {
    'english': {
        'name': 'English',
        'code': 'en',
        'system_prompt': 'Respond in English only.',
        'labels': {
            'recipe_name': 'Recipe Name',
            'ingredients': 'Ingredients', 
            'instructions': 'Instructions',
            'chef_tip': "Chef's Tip",
            'cooking_time': 'Cooking Time',
            'servings': 'Servings'
        }
    },
    'hindi': {
        'name': 'हिन्दी',
        'code': 'hi',
        'system_prompt': 'Respond in Hindi language only. Use Devanagari script.',
        'labels': {
            'recipe_name': 'रेसिपी का नाम',
            'ingredients': 'सामग्री',
            'instructions': 'विधि', 
            'chef_tip': 'शेफ की सलाह',
            'cooking_time': 'पकाने का समय',
            'servings': 'सर्विंग्स'
        }
    }
}

def normalize_lang_code(lang_code):
    return lang_code if lang_code in LANGUAGES else 'english'

# ============ ROUTES ============

@app.route('/')
def home():
    if 'user' not in session:
        session['user'] = {'name': 'Guest Chef', 'email': 'guest@flavorax.com', 'picture': ''}
        session['language'] = 'english'
    return render_template('index.html')

@app.route('/login')
def login_page():
    return redirect(url_for('home'))

@app.route('/google_client_login', methods=['POST'])
def google_client_login():
    data = request.json
    session['user'] = {
        'name': data.get('name', 'Guest'),
        'email': data.get('email', 'guest@flavorax.com'),
        'picture': data.get('picture', '')
    }
    return jsonify({'success': True})

@app.route('/check_session')
def check_session():
    if 'user' not in session:
        session['user'] = {'name': 'Guest Chef', 'email': 'guest@flavorax.com', 'picture': ''}
        session['language'] = 'english'
    return jsonify({
        'logged_in': True,
        'user': session['user'].get('name'),
        'email': session['user'].get('email'),
        'picture': session['user'].get('picture'),
        'language': session.get('language', 'english')
    })

@app.route('/set_language', methods=['POST'])
def set_language():
    data = request.json
    session['language'] = normalize_lang_code(data.get('language', 'english'))
    return jsonify({'success': True})

@app.route('/get_recipe', methods=['POST'])
def get_recipe():
    try:
        data = request.json
        dish_name = data.get('ingredients', '').strip()
        lang_code = session.get('language', 'english')
        
        if not dish_name:
            return jsonify({'success': False, 'error': 'Please enter a dish name'})
        
        # Simple prompt - no JSON mode
        prompt = f"Create a complete recipe for {dish_name} in {LANGUAGES[lang_code]['name']}. Include: Recipe Name, Ingredients list, Instructions, Chef's Tip, Cooking Time, Servings. Format nicely."
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        recipe_text = response.choices[0].message.content
        
        # Get image from Pexels
        image_url = None
        if os.getenv("PEXELS_API_KEY"):
            try:
                pexels_key = os.getenv("PEXELS_API_KEY")
                search_query = dish_name.replace(' ', '%20')
                pexels_url = f"https://api.pexels.com/v1/search?query={search_query}%20food&per_page=3"
                headers = {"Authorization": pexels_key}
                resp = requests.get(pexels_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    photos = resp.json().get('photos', [])
                    if photos:
                        image_url = photos[0].get('src', {}).get('large2x')
            except:
                pass
        
        return jsonify({
            'success': True,
            'recipe': recipe_text,
            'dish_name': dish_name,
            'image_url': image_url
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/chat_with_recipe', methods=['POST'])
def chat_with_recipe():
    try:
        data = request.json
        user_message = data.get('message', '')
        recipe_context = data.get('recipe', '')[:500]
        lang_code = session.get('language', 'english')
        
        prompt = f"Recipe: {recipe_context}\n\nUser Question: {user_message}\n\nAnswer helpfully in {LANGUAGES[lang_code]['name']}."
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        return jsonify({'success': True, 'reply': response.choices[0].message.content})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)