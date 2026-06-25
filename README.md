# 🎬 VDownloader

VDownloader is a premium, lightweight local web application that allows you to download videos from virtually any website (YouTube, Twitter/X, Instagram, TikTok, Vimeo, Reddit, and 1000+ more). It features a modern, vibrant light-themed UI with glassmorphic panels, real-time download progress (speed and ETA), and automatic disk cleanup.

---

## ✨ Features

- **Universal Support**: Powered by `yt-dlp` to download from 1000+ websites.
- **Vibrant UI**: Beautiful, fully responsive light-mode interface that looks stunning on both desktop and mobile.
- **Quality Selection**: Fetches and displays all available video resolutions and audio-only formats before downloading.
- **Real-Time Progress**: Interactive progress bar with live speed, percentage, and ETA updates.
- **Zero-Waste Disk Usage**: Automatically purges downloaded videos from the server's disk the moment the file transfer to your device completes.
- **One-Click Startup**: Simple Windows launcher that automatically configures your environment.

---

## 🚀 Local Installation (Windows / macOS / Linux)

### The One-Click Way (Windows)
1. Ensure you have **Python 3.9+** installed and added to your system PATH.
2. Double-click the **`start.bat`** file.
3. The script will automatically install/upgrade dependencies, update `yt-dlp`, start the server at `http://localhost:7878`, and open your default browser.

### The Manual Way
1. **Clone the repository**:
   ```bash
   git clone <your-repository-url>
   cd VDownloader
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the app**:
   ```bash
   python app.py
   ```
4. Open your browser and navigate to `http://localhost:7878`.

---

## 📱 How to Use on Mobile (iOS / Android)

### Option 1: Using your Home Wi-Fi (No setup required)
1. Make sure your computer (running the server) and your phone are on the **same Wi-Fi network**.
2. Run `start.bat` on your computer.
3. Note your computer's local IP address (printed on startup, e.g., `http://192.168.1.50:7878`).
4. Open that address in your mobile browser. You can paste video links from your phone, download them, and save them directly to your device!

### Option 2: Running Directly on Android (Offline/On the Go)
You can run the entire server directly on your Android device using the free **Termux** app:
1. Download **Termux** from F-Droid or GitHub.
2. Open Termux and install the dependencies:
   ```bash
   pkg update && pkg install git python ffmpeg
   ```
3. Clone your repository:
   ```bash
   git clone <your-repository-url>
   cd VDownloader
   ```
4. Install Python requirements:
   ```bash
   pip install -r requirements.txt
   ```
5. Launch the app:
   ```bash
   python app.py
   ```
6. Open your mobile browser and go to `http://localhost:7878`.

---

## ☁️ Deploying to Render (Access From Anywhere)

This repository is **1-click deploy ready** for cloud hosting on [Render](https://render.com) using Docker.

1. Push this project to a private or public **GitHub** repository.
2. Log into **Render.com**.
3. Click **New +** -> **Blueprint**.
4. Connect your GitHub account and select this repository.
5. Render will automatically read the `render.yaml` file, spin up a secure container with Python and `ffmpeg` pre-configured, and deploy your app under a public URL (e.g., `https://my-vdownloader.onrender.com`).

---

## 🛠️ Tech Stack

- **Backend**: Python, Flask, `yt-dlp` (Native Python API)
- **Frontend**: HTML5, CSS3 (Vanilla Glassmorphism Layout), Modern JavaScript
- **Production Server**: `gunicorn`
- **Containerization**: Docker (configured for automatic `ffmpeg` integration)
- **Communications**: Server-Sent Events (SSE) for real-time progress streaming
