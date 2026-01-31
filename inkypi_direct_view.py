from flask import Flask, send_file, jsonify, render_template_string, request

import io
import json
import os
import requests
import time
from pathlib import Path

from PIL import Image, ImageOps, ImageEnhance


app = Flask(__name__)

# --- CONFIGURATION PATHS ---

# Find InkyPi Path
def find_inkypi_src(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "config" / "device_dev.json").exists() and (p / "static" / "images").exists():
            return p
    return (Path.home() / "InkyPi" / "src").resolve()  # final fallback

BASE_DIR = Path(os.getenv("INKYPI_SRC", find_inkypi_src(Path(__file__).resolve().parent))).expanduser().resolve()

SETTINGS_FILE = Path(os.getenv("INKYPI_SETTINGS_FILE", BASE_DIR / "config" / "device_dev.json")).expanduser().resolve()
IMAGE_PATH    = Path(os.getenv("INKYPI_IMAGE_PATH",    BASE_DIR / "static" / "images" / "current_image.png")).expanduser().resolve()

# Confirmation
print(f"--- Path Debugging ---")
print(f"Base Directory: {BASE_DIR}")
print(f"Looking for Settings at: {SETTINGS_FILE} (Exists: {SETTINGS_FILE.exists()})")
print(f"Looking for Image at: {IMAGE_PATH} (Exists: {IMAGE_PATH.exists()})")
print(f"----------------------")


#Get InkyPi Settings
def get_inkypi_settings():
    default_settings = {
        "orientation": "horizontal",
        "inverted_image": False,
        "brightness": 1.0,
        "contrast": 1.0,
        "sharpness": 1.0,
        "saturation": 1.0
    }

    def normalize(data: dict) -> dict:
        data = data or {}
        img_opts = data.get("image_settings", {}) or {}
        return {
            "orientation": data.get("orientation", "horizontal"),
            "inverted_image": bool(data.get("inverted_image") or data.get("invertImage") or False),
            "brightness": float(img_opts.get("brightness", 1.0)),
            "contrast": float(img_opts.get("contrast", 1.0)),
            "sharpness": float(img_opts.get("sharpness", 1.0)),
            "saturation": float(img_opts.get("saturation", 1.0)),
        }

    # 1) Try tje .json file first
    if SETTINGS_FILE.exists():
        try:
            with open(str(SETTINGS_FILE), "r") as f:
                data = json.load(f)
            return normalize(data)
        except Exception:
            pass


    # 2) Fallback to main app config endpoint
    try:
        response = requests.get("http://127.0.0.1:5000/get_current_config", timeout=1)
        if response.status_code == 200:
            return normalize(response.json())
    except Exception:
        pass

    # 3) Final fallback
    return default_settings


