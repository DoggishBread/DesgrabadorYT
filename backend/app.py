import os
import base64
import time
import traceback
import requests
import yt_dlp
import re

from yt_dlp.utils import DownloadError
from pytube import YouTube
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
API_KEY     = os.getenv("ASSEMBLYAI_API_KEY")
HEADERS     = {"authorization": API_KEY}
COOKIE_FILE = os.getenv("YTDLP_COOKIE_FILE", "")

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, os.pardir, "frontend")
AUDIO_FOLDER = os.path.join(BASE_DIR, "audio")
os.makedirs(AUDIO_FOLDER, exist_ok=True)

B64 = os.getenv("YTDLP_COOKIE_B64", "")
if B64:
    path = os.path.join(BASE_DIR, "cookies.txt")
    with open(path, "wb") as f:
        f.write(base64.b64decode(B64))
    COOKIE_FILE = path
    print("→ Cookiefile escrito desde B64 en:", COOKIE_FILE)

print(">>> COOKIE_FILE path:", COOKIE_FILE)
print(">>> Existe en disco? ", os.path.isfile(COOKIE_FILE))
if os.path.isfile(COOKIE_FILE):
    size = os.path.getsize(COOKIE_FILE)
    print(f">>> Tamaño cookies: {size} bytes")
    with open(COOKIE_FILE, "r", errors="ignore") as f:
        lines = f.readlines()
        print(">>> Primeras 3 líneas de cookies:\n", "".join(lines[:3]))

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve(path):
    return send_from_directory(FRONTEND_DIR, path)

def download_with_yt_dlp(url: str) -> str:
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(AUDIO_FOLDER, "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }],
        "geo_bypass": True,
        "force_ipv4": True,
        "source_address": "0.0.0.0",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/115.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9"
        },
        "force_generic_extractor": True,

        "cookiefile": COOKIE_FILE,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.join(AUDIO_FOLDER, f"{info['id']}.mp3")

def download_with_pytube(url: str) -> str:
    """
    Descarga audio con pytube, genera un .mp4 y lo convierte a .mp3 con ffmpeg.
    """
    yt = YouTube(url)
    stream = yt.streams.filter(only_audio=True, file_extension="mp4")\
                       .order_by("abr").desc().first()
    if not stream:
        raise RuntimeError("pytube no encontró streams de audio.")
    mp4_path = stream.download(output_path=AUDIO_FOLDER)
    mp3_path = os.path.splitext(mp4_path)[0] + ".mp3"

    cmd = f'ffmpeg -y -i "{mp4_path}" "{mp3_path}"'
    if os.system(cmd) != 0:
        raise RuntimeError("Error convirtiendo MP4 a MP3 con ffmpeg.")
    os.remove(mp4_path)
    return mp3_path

def download_audio_from_youtube(url: str) -> str:
    """
    1) yt-dlp directo
    2) Invidious mirrors
    3) pytube fallback
    """
    try:
        print("Probando con yt_dlp:", url)
        return download_with_yt_dlp(url)
    except DownloadError as e1:
        print("yt_dlp falló:", e1)

    invidious_hosts = [
        "yewtu.be",
        "yewtu.eu.org",
        "yewtu.snopyta.org"
    ]
    for host in invidious_hosts:
        alt = re.sub(
            r"https?://(www\.)?youtube\.com/watch",
            f"https://{host}/watch",
            url
        )
        try:
            print("🔄 Probando Invidious:", alt)
            return download_with_yt_dlp(alt)
        except DownloadError as e2:
            print(f"Invidious {host} falló:", e2)

    try:
        print("Intentando fallback con pytube")
        return download_with_pytube(url)
    except Exception as e3:
        print("pytube falló:", e3)
        raise DownloadError("No se pudo descargar el video por ningún método.")

def upload_to_assemblyai(path: str) -> str:
    with open(path, "rb") as f:
        r = requests.post("https://api.assemblyai.com/v2/upload",
                          headers=HEADERS, files={"file": f})
    r.raise_for_status()
    url = r.json().get("upload_url")
    if not url:
        raise RuntimeError(f"No upload_url: {r.text}")
    return url

def start_transcription(audio_url: str, lang: str) -> str:
    payload = {"audio_url": audio_url}
    if lang != "auto":
        payload["language_code"] = lang
    r = requests.post("https://api.assemblyai.com/v2/transcript",
                      json=payload, headers=HEADERS)
    r.raise_for_status()
    tid = r.json().get("id")
    if not tid:
        raise RuntimeError(f"No se obtuvo ID: {r.text}")
    return tid

def wait_for_transcript(tid: str) -> dict:
    url = f"https://api.assemblyai.com/v2/transcript/{tid}"
    while True:
        r = requests.get(url, headers=HEADERS).json()
        if r.get("status") == "completed":
            return r
        if r.get("status") == "error":
            raise RuntimeError(r.get("error"))
        time.sleep(3)

@app.route("/transcribir", methods=["POST"])
def transcribir():
    try:
        data    = request.json or {}
        vid     = data.get("url", "").strip()
        lang    = data.get("language", "auto")

        if not vid:
            return jsonify(error="Falta la URL de YouTube."), 400

        audio      = download_audio_from_youtube(vid)
        upload_url = upload_to_assemblyai(audio)
        tid        = start_transcription(upload_url, lang)
        wait_for_transcript(tid)

        srt = requests.get(f"https://api.assemblyai.com/v2/transcript/{tid}/srt",
                           headers=HEADERS).text

        try:
            os.remove(audio)
        except:
            pass

        return jsonify(transcripcion=srt)

    except Exception as e:
        traceback.print_exc()
        code = 400 if isinstance(e, DownloadError) else 500
        return jsonify(error=str(e)), code

@app.route("/_nettest")
def nettest():
    try:
        r = requests.get("https://www.youtube.com/", timeout=5)
        return f"HEAD https://youtube.com → {r.status_code}"
    except Exception as e:
        return f"ERROR: {e}"

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() == "true"
    app.run("0.0.0.0", port=port, debug=debug)