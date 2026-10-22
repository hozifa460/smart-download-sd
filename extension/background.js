/**
 * ======================================================================================
 * ⚡ TURBO DOWNLOAD MANAGER PRO — WebExtension Service Worker / Background Script
 * ======================================================================================
 * Features:
 * 1. Intercepts browser downloads and forwards them to Turbo Download Manager Pro.
 * 2. Adds context menus to right-click links, media, and pages.
 * 3. Graceful fallback: If local app is not running, browser download proceeds uninterrupted.
 * 4. Periodic health check of local IPC loopback server (127.0.0.1:9242).
 * ======================================================================================
 */

const DEFAULT_CONFIG = {
  enabled: true,
  port: 9242,
  interceptAll: false,
  fileExtensions: [
    ".exe", ".zip", ".rar", ".iso", ".bin", ".tar", ".gz", ".7z",
    ".mp4", ".mkv", ".mp3", ".pdf", ".dmg", ".pkg", ".apk", ".msi",
    ".epub", ".docx", ".xlsx", ".pptx", ".webm", ".flac", ".wav", ".avi"
  ],
  ignoredDomains: ["127.0.0.1", "localhost"]
};

// Retrieve settings from local storage with default fallback
async function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.local.get(DEFAULT_CONFIG, (stored) => {
      resolve({ ...DEFAULT_CONFIG, ...stored });
    });
  });
}

// Check health of desktop application via Native Messaging or loopback HTTP
async function checkAppHealth() {
  // 1. Try Native Messaging Host first
  try {
    const nativeOnline = await new Promise((resolve) => {
      chrome.runtime.sendNativeMessage(
        "com.smartdownload.host",
        { action: "ping" },
        (res) => {
          if (chrome.runtime.lastError || !res) {
            resolve(false);
          } else {
            resolve(res.success && res.app_online);
          }
        }
      );
    });

    if (nativeOnline) {
      chrome.action.setBadgeText({ text: "ON" });
      chrome.action.setBadgeBackgroundColor({ color: "#10b981" }); // Emerald green
      return true;
    }
  } catch (e) {
    // Native messaging host not registered or failed, fall through to HTTP
  }

  // 2. Fallback to loopback HTTP IPC ping
  const config = await getConfig();
  const url = `http://127.0.0.1:${config.port}/ping`;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1200);

    const res = await fetch(url, { method: "GET", signal: controller.signal });
    clearTimeout(timer);

    if (res.ok) {
      chrome.action.setBadgeText({ text: "ON" });
      chrome.action.setBadgeBackgroundColor({ color: "#10b981" }); // Emerald green
      return true;
    }
  } catch (err) {
    // Offline or unreachable
  }

  chrome.action.setBadgeText({ text: "" });
  return false;
}

// Send download task to Smart Download (SD) via Native Messaging or HTTP IPC
async function sendToTurbo(payload) {
  // 1. Try Native Messaging Host first (direct Windows Registry IPC)
  try {
    const nativeSuccess = await new Promise((resolve) => {
      chrome.runtime.sendNativeMessage(
        "com.smartdownload.host",
        { action: "download", ...payload },
        (res) => {
          if (chrome.runtime.lastError || !res) {
            resolve(false);
          } else {
            resolve(res.success === true);
          }
        }
      );
    });

    if (nativeSuccess) {
      return true;
    }
  } catch (e) {
    // Fall through to loopback HTTP
  }

  // 2. Fallback to HTTP IPC Loopback
  const config = await getConfig();
  const url = `http://127.0.0.1:${config.port}/download`;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);

    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json();
      return data.success === true;
    }
  } catch (err) {
    console.warn("[Turbo Extension] Desktop app unreachable:", err.message);
  }
  return false;
}

// Setup context menus on installation
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(null, (existing) => {
    if (!existing || Object.keys(existing).length === 0) {
      chrome.storage.local.set(DEFAULT_CONFIG);
    }
  });

  chrome.contextMenus.create({
    id: "turbo-download-target",
    title: "⚡ Download with Smart Download",
    contexts: ["link", "video", "audio", "image"]
  });

  chrome.contextMenus.create({
    id: "turbo-download-page",
    title: "⚡ Download Current Video / Page with Smart Download",
    contexts: ["page"]
  });

  // Setup periodic health check alarm (every 1 minute)
  chrome.alarms.create("turboHealthCheck", { periodInMinutes: 1 });
  checkAppHealth();
});

// Periodic and startup health check
chrome.runtime.onStartup.addListener(() => {
  checkAppHealth();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "turboHealthCheck") {
    checkAppHealth();
  }
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const targetUrl = info.linkUrl || info.srcUrl || info.pageUrl;
  if (!targetUrl) return;

  const success = await sendToTurbo({
    url: targetUrl,
    filename: "",
    referrer: info.pageUrl || (tab ? tab.url : ""),
    start_immediately: true
  });

  if (success) {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Smart Download (SD)",
      message: "Download task dispatched to Smart Download (SD)!"
    });
  } else {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Smart Download (SD)",
      message: "Could not connect to desktop app. Please make sure Smart Download (SD) is running."
    });
  }
});

// Intercept browser downloads
chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  (async () => {
    const config = await getConfig();

    // If interception disabled, let browser handle it
    if (!config.enabled) {
      suggest();
      return;
    }

    const downloadUrl = item.url || item.finalUrl || "";
    if (!downloadUrl) {
      suggest();
      return;
    }

    // Only intercept network URL schemes (ignore data:, blob:, chrome:, etc.)
    const schemeLower = downloadUrl.toLowerCase();
    if (!schemeLower.startsWith("http://") && !schemeLower.startsWith("https://") && !schemeLower.startsWith("ftp://")) {
      suggest();
      return;
    }

    // Ignore local loopback requests to avoid loops
    try {
      const parsedUrl = new URL(downloadUrl);
      if (config.ignoredDomains.includes(parsedUrl.hostname)) {
        suggest();
        return;
      }
    } catch (e) {
      suggest();
      return;
    }

    // Check extension matching
    const filename = (item.filename || "").toLowerCase();
    const urlLower = downloadUrl.toLowerCase();
    let shouldIntercept = config.interceptAll;

    if (!shouldIntercept) {
      for (const ext of config.fileExtensions) {
        if (filename.endsWith(ext) || urlLower.includes(ext)) {
          shouldIntercept = true;
          break;
        }
      }
    }

    if (!shouldIntercept) {
      suggest();
      return;
    }

    // Attempt sending to local Turbo app
    const sent = await sendToTurbo({
      url: downloadUrl,
      filename: item.filename || "",
      referrer: item.referrer || "",
      start_immediately: true
    });

    if (sent) {
      // First resolve the suggest callback cleanly to fulfill asynchronous contract
      suggest();
      // Then cancel and erase the browser download so it doesn't duplicate
      chrome.downloads.cancel(item.id, () => {
        chrome.downloads.erase({ id: item.id }, () => {});
      });

      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "⚡ Turbo Download Manager Pro",
        message: `Intercepted: ${item.filename || "New Download"}`
      });
    } else {
      // If desktop app was not reachable, allow browser download to continue normally!
      suggest();
    }
  })();

  return true; // Asynchronous suggestion
});

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "pingApp") {
    checkAppHealth().then((isOnline) => sendResponse({ online: isOnline }));
    return true;
  }
  if (request.action === "sendUrl") {
    sendToTurbo(request.payload).then((success) => sendResponse({ success }));
    return true;
  }
});
