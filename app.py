from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
import os
import requests
import re
import json

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "flavorax-secret-key-2024")
CORS(app)

# APIs
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODELS = [GROQ_MODEL, "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]

# Languages
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

SCRIPT_RANGES = {
    'hindi': r'[\u0900-\u097F]'
}

def uses_expected_script(text, lang_code):
    if lang_code == 'english':
        return True
    pattern = SCRIPT_RANGES.get(lang_code)
    if not pattern:
        return True
    script_chars = len(re.findall(pattern, text or ''))
    letters = len(re.findall(r'[^\W\d_]', text or '', flags=re.UNICODE))
    return script_chars >= 20 and (letters == 0 or script_chars / max(letters, 1) >= 0.35)

def groq_text(prompt, system_prompt=None, json_mode=False):
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': prompt})

    last_error = None
    for model in dict.fromkeys(GROQ_FALLBACK_MODELS):
        for use_json_mode in ([True, False] if json_mode else [False]):
            kwargs = {
                'model': model,
                'temperature': 0.2,
                'messages': messages
            }
            if use_json_mode:
                kwargs['response_format'] = {'type': 'json_object'}
            try:
                response = client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except Exception as error:
                last_error = error
                continue

    raise last_error

def normalize_lang_code(lang_code):
    return lang_code if lang_code in LANGUAGES else 'english'

def parse_json_object(text):
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text or '', re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
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

def clean_dish_query(dish_name):
    dish = re.sub(r'[^a-zA-Z0-9\s-]', ' ', dish_name or '').lower()
    dish = re.sub(r'\s+', ' ', dish).strip()
    remove_words = {
        'easy', 'simple', 'quick', 'best', 'homemade', 'authentic',
        'traditional', 'recipe', 'make', 'with', 'and', 'the'
    }
    words = [word for word in dish.split() if word not in remove_words]
    return ' '.join(words) or dish

def get_dish_image_wikipedia(dish_name):
    dish = clean_dish_query(dish_name)
    if not dish:
        return None

    try:
        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{dish} food dish",
                "gsrlimit": 4,
                "prop": "pageimages",
                "piprop": "thumbnail",
                "pithumbsize": 800,
                "format": "json"
            },
            headers={"User-Agent": "FlavoraXRecipeGenerator/1.0"},
            timeout=8
        )
        if response.status_code != 200:
            return None

        pages = response.json().get("query", {}).get("pages", {})
        dish_words = set(dish.split())
        best = None
        best_score = 0

        for page in pages.values():
            title = page.get("title", "").lower()
            thumbnail = page.get("thumbnail", {}).get("source")
            if not thumbnail:
                continue

            score = sum(3 for word in dish_words if word in title)
            if any(word in title for word in ("dish", "food", "cuisine", "recipe")):
                score += 1

            if score > best_score:
                best = thumbnail
                best_score = score

        return best if best_score >= 3 else None
    except Exception:
        return None

