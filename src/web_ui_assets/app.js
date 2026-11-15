const $ = (id) => document.getElementById(id);
const isDock = location.pathname === "/dock";
document.body.classList.toggle("dock", isDock);

function readStorage(storage, key) {
  try { return storage.getItem(key); } catch { return null; }
}
function writeStorage(storage, key, value) {
  try { storage.setItem(key, value); } catch { /* Storage can be disabled in an OBS dock. */ }
}
const suppliedToken = new URLSearchParams(location.hash.slice(1)).get("session");
let token = suppliedToken || readStorage(sessionStorage, "kototsuna-session") || "";
if (suppliedToken) writeStorage(sessionStorage, "kototsuna-session", suppliedToken);
history.replaceState(null, "", location.pathname);

let state = null;
let busy = false;
let online = false;
let commentSignature = "";
let generation = 0;
let messageTimer;
let settingsGroup = "接続";
let settingsTrigger = null;
const settingGroups = new Map();

function setLayout(layout) {
  const mode = layout === "focus" ? "focus" : "studio";
  const changed = document.body.dataset.layout !== (isDock ? "studio" : mode);
  document.body.dataset.layout = isDock ? "studio" : mode;
  for (const button of document.querySelectorAll("[data-layout-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.layoutChoice === mode));
  }
  writeStorage(localStorage, "kototsuna-layout", mode);
  if (changed) requestAnimationFrame(scrollToLatest);
}
function scrollToLatest() {
  if ($("autoscroll").checked) $("chat-scroll").scrollTop = $("chat-scroll").scrollHeight;
}
window.addEventListener("resize", () => requestAnimationFrame(scrollToLatest));
setLayout(readStorage(localStorage, "kototsuna-layout"));
for (const button of document.querySelectorAll("[data-layout-choice]")) {
  button.onclick = () => state?.desktop
    ? send("save_settings", { web_workspace_layout: button.dataset.layoutChoice })
    : setLayout(button.dataset.layoutChoice);
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme").textContent = theme === "light" ? "ダーク表示" : "ライト表示";
  $("theme").setAttribute("aria-label", $("theme").textContent + "に切り替え");
  writeStorage(localStorage, "kototsuna-web-theme", theme);
}
setTheme(readStorage(localStorage, "kototsuna-web-theme") === "light" ? "light" : "dark");
$("theme").onclick = () => {
  const light = document.documentElement.dataset.theme !== "light";
  if (state?.desktop) send("save_settings", { ui_theme: light ? "minimal" : "default" });
  else setTheme(light ? "light" : "dark");
};
$("help").onclick = () => $("help-dialog").showModal();

function message(text, error = false) {
  clearTimeout(messageTimer);
  $("action-message").textContent = text;
  $("action-message").classList.toggle("error", error);
  $("action-message").hidden = !text;
  $("start-hint").hidden = Boolean(text);
  $("settings-feedback").textContent = text;
  $("settings-feedback").classList.toggle("error", error);
  if (text && !error) messageTimer = setTimeout(() => {
    $("action-message").hidden = true; $("start-hint").hidden = false;
  }, 4500);
}

async function api(path, command) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), command ? 12000 : 5000);
  try {
    const response = await fetch(path, {
      method: command ? "POST" : "GET", credentials: "omit", cache: "no-store",
      headers: { Authorization: `Bearer ${token}`, ...(command ? { "Content-Type": "application/json" } : {}) },
      body: command ? JSON.stringify(command) : undefined, signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || "操作できませんでした。");
      error.status = response.status;
      throw error;
    }
    return data;
  } finally { clearTimeout(timeout); }
}

