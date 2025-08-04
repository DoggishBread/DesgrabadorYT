import os
import time
import base64
import requests
from pytube import YouTube
from pytube.extract import video_id

AUDIO_FILENAME = "temp_audio.mp3"
ASSEMBLY_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")
HEADERS = {"authorization": ASSEMBLY_API_KEY}


def cargar_cookies():
    cookie_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(cookie_path):
        print("→ Usando cookies.txt")
        with open(cookie_path, "r", encoding="utf-8") as f:
            return f.read()
    if not os.path.exists("cookies.txt"):
        print("⚠️ Advertencia: cookies.txt no encontrado. Algunas descargas pueden fallar.")
    return None

def descargar_audio(url):
    print(f"→ Descargando audio desde: {url}")
    cookies_str = cargar_cookies()

    if cookies_str:
        cookie_file = "temp_cookies.txt"
        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write(cookies_str)
        yt = YouTube(url, use_oauth=False, allow_oauth_cache=True)
    else:
        yt = YouTube(url)

    audio_stream = yt.streams.filter(only_audio=True).first()
    audio_stream.download(filename=AUDIO_FILENAME)

    if os.path.exists("temp_cookies.txt"):
        os.remove("temp_cookies.txt")


def subir_audio_a_assemblyai():
    print("→ Subiendo audio a AssemblyAI")
    with open(AUDIO_FILENAME, "rb") as f:
        response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=HEADERS,
            files={"file": f}
        )
    response.raise_for_status()
    return response.json()["upload_url"]


def solicitar_transcripcion(upload_url, idioma):
    print(f"→ Solicitando transcripción en idioma: {idioma}")
    response = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=HEADERS,
        json={
            "audio_url": upload_url,
            "language_code": idioma
        }
    )
    response.raise_for_status()
    return response.json()["id"]


def esperar_resultado(transcript_id):
    print("→ Esperando resultado de transcripción")
    url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"

    while True:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        result = response.json()

        if result["status"] == "completed":
            print("✓ Transcripción completada")
            return result["text"]
        elif result["status"] == "error":
            raise Exception(f"Error en transcripción: {result['error']}")

        print("... esperando 3s")
        time.sleep(3)


def limpiar_archivos():
    if os.path.exists(AUDIO_FILENAME):
        os.remove(AUDIO_FILENAME)


def procesar_transcripcion(url, idioma="es"):
    try:
        descargar_audio(url)
        upload_url = subir_audio_a_assemblyai()
        transcript_id = solicitar_transcripcion(upload_url, idioma)
        texto = esperar_resultado(transcript_id)
        return texto
    except Exception as e:
        print(f"✗ Error: {e}")
        return None
    finally:
        limpiar_archivos()