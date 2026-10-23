import os
import sys
import json
import urllib.request
import urllib.error
import subprocess

REPO_OWNER = "hozifa460"
REPO_NAME = "smart-download-sd"
TAG = "v2.0.0"
RELEASE_NAME = "Smart Download (SD) v2.0.0 — Multi-Platform Social Media Downloader"

RELEASE_BODY = r"""# Smart Download (SD) v2.0.0 — Multi-Platform Social Media Downloader
## الإصدار الجديد v2.0.0 — مُنزّل وسائط وفيديوهات متكامل وعالي السرعة

---

### 🌟 English Highlights
Smart Download (SD) v2.0.0 introduces a major rebrand and architectural upgrade from the legacy Turbo Download Manager Pro. It brings full-featured video downloading from leading social media platforms, a modern high-DPI frameless UI, and a streamlined Windows installer.

- **Multi-Platform Social Media Downloader**: Effortlessly download high-definition videos and audio from **YouTube, TikTok, Instagram, Facebook, X (formerly Twitter), and Reddit**.
- **Transparent High-DPI Modern Icon**: Brand new pixel-perfect transparent application icon with full multi-resolution Windows support (16x16 up to 256x256).
- **Optimized Ultra-Compact Installer**: Optimized payload bundling reduces setup installer file size by over 43% (~56 MB down from ~105 MB).
- **High-Performance Multi-Segment Engine**: Lightning-fast parallel chunk downloads with dynamic midpoint splitting, rate limiting, and auto-reassembly.
- **Chrome & Edge Browser Integration**: Seamless native messaging extension integration with automatic one-click media capture.
- **Instant Zero-Elevation Background Startup**: Multi-tiered instant startup on Windows boot (Run key, Scheduled Task, and Startup shortcut) with zero elevation, starting silently in the tray.
- **Automatic `yt-dlp` Dynamic Self-Update Engine**: Automatically updates and loads the latest `yt-dlp` extractors in `%APPDATA%\SmartDownload\yt_dlp_plugin` without needing to rebuild or reinstall the `.exe`.
- **Built-in Application Auto-Updater**: Checks GitHub Releases for new versions in the background and provides a one-click **[⬇ Update Now]** upgrade experience.
- **Dual Distribution Options**:
  - `SmartDownload-Setup.exe`: Full Windows installer with zero-elevation installation, Desktop & Start Menu shortcuts, auto-startup, and clean uninstaller.
  - `SmartDownload.exe`: Ultra-portable standalone executable requiring no installation.

---

### 🌟 أبرز مميزات الإصدار باللغة العربية
يمثل الإصدار **Smart Download (SD) v2.0.0** نقلة نوعية وتطويراً شاملاً للهوية والأداء:

- **تحميل الفيديوهات من كافة منصات التواصل الاجتماعي**: دعم التحميل بأعلى جودة وصيغ متعددة من **تيك توك (TikTok)، إنستغرام (Instagram)، فيسبوك (Facebook)، إكس / تويتر (X/Twitter)، ريديت (Reddit)، ويوتيوب (YouTube)**.
- **تحديث ذاتي تلقائي لمحرك `yt-dlp` والبرنامج**: تحديث استخراج الفيديوهات تلقائياً في الخلفية مع نظام فحص وتحديث البرنامج بضغطة زر واحدة.
- **أيقونة شفافة فائقة الدقة (High-DPI)**: تصميم احترافي حديث بخلفية شفافة يدعم كافة شاشات العرض بدقة كاملة من 16×16 وحتى 256×256 بكسل.
- **مُثبّت فائق الرشاقة وصغير الحجم**: تقليل حجم ملف التثبيت بنسبة تفوق 43% (من ~105 ميجابايت إلى ~56 ميجابايت) عبر إزالة التكرار وربط التوافق ديناميكياً.
- **تشغيل تلقائي فوري في الخلفية بدون صلاحيات مسؤول**: بدء تلقائي صامت في شريط المهام عند إقلاع ويندوز عبر منظومة ثلاثية موثوقة (Run Key و Scheduled Task واختصار Startup) دون الحاجة لأي صلاحيات إدارية (UAC-free).
- **محرك تحميل خارق متعدد المسارات**: تجزئة ذكية ديناميكية للملفات أثناء التحميل لزيادة السرعة إلى أقصى حد ممكن مع إمكانية تحديد السرعة والإيقاف والاستئناف.
- **تكامل متكامل مع متصفحات Chrome و Edge**: التقاط الروابط تلقائياً عبر إضافة المتصفح الرسمية.
- **خيارات تشغيل مرنة**:
  - `SmartDownload-Setup.exe`: برنامج تثبيت سريع وسلس لا يتطلب صلاحيات مسؤول ويندوز مع دعم الاختصارات وبدء التشغيل التلقائي وإلغاء التثبيت النظيف.
  - `SmartDownload.exe`: نسخة محمولة (Portable) فورية تعمل مباشرة بدون تثبيت.
"""


def log(msg):
    print(msg, flush=True)


def get_git_credentials():
    p = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True
    )
    token = None
    username = None
    for line in p.stdout.splitlines():
        if line.startswith("username="):
            username = line.split("=", 1)[1].strip()
        elif line.startswith("password="):
            token = line.split("=", 1)[1].strip()
    if not token:
        raise RuntimeError("Could not retrieve GitHub PAT/token from git credential fill")
    return username, token


def api_request(url, token, data=None, method="GET", headers=None):
    req_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SmartDownload-ReleaseTool"
    }
    if headers:
        req_headers.update(headers)

    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif isinstance(data, bytes):
            body = data

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
            if resp.headers.get_content_type() == "application/json":
                return resp.status, json.loads(content.decode("utf-8"))
            return resp.status, content
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            return e.code, err_json
        except Exception:
            return e.code, err_body


