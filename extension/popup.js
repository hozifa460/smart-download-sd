/**
 * ======================================================================================
 * ⚡ TURBO DOWNLOAD MANAGER PRO — Popup UI Script
 * ======================================================================================
 */

const DEFAULT_CONFIG = {
  enabled: true,
  port: 9242,
  interceptAll: false
};

const statusCard = document.getElementById("status-card");
const statusTitle = document.getElementById("status-title");
const statusDesc = document.getElementById("status-desc");
const btnRefresh = document.getElementById("btn-refresh");
const btnDownloadTab = document.getElementById("btn-download-tab");
const toggleEnabled = document.getElementById("toggle-enabled");
const toggleAll = document.getElementById("toggle-all");
const inputPort = document.getElementById("input-port");
const btnSavePort = document.getElementById("btn-save-port");
const toast = document.getElementById("toast");

function showToast(msg, isError = false) {
  toast.textContent = msg;
  toast.style.backgroundColor = isError ? "#ef4444" : "#10b981";
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}

async function checkStatus(port) {
  statusCard.className = "status-card";
  statusTitle.textContent = "Connecting...";
  statusDesc.textContent = `http://127.0.0.1:${port}`;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1200);

    const res = await fetch(`http://127.0.0.1:${port}/ping`, {
      method: "GET",
      signal: controller.signal
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json();
      statusCard.className = "status-card online";
      statusTitle.textContent = "● Desktop App Connected";
      statusDesc.textContent = `${data.app || "Turbo Pro"} (v${data.version || "1.0"})`;
      return true;
    }
  } catch (err) {
    // Offline
  }

  statusCard.className = "status-card offline";
  statusTitle.textContent = "● Desktop App Offline";
  statusDesc.textContent = "Open Turbo Download Manager to connect";
  return false;
}

// Load initial preferences
chrome.storage.local.get(DEFAULT_CONFIG, (cfg) => {
  toggleEnabled.checked = cfg.enabled !== false;
  toggleAll.checked = cfg.interceptAll === true;
  inputPort.value = cfg.port || 9242;

  checkStatus(cfg.port || 9242);
});

// Refresh button
btnRefresh.addEventListener("click", () => {
  const port = parseInt(inputPort.value, 10) || 9242;
  checkStatus(port);
});

// Toggle enabled
toggleEnabled.addEventListener("change", () => {
  const enabled = toggleEnabled.checked;
  chrome.storage.local.set({ enabled }, () => {
    showToast(enabled ? "Auto-interception Enabled" : "Auto-interception Disabled");
  });
});

// Toggle intercept all
toggleAll.addEventListener("change", () => {
  const interceptAll = toggleAll.checked;
  chrome.storage.local.set({ interceptAll }, () => {
    showToast(interceptAll ? "Intercepting all files" : "Intercepting common files");
  });
});

// Save port
btnSavePort.addEventListener("click", () => {
  const port = parseInt(inputPort.value, 10);
  if (!port || port < 1024 || port > 65535) {
    showToast("Invalid port (1024-65535)", true);
    return;
  }
  chrome.storage.local.set({ port }, () => {
    showToast("Port saved");
    checkStatus(port);
  });
});

// Download current active tab or video
btnDownloadTab.addEventListener("click", async () => {
  chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
    if (!tabs || tabs.length === 0) return;
    const activeTab = tabs[0];
    const url = activeTab.url;

    if (!url || url.startsWith("chrome://") || url.startsWith("about:")) {
      showToast("Cannot download browser page", true);
      return;
    }

    const port = parseInt(inputPort.value, 10) || 9242;
    try {
      const res = await fetch(`http://127.0.0.1:${port}/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url,
          filename: "",
          referrer: url,
          start_immediately: true
        })
      });

      if (res.ok) {
        showToast("Sent to Turbo Download Manager! 🚀");
      } else {
        showToast("Failed to dispatch to Turbo App", true);
      }
    } catch (err) {
      showToast("Desktop app is not reachable", true);
    }
  });
});