def get_dish_image(dish_name):
    wiki_image = get_dish_image_wikipedia(dish_name)
    if wiki_image:
        return wiki_image

    if not PEXELS_API_KEY:
        return None

    dish = clean_dish_query(dish_name)
    dish_words = set(dish.split())
    category_queries = {
        'butter chicken': 'butter chicken curry indian food',
        'dosa': 'dosa south indian food',
        'plain dosa': 'plain dosa south indian food',
        'biryani': 'biryani rice indian food',
        'chicken biryani': 'chicken biryani indian food',
        'paneer tikka': 'paneer tikka indian appetizer',
        'pasta carbonara': 'spaghetti carbonara pasta dish',
        'carbonara': 'spaghetti carbonara pasta dish',
        'margherita pizza': 'margherita pizza food',
        'chocolate cake': 'chocolate cake dessert',
        'garlic bread': 'garlic bread food',
        'omelette': 'omelette breakfast food'
    }
    food_words = {
        'food', 'dish', 'meal', 'plate', 'bowl', 'curry', 'rice', 'pasta',
        'pizza', 'cake', 'bread', 'soup', 'salad', 'chicken', 'paneer',
        'breakfast', 'dessert', 'cuisine'
    }
    bad_words = {'person', 'people', 'woman', 'man', 'child', 'kitchen', 'market'}
    search_queries = []
    mapped_query = category_queries.get(dish)
    if mapped_query:
        search_queries.append(mapped_query)
    search_queries.extend([
        f"{dish} food",
        f"{dish} dish",
        f"{dish} cuisine",
        dish
    ])

    try:
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        best_image = None
        best_score = -1

        for query in dict.fromkeys(search_queries):
            params = {
                "query": query,
                "per_page": 10,
                "orientation": "landscape",
                "size": "large"
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code != 200:
                continue

            for photo in response.json().get("photos", []):
                alt = (photo.get("alt") or "").lower()
                score = 0
                score += sum(4 for word in dish_words if word and word in alt)
                score += sum(1 for word in food_words if word in alt)
                score -= sum(2 for word in bad_words if word in alt)
                if photo.get("width", 0) >= photo.get("height", 1):
                    score += 1

                if score > best_score:
                    best_score = score
                    best_image = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")

            if best_image and best_score >= max(4, len(dish_words) * 2):
                return best_image

        return best_image if best_score >= 2 else None
    except Exception:
        pass
    return None

# ============ GUEST MODE ROUTES (No OAuth required) ============

@app.route('/')
def home():
    # Guest mode - automatically logged in
    if 'user' not in session:
        session['user'] = {
            'email': 'guest@flavorax.local',
            'name': 'Guest Chef',
            'picture': ''
        }
        session['language'] = 'english'
    return render_template('index.html')

@app.route('/login')
def login_page():
    # Redirect to home directly in guest mode
    return redirect(url_for('home'))

@app.route('/google_client_login', methods=['POST'])
def google_client_login():
    # Simple guest login
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
    # Reset guest session
    session['user'] = {
        'email': 'guest@flavorax.local',
        'name': 'Guest Chef',
        'picture': ''
    }
    session['language'] = 'english'
    return redirect(url_for('home'))

@app.route('/check_session')
def check_session():
    if 'user' not in session:
        session['user'] = {
            'email': 'guest@flavorax.local',
            'name': 'Guest Chef',
            'picture': ''
        }
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
    lang_code = data.get('language', 'english')
    session['language'] = normalize_lang_code(lang_code)
    return jsonify({'success': True, 'language': session['language']})

@app.route('/get_recipe', methods=['POST'])
def get_recipe():
    if 'user' not in session:
        session['user'] = {'email': 'guest@flavorax.local', 'name': 'Guest Chef', 'picture': ''}
    
    try:
        data = request.get_json()
        user_input = data.get('ingredients', '').strip()
        lang_code = normalize_lang_code(data.get('language') or session.get('language', 'english'))
        lang = LANGUAGES[lang_code]
        
        if not user_input:
            return jsonify({'success': False, 'error': 'Please enter dish name!'})
        
        examples = LANGUAGE_EXAMPLES.get(lang_code, LANGUAGE_EXAMPLES['english'])
        prompt = f"""Create a complete recipe for "{user_input}" in {lang['name']}.

Critical language rule: {examples['script_rule']} Translate the dish name and every recipe detail naturally.

Return ONLY valid JSON with this exact shape:
{{
  "title": "translated dish name",
  "ingredients": ["{examples['ingredient_1']}", "{examples['ingredient_2']}"],
  "instructions": ["{examples['step_1']}", "{examples['step_2']}"],
  "chef_tip": "{examples['tip']}",
  "cooking_time": "{examples['time']}",
  "servings": "{examples['servings']}"
}}

All JSON values must be in {lang['name']} only. Do not mix languages.
{lang['system_prompt']}"""

        system_message = f"You are a multilingual professional chef. {examples['script_rule']} Return strict JSON only."
        raw_recipe = groq_text(prompt, system_message, json_mode=True)
        structured_recipe = parse_json_object(raw_recipe)

        if not structured_recipe or not uses_expected_script(json.dumps(structured_recipe, ensure_ascii=False), lang_code):
            retry_prompt = prompt + f"\n\nRewrite the JSON values only in {lang['name']}. {examples['script_rule']}"
            raw_recipe = groq_text(retry_prompt, system_message, json_mode=True)
            structured_recipe = parse_json_object(raw_recipe)

        recipe_text = recipe_from_structured(structured_recipe, lang) if structured_recipe else raw_recipe
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
    if 'user' not in session:
        session['user'] = {'email': 'guest@flavorax.local', 'name': 'Guest Chef', 'picture': ''}
    
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        recipe_text = data.get('recipe', '')
        lang_code = normalize_lang_code(data.get('language') or session.get('language', 'english'))
        lang = LANGUAGES[lang_code]
        
        examples = LANGUAGE_EXAMPLES.get(lang_code, LANGUAGE_EXAMPLES['english'])
        prompt = f"""You are a cooking assistant.
Recipe: {recipe_text[:500]}

User: {user_message}

Answer naturally and concisely in {lang['name']}.
Critical language rule: {examples['script_rule']}
{lang['system_prompt']}"""

        system_message = f"You are a multilingual cooking assistant. {examples['script_rule']}"
        reply = groq_text(prompt, system_message)
        if not uses_expected_script(reply, lang_code):
            reply = groq_text(prompt + f"\n\nRewrite only in {lang['name']}. {examples['script_rule']}", system_message)
        
        return jsonify({'success': True, 'reply': reply})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============ RUN ============
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"\n🍳 FlavoraX Started on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)