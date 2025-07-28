import os
import time
import traceback
import requests
import yt_dlp

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
HEADERS = {"authorization": API_KEY}

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, os.pardir)
AUDIO_FOLDER = os.path.join(BASE_DIR, "audio")
os.makedirs(AUDIO_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="/")
CORS(app)

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    full = os.path.join(FRONTEND_DIR, path)
    if path and os.path.exists(full):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")

def download_audio_from_youtube(url):
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(AUDIO_FOLDER, "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }],
        "quiet": True,
        "no_warnings": True
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.join(AUDIO_FOLDER, f"{info['id']}.mp3")

def upload_to_assemblyai(path):
    with open(path, "rb") as f:
        resp = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=HEADERS,
            files={"file": f}
        )
    resp.raise_for_status()
    data = resp.json()
    url  = data.get("upload_url")
    if not url:
        raise Exception(f"No vino upload_url: {data}")
    return url

def start_transcription(audio_url, src_lang):
    payload = {"audio_url": audio_url}
    if src_lang and src_lang != "auto":
        payload["language_code"] = src_lang

    print(">>> Payload a AssemblyAI:", payload)
    r = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json=payload,
        headers=HEADERS
    )
    print(f">>> AssemblyAI respondió ({r.status_code}): {r.text}")
    data = r.json()
    if "id" not in data:
        raise Exception(f"Error iniciando transcription: {data}")
    return data["id"]

def wait_for_transcript(tid):
    url = f"https://api.assemblyai.com/v2/transcript/{tid}"
    while True:
        r = requests.get(url, headers=HEADERS).json()
        if r.get("status") == "completed":
            return r
        if r.get("status") == "error":
            raise Exception(r.get("error"))
        time.sleep(3)

@app.route("/transcribir", methods=["POST"])
def transcribir():
    try:
        body    = request.json
        vid_url = body.get("url")
        src     = body.get("language", "auto")

        audio_path = download_audio_from_youtube(vid_url)
        upload_url = upload_to_assemblyai(audio_path)
        tid        = start_transcription(upload_url, src)
        result     = wait_for_transcript(tid)

        srt_text = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{tid}/srt",
            headers=HEADERS
        ).text

        if os.remove(audio_path):
            os.remove(audio_path)
        return jsonify({"transcripcion": srt_text})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)