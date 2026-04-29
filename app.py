from flask import Flask, render_template, request, jsonify
import os
import traceback

app = Flask(__name__)

@app.route('/')
def home():
    try:
        return render_template('index.html')
    except:
        return "FlavoraX is Live! (index.html not found, but server works)"

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Server is running!"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port)