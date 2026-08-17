"use strict";

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const selectedFileEl = document.getElementById("selected-file");
const thumbnail = document.getElementById("thumbnail");
const startBtn = document.getElementById("start-btn");

const uploadSection = document.getElementById("upload-section");
const progressSection = document.getElementById("progress-section");
const resultSection = document.getElementById("result-section");
const errorSection = document.getElementById("error-section");

const preview = document.getElementById("preview");
const downloadLink = document.getElementById("download-txt");
const copyBtn = document.getElementById("copy-btn");

let selectedFile = null;
let thumbnailUrl = null;
let downloadUrl = null;

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length > 0) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) setFile(fileInput.files[0]);
});

// 스크린샷은 파일로 저장하지 않고 클립보드에서 바로 붙여넣는 경우가 많다.
document.addEventListener("paste", (e) => {
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (!item) return;
  const file = item.getAsFile();
  if (!file) return;
  const ext = (file.type.split("/")[1] || "png").replace("jpeg", "jpg");
  setFile(new File([file], file.name || `clipboard.${ext}`, { type: file.type }));
  resetAll();
});

function setFile(file) {
  selectedFile = file;
  selectedFileEl.textContent = `선택된 이미지: ${file.name} (${formatSize(file.size)})`;
  selectedFileEl.classList.remove("hidden");

  if (thumbnailUrl) URL.revokeObjectURL(thumbnailUrl);
  thumbnailUrl = URL.createObjectURL(file);
  thumbnail.src = thumbnailUrl;
  thumbnail.classList.remove("hidden");

  startBtn.disabled = false;
}

startBtn.addEventListener("click", async () => {
  const form = new FormData();
  form.append("file", selectedFile);
  form.append("page_mode", document.getElementById("page-mode").value);
  form.append("layout", document.getElementById("layout").value);
  form.append("enhance", document.getElementById("enhance").checked ? "true" : "false");

  hide(uploadSection);
  show(progressSection);

  try {
    const res = await fetch("/api/ocr", { method: "POST", body: form });
    if (!res.ok) throw new Error(await errorText(res));
    showResult(await res.json());
  } catch (err) {
    showError(err.message);
  }
});

function showResult(result) {
  hide(progressSection);
  show(resultSection);

  const hasText = result.text.trim().length > 0;
  preview.textContent = hasText
    ? result.text
    : "(이미지에서 영어 텍스트를 찾지 못했습니다)";

  const parts = [
    result.filename,
    `${result.width}×${result.height}`,
    `단어 ${result.word_count}개`,
  ];
  if (result.confidence != null) parts.push(`평균 신뢰도 ${result.confidence}%`);
  document.getElementById("result-info").textContent = parts.join(" · ");

  const warning = document.getElementById("quality-warning");
  if (!hasText) {
    warning.textContent =
      "인식 모드를 바꾸거나, 글자가 더 크고 선명하게 나온 이미지로 다시 시도해 보세요.";
    warning.classList.remove("hidden");
  } else if (result.low_confidence_words > 0) {
    warning.textContent =
      `흐릿하게 읽힌 단어가 ${result.low_confidence_words}개 있습니다. ` +
      "결과를 원본과 한 번 대조해 보세요.";
    warning.classList.remove("hidden");
  } else {
    warning.classList.add("hidden");
  }

  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = URL.createObjectURL(
    new Blob([result.text], { type: "text/plain;charset=utf-8" })
  );
  downloadLink.href = downloadUrl;
  downloadLink.download = `${result.filename.replace(/\.[^.]+$/, "")}.txt`;
  downloadLink.classList.toggle("hidden", !hasText);
  copyBtn.classList.toggle("hidden", !hasText);
  copyBtn.textContent = "텍스트 복사";
}

copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(preview.textContent);
    copyBtn.textContent = "복사됨!";
  } catch {
    copyBtn.textContent = "복사 실패 (직접 선택해 주세요)";
  }
});

function showError(message) {
  hide(uploadSection);
  hide(progressSection);
  hide(resultSection);
  show(errorSection);
  document.getElementById("error-message").textContent = message;
}

function resetAll() {
  hide(progressSection);
  hide(resultSection);
  hide(errorSection);
  show(uploadSection);
}
document.getElementById("reset-btn").addEventListener("click", resetAll);
document.getElementById("error-reset-btn").addEventListener("click", resetAll);

async function errorText(res) {
  try {
    const body = await res.json();
    return body.detail || `요청 실패 (HTTP ${res.status})`;
  } catch {
    return `요청 실패 (HTTP ${res.status})`;
  }
}

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${bytes}B`;
}

function show(el) {
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}
