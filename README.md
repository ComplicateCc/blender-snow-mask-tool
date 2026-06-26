# Universal Snow Mask Tool for Blender

Blender 插件，用于把可调覆雪 mask 材质批量应用到 FBX 建筑模型上，并保留每个 submesh 自己的原始贴图、法线、打包材质贴图和 UV。

## 功能

- 导入 FBX 并为每个原始材质创建独立覆雪材质。
- 支持 ASCII FBX 兜底导入，适配 Blender 原生 FBX 导入器不支持的旧 ASCII FBX。
- 保留每个 submesh 自己的 diffuse、normal、`_m` 打包贴图和活动 UV。
- 可选择一个模板材质，只同步 `SNOW_MASK_CONTROLS` 覆雪参数到其他材质。
- 全局 Debug View：一键查看 `Final`、`Normal`、`Corner`、`Ground` mask。
- Preview Mode：在 `Original+Snow` 和 `Mask Only` 之间切换。

## 安装

1. 下载或 clone 本仓库。
2. 在 Blender 中打开 `Edit > Preferences > Add-ons > Install...`。
3. 选择 `addons/snow_mask_universal_tool/__init__.py`。
4. 启用 `Universal Snow Mask Tool`。
5. 在 3D View 右侧栏按 `N`，打开 `Snow Mask` 标签。

也可以直接把 `addons/snow_mask_universal_tool` 文件夹复制到 Blender 用户插件目录。

## 推荐工作流

1. 点击 `Import FBX And Apply Snow` 导入 FBX。
2. 插件会为每个原始材质创建独立的 `*_OriginalTexture_SnowMix` 材质。
3. 选择一个覆雪材质，调整节点里的 `SNOW_MASK_CONTROLS`。
4. 在面板的 `Template` 下拉框选择这个材质。
5. 点击 `Sync From Template Material`，只同步覆雪参数，不改贴图和 normal map。
6. 用 `Preview Mode > Mask Only` 加 `Global Debug View` 检查不同 mask。
7. 回到 `Original+Snow` 和 `Final` 查看最终效果。

## 面板说明

- `Import FBX And Apply Snow`：导入 FBX 并应用覆雪材质。
- `Create Independent Snow Materials`：对当前场景已有材质批量创建独立覆雪材质。
- `Template`：选择一个已经调好的覆雪材质作为参数模板。
- `Sync From Template Material`：同步模板材质的覆雪参数到所有覆雪材质。
- `Sync From Active Material`：从当前选中物体的 active material 同步覆雪参数。
- `Global Debug View`：切换 `Final`、`Normal`、`Corner`、`Ground` mask。
- `Preview Mode`：切换 `Original+Snow` 或 `Mask Only`。
- `Setup Snow Preview Lighting`：设置预览灯光和相机。

## 示例

`examples/` 目录包含：

- 原始贴图导入检查工程。
- 覆雪材质示例工程。
- 对应预览 PNG。

示例工程中的贴图可能引用本地原始资源路径；插件本身不依赖这些示例贴图。

## 版本

当前插件版本：`1.0.6`。

主要修正：

- 导入所有 FBX UV 层，不再错误翻转 V 坐标。
- 贴图使用 FBX `UVSet` 对应的活动 UV。
- 每个 submesh 保留自己的贴图和材质信息。
- Debug View 直接重连到真实 mask 输出，避免依赖失效的 `Selected Debug Mask`。
