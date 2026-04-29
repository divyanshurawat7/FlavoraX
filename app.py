from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
import os
import requests
import re

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

MODEL = "llama-3.3-70b-versatile"

LANGUAGES = {
    "english": {"name": "English"},
    "hindi": {"name": "Hindi"}
}

def normalize_lang_code(lang):
    return lang if lang in LANGUAGES else "english"

def groq_text(prompt):
    res = client.chat.completions.create(
        model=MODEL,
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": "You are a professional chef AI."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return res.choices[0].message.content

def clean_dish_query(name):
    dish = re.sub(r"[^a-zA-Z0-9\s-]", " ", name or "").lower()
    dish = re.sub(r"\s+", " ", dish).strip()
    return dish

def get_dish_image(name):
    if not PEXELS_API_KEY:
        return None

    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={
                "Authorization": PEXELS_API_KEY
            },
            params={
                "query": f"{clean_dish_query(name)} food",
                "per_page": 1
            },
            timeout=5
        )

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
    if "user" in session:
        return redirect("/")

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

        if "language" not in session:
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
    return redirect("/login")

# ---------------- LANGUAGE ----------------

@app.route("/set_language", methods=["POST"])
def set_language():
    data = request.get_json()

    lang = normalize_lang_code(
        data.get("language", "english")
    )

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
Create recipe for {dish} in {LANGUAGES[lang]['name']}.

Return exactly in this format:

Recipe Name: {dish}

Ingredients:
- item 1
- item 2
- item 3

Instructions:
1. step one
2. step two
3. step three

Cooking Time: 30 minutes
Servings: 4 people
Chef Tip: short tip only

No intro paragraph.
No markdown.
"""

        recipe = groq_text(prompt)
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