function controlsEnabled() {
  $("controls").disabled = !online || busy;
  $("copy-overlay").disabled = !online;
  $("copy-dock").disabled = !online;
  $("settings").disabled = !online || busy;
  $("settings-fields").disabled = !online || busy;
  $("save-settings").disabled = !online || busy;
  $("theme").disabled = busy;
  for (const button of document.querySelectorAll("[data-settings-target], [data-layout-choice]")) button.disabled = !online || busy;
  for (const id of ["authenticate", "logout", "refresh-devices", "test-voice", "check-update", "install-update", "restart"]) {
    $(id).disabled = !online || busy;
  }
  if (!state) return;
  const jobs = state.jobs || [];
  $("authenticate").disabled ||= jobs.includes("auth") || settingsDirty();
  $("logout").disabled ||= jobs.includes("auth") || !state.authenticated;
  $("refresh-devices").disabled ||= jobs.includes("devices") || jobs.includes("tts");
  $("check-update").disabled ||= jobs.includes("update");
  $("install-update").disabled ||= jobs.includes("update");
  $("tts").disabled ||= jobs.includes("tts");
  $("test-voice").disabled ||= jobs.includes("tts");
  $("refresh-devices").textContent = jobs.includes("devices") ? "一覧を取得中…" : "マイク・ボイス一覧を更新";
  const running = ["connected", "connecting"].includes(state.connection);
  $("start-stop").disabled = !online || busy || (running ? !state.can_stop : !state.authenticated || !state.channel);
}

function updateValue(id, value) {
  // Polling must not move a slider while it is being dragged or edited by keyboard.
  if (document.activeElement !== $(id)) $(id).value = value;
}

const connectionNames = { needs_auth: "認証待ち", stopped: "停止中", connecting: "接続待ち", connected: "接続済み", error: "接続エラー" };
function render(next) {
  state = next;
  online = true;
  $("connection-alert").hidden = true;
  $("connection-alert").classList.remove("offline");
  $("channel").textContent = next.channel ? `# ${next.channel}` : "チャンネル未設定";
  $("bot-status").textContent = connectionNames[next.connection] || "確認中";
  $("bot-status").classList.toggle("live", next.connection === "connected");
  $("engine-status").textContent = next.voice_active ? "マイク翻訳 ON" : "マイク翻訳 OFF";
  const running = ["connected", "connecting"].includes(next.connection);
  $("start-stop").textContent = running ? "■ BOTを停止" : "▶ BOTを開始";
  $("start-stop").classList.toggle("stop", running);
  $("start-hint").textContent = !next.authenticated ? "「設定・Twitch接続」から認証してください。"
    : !next.channel ? "「設定・Twitch接続」でチャンネルを指定してください。"
    : next.connection === "error" ? "本体の状態と接続設定を確認してください。"
    : next.connection === "connecting" ? "Twitchとの接続を待っています。"
    : running ? "コメントを受信しています。" : "準備ができました。BOTを開始できます。";
  $("translation").checked = next.translation_enabled;
  $("include-name").checked = next.include_name;
  updateValue("language", next.language_mode);
  updateValue("volume", next.tts_volume);
  updateValue("speed", next.tts_speed);
  $("volume-value").textContent = `${$("volume").value}%`;
  $("speed-value").textContent = `${Number($("speed").value).toFixed(1)}x`;
  $("tts-status").textContent = next.jobs?.includes("tts") ? "音声を準備中…"
    : next.tts_active ? (next.tts_volume === 0 ? "ミュート · 音量 0" : next.tts_speaking ? "読み上げ中" : "次のコメントを待機") : "読み上げ OFF";
  $("mic-status").textContent = next.voice_active ? (next.voice_processing ? "音声を翻訳中…" : "マイク入力を受付中") : "マイク OFF";
  $("mic-level").value = next.voice_active ? Math.max(0, Math.min(100, next.mic_level || 0)) : 0;
  $("voice").checked = next.voice_active;
  $("tts").checked = next.tts_active;
  $("voice").disabled = $("tts").disabled = !next.desktop;
  $("runtime-notice").textContent = next.notice || "";
  $("auth-state").textContent = next.jobs?.includes("auth") ? "認証を確認しています…" : next.authenticated ? `接続済み ${next.auth_username || ""}` : "Twitch未接続";
  if (next.settings) {
    const theme = next.settings.values.ui_theme;
    setTheme(({ default: "dark", minimal: "light" })[theme] || theme);
    setLayout(next.settings.values.web_workspace_layout);
    syncSettings();
    renderDevices(next.devices || {});
    $("update-status").textContent = [next.update?.message, next.update?.version].filter(Boolean).join(" ");
    $("install-update").hidden = next.update?.status !== "available";
    $("restart").hidden = next.update?.status !== "ready";
  }
  $("version").textContent = `ことつな！ v${next.version}`;
  const emptyText = $("empty-state").querySelector("p");
  emptyText.textContent = next.connection === "connected" ? "接続できました。コメントが届くと、ここに表示されます。"
    : next.authenticated && next.channel ? "準備ができました。上の「BOTを開始」でコメントを受信できます。"
    : "BOTを開始すると、コメントと翻訳が届きます。まずは設定からTwitchに接続しましょう。";
  if (!isDock) renderComments(next.comments);
  controlsEnabled();
}

