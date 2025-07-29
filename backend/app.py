import os
import time
import traceback
import requests
import yt_dlp
from yt_dlp.utils import DownloadError

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
API_KEY     = os.getenv("ASSEMBLYAI_API_KEY")
HEADERS     = {"authorization": API_KEY}
COOKIE_FILE = os.getenv("YTDLP_COOKIE_FILE")

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, os.pardir, "frontend")
AUDIO_FOLDER = os.path.join(BASE_DIR, "audio")
os.makedirs(AUDIO_FOLDER, exist_ok=True)

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=""
)
CORS(app)

@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve(path):
    return send_from_directory(FRONTEND_DIR, path)


def download_audio_from_youtube(url: str) -> str:
    """
    Descarga y convierte a MP3 con geo-bypass, IPv4 y (opcional) cookies.
    """
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(AUDIO_FOLDER, "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }],
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "geo_bypass_country": "US",
        "source_address": "0.0.0.0",
    }
    if COOKIE_FILE and os.path.exists(COOKIE_FILE):
        opts["cookiefile"] = COOKIE_FILE

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.join(AUDIO_FOLDER, f"{info['id']}.mp3")


def upload_to_assemblyai(path: str) -> str:
    with open(path, "rb") as f:
        resp = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=HEADERS,
            files={"file": f}
        )
    resp.raise_for_status()
    upload_url = resp.json().get("upload_url")
    if not upload_url:
        raise RuntimeError(f"No upload_url in response: {resp.text}")
    return upload_url


def start_transcription(audio_url: str, src_lang: str) -> str:
    payload = {"audio_url": audio_url}
    if src_lang and src_lang != "auto":
        payload["language_code"] = src_lang

    r = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json=payload,
        headers=HEADERS
    )
    r.raise_for_status()
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"Error iniciando transcription: {data}")
    return data["id"]


def wait_for_transcript(tid: str) -> dict:
    url = f"https://api.assemblyai.com/v2/transcript/{tid}"
    while True:
        r = requests.get(url, headers=HEADERS).json()
        status = r.get("status")
        if status == "completed":
            return r
        if status == "error":
            raise RuntimeError(r.get("error"))
        time.sleep(3)


@app.route("/transcribir", methods=["POST"])
def transcribir():
    try:
        body    = request.json or {}
        vid_url = body.get("url", "").strip()
        src     = body.get("language", "auto")

        if not vid_url:
            return jsonify({"error": "Falta la URL de YouTube."}), 400

        try:
            audio_path = download_audio_from_youtube(vid_url)
        except DownloadError as de:
            return jsonify({
                "error": "No se pudo descargar el audio. Vérifica la URL, las cookies o restricciones regionales."
            }), 400

        upload_url = upload_to_assemblyai(audio_path)
        tid        = start_transcription(upload_url, src)
        wait_for_transcript(tid)

        srt_text = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{tid}/srt",
            headers=HEADERS
        ).text

        try:
            os.remove(audio_path)
        except OSError:
            pass

        return jsonify({"transcripcion": srt_text})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port       = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)