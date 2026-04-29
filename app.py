from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
import os
import requests
import re
import json
import traceback

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "flavorax-secret-key-2024")
app.config['SESSION_COOKIE_SECURE'] = False  # Render HTTP ke liye
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app)

# ============ API INIT ============
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Agar API key nahi hai to error mat do, baad me handle karenge
client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except:
        client = None

GROQ_FALLBACK_MODELS = [GROQ_MODEL, "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]

# ============ LANGUAGES ============
LANGUAGES = {
    'english': {
        'name': 'English', 'code': 'en', 'voice_lang': 'en-US',
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
        'name': 'हिन्दी', 'code': 'hi', 'voice_lang': 'hi-IN',
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

LANGUAGE_EXAMPLES = {
    'english': {
        'ingredient_1': '1 cup rice',
        'ingredient_2': '1 tsp salt',
        'step_1': 'Wash and prepare the ingredients.',
        'step_2': 'Cook until done.',
        'tip': 'Use fresh ingredients for better flavor.',
        'time': '25 minutes',
        'servings': '2 people',
        'script_rule': 'Use English words only.'
    },
    'hindi': {
        'ingredient_1': '1 कप चावल',
        'ingredient_2': '1 छोटा चम्मच नमक',
        'step_1': 'सामग्री को धोकर तैयार करें।',
        'step_2': 'अच्छी तरह पकने तक पकाएं।',
        'tip': 'बेहतर स्वाद के लिए ताजी सामग्री इस्तेमाल करें।',
        'time': '25 मिनट',
        'servings': '2 लोग',
        'script_rule': 'Use only Devanagari script. Do not answer in English.'
    }
}

# ============ HELPER FUNCTIONS ============
def normalize_lang_code(lang_code):
    return lang_code if lang_code in LANGUAGES else 'english'

def groq_text(prompt, system_prompt=None, json_mode=False):
    if not client:
        return json.dumps({"error": "GROQ_API_KEY not configured"})
    
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': prompt})

    for model in dict.fromkeys(GROQ_FALLBACK_MODELS):
        try:
            kwargs = {'model': model, 'temperature': 0.2, 'messages': messages}
            if json_mode:
                kwargs['response_format'] = {'type': 'json_object'}
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            continue
    return json.dumps({"error": "All Groq models failed"})

def parse_json_object(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r'\{.*\}', text or '', re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                return None
        return None

def recipe_from_structured(data, lang):
    labels = lang['labels']
    title = str(data.get('title') or '').strip()
    ingredients = data.get('ingredients') or []
    instructions = data.get('instructions') or []
    tip = str(data.get('chef_tip') or '').strip()
    cooking_time = str(data.get('cooking_time') or '').strip()
    servings = str(data.get('servings') or '').strip()
    
    if not isinstance(ingredients, list):
        ingredients = [str(ingredients)]
    if not isinstance(instructions, list):
        instructions = [str(instructions)]
    
    lines = [f"{labels['recipe_name']}: {title}", '', f"{labels['ingredients']}:"]
    lines.extend(f"- {str(item).strip()}" for item in ingredients if str(item).strip())
    lines.extend(['', f"{labels['instructions']}:"])
    lines.extend(f"{idx}. {str(step).strip()}" for idx, step in enumerate(instructions, 1) if str(step).strip())
    lines.extend(['', f"{labels['chef_tip']}: {tip}", '', f"{labels['cooking_time']}: {cooking_time}", f"{labels['servings']}: {servings}"])
    return '\n'.join(lines)

def get_dish_image(dish_name):
    if not PEXELS_API_KEY:
        return None
    try:
        dish = re.sub(r'[^a-zA-Z0-9\s-]', ' ', dish_name or '').lower().strip()
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": f"{dish} food", "per_page": 5, "orientation": "landscape"}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            photos = response.json().get("photos", [])
            if photos:
                return photos[0].get("src", {}).get("large2x") or photos[0].get("src", {}).get("large")
    except Exception as e:
        print(f"Image fetch error: {e}")
    return None

# ============ ROUTES ============
@app.route('/')
def home():
    if 'user' not in session:
        session['user'] = {'email': 'guest@flavorax.local', 'name': 'Guest Chef', 'picture': ''}
        session['language'] = 'english'
    return render_template('index.html')

@app.route('/login')
def login_page():
    return redirect(url_for('home'))

@app.route('/google_client_login', methods=['POST'])
def google_client_login():
    data = request.get_json()
    session['user'] = {
        'email': data.get('email', 'guest@flavorax.local'),
        'name': data.get('name', 'Guest Chef'),
        'picture': data.get('picture', '')
    }
    session['language'] = 'english'
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.clear()
    session['user'] = {'email': 'guest@flavorax.local', 'name': 'Guest Chef', 'picture': ''}
    session['language'] = 'english'
    return redirect(url_for('home'))

@app.route('/check_session')
def check_session():
    if 'user' not in session:
        session['user'] = {'email': 'guest@flavorax.local', 'name': 'Guest Chef', 'picture': ''}
        session['language'] = 'english'
    return jsonify({
        'logged_in': True,
        'user': session['user'].get('name', 'Guest Chef'),
        'email': session['user'].get('email', 'guest@flavorax.local'),
        'picture': session['user'].get('picture', ''),
        'language': session.get('language', 'english')
    })

@app.route('/set_language', methods=['POST'])
def set_language():
    data = request.get_json()
    session['language'] = normalize_lang_code(data.get('language', 'english'))
    return jsonify({'success': True, 'language': session['language']})

@app.route('/get_recipe', methods=['POST'])
def get_recipe():
    try:
        data = request.get_json()
        user_input = data.get('ingredients', '').strip()
        lang_code = normalize_lang_code(data.get('language') or session.get('language', 'english'))
        lang = LANGUAGES[lang_code]
        
        if not user_input:
            return jsonify({'success': False, 'error': 'Please enter dish name!'})
        
        examples = LANGUAGE_EXAMPLES.get(lang_code, LANGUAGE_EXAMPLES['english'])
        prompt = f"""Create a complete recipe for "{user_input}" in {lang['name']}.

Critical language rule: {examples['script_rule']}

Return ONLY valid JSON with this exact shape:
{{
  "title": "translated dish name",
  "ingredients": ["{examples['ingredient_1']}", "{examples['ingredient_2']}"],
  "instructions": ["{examples['step_1']}", "{examples['step_2']}"],
  "chef_tip": "{examples['tip']}",
  "cooking_time": "{examples['time']}",
  "servings": "{examples['servings']}"
}}

All JSON values must be in {lang['name']} only. Do not mix languages."""

        system_message = f"You are a multilingual professional chef. {examples['script_rule']} Return strict JSON only."
        raw_recipe = groq_text(prompt, system_message, json_mode=True)
        structured_recipe = parse_json_object(raw_recipe)
        
        if structured_recipe and 'error' not in structured_recipe:
            recipe_text = recipe_from_structured(structured_recipe, lang)
        else:
            recipe_text = raw_recipe
        
        image_url = get_dish_image(user_input)
        
        return jsonify({
            'success': True,
            'recipe': recipe_text,
            'dish_name': user_input,
            'image_url': image_url
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/chat_with_recipe', methods=['POST'])
def chat_with_recipe():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        recipe_text = data.get('recipe', '')
        lang_code = normalize_lang_code(data.get('language') or session.get('language', 'english'))
        lang = LANGUAGES[lang_code]
        
        examples = LANGUAGE_EXAMPLES.get(lang_code, LANGUAGE_EXAMPLES['english'])
        prompt = f"""You are a cooking assistant.
Recipe Context: {recipe_text[:800]}

User Question: {user_message}

Answer naturally and concisely in {lang['name']} as a helpful cooking assistant.
{examples['script_rule']}
{lang['system_prompt']}

Keep answer under 100 words."""

        system_message = f"You are a multilingual cooking assistant. {examples['script_rule']}"
        reply = groq_text(prompt, system_message)
        
        return jsonify({'success': True, 'reply': reply})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============ RUN ============
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"\n🍳 FlavoraX Started on port {port}")
    print(f"📍 Visit: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)