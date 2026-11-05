"""Reference image composer with optional local gallery browsing."""
import json
import math
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
    RETURN_TYPES = ("STRING", "IMAGE", "STRING", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "INT", "INT")
    RETURN_NAMES = ("📝最终提示词", "🖼️参考图列表", "📋参考图顺序", "👩脸模参考", "🌄场景参考", "👗服装参考", "🧍姿势参考", "↔️姿势画幅宽", "↕️姿势画幅高")
    OUTPUT_IS_LIST = (False, True, False, False, False, False, False, False, False)
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
            "🎯姿势优先": ("BOOLEAN", {"default": False}),
            "🖼️构图范围": (["自动跟随姿势", "半身", "全身"],),
        }}

    def compose(self, **kw):
        images, order, present = [], [], []
        separate = {}
        roles = [
            ("人物上传文件", "人物素材ID", "face", "人物"),
            ("场景上传文件", None, None, "场景"),
            ("服装上传文件", "服装素材ID", "costume", "服装"),
            ("姿势上传文件", "姿势素材ID", "pose", "姿势"),
        ]
        if kw.get("🎯姿势优先", False):
            roles = [roles[3], *roles[:3]]
        for upload_field, field, kind, label in roles:
            uploaded = str(kw.get(upload_field, "")).strip()
            image = load_uploaded(uploaded) if uploaded else None
            if image is None and field and kw.get(field, "").strip():
                image = load_image(kind, kw[field].strip())
            if image is None:
                separate[label] = None
                continue
            if len(image.shape) != 4 or image.shape[0] != 1 or image.shape[-1] not in (3, 4):
                raise ValueError(f"{label}参考必须是单张 RGB 或 RGBA IMAGE")
            images.append(image)
            separate[label] = image
            tag = f"<image{len(images)}>"
            order.append(f"{tag}：{label}参考")
            present.append(label)
        pose = separate["姿势"]
        if pose is not None:
            ratio = max(0.5, min(2.0, pose.shape[2] / pose.shape[1]))
            width = round(math.sqrt(3 * 1024 * 1024 * ratio) / 32) * 32
            width = max(512, min(2048, width))
            height = round(width / ratio / 32) * 32
            height = max(512, min(2048, height))
        else:
            width, height = 1024, 1536
        return (
            compose_text(present, kw),
            images,
            "\n".join(order) if order else "未连接参考图（文生图）",
            separate["人物"], separate["场景"], separate["服装"], separate["姿势"],
            width, height,
        )


def compose_text(present, kw):
    lines = []
    number = {name: index + 1 for index, name in enumerate(present)}
    if kw.get("🎯姿势优先", False) and "姿势" in number:
        lines.append(f"以<image{number['姿势']}>作为构图和肢体排列的主要画布。先观察当前姿势图，准确识别左右手掌落点、肘部弯曲方向、肩膀、躯干及可见腿部的位置，并在最终提示词中写出这些具体关系；姿势图变化时必须重新识别，不沿用旧姿势描述。生成结果必须跟随当前图的可见姿态，把线稿转换为写实真人，不保留线条或关节圆圈；服装图里的模特站姿不得覆盖姿势图。")
    if "人物" in number:
        lines.append(f"以<image{number['人物']}>中的人物为角色身份参考，保持面部特征、发型和身份一致；不沿用原人物照片的背景和棚拍光线。")
    if "场景" in number:
        rule = {"仅环境场景": "只参考环境、布景和光照；不要把图中人物作为额外角色。", "环境与构图": "参考环境、布景、光照及画面构图；不要把图中人物作为额外角色。", "第二个人物": "参考其中的第二个人物，保持其身份特征，并结合场景。"}[kw["🌄场景图用途"]]
        lines.append(f"<image{number['场景']}>：{rule}")
        lines.append("场景光影是最终画面的统一光源：分析场景中主光的方向、色温、强弱、阴影边缘和明暗分布；让人物面部、头发、皮肤、衣服、毛绒与鞋子受到同方向的光照并产生对应自阴影。人物脚下应有与地面接触、方向和软硬度一致的投影，衣物与身体交界处有真实遮挡阴影。保留场景原有光斑，但光斑照到人物时也应改变人物局部亮度和颜色；避免人物边缘发白、悬浮或像贴在背景上。")
    if "服装" in number:
        lines.append(f"只提取<image{number['服装']}>的衣物款式、颜色、材质和细节，为主角穿上该服装；忽略服装图中的假人、模特身体、面孔、背景和道具，不改变主角身份。")
    if "姿势" in number:
        lines.append(f"只参考<image{number['姿势']}>的身体姿势、手部位置和肢体方向；构图跟随姿势图实际可见的范围：半身姿势优先半身画面，完整全身姿势才安排全身画面，不要因服装图是全身就强行补出姿势图未展示的腿部。不要把姿势线稿、人体模型、关节标记或其服装画进成图。" + ("同时参考其拍摄视角。" if kw["📷使用姿势视角"] else "拍摄视角由创作需求决定。"))
        framing = kw.get("🖼️构图范围", "自动跟随姿势")
        if framing == "自动跟随姿势" and not kw.get("姿势上传文件") and kw.get("姿势素材ID"):
            framing = "半身" if selected("pose", str(kw["姿势素材ID"]).strip()).get("system") == "上半身单人" else "全身"
        if framing == "半身":
            lines.append("最终成图必须是半身摄影构图：画面从头顶到腰部或臀部附近，人物上半身占画面主体，画面下沿在腰部附近裁切；不展示完整双腿、鞋子或地面。服装图即使是全身照，也只提供画面内可见衣物，不决定构图。")
        elif framing == "全身":
            lines.append("最终成图为完整全身构图，头、手、腿和脚均在画面内；姿势图没有展示的下半身应自然延续，不照搬服装图模特的站姿。")
    if "人物" in number:
        lines.append("最终画面是一位面容清晰、皮肤和肢体自然的真人；人物身份以脸模参考为准，其他参考图只提供各自指定的信息。避免假人质感、塑料关节、重复肢体和拼贴感。")
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
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return web.json_response({"error": str(exc)}, status=400)


WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {"ReferenceImageComposer": ReferenceImageComposer}
NODE_DISPLAY_NAME_MAPPINGS = {"ReferenceImageComposer": "🖼️ 参考图创作台"}