function renderComments(comments) {
  $("comment-count").textContent = `${comments.length} 件`;
  const signature = JSON.stringify(comments);
  if (!$("autoscroll").checked && commentSignature) {
    $("feed-status").textContent = signature !== commentSignature ? "表示を一時停止中 · 新しいコメントがあります" : "表示を一時停止中";
    return;
  }
  $("feed-status").textContent = state.connection === "connected" ? "● コメントを受信中" : "受信待機中";
  if (signature === commentSignature) return;
  commentSignature = signature;
  const existing = new Map([...$("comments").children].map(item => [item.dataset.id, item]));
  const fragment = document.createDocumentFragment();
  for (const comment of comments) {
    const previous = existing.get(comment.id);
    const content = JSON.stringify(comment);
    if (previous?._content === content) {
      previous.classList.add("known"); fragment.append(previous); continue;
    }
    const item = document.createElement("li"); item.className = "comment";
    item.dataset.id = comment.id; item._content = content;
    const meta = document.createElement("div"); meta.className = "comment-meta";
    const avatar = document.createElement("span"); avatar.className = "avatar"; avatar.setAttribute("aria-hidden", "true"); avatar.textContent = [...comment.name][0] || "?";
    const name = document.createElement("span"); name.className = "comment-name"; name.textContent = comment.name;
    const time = document.createElement("span"); time.className = "comment-time"; time.textContent = comment.time;
    meta.append(avatar, name, time);
    const body = document.createElement("p"); body.className = "comment-body"; body.textContent = comment.message;
    item.append(meta, body);
    if (comment.translated) {
      const translation = document.createElement("div"); translation.className = "translation";
      const label = document.createElement("span"); label.className = "translation-label"; label.textContent = "翻訳";
      translation.append(label, document.createTextNode(comment.translated)); item.append(translation);
    }
    fragment.append(item);
  }
  $("comments").replaceChildren(fragment);
  $("empty-state").hidden = comments.length > 0;
  if ($("autoscroll").checked) $("chat-scroll").scrollTop = $("chat-scroll").scrollHeight;
}

$("autoscroll").onchange = () => { if (state) renderComments(state.comments); };

function disconnected(error) {
  online = false;
  $("connection-alert").hidden = false;
  $("connection-alert").classList.add("offline");
  $("connection-alert").textContent = error.status === 401
    ? "接続の有効期限が切れています。アプリを起動し直してください。OBSドックはURLをコピーし直してください。"
    : "処理エンジンに接続できません。自動で再接続します。復旧しない場合はアプリを起動し直してください。";
  $("bot-status").textContent = "本体と未接続";
  $("bot-status").classList.remove("live");
  $("mic-level").value = 0;
  $("mic-status").textContent = "入力状態を確認できません";
  $("tts-status").textContent = "読み上げ状態を確認できません";
  $("feed-status").textContent = "通信断 · 最後に受信したコメントを表示";
  controlsEnabled();
}

