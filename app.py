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
app.secret_key = os.getenv("SECRET_KEY", "flavorax-secret-key-2024")

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_HTTPONLY"] = True

CORS(app, supports_credentials=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODELS = [
    GROQ_MODEL,
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant"
]

LANGUAGES = {
    "english": {
        "name": "English",
        "code": "en",
        "voice_lang": "en-US",
        "system_prompt": "Respond in English only.",
        "labels": {
            "recipe_name": "Recipe Name",
            "ingredients": "Ingredients",
            "instructions": "Instructions",
            "chef_tip": "Chef's Tip",
            "cooking_time": "Cooking Time",
            "servings": "Servings"
        }
    },
    "hindi": {
        "name": "हिन्दी",
        "code": "hi",
        "voice_lang": "hi-IN",
        "system_prompt": "Respond in Hindi only using Devanagari script.",
        "labels": {
            "recipe_name": "रेसिपी का नाम",
            "ingredients": "सामग्री",
            "instructions": "विधि",
            "chef_tip": "शेफ की सलाह",
            "cooking_time": "पकाने का समय",
            "servings": "सर्विंग्स"
        }
    }
}

LANGUAGE_EXAMPLES = {
    "english": {
        "ingredient_1": "1 cup rice",
        "ingredient_2": "1 tsp salt",
        "step_1": "Wash ingredients.",
        "step_2": "Cook well.",
        "tip": "Use fresh ingredients.",
        "time": "25 minutes",
        "servings": "2 people",
        "script_rule": "Use English only."
    },
    "hindi": {
        "ingredient_1": "1 कप चावल",
        "ingredient_2": "1 छोटा चम्मच नमक",
        "step_1": "सामग्री धो लें।",
        "step_2": "अच्छी तरह पकाएं।",
        "tip": "ताजी सामग्री इस्तेमाल करें।",
        "time": "25 मिनट",
        "servings": "2 लोग",
        "script_rule": "Use only Devanagari script."
    }
}

SCRIPT_RANGES = {
    "hindi": r"[\u0900-\u097F]"
}

def normalize_lang_code(lang):
    return lang if lang in LANGUAGES else "english"

def uses_expected_script(text, lang):
    if lang == "english":
        return True
    pattern = SCRIPT_RANGES.get(lang)
    if not pattern:
        return True
    return len(re.findall(pattern, text or "")) > 10

def parse_json_object(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                return None
        return None

def groq_text(prompt, system_prompt=None, json_mode=False):
    messages = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    last_error = None

    for model in GROQ_FALLBACK_MODELS:
        try:
            kwargs = {
                "model": model,
                "temperature": 0.3,
                "messages": messages
            }

            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            res = client.chat.completions.create(**kwargs)
            return res.choices[0].message.content

        except Exception as e:
            last_error = e

    raise last_error

def recipe_from_structured(data, lang):
    labels = lang["labels"]

    ingredients = data.get("ingredients", [])
    instructions = data.get("instructions", [])

    if not isinstance(ingredients, list):
        ingredients = [ingredients]

    if not isinstance(instructions, list):
        instructions = [instructions]

    lines = [
        f"{labels['recipe_name']}: {data.get('title','')}",
        "",
        f"{labels['ingredients']}:"
    ]

    for i in ingredients:
        lines.append(f"- {i}")

    lines.append("")
    lines.append(f"{labels['instructions']}:")

    for idx, step in enumerate(instructions, 1):
        lines.append(f"{idx}. {step}")

    lines.append("")
    lines.append(f"{labels['chef_tip']}: {data.get('chef_tip','')}")
    lines.append("")
    lines.append(f"{labels['cooking_time']}: {data.get('cooking_time','')}")
    lines.append(f"{labels['servings']}: {data.get('servings','')}")

    return "\n".join(lines)

def clean_dish_query(name):
    dish = re.sub(r"[^a-zA-Z0-9\s-]", " ", name or "").lower()
    dish = re.sub(r"\s+", " ", dish).strip()
    return dish

def get_dish_image(name):
    if not PEXELS_API_KEY:
        return None

    try:
        url = "https://api.pexels.com/v1/search"

        headers = {
            "Authorization": PEXELS_API_KEY
        }

        params = {
            "query": f"{clean_dish_query(name)} food",
            "per_page": 1
        }

        r = requests.get(url, headers=headers, params=params, timeout=5)

        if r.status_code != 200:
            return None

        data = r.json()
        photos = data.get("photos", [])

        if photos:
            return photos[0]["src"]["large"]

        return None

    except:
        return None

@app.route("/")
def home():
    if "user" not in session:
        session["user"] = {
            "email": "guest@flavorax.local",
            "name": "Guest Chef",
            "picture": ""
        }
        session["language"] = "english"

    return render_template("index.html")

@app.route("/login")
def login_page():
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/check_session")
def check_session():
    if "user" not in session:
        session["user"] = {
            "email": "guest@flavorax.local",
            "name": "Guest Chef",
            "picture": ""
        }

    return jsonify({
        "logged_in": True,
        "user": session["user"]["name"],
        "email": session["user"]["email"],
        "language": session.get("language", "english")
    })

@app.route("/set_language", methods=["POST"])
def set_language():
    data = request.get_json()
    lang = normalize_lang_code(data.get("language", "english"))
    session["language"] = lang
    return jsonify({"success": True})

@app.route("/get_recipe", methods=["POST"])
def get_recipe():
    try:
        data = request.get_json()

        user_input = data.get("ingredients", "").strip()

        if not user_input:
            return jsonify({
                "success": False,
                "error": "Please enter dish name"
            })

        lang_code = normalize_lang_code(
            data.get("language") or session.get("language", "english")
        )

        lang = LANGUAGES[lang_code]
        examples = LANGUAGE_EXAMPLES[lang_code]

        prompt = f"""
Create recipe for {user_input} in {lang['name']}.

Return JSON:
{{
"title":"...",
"ingredients":["...","..."],
"instructions":["...","..."],
"chef_tip":"...",
"cooking_time":"...",
"servings":"..."
}}

{examples['script_rule']}
"""

        system = f"You are chef AI. Return strict JSON only."

        raw = groq_text(prompt, system, True)

        structured = parse_json_object(raw)

        if structured:
            recipe = recipe_from_structured(structured, lang)
        else:
            recipe = raw

        image = get_dish_image(user_input)

        return jsonify({
            "success": True,
            "recipe": recipe,
            "dish_name": user_input,
            "image_url": image
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route("/chat_with_recipe", methods=["POST"])
def chat_with_recipe():
    try:
        data = request.get_json()

        msg = data.get("message", "")
        recipe = data.get("recipe", "")

        lang_code = normalize_lang_code(
            data.get("language") or session.get("language", "english")
        )

        lang = LANGUAGES[lang_code]

        prompt = f"""
Recipe:
{recipe[:700]}

User question:
{msg}

Reply in {lang['name']}.
"""

        reply = groq_text(prompt)

        return jsonify({
            "success": True,
            "reply": reply
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)