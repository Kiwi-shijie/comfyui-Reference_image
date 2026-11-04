"""Reference image composer with optional local gallery browsing."""
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import folder_paths
from aiohttp import web
from PIL import Image
from server import PromptServer

KINDS = {"face": "face-gallery", "costume": "costume-gallery", "pose": "pose-gallery"}
SINGLE_POSE = {"全身单人・标准系", "全身单人・性感系", "上半身单人"}


def gallery_root(kind):
    if kind not in KINDS:
        raise ValueError("未知素材类型")
    base = Path(__file__).resolve().parent
    candidates = [base / "resources" / KINDS[kind]]
    candidates += [p / "resources" / KINDS[kind] for p in base.parent.iterdir() if p.is_dir() and p != base]
    for folder in candidates:
        if (folder / "manifest.json").is_file():
            return folder
    raise FileNotFoundError(f"没有找到 {KINDS[kind]} 素材目录；请先安装包含该素材的插件。")


@lru_cache(maxsize=6)
def _catalog(path, stamp):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("素材目录格式无效")
    return items


def catalog(kind):
    manifest = gallery_root(kind) / "manifest.json"
    stat = manifest.stat()
    return _catalog(str(manifest), (stat.st_mtime_ns, stat.st_size))


def selected(kind, identifier):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier or ""):
        raise ValueError("素材 ID 无效")
    item = next((i for i in catalog(kind) if i.get("id") == identifier), None)
    if item is None:
        raise ValueError("素材不存在")
    if kind == "pose" and item.get("system") not in SINGLE_POSE:
        raise ValueError("请选择单人姿势")
    return item


def image_path(kind, item, thumbnail=False):
    identifier = item["id"]
    relative = item.get("file") if kind == "pose" else item.get("files", {}).get("thumb" if thumbnail else "image")
    expected = f"images/{identifier}.webp" if kind == "pose" else f"{'thumb' if thumbnail else 'image'}/{identifier}.webp"
    if relative != expected:
        raise ValueError("素材路径无效")
    path = gallery_root(kind) / relative
    if not path.is_file():
        raise FileNotFoundError("素材图片缺失")
    return path


def load_image(kind, identifier):
    import torch
    with Image.open(image_path(kind, selected(kind, identifier))) as source:
        pixels = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(pixels).unsqueeze(0)


def load_uploaded(name):
    import torch
    if not name or len(name) > 220 or Path(name).name != name or "/" in name or "\\" in name or not re.search(r"\.(png|jpg|jpeg|webp)$", name, re.I):
        raise ValueError("上传图片文件名无效")
    path = Path(folder_paths.get_input_directory()) / "reference-image" / name
    if not path.is_file():
        raise FileNotFoundError("上传图片不存在，请重新上传")
    with Image.open(path) as source:
        pixels = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(pixels).unsqueeze(0)


@PromptServer.instance.routes.get("/reference-image/catalog/{kind}")
async def serve_catalog(request):
    try:
        kind = request.match_info["kind"]
        items = catalog(kind)
        if kind == "pose":
            items = [i for i in items if i.get("system") in SINGLE_POSE]
        result = [{"id": i["id"], "name": i.get("name") or i.get("category_zh") or i["id"], "category": i.get("category_zh") or i.get("category") or i.get("system") or "", "angle": i.get("angle", "")} for i in items]
        return web.json_response({"items": result})
    except (ValueError, OSError) as exc:
        return web.json_response({"error": str(exc)}, status=400)


@PromptServer.instance.routes.get("/reference-image/image/{kind}/{identifier}")
async def serve_image(request):
    try:
        kind = request.match_info["kind"]
        return web.FileResponse(image_path(kind, selected(kind, request.match_info["identifier"]), request.query.get("size") == "thumb"))
    except (ValueError, OSError):
        raise web.HTTPNotFound(text="素材不存在")


