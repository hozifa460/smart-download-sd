# 🌐 Turbo Download Manager Pro — Browser Integration Extension

High-performance browser download interceptor for **Google Chrome, Microsoft Edge, Brave, and Mozilla Firefox**.

---

## ⚡ How It Works
When you click a download link or start a file download in your browser, this WebExtension intercepts the request, cancels the standard browser download, and transfers the link directly to **Turbo Download Manager Pro** via a local IPC loopback server (`http://127.0.0.1:9242`).

Your downloads then benefit immediately from:
- **Dynamic Multi-Chunk Acceleration** (TDM adaptive midpoint candidate splitting).
- **Smooth Live Speed Limiter** (Token Bucket rate limiter slider).
- **Segmented visual byte map and instant pause/resume**.

---

## 🚀 Installation Guide

### 1. Google Chrome & Brave Browser
1. Open your browser and navigate to `chrome://extensions` (or `brave://extensions`).
2. Toggle on **"Developer mode"** in the top-right corner.
3. Click the **"Load unpacked"** button in the top-left toolbar.
4. Select this `extension` directory (the folder containing `manifest.json`).
5. The extension icon ⚡ will appear in your browser extension toolbar! Pin it for quick access.

---

### 2. Microsoft Edge
1. Navigate to `edge://extensions`.
2. Enable **"Developer mode"** from the left sidebar toggle.
3. Click **"Load unpacked"**.
4. Select this `extension` directory.
5. The extension will be installed and active immediately.

---

### 3. Mozilla Firefox
1. Open Firefox and navigate to `about:debugging#/runtime/this-firefox`.
2. Click **"Load Temporary Add-on..."**.
3. Select the `manifest.json` file inside this `extension` directory.
4. The extension is now loaded and connected to Turbo Download Manager Pro.

---

## 🛠️ Features & Usage
- **Automatic Interception:** Automatically redirects archive files (`.zip`, `.rar`, `.7z`, `.iso`), video & audio streams (`.mp4`, `.mkv`, `.mp3`), and application packages (`.exe`, `.msi`, `.dmg`, `.apk`) to Turbo Download Manager Pro.
- **Context Menu:** Right-click on any download link, image, or video on any page and choose **"⚡ Download with Turbo Download Manager"**.
- **One-Click Page / Video Download:** Click the extension icon in your browser toolbar and press **"📥 Download Current Tab / Video"** to capture streaming links (such as YouTube videos!).
- **Safe Fallback:** If Turbo Download Manager Pro is not open, the extension gracefully allows your browser to download files normally without dropping them.
