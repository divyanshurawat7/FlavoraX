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
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

client = Groq(api_key=GROQ_API_KEY)

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODELS = [
    GROQ_MODEL,
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant"
]

LANGUAGES = {
    "english": {
        "name": "English"
    },
    "hindi": {
        "name": "हिन्दी"
    }
}

def normalize_lang_code(lang):
    return lang if lang in LANGUAGES else "english"

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
        messages.append({
            "role": "system",
            "content": system_prompt
        })

    messages.append({
        "role": "user",
        "content": prompt
    })

    last_error = None

    for model in GROQ_FALLBACK_MODELS:
        try:
            kwargs = {
                "model": model,
                "temperature": 0.4,
                "messages": messages
            }

            if json_mode:
                kwargs["response_format"] = {
                    "type": "json_object"
                }

            res = client.chat.completions.create(**kwargs)
            return res.choices[0].message.content

        except Exception as e:
            last_error = e

    raise last_error

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

# ---------------- HOME ----------------

@app.route("/")
def home():
    if "user" in session:
        return render_template("index.html")

    return render_template(
        "login.html",
        google_client_id=GOOGLE_CLIENT_ID
    )

# ---------------- LOGIN ----------------

@app.route("/login")
def login_page():
    return render_template(
        "login.html",
        google_client_id=GOOGLE_CLIENT_ID
    )

# ---------------- GOOGLE LOGIN ----------------

@app.route("/google_client_login", methods=["POST"])
def google_client_login():
    try:
        data = request.get_json()

        session["user"] = {
            "email": data.get("email"),
            "name": data.get("name"),
            "picture": data.get("picture", "")
        }

        session["language"] = "english"

        return jsonify({
            "success": True
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

# ---------------- CHECK SESSION ----------------

@app.route("/check_session")
def check_session():
    if "user" in session:
        return jsonify({
            "logged_in": True,
            "user": session["user"]["name"],
            "email": session["user"]["email"],
            "picture": session["user"]["picture"],
            "language": session.get("language", "english")
        })

    return jsonify({
        "logged_in": False
    })

# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- LANGUAGE ----------------

@app.route("/set_language", methods=["POST"])
def set_language():
    data = request.get_json()
    lang = normalize_lang_code(data.get("language", "english"))
    session["language"] = lang

    return jsonify({
        "success": True
    })

# ---------------- RECIPE ----------------

@app.route("/get_recipe", methods=["POST"])
def get_recipe():
    try:
        data = request.get_json()

        dish = data.get("ingredients", "").strip()

        if not dish:
            return jsonify({
                "success": False,
                "error": "Please enter dish name"
            })

        lang = normalize_lang_code(
            data.get("language") or session.get("language", "english")
        )

        prompt = f"""
Give full recipe for {dish} in {LANGUAGES[lang]['name']} language.

Include:
1. Recipe Name
2. Ingredients
3. Instructions
4. Cooking Time
5. Servings
6. Chef Tip
"""

        recipe = groq_text(prompt, "You are a professional chef AI.")
        image = get_dish_image(dish)

        return jsonify({
            "success": True,
            "dish_name": dish,
            "recipe": recipe,
            "image_url": image
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

# ---------------- CHAT ----------------

@app.route("/chat_with_recipe", methods=["POST"])
def chat_with_recipe():
    try:
        data = request.get_json()

        msg = data.get("message", "")
        recipe = data.get("recipe", "")
        lang = normalize_lang_code(
            data.get("language") or session.get("language", "english")
        )

        prompt = f"""
Recipe:
{recipe}

User Question:
{msg}

Reply in {LANGUAGES[lang]['name']}.
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

# ---------------- RUN ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)