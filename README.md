# comfyui-Reference_image

独立的 ComfyUI 参考图创作节点。安装到 `ComfyUI/custom_nodes/comfyui-Reference_image` 后重启 ComfyUI，在画布搜索 **参考图创作台**。

节点内四张卡片分别处理人物、场景、姿势和服装。人物、姿势、服装可以直接选择本地素材库或上传图片；场景可以上传图片。选择和上传只改变本节点，不自动运行工作流。图片保存在 ComfyUI 的 `input/reference-image`。

本地图库放在插件内的 `resources/face-gallery`、`resources/costume-gallery`、`resources/pose-gallery`。节点优先从本插件读取这些目录。若没有这些目录，仍可上传图片使用。

点击“刷新提示词”可预览整合后的文字；运行工作流时，后端使用同一套提示词逻辑。节点依次输出最终提示词、IMAGE 列表和参考图编号说明。列表按实际选择的人物、场景、姿势、服装排序，需连接支持 IMAGE 列表的下游生图节点。此节点不内置生图服务。

图库素材体积约 4 GB，且具有独立授权条件，因此 GitHub 仓库只包含代码，本地素材目录被 Git 忽略；请保留素材目录中的来源和许可说明。
