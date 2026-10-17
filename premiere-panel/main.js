// OpenRoughCut panel for Premiere Pro (UXP). The heavy lifting happens in the
// local engine (`orc serve`); this panel only sends the file path and imports
// the resulting sequence XML back into the open project.
const { localFileSystem } = require("uxp").storage;

const ENGINE = "http://127.0.0.1:8765";
let videoPath = null;

const $ = (id) => document.getElementById(id);
function status(text, isError = false) {
  $("status").textContent = text;
  $("status").className = isError ? "err" : "";
}

$("pick").addEventListener("click", async () => {
  const file = await localFileSystem.getFileForOpening({
    types: ["mp4", "mov", "mxf", "mkv", "m4v", "wav", "mp3"],
  });
  if (file) {
    videoPath = file.nativePath;
    $("file").textContent = file.name;
  }
});

async function importIntoProject(paths) {
  // Premiere's UXP DOM; if it is unavailable in this version, fall back to a
  // manual import hint so the user still gets the result.
  try {
    const ppro = require("premierepro");
    const project = await ppro.Project.getActiveProject();
    await project.importFiles(paths, true);
    return true;
  } catch (e) {
    console.error(e);
    return false;
  }
}

$("run").addEventListener("click", async () => {
  if (!videoPath) return status("Choose a recording first.", true);
  const language = $("language").value.trim();
  const options = {
    silence: $("silence").checked,
    fillers: $("fillers").checked,
    retakes: $("retakes").checked,
    captions: $("captions").checked,
    ai: $("ai").checked,
    ai_instructions: $("instructions").value.trim() || null,
    language: language || null,
    formats: ["xml", "srt", "json"],
  };
  status("Working… the first run downloads the speech model.");
  try {
    const res = await fetch(`${ENGINE}/cut`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video: videoPath, options }),
    });
    const data = await res.json();
    if (!res.ok) return status(`Engine error: ${data.error}`, true);
    const s = data.stats;
    const files = [data.outputs.xml, data.outputs.srt].filter(Boolean);
    const imported = await importIntoProject(files);
    status(
      `${s.source_seconds}s → ${s.kept_seconds}s (−${s.removed_percent}%, ${s.clips} clips)\n` +
        (data.ai_notes ? `Claude: ${data.ai_notes}\n` : "") +
        (imported
          ? "Imported the rough-cut sequence into the project."
          : `Import manually (File > Import):\n${files.join("\n")}`)
    );
  } catch (e) {
    status(`Could not reach the engine at ${ENGINE}. Is "orc serve" running?\n${e}`, true);
  }
});
