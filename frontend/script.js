console.log("script.js se está ejecutando");

let rawSrt = '';
let cues   = [];

const getBtn            = document.getElementById("getSubtitles");
const display           = document.getElementById("subtitleDisplay");
const downloadBtn       = document.getElementById("downloadSrt");
const copyBtn           = document.getElementById("copyText");
const progressContainer = document.getElementById("progressContainer");
const progressBar       = document.getElementById("progressBar");

getBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  const videoUrl = document.getElementById("videoUrl").value.trim();
  const language = document.getElementById("language").value;
  if (!videoUrl) {
    display.textContent = "Por favor ingresa una URL de YouTube válida.";
    return;
  }

  getBtn.disabled               = true;
  getBtn.textContent            = "Cargando...";
  progressContainer.style.display = "flex";
  progressBar.removeAttribute("value");
  display.textContent           = "";

  try {
    const resp = await fetch("/transcribir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: videoUrl, language: language })
    });

    if (!resp.ok) {
      throw new Error(`Error en servidor: ${resp.status} ${resp.statusText}`);
    }

    const data = await resp.json();

    if (data.transcripcion) {
      rawSrt = data.transcripcion;
      cues   = parseSrt(rawSrt);
      renderTimestamped();

      downloadBtn.style.display = "inline-block";
      copyBtn.style.display     = "inline-block";
    } else if (data.error) {
      throw new Error(data.error);
    } else {
      throw new Error("Respuesta inesperada del servidor");
    }

  } catch (err) {
    console.error(err);
    alert("Ocurrió un error: " + err.message);
    display.textContent = `Error: ${err.message}`;
  } finally {
    getBtn.disabled               = false;
    getBtn.textContent            = "Obtener subtítulos";
    progressContainer.style.display = "none";
    progressBar.value             = 0;
  }
});

downloadBtn.addEventListener("click", () => {
  const blob = new Blob([rawSrt], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = "subtitles.srt";
  a.click();
  URL.revokeObjectURL(url);
});

copyBtn.addEventListener("click", () => {
  const text = cues.map(cue => cue.text).join(" ");
  navigator.clipboard.writeText(text)
    .then(() => alert("Texto copiado al portapapeles"))
    .catch(err => {
      console.error("Error copiando al portapapeles", err);
      alert("Error copiando al portapapeles");
    });
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then(reg => {console.log('Service Worker registrado:', reg.scope);
      })
      .catch(err => {console.error('Fallo al registrar SW:', err);
    });
  });
}

function parseSrt(srt) {
  const blocks = srt.trim().split(/\n\s*\n/);
  return blocks.map(block => {
    const lines = block.split('\n');
    const [start] = lines[1].split(' --> ');
    const text    = lines.slice(2).join(' ');
    return { start: start.split(',')[0], text };
  });
}

function renderTimestamped() {
  display.textContent = cues
    .map(cue => `[${cue.start}] ${cue.text}`)
    .join("\n");
}

function renderScript() {
  display.textContent = cues
    .map(cue => cue.text)
    .join(" ");
}

document.getElementById('viewTimestamped')
  .addEventListener('click', renderTimestamped);

document.getElementById('viewScript')
  .addEventListener('click', renderScript);