async function send(action, value) {
  if (busy || !online) return false;
  busy = true;
  generation += 1;
  controlsEnabled();
  message("操作を反映しています…");
  try {
    render(await api("/api/command", value === undefined ? { action } : { action, value }));
    message(action === "save_settings" ? "設定を保存しました。" : "操作を受け付けました。");
    return true;
  } catch (error) {
    message(error.status ? error.message : "応答を確認できませんでした。状態を確認してから操作してください。", true);
    if (!error.status || error.status === 401 || error.status === 503) disconnected(error);
    if (state) {
      $("translation").checked = state.translation_enabled;
      $("include-name").checked = state.include_name;
      $("volume").value = state.tts_volume;
      $("speed").value = state.tts_speed;
      $("language").value = state.language_mode;
      $("voice").checked = state.voice_active;
      $("tts").checked = state.tts_active;
    }
    return false;
  } finally { busy = false; controlsEnabled(); }
}
$("start-stop").onclick = () => send(["connected", "connecting"].includes(state.connection) ? "stop" : "start");
function openSettings(group, trigger) {
  if (!state?.settings) { send("settings"); return; }
  if ($("settings-panel").hidden) {
    buildSettings(); $("settings-feedback").textContent = "";
  }
  settingsTrigger = trigger;
  $("settings-panel").hidden = false;
  $("quick-panel").hidden = true;
  document.querySelector(".workspace").classList.add("settings-open");
  selectSettingsGroup(group);
  $("settings-title").focus({ preventScroll: true });
  if (matchMedia("(max-width:700px)").matches || isDock) $("inspector").scrollIntoView({ block: "start" });
}
$("settings").onclick = () => openSettings("接続", $("settings"));
$("home").onclick = closeSettings;
for (const button of document.querySelectorAll("[data-settings-target]")) {
  button.onclick = () => openSettings(button.dataset.settingsTarget, button);
}
$("voice").onchange = (event) => send("voice", event.target.checked);
$("tts").onchange = (event) => send("tts", event.target.checked);
$("translation").onchange = (event) => send("translation", event.target.checked);
$("include-name").onchange = (event) => send("include_name", event.target.checked);
$("language").onchange = (event) => send("language", event.target.value);
for (const id of ["volume", "speed"]) {
  $(id).oninput = () => { $(id + "-value").textContent = id === "volume" ? `${$(id).value}%` : `${Number($(id).value).toFixed(1)}x`; };
  $(id).onchange = () => send(id, Number($(id).value));
}
async function copy(text, success) {
  try { await navigator.clipboard.writeText(text); message(success); }
  catch { message("コピーできませんでした。ブラウザのクリップボード許可を確認してください。", true); }
}
$("copy-overlay").onclick = () => copy(state.overlay_url, "コメント表示URLをコピーしました。OBSのブラウザソースに貼り付けてください。");
$("copy-dock").onclick = () => copy(`${location.origin}/dock#session=${token}`, "操作パネルURLをコピーしました。OBSのカスタムブラウザドックに貼り付けてください。");

