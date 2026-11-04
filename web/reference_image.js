import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const css = document.createElement("link");
css.rel = "stylesheet";
css.href = new URL("./reference_image.css", import.meta.url).href;
document.head.append(css);

const ROLES = [
  { key: "face", label: "脸模", icon: "👩", id: "人物素材ID", upload: "人物上传文件" },
  { key: "scene", label: "场景", icon: "🌄", upload: "场景上传文件" },
  { key: "costume", label: "服装", icon: "👗", id: "服装素材ID", upload: "服装上传文件" },
  { key: "pose", label: "姿势", icon: "🧍", id: "姿势素材ID", upload: "姿势上传文件" },
];
const NAME = { face: "人物", scene: "场景", costume: "服装", pose: "姿势" };
const el = (tag, cls = "", value = "") => {
  const node = document.createElement(tag);
  node.className = cls;
  if (value) node.textContent = value;
  return node;
};
const button = (text, cls, action) => {
  const node = el("button", cls, text);
  node.type = "button";
  node.onclick = action;
  return node;
};
const galleryUrl = (role, id, thumb = true) => api.apiURL(`/reference-image/image/${role.key}/${encodeURIComponent(id)}${thumb ? "?size=thumb" : ""}`);
const uploadedUrl = name => api.apiURL(`/view?${new URLSearchParams({ filename: name, subfolder: "reference-image", type: "input" })}`);

async function jsonResponse(response, title) {
  if (response.status === 404) throw Error(`${title}接口尚未加载，请完全重启 ComfyUI。`);
  if (!(response.headers.get("content-type") || "").includes("application/json")) throw Error(`${title}返回了非 JSON 内容（HTTP ${response.status}）。`);
  const result = await response.json();
  if (!response.ok) throw Error(result.error || `${title}失败（HTTP ${response.status}）`);
  return result;
}

