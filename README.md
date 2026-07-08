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

当前插件版本：`1.3.1-test`。

主要修正：

- 导入所有 FBX UV 层，不再错误翻转 V 坐标。
- 贴图使用 FBX `UVSet` 对应的活动 UV。
- 每个 submesh 保留自己的贴图和材质信息。
- Debug View 直接重连到真实 mask 输出，避免依赖失效的 `Selected Debug Mask`。

## 1.1.0 Normal Mask 与 Top Projection

### Normal Noise Blend

新增 `Normal Noise Blend`：

- `0`：使用干净的顶面朝上 normal mask，不叠加 normal noise。
- `1`：使用原来的带 noise normal mask。
- `0-1`：在两者之间线性混合，方便调出既稳定又有自然破碎感的覆雪范围。

### Top Projection Mask

新增 `Bake Top Projection Mask`：

- 从模型正上方向下做 raycast。
- 每个 mesh 面如果是从上方第一个被看到的面，就写入 `SnowTopProjectionMask` face attribute。
- 材质中可通过 `Top Projection On/Off` 和 `Weight` 控制它是否并入最终覆雪范围。
- 适合标记“从天空落雪一定能覆盖”的屋顶、平台等区域。

注意：Top Projection 是烘焙到当前模型 face attribute 的工具层。模型拓扑或摆放变了，需要重新 Bake。
## 1.1.1 Top Projection 漏区修正

Top Projection Bake 从单点 face center 检测升级为更稳的多采样：

- 采样 face center、内缩顶点、内缩边中点。
- 增加 `Self Tolerance`，减少同一屋顶斜面被相邻三角面误挡导致的漏标。
- 增加 `Dilate Steps`，可把已标记区域扩张到邻接 face，用于补屋脊、檐口、切碎三角面造成的小洞。
- 默认参数：`Normal Z Min = -0.05`、`Sample Inset = 0.08`、`Self Tolerance = 0.35`、`Dilate Steps = 1`。

当前示例工程已用新版 Bake 重烘焙，标记面数从旧版约 `2266 / 40327` 提升到 `6427 / 40327`，用于补足屋顶和平台上方可见区域的漏雪问题。

如果覆盖过强，建议降低 `Top Projection Weight`；如果仍有小洞，Bake 时增加 `Dilate Steps` 到 `2`。
## 1.2.0 中文默认 UI 与 Top Projection Debug

- UI 默认改为中文，并新增 `语言 / Language` 下拉框，可切换中文和英文。
- `Global Debug View` 新增 `投影 / Top`，可直接查看 Top Projection mask。
- Top Projection debug 显示的是 `SnowTopProjectionMask * Top Projection Weight`，因此 `Weight` 会同时影响最终混合和 debug 预览强度。
- `Final` debug 仍显示最终 mask，包括 Top Projection 与原有 normal/corner/ground 的合并结果。
## 1.3.0 NeoX GIM 导入预览

新增 `.gim` 导入支持，用于 NeoX/G66 模型预览和覆雪材质调试：

- 支持读取 `.gim` XML 中的 `SubMesh` 和 `MtlIdx`。
- 按同名文件加载 `.mesh` 二进制几何。
- 按同名 `.mtg` 材质组读取 `Tex0`、`NormalMap`、`ParamMap`。
- 根据 `lightmap_pbr` 约定，`ParamMap` 使用 `R=Roughness`、`G=Metallic`、`A=AO`；当前 Blender 预览会连接 R/G 到 Roughness/Metallic，并保留贴图节点供后续扩展。
- 导入后会为每个 submesh 创建独立材质，再可用原有覆雪节点、Debug、Top Projection、参数同步工作流。

限制：当前 `.gim` 支持定位为 Blender 预览导入器，不写回 GIM/MTG/MESH；暂不支持 morph/track/per-key-bounding mesh。

测试样例：`hp_bank01.gim` 已验证可导入 2 个 submesh、2 个材质，并正常套用覆雪材质。
## 测试分支：GIM 坐标轴/UV 修正

本测试分支修正 NeoX GIM 预览导入：

- NeoX mesh 原始坐标按 `X, Y(height), Z` 解释。
- 导入 Blender 时转换为 `X, -Z, Y`，适配 Blender Z-up。
- 法线同样做 `X, -Z, Y` 转换。
- 保留 UV0 作为主贴图 UV，UV1 作为额外 UV/lightmap 通道。
- 使用 `model_high_2024/happy101/new/building/hp_bank01.gim` 做过导入/覆雪测试。