def upload_asset_with_curl(upload_url, token, file_path):
    """Uses curl.exe for high-reliability binary streaming upload."""
    cmd = [
        "curl.exe",
        "-L",
        "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Accept: application/vnd.github+json",
        "-H", "Content-Type: application/octet-stream",
        "--data-binary", f"@{file_path}",
        upload_url
    ]
    log(f"[*] Running curl.exe to stream '{os.path.basename(file_path)}'...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"curl.exe failed with code {res.returncode}: {res.stderr}")
    try:
        data = json.loads(res.stdout)
        if isinstance(data, dict):
            if "errors" in data or ("message" in data and "id" not in data):
                raise RuntimeError(f"GitHub API error during upload of '{os.path.basename(file_path)}': {data}")
        return data
    except json.JSONDecodeError:
        return {"raw_output": res.stdout}


def main():
    username, token = get_git_credentials()
    log(f"[+] Retrieved git credentials for user: {username}")

    base_api = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

    # 1. Inspect release v2.0.0
    log(f"[*] Checking release {TAG}...")
    status, res = api_request(f"{base_api}/releases/tags/{TAG}", token)
    release_data = None
    if status == 200:
        log(f"[+] Release {TAG} exists (id: {res['id']}). Updating metadata...")
        release_data = res
        # Update name and body to ensure latest formatting
        update_payload = {
            "name": RELEASE_NAME,
            "body": RELEASE_BODY
        }
        api_request(f"{base_api}/releases/{res['id']}", token, data=update_payload, method="PATCH")
    elif status == 404:
        log(f"[*] Release {TAG} not found. Creating new release...")
        payload = {
            "tag_name": TAG,
            "target_commitish": "main",
            "name": RELEASE_NAME,
            "body": RELEASE_BODY,
            "draft": False,
            "prerelease": False
        }
        create_status, create_res = api_request(f"{base_api}/releases", token, data=payload, method="POST")
        if create_status in (200, 201):
            log(f"[+] Successfully created release {TAG} (id: {create_res['id']})!")
            release_data = create_res
        else:
            raise RuntimeError(f"Failed to create release: HTTP {create_status}: {create_res}")
    else:
        raise RuntimeError(f"Failed to inspect release: HTTP {status}: {res}")

    release_id = release_data["id"]
    upload_url_template = release_data["upload_url"]
    upload_base = upload_url_template.split("{")[0]
    log(f"[+] Upload URL base: {upload_base}")

    # Re-fetch latest release data to get current assets
    _, fresh_release = api_request(f"{base_api}/releases/{release_id}", token)
    existing_assets = {a["name"]: a for a in fresh_release.get("assets", [])}
    log(f"[*] Existing assets on release: {list(existing_assets.keys())}")

    assets_to_upload = [
        os.path.abspath(r"dist\SmartDownload.exe"),
        os.path.abspath(r"dist\SmartDownload-Setup.exe")
    ]

    for asset_path in assets_to_upload:
        asset_name = os.path.basename(asset_path)
        if not os.path.isfile(asset_path):
            raise FileNotFoundError(f"Asset file not found: {asset_path}")

        file_size = os.path.getsize(asset_path)
        log(f"\n[*] Evaluating '{asset_name}' ({file_size:,} bytes)...")

        # Check if already uploaded and valid size
        if asset_name in existing_assets:
            existing_info = existing_assets[asset_name]
            existing_size = existing_info.get("size", 0)
            existing_state = existing_info.get("state", "")
            if existing_size == file_size and existing_state == "uploaded":
                log(f"[+] Asset '{asset_name}' is already completely uploaded ({existing_size:,} bytes). Skipping.")
                continue
            else:
                log(f"[*] Deleting incomplete/mismatched existing asset (id: {existing_info['id']}, size: {existing_size:,})...")
                api_request(f"{base_api}/releases/assets/{existing_info['id']}", token, method="DELETE")

        target_upload_url = f"{upload_base}?name={asset_name}"
        log(f"[*] Uploading '{asset_name}' via curl stream...")
        up_res = upload_asset_with_curl(target_upload_url, token, asset_path)
        if "browser_download_url" in up_res:
            log(f"[+] Successfully uploaded '{asset_name}'!")
            log(f"    Download URL: {up_res.get('browser_download_url')}")
            log(f"    Size: {up_res.get('size'):,} bytes")
        elif "id" in up_res:
            log(f"[+] Uploaded '{asset_name}' with asset ID: {up_res.get('id')}")
        else:
            log(f"[?] Upload output: {up_res}")

    # Final verification
    log("\n[*] Verifying release assets on GitHub...")
    v_status, v_res = api_request(f"{base_api}/releases/{release_id}", token)
    if v_status == 200:
        final_assets = v_res.get("assets", [])
        log(f"[+] Verification succeeded! Total assets uploaded: {len(final_assets)}")
        for a in final_assets:
            log(f" - {a['name']} ({a['size']:,} bytes, state={a.get('state')}) -> {a['browser_download_url']}")

        required_asset_names = {"SmartDownload.exe", "SmartDownload-Setup.exe"}
        uploaded_names = {a["name"]: a for a in final_assets if a.get("state") == "uploaded"}
        missing = required_asset_names - set(uploaded_names.keys())
        if missing:
            raise RuntimeError(f"Release verification failed: missing assets {missing}")
    else:
        raise RuntimeError(f"Could not verify release: HTTP {v_status}")

    log("\n[+] RELEASE v2.0.0 COMPLETE & PUBLISHED!")


if __name__ == "__main__":
    main()