app.registerExtension({
  name: "ReferenceImage.Composer",
  async beforeRegisterNodeDef(Node, data) {
    if (data.name !== "ReferenceImageComposer") return;
    const original = Node.prototype.onNodeCreated;
    Node.prototype.onNodeCreated = function () {
      original?.apply(this, arguments);
      const node = this;
      node.color = "#173b78";
      node.bgcolor = "#0b2456";
      const widgets = Object.fromEntries((node.widgets || []).map(w => [w.name, w]));
      for (const widget of Object.values(widgets)) {
        widget.type = "reference-hidden";
        widget.computeSize = () => [0, -4];
        widget.options ??= {};
        widget.options.hidden = true;
      }
      const root = el("div", "ri-root");
      const title = el("div", "ri-title", "四图组合 · 单人角色");
      const subtitle = el("div", "ri-subtitle", "1 脸模 → 2 场景 → 3 服装 → 4 姿势 · 上传图片不参与随机");
      const toolbar = el("div", "ri-toolbar");
      const status = el("span", "ri-status", "");
      const prompt = el("textarea", "ri-prompt");
      prompt.readOnly = true;
      prompt.placeholder = "选择参考素材或填写创作要求后，提示词会显示在这里";
      const rows = [];
      const catalogs = new Map();
      let busy = false;
      let previewVersion = 0;
      let removed = false;

      const get = name => widgets[name]?.value || "";
      const set = (name, value) => { widgets[name].value = value; node.setDirtyCanvas?.(true, true); };
      const reference = role => get(role.upload) ? { source: "upload", value: get(role.upload) } : role.id && get(role.id) ? { source: "gallery", value: get(role.id) } : null;
      const chosen = () => ROLES.filter(reference).map(role => NAME[role.key]);

      async function refresh() {
        const version = ++previewVersion;
        const present = chosen();
        if (!present.length && !get("📝创作需求").trim() && !get("🧍姿势说明").trim()) {
          prompt.value = "";
          status.textContent = "选择参考图后生成提示词";
          return;
        }
        const payload = {
          present,
          "📝创作需求": get("📝创作需求"),
          "🌄场景图用途": get("🌄场景图用途") || "仅环境场景",
          "📷使用姿势视角": widgets["📷使用姿势视角"]?.value ?? true,
          "🧍姿势说明": get("🧍姿势说明"),
        };
        try {
          const response = await api.fetchApi("/reference-image/prompt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
          const result = await jsonResponse(response, "提示词");
          if (version !== previewVersion || removed) return;
          prompt.value = result.prompt;
          status.textContent = `${present.length} 张参考图`;
        } catch (error) {
          if (version !== previewVersion || removed) return;
          prompt.value = "";
          status.textContent = error.message;
        }
      }
      function update() { rows.forEach(row => row.render()); void refresh(); }
      async function catalog(role) {
        if (catalogs.has(role.key)) return catalogs.get(role.key);
        const response = await api.fetchApi(`/reference-image/catalog/${role.key}`);
        const result = await jsonResponse(response, `${role.label}素材库`);
        catalogs.set(role.key, result.items);
        return result.items;
      }
      async function randomize(role = null) {
        if (busy) return;
        busy = true;
        status.textContent = "正在选择素材…";
        try {
          for (const item of role ? [role] : ROLES.filter(r => r.id)) {
            if (get(item.upload)) continue;
            const items = await catalog(item);
            if (!items.length) continue;
            const alternatives = items.filter(v => v.id !== get(item.id));
            const pool = alternatives.length ? alternatives : items;
            set(item.id, pool[Math.floor(Math.random() * pool.length)].id);
          }
          update();
        } catch (error) { status.textContent = error.message; }
        finally { busy = false; }
      }
      toolbar.append(button("🎲 随机组合", "ri-primary", () => randomize()), button("更新提示词", "", refresh), button("创作设置", "", openSettings), status);
      root.append(title, subtitle, toolbar);
      const grid = el("div", "ri-grid");
      root.append(grid);

      for (const [index, role] of ROLES.entries()) {
        const card = el("section", "ri-card");
        const head = el("div", "ri-card-head");
        head.append(el("strong", "", `${role.icon} ${index + 1} · ${role.label}`));
        if (role.id) head.append(button("🎲", "ri-dice", () => randomize(role)));
        const source = el("select", "ri-source");
        for (const option of role.id ? ["素材库", "上传图片"] : ["上传图片"]) source.add(new Option(option, option));
        const frame = el("div", "ri-frame");
        const image = el("img", "ri-image");
        const empty = el("div", "ri-empty", "选择参考图");
        const zoom = button("🔍", "ri-zoom", () => {
          const ref = reference(role);
          if (ref) showImage(ref.source === "upload" ? uploadedUrl(ref.value) : galleryUrl(role, ref.value, false), `${role.label}参考`);
        });
        frame.append(image, empty, zoom);
        const name = el("div", "ri-name", "尚未选择");
        const choose = button(role.id ? "打开素材库" : "上传场景图", "ri-wide", () => role.id && source.value === "素材库" ? openGallery(role) : file.click());
        const file = el("input", ""); file.type = "file"; file.accept = "image/png,image/jpeg,image/webp"; file.hidden = true;
        const clear = button("清除", "ri-clear", () => { if (role.id) set(role.id, ""); set(role.upload, ""); update(); });
        const actions = el("div", "ri-card-actions"); actions.append(choose, clear);
        card.append(head, source, frame, name, actions, file);
        grid.append(card);
        const render = () => {
          const ref = reference(role);
          source.value = role.id && ref?.source !== "upload" ? "素材库" : "上传图片";
          const url = ref ? ref.source === "upload" ? uploadedUrl(ref.value) : galleryUrl(role, ref.value) : "";
          image.hidden = !url; empty.hidden = !!url; zoom.hidden = !url;
          if (url && image.getAttribute("src") !== url) image.src = url;
          if (!url) image.removeAttribute("src");
          name.textContent = ref?.value || "尚未选择";
          choose.textContent = role.id && source.value === "素材库" ? "打开素材库" : "上传图片";
          clear.hidden = !ref;
        };
        source.onchange = () => {
          if (source.value === "上传图片") file.click();
          else { set(role.upload, ""); update(); }
        };
        file.addEventListener("cancel", update);
        file.onchange = async () => {
          const selected = file.files?.[0]; file.value = ""; if (!selected) return;
          if (selected.size > 30 * 1024 * 1024) { status.textContent = "图片不能超过 30MB"; return; }
          const form = new FormData(); form.append("image", selected); form.append("type", "input"); form.append("subfolder", "reference-image"); form.append("overwrite", "false");
          try {
            const response = await api.fetchApi("/upload/image", { method: "POST", body: form });
            const result = await jsonResponse(response, "上传图片");
            set(role.upload, result.name); if (role.id) set(role.id, ""); update();
          } catch (error) { status.textContent = error.message; }
        };
        rows.push({ render }); render();
      }

      const promptHeading = el("div", "ri-prompt-heading", "✨ 整合提示词");
      const copy = button("复制提示词", "ri-copy", async () => {
        try { await navigator.clipboard.writeText(prompt.value); status.textContent = "提示词已复制"; }
        catch { prompt.focus(); prompt.select(); status.textContent = "按 Ctrl+C 复制"; }
      });
      root.append(promptHeading, prompt, copy, el("div", "ri-foot", "输出四类有序参考图；连接生图节点后手动运行。"));
      for (const event of ["pointerdown", "keydown", "wheel"]) root.addEventListener(event, e => e.stopPropagation());
      const dom = node.addDOMWidget("reference_studio", "reference_studio", root, { serialize: false, getMinHeight: () => 645, getHeight: () => 645, hideOnZoom: false });
      dom.computeSize = width => [Math.max(width || 0, 780), 645];
      node.setSize([Math.max(node.size[0], 780), Math.max(node.size[1], 750)]);
      const configured = node.onConfigure;
      node.onConfigure = function () { const result = configured?.apply(this, arguments); queueMicrotask(() => { node.setSize([Math.max(node.size[0], 780), Math.max(node.size[1], 750)]); update(); }); return result; };
      const onRemoved = node.onRemoved;
      node.onRemoved = function () { removed = true; return onRemoved?.apply(this, arguments); };
      queueMicrotask(refresh);

      async function openGallery(role) {
        const shade = el("div", "ri-shade");
        const modal = el("div", "ri-modal");
        const bar = el("div", "ri-modal-bar");
        const close = button("关闭", "", () => shade.remove());
        bar.append(el("strong", "", `${role.icon} ${role.label}素材库`), close);
        const search = el("input", "ri-search"); search.placeholder = "搜索名称、类别或姿势视角";
        const gallery = el("div", "ri-gallery");
        const message = el("div", "ri-gallery-status", "正在读取…");
        modal.append(bar, search, message, gallery); shade.append(modal); document.body.append(shade);
        shade.onclick = event => { if (event.target === shade) shade.remove(); };
        try {
          const items = await catalog(role);
          message.textContent = `共 ${items.length} 张；显示前 120 张，可输入关键词筛选`;
          search.oninput = draw; draw();
          function draw() {
            const query = search.value.trim().toLowerCase();
            const filtered = items.filter(item => `${item.id} ${item.name} ${item.category} ${item.angle}`.toLowerCase().includes(query));
            gallery.replaceChildren();
            for (const item of filtered.slice(0, 120)) {
              const tile = button("", "ri-tile", () => { set(role.id, item.id); set(role.upload, ""); shade.remove(); update(); });
              const photo = el("img"); photo.loading = "lazy"; photo.src = galleryUrl(role, item.id);
              tile.append(photo, el("span", "", `${item.name}${item.angle ? ` · ${item.angle}` : ""}`));
              gallery.append(tile);
            }
            if (!filtered.length) gallery.append(el("div", "ri-gallery-status", "没有匹配的素材"));
          }
        } catch (error) { message.textContent = error.message; }
      }
      function openSettings() {
        const shade = el("div", "ri-shade");
        const modal = el("div", "ri-modal ri-settings");
        const bar = el("div", "ri-modal-bar");
        bar.append(el("strong", "", "创作设置"), button("完成", "", () => { shade.remove(); void refresh(); }));
        modal.append(bar);
        const textarea = (label, field) => {
          modal.append(el("label", "ri-setting-label", label));
          const input = el("textarea", "ri-setting-text"); input.value = get(field); input.oninput = () => { set(field, input.value); void refresh(); }; modal.append(input);
        };
        textarea("创作需求", "📝创作需求");
        const sceneLabel = el("label", "ri-setting-label", "场景图用途");
        const sceneSelect = el("select", "ri-setting-select");
        for (const value of ["仅环境场景", "环境与构图", "第二个人物"]) sceneSelect.add(new Option(value, value));
        sceneSelect.value = get("🌄场景图用途") || "仅环境场景";
        sceneSelect.onchange = () => { set("🌄场景图用途", sceneSelect.value); void refresh(); };
        modal.append(sceneLabel, sceneSelect);
        const poseCheck = el("label", "ri-setting-check");
        const checkbox = el("input"); checkbox.type = "checkbox"; checkbox.checked = widgets["📷使用姿势视角"]?.value ?? true;
        checkbox.onchange = () => { set("📷使用姿势视角", checkbox.checked); void refresh(); };
        poseCheck.append(checkbox, document.createTextNode(" 使用姿势参考的拍摄视角")); modal.append(poseCheck);
        textarea("姿势补充说明", "🧍姿势说明");
        shade.append(modal); document.body.append(shade);
        shade.onclick = event => { if (event.target === shade) shade.remove(); };
      }
    };
  },
});

function showImage(url, title) {
  const shade = el("div", "ri-shade");
  const modal = el("div", "ri-lightbox");
  const bar = el("div", "ri-modal-bar");
  bar.append(el("strong", "", title), button("关闭", "", () => shade.remove()));
  const image = el("img"); image.src = url;
  modal.append(bar, image); shade.append(modal); document.body.append(shade);
  shade.onclick = event => { if (event.target === shade) shade.remove(); };
}
