const fileInput = document.getElementById("fileInput");
const dropZone = document.getElementById("dropZone");
const dropTitle = document.getElementById("dropTitle");
const dropSubtitle = document.getElementById("dropSubtitle");
const selectedFile = document.getElementById("selectedFile");
const fileName = document.getElementById("fileName");
const fileSize = document.getElementById("fileSize");
const removeFile = document.getElementById("removeFile");
const extractButton = document.getElementById("extractButton");
const buttonText = document.getElementById("buttonText");
const message = document.getElementById("message");

let currentFile = null;

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
function showMessage(text, type = "info") {
  message.textContent = text;
  message.className = `message ${type}`;
}
function clearMessage() {
  message.textContent = "";
  message.className = "message hidden";
}
function setFile(file) {
  clearMessage();
  if (!file) return;
  const extension = file.name.split(".").pop().toLowerCase();
  if (!["pbix", "pbit"].includes(extension)) {
    showMessage("Please select a Power BI .pbix or .pbit file.", "error");
    return;
  }
  if (file.size > 200 * 1024 * 1024) {
    showMessage("This file is larger than the 200 MB limit.", "error");
    return;
  }
  currentFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);
  selectedFile.classList.remove("hidden");
  dropTitle.textContent = "Report selected";
  dropSubtitle.textContent = "Choose another file by clicking here";
  extractButton.disabled = false;
}
fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
removeFile.addEventListener("click", () => {
  currentFile = null;
  fileInput.value = "";
  selectedFile.classList.add("hidden");
  dropTitle.textContent = "Drop your Power BI file here";
  dropSubtitle.innerHTML = 'or <span class="browse-link">browse files</span> on your computer';
  extractButton.disabled = true;
  clearMessage();
});
["dragenter", "dragover"].forEach(name => dropZone.addEventListener(name, event => {
  event.preventDefault();
  dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach(name => dropZone.addEventListener(name, event => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
}));
dropZone.addEventListener("drop", event => {
  const file = event.dataTransfer.files[0];
  if (file) setFile(file);
});

extractButton.addEventListener("click", async () => {
  if (!currentFile) return;
  const formData = new FormData();
  formData.append("file", currentFile);
  extractButton.disabled = true;
  buttonText.textContent = "Reading report…";
  showMessage("Inspecting report pages and the embedded semantic model. Larger reports may take a little longer.", "info");
  try {
    const response = await fetch("/api/extract", { method: "POST", body: formData });
    if (!response.ok) {
      let detail = "The report could not be processed.";
      try { const payload = await response.json(); detail = payload.detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const downloadName = match ? match[1] : `${currentFile.name.replace(/\.(pbix|pbit)$/i, "")}_metadata.xlsx`;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = downloadName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    showMessage("Your metadata workbook is ready. The Excel download should now be available.", "success");
  } catch (error) {
    showMessage(error.message || "Something went wrong while extracting metadata.", "error");
  } finally {
    extractButton.disabled = !currentFile;
    buttonText.textContent = "Extract metadata";
  }
});