let settingsBaseline = {};
let deviceSignature = "";
function savedSettingValues() {
  const values = { ...state.settings.values };
  for (const field of state.settings.fields) {
    // color入力は小文字へ正規化されるため、未編集でも差分にしない。
    if (field.type === "color") values[field.key] = values[field.key]?.toLowerCase();
  }
  return values;
}
function settingValue(field) {
  const input = $("setting-" + field.key);
  if (!input) return undefined;
  if (field.type === "checkbox") return input.checked;
  if (field.type === "number") return input.value === "" ? null : Number(input.value);
  if (field.type === "microphone") return input.value === "" ? null : Number(input.value);
  return input.value;
}
function changedSettings() {
  const changes = {};
  for (const field of state?.settings?.fields || []) {
    const value = settingValue(field);
    if (value === undefined || (field.type === "password" && !value)) continue;
    if (value !== settingsBaseline[field.key]) changes[field.key] = value;
  }
  return changes;
}
function settingsDirty() { return Object.keys(changedSettings()).length > 0; }
function markDirty() {
  $("settings-dirty").textContent = settingsDirty() ? "未保存の変更があります" : "保存済み";
  renderSubtitlePreview();
  controlsEnabled();
}
function syncSettings() {
  // 別の操作画面で変わった値は同期するが、この画面で編集中の値は保持する。
  if ($("settings-panel").hidden) return;
  const saved = savedSettingValues();
  for (const field of state.settings.fields) {
    const input = $("setting-" + field.key);
    if (!input || field.type === "password" || settingValue(field) !== settingsBaseline[field.key]) continue;
    settingsBaseline[field.key] = saved[field.key];
    if (field.type === "checkbox") input.checked = Boolean(settingsBaseline[field.key]);
    else input.value = settingsBaseline[field.key] ?? "";
  }
  markDirty();
}
function selectSettingsGroup(group) {
  settingsGroup = group;
  for (const tools of document.querySelectorAll("[data-settings-group]")) tools.hidden = tools.dataset.settingsGroup !== group;
  for (const [name, item] of settingGroups) {
    item.section.hidden = name !== group;
    item.tab.setAttribute("aria-pressed", String(name === group));
    for (const input of item.section.querySelectorAll("input, select")) input.disabled = name !== group;
  }
  // 非表示の必須形式検証に阻まれないよう、保存時に全グループを検証する。
  $("settings-title").textContent = group === "接続" ? "設定・Twitch接続" : `${group}の設定`;
  for (const button of document.querySelectorAll(".rail-button")) {
    const selected = button.id === "settings" ? !["音声", "字幕", "OBS連携"].includes(group) : button.dataset.settingsTarget === group;
    button.setAttribute("aria-pressed", String(selected));
  }
  document.querySelector(".settings-body").scrollTop = 0;
  renderSubtitlePreview();
}
function renderSubtitlePreview() {
  const values = { ...state?.settings?.values, ...changedSettings() };
  if (!state?.settings) return;
  const sample = $("subtitle-sample");
  sample.style.fontFamily = values.subtitle_font_family;
  sample.style.fontSize = `${Math.max(8, Math.min(120, Number(values.subtitle_font_size) || 32)) * .65}px`;
  sample.style.color = values.subtitle_text_color;
  sample.style.webkitTextStroke = `${Math.max(0, Math.min(10, Number(values.subtitle_stroke_width) || 0)) * .65}px ${values.subtitle_stroke_color}`;
  sample.style.paintOrder = "stroke fill";
  $("sample-original").hidden = !values.subtitle_show_original;
  $("sample-translation").hidden = !values.subtitle_show_translated;
  $("sample-meta").textContent = [values.subtitle_show_speaker ? "ことつな！" : "", values.subtitle_show_timestamp ? "20:30" : ""].filter(Boolean).join(" · ");
  $("sample-meta").hidden = !$("sample-meta").textContent;
  $("subtitle-stage").classList.toggle("disabled", !values.subtitle_enabled);
  $("subtitle-preview-state").textContent = values.subtitle_enabled ? "字幕 ON · 縮小サンプル。実際の表示はOBSで確認できます。" : "字幕 OFF · 有効にすると配信に表示されます。";
}
function buildSettings() {
  settingsBaseline = savedSettingValues();
  for (const tools of document.querySelectorAll("[data-settings-group]")) tools.hidden = tools.dataset.settingsGroup !== "接続";
  $("settings-fields").replaceChildren(); $("settings-tabs").replaceChildren();
  settingGroups.clear();
  const groups = settingGroups;
  for (const field of state.settings.fields) {
    if (!groups.has(field.group)) {
      const section = document.createElement("div"); section.className = "settings-grid";
      section.hidden = groups.size > 0;
      const tab = document.createElement("button"); tab.type = "button"; tab.className = "quiet";
      tab.textContent = field.group; tab.setAttribute("aria-pressed", String(groups.size === 0));
      tab.onclick = () => selectSettingsGroup(field.group);
      groups.set(field.group, { section, tab });
      $("settings-tabs").append(tab); $("settings-fields").append(section);
    }
    const label = document.createElement("label"); label.className = "settings-field";
    const text = document.createElement("span"); text.textContent = field.label;
    const input = document.createElement(["select", "microphone"].includes(field.type) ? "select" : "input");
    input.id = "setting-" + field.key;
    if (input.tagName === "INPUT") input.type = field.type;
    if (field.type === "select") {
      field.choices.forEach((value, i) => input.add(new Option(field.labels?.[i] || value || "オフ", value)));
    }
    for (const attr of ["min", "max", "step"]) if (field[attr] !== undefined) input[attr] = field[attr];
    if (field.type === "checkbox") input.checked = Boolean(settingsBaseline[field.key]);
    else if (field.type !== "microphone") input.value = field.type === "password" ? "" : settingsBaseline[field.key] ?? "";
    input.autocomplete = "off";
    input.oninput = markDirty;
    label.append(text, input); groups.get(field.group).section.append(label);
  }
  deviceSignature = ""; renderDevices(state.devices || {});
  $("settings-dirty").textContent = "保存済み";
}
function renderDevices(devices) {
  const signature = JSON.stringify(devices);
  if (signature === deviceSignature) return;
  deviceSignature = signature;
  const mic = $("setting-mic_device_index");
  if (mic) {
    const previous = mic.options.length ? mic.value : settingsBaseline.mic_device_index;
    mic.replaceChildren(new Option("システムの既定のマイク", ""));
    for (const device of devices.microphones || []) mic.add(new Option(device.name, String(device.index)));
    if (previous !== null && previous !== undefined && previous !== "" && ![...mic.options].some(o => o.value === String(previous))) {
      mic.add(new Option(`保存済みのマイク (${previous})`, String(previous)));
    }
    mic.value = previous ?? "";
  }
  $("voice-choice").replaceChildren(new Option("ボイスを選択して保存", ""));
  for (const voice of devices.voices || []) $("voice-choice").add(new Option(voice.display, String(voice.id)));
}
$("voice-choice").onchange = (event) => {
  if (event.target.value === "") return;
  const engine = $("setting-tts_engine");
  if (!engine || engine.value !== state.settings.values.tts_engine) {
    message("先にエンジンを保存して、一覧を更新してください。", true); return;
  }
  const input = $(engine.value === "edge-tts" ? "setting-edge_tts_voice" : "setting-voicevox_speaker_id");
  input.value = event.target.value; markDirty();
};
$("settings-form").onsubmit = async (event) => {
  event.preventDefault();
  for (const field of state.settings.fields) {
    const input = $("setting-" + field.key);
    input.disabled = false;
    if (!input.checkValidity()) {
      selectSettingsGroup(field.group); input.reportValidity(); return;
    }
  }
  selectSettingsGroup(settingsGroup);
  const changes = changedSettings();
  if (!Object.keys(changes).length) { message("変更はありません。"); return; }
  if (await send("save_settings", changes)) {
    settingsBaseline = savedSettingValues();
    for (const field of state.settings.fields) {
      const input = $("setting-" + field.key);
      if (field.type === "checkbox") input.checked = Boolean(settingsBaseline[field.key]);
      else input.value = field.type === "password" ? "" : settingsBaseline[field.key] ?? "";
    }
    markDirty();
  }
};
function closeSettings() {
  if ($("settings-panel").hidden) return;
  if (settingsDirty() && !confirm("未保存の変更を破棄して閉じますか？")) return;
  $("settings-panel").hidden = true;
  $("quick-panel").hidden = false;
  document.querySelector(".workspace").classList.remove("settings-open");
  for (const button of document.querySelectorAll(".rail-button")) button.setAttribute("aria-pressed", String(button.id === "home"));
  $("settings-fields").replaceChildren();
  settingGroups.clear();
  settingsTrigger?.focus({ preventScroll: true });
  controlsEnabled();
}
$("close-settings").onclick = closeSettings;
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("help-dialog").open && !$("settings-panel").hidden) {
    event.preventDefault(); closeSettings();
  }
});
for (const [id, action] of [["authenticate", "authenticate"], ["logout", "logout"], ["refresh-devices", "refresh_devices"], ["test-voice", "test_voice"], ["check-update", "check_update"], ["install-update", "install_update"], ["restart", "restart"]]) {
  $(id).onclick = () => {
    if (action === "logout" && !confirm("Twitchからログアウトしますか？")) return;
    if (action === "restart" && !confirm("配信処理を終了し、再起動して更新しますか？")) return;
    send(action);
  };
}

async function poll() {
  const current = generation;
  try {
    if (!busy) {
      const next = await api("/api/state");
      if (!busy && current === generation) render(next);
    }
  } catch (error) { if (!busy && current === generation) disconnected(error); }
  finally { setTimeout(poll, 1000); }
}
poll();