class ReferenceImageComposer:
    CATEGORY = "image/reference"
    FUNCTION = "compose"
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("📝最终提示词", "🖼️参考图列表", "📋参考图顺序")
    OUTPUT_IS_LIST = (False, True, False)
    DESCRIPTION = "四栏组合人物、场景、服装和姿势参考，预览整合提示词。连接下游多图生图节点使用。"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "📝创作需求": ("STRING", {"default": "", "multiline": True}),
            "🌄场景图用途": (["仅环境场景", "环境与构图", "第二个人物"],),
            "📷使用姿势视角": ("BOOLEAN", {"default": True}),
            "🧍姿势说明": ("STRING", {"default": "", "multiline": True}),
            "人物素材ID": ("STRING", {"default": ""}),
            "人物上传文件": ("STRING", {"default": ""}),
            "场景上传文件": ("STRING", {"default": ""}),
            "姿势素材ID": ("STRING", {"default": ""}),
            "姿势上传文件": ("STRING", {"default": ""}),
            "服装素材ID": ("STRING", {"default": ""}),
            "服装上传文件": ("STRING", {"default": ""}),
        }}

    def compose(self, **kw):
        images, order, present = [], [], []
        roles = [
            ("人物上传文件", "人物素材ID", "face", "人物"),
            ("场景上传文件", None, None, "场景"),
            ("服装上传文件", "服装素材ID", "costume", "服装"),
            ("姿势上传文件", "姿势素材ID", "pose", "姿势"),
        ]
        for upload_field, field, kind, label in roles:
            uploaded = str(kw.get(upload_field, "")).strip()
            image = load_uploaded(uploaded) if uploaded else None
            if image is None and field and kw.get(field, "").strip():
                image = load_image(kind, kw[field].strip())
            if image is None:
                continue
            if len(image.shape) != 4 or image.shape[0] != 1 or image.shape[-1] not in (3, 4):
                raise ValueError(f"{label}参考必须是单张 RGB 或 RGBA IMAGE")
            images.append(image)
            tag = f"<image{len(images)}>"
            order.append(f"{tag}：{label}参考")
            present.append(label)
        return compose_text(present, kw), images, "\n".join(order) if order else "未连接参考图（文生图）"


def compose_text(present, kw):
    lines = []
    number = {name: index + 1 for index, name in enumerate(present)}
    if "人物" in number:
        lines.append(f"以<image{number['人物']}>中的人物为角色身份参考，保持面部特征、发型和身份一致。")
    if "场景" in number:
        rule = {"仅环境场景": "只参考环境、布景和光照；不要把图中人物作为额外角色。", "环境与构图": "参考环境、布景、光照及画面构图；不要把图中人物作为额外角色。", "第二个人物": "参考其中的第二个人物，保持其身份特征，并结合场景。"}[kw["🌄场景图用途"]]
        lines.append(f"<image{number['场景']}>：{rule}")
    if "服装" in number:
        lines.append(f"参考<image{number['服装']}>中的服装款式、颜色、材质和细节，为主角换上该服装，不改变人物身份。")
    if "姿势" in number:
        lines.append(f"参考<image{number['姿势']}>的身体姿势、手部位置和肢体方向。" + ("同时参考其拍摄视角。" if kw["📷使用姿势视角"] else "拍摄视角由创作需求决定。"))
    description = str(kw.get("🧍姿势说明", "")).strip()
    if description:
        lines.append("姿势补充：" + description)
    brief = str(kw.get("📝创作需求", "")).strip()
    if brief:
        lines.append("创作要求：" + brief)
    if not lines:
        raise ValueError("请填写创作需求或选择参考图")
    return "\n".join(lines)


@PromptServer.instance.routes.post("/reference-image/prompt")
async def serve_prompt(request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("提示词参数无效")
        present = payload.get("present", [])
        if not isinstance(present, list) or len(present) > 4 or any(x not in ("人物", "场景", "姿势", "服装") for x in present) or len(set(present)) != len(present):
            raise ValueError("参考图顺序无效")
        result = compose_text(present, payload)
        return web.json_response({"prompt": result})
    except (ValueError, KeyError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)


WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {"ReferenceImageComposer": ReferenceImageComposer}
NODE_DISPLAY_NAME_MAPPINGS = {"ReferenceImageComposer": "🖼️ 参考图创作台"}
