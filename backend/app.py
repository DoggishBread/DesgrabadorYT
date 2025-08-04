import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from descarga import procesar_transcripcion

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, os.pardir, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve(path):
    return send_from_directory(FRONTEND_DIR, path)

@app.route("/transcribir", methods=["POST"])
def transcribir():
    try:
        data = request.json or {}
        vid = data.get("url", "").strip()
        lang = data.get("language", "es")

        if not vid:
            return jsonify(error="Falta la URL de YouTube."), 400

        texto = procesar_transcripcion(vid, lang)
        if texto is None:
            return jsonify(error="Error al procesar la transcripción."), 500

        return jsonify(transcripcion=texto)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(error=str(e)), 500

@app.route("/_nettest")
def nettest():
    import requests
    try:
        r = requests.get("https://www.youtube.com/", timeout=5)
        return f"HEAD https://youtube.com → {r.status_code}"
    except Exception as e:
        return f"ERROR: {e}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() == "true"
    app.run("0.0.0.0", port=port, debug=debug)