# --- Some HTML ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>InkyPi Unified Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: white; display: flex; flex-direction: column; height: 100vh; margin: 0; }
        .header { padding: 15px 25px; background: #1f1f1f; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }
        .container { display: flex; flex: 1; overflow: hidden; }
        .preview-area { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #000; padding: 20px; }
        .sidebar { width: 350px; background: #1f1f1f; padding: 25px; border-left: 1px solid #444; overflow-y: auto; }
        .inky-screen {
            border: 5px solid #2a2a2a; border-radius: 8px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.7); max-width: 95%; max-height: 85%;
        }
        .stat-group { background: #2a2a2a; border-radius: 8px; padding: 15px; margin-bottom: 20px; border: 1px solid #3d3d3d; }
        .stat-row { display: flex; justify-content: space-between; margin-bottom: 12px; font-family: 'Courier New', monospace; font-size: 0.9em; }
        .label { color: #888; text-transform: uppercase; letter-spacing: 1px; }
        .value { color: #00ff95; font-weight: bold; }
        .btn { background: #2c66b1; color: white; border: none; padding: 12px; width: 100%; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.2s; }
        .btn:hover { background: #3a80db; }
        .live-indicator { height: 8px; width: 8px; background: #00ff00; border-radius: 50%; display: inline-block; margin-right: 8px; box-shadow: 0 0 8px #00ff00; }
        h3 { margin-top: 0; font-weight: 400; color: #ccc; }
    </style>
</head>
<body>
    <div class="header">
        <div style="font-weight: bold; font-size: 1.2em;">InkyPi <span style="color: #4db8ff;">Direct-View</span></div>
        <div><span class="live-indicator"></span> <span id="device-ip">Detecting...</span></div>
    </div>

    <div class="container">
        <div class="preview-area">
            <img src="/image" id="previewImg" class="inky-screen" onerror="this.src='https://via.placeholder.com/600x400?text=Waiting+for+Image...'">
        </div>

        <div class="sidebar">
            <h3>Active InkyPi Settings</h3>

            <div class="stat-group" id="settings-content"></div>

            <div style="height:12px;"></div>

            <button class="btn" onclick="downloadCurrentImage()">Download Image</button>
            <div id="save-status" style="margin-top:10px; font-family:'Courier New', monospace; font-size:0.85em; color:#ccc;"></div>

            <p style="font-size: 0.75em; color: #666; margin-top: 20px; line-height: 1.4;">
                Current Image Path: <br><code>{{ img_path }}</code>
            </p>
        </div>
    </div>

    <script>
      function updateIPDisplay() {
        const el = document.getElementById('device-ip');
        if (el) el.textContent = window.location.host;
      }

      async function refresh() {
        const img = document.getElementById('previewImg');
        if (img) img.src = '/image?t=' + Date.now();

        try {
          const res = await fetch('/get_current_config');
          const data = await res.json();

          let html = '';
          for (const [key, val] of Object.entries(data)) {
            html += `<div class="stat-row"><span class="label">${key}</span><span class="value">${val}</span></div>`;
          }

          const settingsEl = document.getElementById('settings-content');
          if (settingsEl) settingsEl.innerHTML = html;
        } catch (e) {
          console.error("Config fetch failed", e);
        }
      }

      function downloadCurrentImage() {
        const statusEl = document.getElementById('save-status');
        if (statusEl) statusEl.textContent = "Downloading...";

        const d = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        const filename =
          `inkypi_${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_` +
          `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}.png`;

        const url = `/image?t=${Date.now()}`;

        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();

        if (statusEl) statusEl.textContent = "Download started: " + filename;
      }

      window.refresh = refresh;
      window.downloadCurrentImage = downloadCurrentImage;

      window.onload = () => {
        updateIPDisplay();
        refresh();
      };

      setInterval(refresh, 15000);
    </script>
</body>
</html>
"""



# --- ROUTES ---


@app.route('/get_current_config')
def get_current_config():
    return jsonify(get_inkypi_settings())


@app.route('/')
def dashboard():
    return render_template_string(
        DASHBOARD_HTML,
        img_path=str(IMAGE_PATH)
    )


@app.route('/image')
def serve_image():
    if not IMAGE_PATH.exists():
        return "Image not found on disk", 404

    settings = get_inkypi_settings()

    # Open image safely (handles file mid-write)
    img = None
    for _ in range(3):
        try:
            img = Image.open(str(IMAGE_PATH)).convert("RGB")
            break
        except Exception:
            time.sleep(0.05)
    if img is None:
        return "Image read error (file mid-write)", 500

    # Invert
    if settings.get("inverted_image"):
        img = ImageOps.invert(img)

    # Enhancements
    img = ImageEnhance.Brightness(img).enhance(settings["brightness"])
    img = ImageEnhance.Contrast(img).enhance(settings["contrast"])
    img = ImageEnhance.Color(img).enhance(settings["saturation"])
    img = ImageEnhance.Sharpness(img).enhance(settings["sharpness"])

    # Orientation (optional)
    # if (settings.get("orientation") or "").lower() == "vertical":
    #     img = img.rotate(90, expand=True)

    # Spectra 6 palette (6 colors, paletted output)
    palette_data = [
        0, 0, 0,          # Black
        255, 255, 255,    # White
        0, 255, 0,        # Green
        0, 0, 255,        # Blue
        255, 0, 0,        # Red
        255, 255, 0       # Yellow
    ]
    palette_img = Image.new("P", (1, 1))
    palette_img.putpalette(palette_data + [0] * (768 - len(palette_data)))

    img = img.quantize(palette=palette_img, dither=Image.FLOYDSTEINBERG)

    img_io = io.BytesIO()
    img.save(img_io, "PNG", optimize=True)
    img_io.seek(0)
    return send_file(img_io, mimetype="image/png")

# Run on port 5010 or choose another port
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010)

