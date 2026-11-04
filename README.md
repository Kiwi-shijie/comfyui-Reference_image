# comfyui-Reference_image

独立的 ComfyUI 参考图创作节点。安装到 `ComfyUI/custom_nodes/comfyui-Reference_image` 后重启 ComfyUI，在画布搜索 **参考图创作台**。

节点内提供人物、姿势和服装素材缩略图选择与关键词筛选；场景连接 ComfyUI 的 Load Image。也可给四个参考输入直接连接 IMAGE，此时连接图优先于图库选择。素材从同一 `custom_nodes` 目录下已安装插件的 `resources/face-gallery`、`resources/pose-gallery`、`resources/costume-gallery` 读取，不复制或上传素材。缺少图库时仍可连接外部图片使用。

输出依次为最终提示词、IMAGE 列表和编号说明。列表依人物、场景、姿势、服装中实际存在的参考图排序。下游生图节点需支持 IMAGE 列表；若它只接受独立 IMAGE 输入，请直接将相同图片接到下游，并按编号调整提示词。此节点编排参考图，不内置生图服务。选取图库素材只更新节点，不自动执行工作流。

图库素材可能有单独的来源与授权条件；使用时遵守原素材目录附带的许可说明。
