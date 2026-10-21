# ⚡ Turbo Download Manager (TDM)
> **High-Performance Multi-Threaded Download Manager with YouTube Support & Browser Integration**  
> *مدير تحميل فائق السرعة متعدد المسارات مع دعم يوتيوب وتكامل كامل مع المتصفحات*

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6.svg)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-118%20passed-brightgreen.svg)](#-test-suites)
[![Release](https://img.shields.io/badge/release-v1.0.0-orange.svg)](https://github.com/hozifa460/turbo-downlod-manager--TDM-/releases)

---

## 🌐 Language Navigation / تصفح اللغات
- [English Documentation](#-english-documentation)
  - [Key Features](#-key-features)
  - [Architecture & Tech Stack](#-architecture--tech-stack)
  - [Installation & Quick Start](#-installation--quick-start)
  - [Browser Extension Setup](#-browser-extension-setup)
  - [Building Standalone Binary (.exe)](#-building-standalone-binary-exe)
  - [Test Suites & Verification](#-test-suites--verification)
- [التوثيق باللغة العربية](#-التوثيق-باللغة-العربية)
  - [الميزات الرئيسية](#-الميزات-الرئيسية)
  - [الهندسة المعمارية والتقنيات المستخدمة](#-الهندسة-المعمارية-والتقنيات-المستخدمة)
  - [طريقة التثبيت والتشغيل](#-طريقة-التثبيت-والتشغيل)
  - [تثبيت إضافة المتصفح](#-تثبيت-إضافة-المتصفح)
  - [بناء ملف التشغيل المستقل (.exe)](#-بناء-ملف-التشغيل-المستقل-exe)
  - [الاختبارات الآلية](#-الاختبارات-الآلية)

---

## 📖 English Documentation

### 🚀 Key Features

1. **⚡ Dynamic Multi-Segment Acceleration (IDM-Style)**
   - Splits files into up to **32 concurrent byte-range connections**.
   - Dynamic chunk stealing: faster threads dynamically take over chunks from lagging threads to maximize total throughput.
   - Resumable downloads: saves state in `.idm_parts` manifest files allowing pause/resume even across system reboots.

2. **🎥 Adaptive YouTube & Media Downloader**
   - Direct video stream resolution with quality selector (4K, 2K, 1080p, 720p, 480p, 360p, or Audio-only MP3/M4A).
   - High-speed separate audio/video stream download with lossless `ffmpeg` remuxing (`-c copy`).
   - Clean metadata extraction, duration display, and OS-reserved character sanitization.

3. **🌐 Web Browser Integration & Native Messaging**
   - **Chrome / Microsoft Edge / Brave** Chromium browser extension (Manifest V3).
   - Dual-channel communication architecture:
     - **Native Messaging Host** protocol (length-prefixed stdin/stdout) for instant desktop handoff.
     - **Local Loopback HTTP Bridge** (`127.0.0.1:18942`) with CORS preflight support as an automatic fallback.
   - Automatic one-click Windows Registry configuration script (`register_browser.py`).

4. **📋 Clipboard Auto-Sniffer**
   - Real-time clipboard watcher that detects download links and YouTube URLs immediately upon copying.
   - Instant non-intrusive modal prompt to start downloading without manual copy-pasting.

5. **🎨 Modern High-DPI Desktop Interface**
   - Sleek modern dark mode interface with neon accents, custom frameless title bar, and draggable window.
   - Full **Per-Monitor High-DPI Awareness (v2/v1)**: crisp text and UI scaling on 1080p, 2K, and 4K displays.
   - Multi-resolution icon set (`app_icon.ico` bundled with 16x16, 24x24, 32x32, 48x48, 64x64, 128x128, and 256x256).

6. **⏱️ Speed Limiter & Bandwidth Throttling**
   - Token-Bucket algorithm for accurate, smooth network bandwidth throttling.

---

### 🏗 Architecture & Tech Stack

```text
[ Browser Extension (MV3) ]
         │
         ├──► (Primary) Native Messaging Host (native_messaging_host.py) ──┐
         │                                                                  ├──► [ TurboDownloader Core ]
         └──► (Fallback) HTTP Loopback Bridge (browser_bridge.py:18942) ───┘           │
                                                                                       ├── Multi-part Engine
                                                                                       ├── YouTube Resolver (yt-dlp)
                                                                                       ├── Lossless Merger (ffmpeg)
                                                                                       └── Modern High-DPI UI
```

| Component | Technology | Description |
|---|---|---|
| **GUI Framework** | Python `tkinter` + High-DPI Win32 API | Custom dark-mode frameless interface |
| **Download Engine** | Custom HTTP ThreadPool + Socket Streaming | Dynamic multi-part chunking & resumption |
| **YouTube Pipeline** | `yt-dlp` + `ffmpeg` | Stream resolution & lossless remuxing |
| **Browser Bridge** | HTTP Server + Chrome Native Messaging API | Full browser download interception |
| **Asset Pipeline** | PIL (Pillow) + Windows Manifest | 4K High-DPI icons and visual scaling |

---

### 💻 Installation & Quick Start

#### Option 1: Download Pre-compiled Binary (.exe)
Download `TurboDownloader.exe` directly from the [GitHub Releases](https://github.com/hozifa460/turbo-downlod-manager--TDM-/releases) page. No Python installation required!

#### Option 2: Run from Source
1. **Clone the repository:**
   ```bash
   git clone https://github.com/hozifa460/turbo-downlod-manager--TDM-.git
   cd turbo-downlod-manager--TDM-
   ```

2. **Install dependencies:**
   ```bash
   pip install pillow yt-dlp
   ```
   *(Optional for YouTube high-definition merging: ensure `ffmpeg` is installed in your PATH).*

3. **Run application:**
   ```bash
   python turbo_downloader.py
   ```

---

### 🔌 Browser Extension Setup

1. Open your Chromium-based browser (Chrome, Edge, or Brave).
2. Navigate to `chrome://extensions` or `edge://extensions`.
3. Enable **Developer mode** (toggle in the top-right corner).
4. Click **Load unpacked** and select the `extension/` folder inside this repository.
5. Register the Native Messaging Host in the Windows Registry by running:
   ```bash
   python register_browser.py --register
   ```
   *To verify registration status:*
   ```bash
   python register_browser.py --status
   ```

---

### 🔨 Building Standalone Binary (.exe)

You can compile a standalone single-file executable using PyInstaller:
```bash
pip install pyinstaller
pyinstaller TurboDownloader.spec
```
The output executable will be generated at `dist/TurboDownloader.exe`.

---

### 🧪 Test Suites & Verification

The project includes an extensive suite of **118 automated tests**:
```bash
# Run core downloader & chunking engine tests (24 tests)
python test_suite.py

# Run YouTube, browser bridge, and native messaging tests (83 tests)
python test_features.py

# Run High-DPI and multi-resolution assets tests (11 tests)
python test_dpi_and_assets.py
```

---

## 🌍 التوثيق باللغة العربية

### 🚀 الميزات الرئيسية

1. **⚡ تسريع التحميل متعدد المسارات بتجزئة ديناميكية (مثل IDM)**
   - تقسيم الملف الواحد إلى ما يصل إلى **32 اتصال متوازي ومتزامن**.
   - خوارزمية سرقة المقاطع الذكية (Dynamic Chunk Stealing): استغلال الاتصالات الأسرع لإنهاء المقاطع المتبقية من الاتصالات البطيئة.
   - استئناف التحميل الموثوق: حفظ دوري لبيانات المقاطع في ملفات `.idm_parts` للتمكن من استئناف التحميل حتى بعد إعادة تشغيل الجهاز أو انقطاع الإنترنت.

2. **🎥 محمل وسائط ويوتيوب متقدم ومتكيف**
   - استخراج وتحديد جودات الفيديو والصوت بدقة (4K، 2K، 1080p، 720p، 480p، 360p، أو ملف صوتي MP3/M4A منفصل).
   - دمج فائق السرعة وبدون فقدان للجودة (Lossless Remuxing) بين مسار الفيديو ومسار الصوت باستخدام `ffmpeg` عبر خيار `-c copy`.
   - تنظيف وتطهير أسماء الملفات تلقائياً من الرموز الممنوعة في نظام ويندوز.

3. **🌐 تكامل كامل مع المتصفحات (Chrome, Edge, Brave)**
   - إضافة متصفح حديثة تدعم معيار Manifest V3.
   - هيكل اتصال ثنائي فائق المرونة:
     - عبر بروتوكول **Native Messaging Host** المباشر والآمن.
     - عبر جسر محلي **HTTP Loopback Server** على المنفذ `18942` مع دعم كامل لـ CORS.
   - سكريبت تسجيل تلقائي في سجلات ويندوز (Registry) بضغطة زر واحدة.

4. **📋 مراقب الحافظة الذكي (Clipboard Auto-Sniffer)**
   - مراقبة ذكية للحافظة والتعرف التلقائي والفوري على روابط التحميل وروابط يوتيوب بمجرد نسخها.
   - نافذة تفاعلية سريعة تتيح بدء التحميل فوراً وتحديد الجودة دون الحاجة للنسخ واللصق اليدوي.

5. **🎨 واجهة مستخدم عصرية بتصميم داكن ودعم شاشات الدقة العالية (High-DPI)**
   - تصميم حديث بدون إطار (Frameless) مع شريط علوي قابل للسحب وألوان داكنة مريحة للعين.
   - دعم كامل وتلقائي لتدرج الشاشات عالية الدقة (Per-Monitor High-DPI Awareness v2/v1) لضمان وضوح فائق على شاشات 1080p و 2K و 4K.
   - حزمة أيقونات متعددة الأحجام مدمجة من 16x16 حتى 256x256 بكسل.

6. **⏱️ محدد سرعة التحميل (Bandwidth Throttler)**
   - خوارزمية Token-Bucket للتحكم الدقيق في استهلاك سرعة الإنترنت أثناء التحميل.

---

### 💻 التثبيت والتشغيل السريع

#### الطريقة الأولى: تحميل ملف التشغيل المباشر (.exe)
يمكنك تحميل الملف التنفيذي الجاهز مباشرة من قسم [الإصدارات على GitHub](https://github.com/hozifa460/turbo-downlod-manager--TDM-/releases) دون الحاجة لتثبيت بايثون.

#### الطريقة الثانية: التشغيل عبر الكود المصدري
1. **استنساخ المستودع:**
   ```bash
   git clone https://github.com/hozifa460/turbo-downlod-manager--TDM-.git
   cd turbo-downlod-manager--TDM-
   ```

2. **تثبيت المكتبات المطلوبة:**
   ```bash
   pip install pillow yt-dlp
   ```
   *(ملاحظة: لدمج جودات يوتيوب 1080p فما فوق، يفضل توفر `ffmpeg` على نظامك).*

3. **تشغيل البرنامج:**
   ```bash
   python turbo_downloader.py
   ```

---

### 🔌 تثبيت وتفعيل إضافة المتصفح

1. افتح متصفحك (Google Chrome أو Microsoft Edge أو Brave).
2. انتقل إلى إدارة الإضافات `chrome://extensions` أو `edge://extensions`.
3. قم بتفعيل **وضع المطور (Developer Mode)**.
4. اضغط على **تحميل حزمة غير مضغوطة (Load unpacked)** واختر مجلد `extension/` من داخل هذا المستودع.
5. سجّل البرنامج في نظام ويندوز لتمكين الإضافة من الاتصال به بتشغيل:
   ```bash
   python register_browser.py --register
   ```

---

### 🔨 بناء ملف تنفيذي مستقل (.exe)

لبناء نسخة تنفيذية مجمعة بالكامل باستخدام PyInstaller:
```bash
pip install pyinstaller
pyinstaller TurboDownloader.spec
```
سيتم إنشاء الملف التنفيذي في المسار: `dist/TurboDownloader.exe`.

---

### 🧪 الاختبارات الآلية

يحتوي المشروع على حزمة اختبارات شاملة تضم **118 اختباراً آلياً**:
```bash
# اختبار محرك التحميل والتجزئة المتعددة (24 اختبار)
python test_suite.py

# اختبار محلل يوتيوب وتكامل المتصفح (83 اختبار)
python test_features.py

# اختبار دقة الشاشات والأيقونات (11 اختبار)
python test_dpi_and_assets.py
```

---

## 📄 License
This project is licensed under the MIT License.
جميع الحقوق محفوظة للمشروع بموجب ترخيص MIT.
