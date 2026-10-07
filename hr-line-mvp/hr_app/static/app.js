"use strict";

document.querySelectorAll("form").forEach((form) => {
  const originalButton = form.querySelector("[data-submit]");
  if (originalButton) originalButton.dataset.originalLabel = originalButton.textContent;
  form.addEventListener("submit", () => {
    const button = form.querySelector("[data-submit]");
    if (button) {
      button.disabled = true;
      button.textContent = "處理中…";
    }
  });
});
// 返回上一頁時復原提交按鈕，表單 nonce 仍可安全重送。
window.addEventListener("pageshow", () => {
  document.querySelectorAll("[data-submit]").forEach((button) => {
    const wasDisabled = button.disabled;
    button.disabled = false;
    if (wasDisabled) button.textContent = button.dataset.originalLabel;
  });
});

const copyButton = document.getElementById("copy-number");
if (copyButton) {
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(document.getElementById("case-number").textContent);
      copyButton.textContent = "已複製";
      document.getElementById("copy-status").textContent = "案件編號已複製";
    } catch (_) {
      copyButton.textContent = "請選取上方編號複製";
    }
  });
}

// 選用：只在設定 LIFF ID 時載入官方 SDK。
// 顯示名稱只供 UI 使用，不是員工身分驗證；此 MVP 不將 profile 當成授權依據。
async function initializeLiff() {
  const liffId = document.querySelector('meta[name="liff-id"]').content;
  if (!liffId) return;
  const status = document.getElementById("liff-status");
  try {
    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://static.line-scdn.net/liff/edge/2/sdk.js";
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
    await window.liff.init({ liffId });
    if (window.liff.isLoggedIn()) {
      const profile = await window.liff.getProfile();
      status.textContent = `您好，${profile.displayName}。LINE 已連線；員工編號仍使用本機測試查詢。`;
    } else {
      status.textContent = "LIFF 已初始化。登入 LINE 可顯示名稱；員工身分綁定尚未啟用。";
      const loginButton = document.createElement("button");
      loginButton.type = "button";
      loginButton.className = "text-button";
      loginButton.textContent = "登入 LINE";
      loginButton.addEventListener("click", () => window.liff.login());
      status.appendChild(loginButton);
    }
  } catch (_) {
    status.textContent = "LINE 連線尚未完成，請確認 LIFF ID、Endpoint URL 與權限設定。仍可進行本機功能測試。";
  }
  status.hidden = false;
}
initializeLiff();
