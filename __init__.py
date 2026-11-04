"""Compose role-specific references for an existing ComfyUI image workflow."""

class DapaoCharacterStudio:
    CATEGORY = "🍭大炮-llama-cpp"
    FUNCTION = "compose"
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("📝最终提示词", "🖼️参考图列表", "📋参考图顺序")
    OUTPUT_IS_LIST = (False, True, False)
    DESCRIPTION = "按人物、场景、姿势、服装顺序整理已连接的参考图及提示词；需要下游多图生图节点。"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "📝创作需求": ("STRING", {"default": "", "multiline": True}),
            "🌄场景图用途": (["仅环境场景", "环境与构图", "第二个人物"],),
            "📷使用姿势视角": ("BOOLEAN", {"default": True}),
            "🧍姿势说明": ("STRING", {"default": "", "multiline": True}),
        }, "optional": {
            "👤人物参考": ("IMAGE",), "🌄场景参考": ("IMAGE",),
            "🧍姿势参考": ("IMAGE",), "👗服装参考": ("IMAGE",),
            "🔗上游姿势说明": ("STRING", {"forceInput": True}),
        }}

    def compose(self, **kw):
        parts = []
        images = []
        order = []
        angle = kw["📷使用姿势视角"]
        scene = kw["🌄场景图用途"]
        for key, label in (("👤人物参考", "人物"), ("🌄场景参考", "场景"), ("🧍姿势参考", "姿势"), ("👗服装参考", "服装")):
            image = kw.get(key)
            if image is None:
                continue
            if len(image.shape) != 4 or image.shape[0] != 1 or image.shape[-1] not in (3, 4):
                raise ValueError(f"{label}参考必须是单张 RGB 或 RGBA IMAGE，请先拆分批次。")
            images.append(image)
            tag = f"<image{len(images)}>"
            order.append(f"{tag}：{label}参考")
            if label == "人物":
                parts.append(f"以{tag}中的人物为角色身份参考，保持面部特征、发型和身份一致。")
            elif label == "场景":
                rule = {"仅环境场景": "只参考环境、布景和光照；不要把图中人物作为额外角色。", "环境与构图": "参考环境、布景、光照及画面构图；不要把图中人物作为额外角色。", "第二个人物": "参考其中的第二个人物，保持其身份特征，并结合场景。"}[scene]
                parts.append(f"{tag}：{rule}")
            elif label == "姿势":
                parts.append(f"参考{tag}的身体姿势、手部位置和肢体方向。" + ("同时参考其拍摄视角。" if angle else "拍摄视角由创作需求决定。"))
            else:
                parts.append(f"参考{tag}中的服装款式、颜色、材质和细节，为主角换上该服装，不改变人物身份。")
        description = "；".join(x.strip() for x in (kw.get("🧍姿势说明", ""), kw.get("🔗上游姿势说明", "")) if x and x.strip())
        if description:
            parts.append("姿势补充：" + description)
        brief = kw["📝创作需求"].strip()
        if brief:
            parts.append("创作要求：" + brief)
        if not parts:
            raise ValueError("请填写创作需求或连接参考图。")
        return ("\n".join(parts), images, "\n".join(order) if order else "未连接参考图（文生图）")

NODE_CLASS_MAPPINGS = {"DapaoCharacterStudio": DapaoCharacterStudio}
NODE_DISPLAY_NAME_MAPPINGS = {"DapaoCharacterStudio": "🎨 角色创作台@炮老师小课堂"}
