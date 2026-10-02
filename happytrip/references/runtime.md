# 本地执行器与原生工具交接

执行器提供可重复的素材登记、模式路由、计划、提示词、预算记录、导入和确定性合成。它没有远端生图 API；`prepare` 不生成图片，`run --adapter mock` 只验证程序流程。原生工具的调用规则见 [codex-host.md](codex-host.md)。

## 1. 运行前

需要 Python 3.10 或更高版本与 Pillow。使用当前环境已有运行时；先运行 `doctor` 查看依赖和能力。缺依赖时说明，不把安装包或网络接入混入普通生图流程。

以下命令中的 `HAPPYTRIP_SKILL`、`HAPPYTRIP_JOB` 和输入路径必须换成真实绝对路径。任务目录放在用户工作目录，不能放入原片目录并覆盖源文件。每项新任务使用独立目录；恢复任务继续用原目录。

```bash
HAPPYTRIP_SKILL="/实际安装目录/happytrip"
HAPPYTRIP_JOB="/实际工作目录/happytrip-job"
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" doctor
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" catalog
```

`doctor` 的本地依赖检查不能证明宿主生图工具可用，也不能代替真实图像验收。

## 2. 请求记录

从 [自然调光示例](../examples/native-relight.request.json)、[B01 本地合成示例](../examples/b01-local.request.json) 或 [B22 旅行地图海报示例](../examples/b22-travel-poster.request.json) 复制所需字段到实际 `request.json`。示例 `ref: null` 故意不指向任何图片；必须替换成真实素材，删除示例标记，并按照本次用户原话填写目标与授权。不能把示例里的“用户要求”冒充当前授权。

常用字段：

| 字段 | 内容 |
|---|---|
| `mode` | 一个注册模式 ID；模式未定时由路由提出候选，不擅自开始多套生成。 |
| `photos` | `{photo_id, ref, roles}` 数组；`ref` 是真实绝对路径，ID 唯一。 |
| `user_goal` | 当前用户目标；不添加额外修图项目。 |
| `targets`、`protected` | 每项绑定 `photo_id` 和 `description`；可含方向归一化后的 0–1 `box: [x,y,width,height]`。 |
| `facts` | `{value, source, confirmed}` 数组；确认来源为 `user`、`user_confirmed_metadata` 或 `verified_reference`。未确认内容不印入成图。 |
| `edit_contract` | 编辑范围、身份/几何保护、`strict_original` 等模式合同。 |
| `mode_options` | 所选模式专用参数，按该模式卡填写。 |
| `output` | `ratio`、`language`、可选 `title`/`subtitle`/`text`、`caption`。未给日期不加当天日期。 |
| `budget` | 默认 `max_image_calls: 4`、`max_repairs_per_stage: 1`。 |
| `capabilities` | 依据当前宿主和已授权本地路径确认的能力，见下表。 |

能力值为 `true`、`false` 或 `"unknown"`，未知不按支持处理。字段有 `vision`、`image_generation`、`image_editing`、`masked_editing`、`multiple_references`、`transparent_assets`、`local_composition`、`exact_text_rendering`、`geographic_rendering`，以及数字或 `null` 的 `max_reference_images`。

当前原生图像工具没有独立 `mask` 参数，不能将 `masked_editing` 写成 true。本机存在 Pillow 也不意味着可以绕过宿主图像编辑规则：普通图片任务没有用户明确本地处理选择时，将本任务的 `local_composition` 和依赖本地程序的 `exact_text_rendering` 保持 false。已明确要求本地原片排版或合成不重复确认；开发、升级与测试本地功能属于代码任务。`num_last_images_to_include` 路径最多 5 张；本地路径模式的上限未声明时保留 `null`，不要虚构更大的数值。

A11 在 `mode_options.object_words` 中逐项绑定 `photo_id`、`target`、`word`、`color`。B16 在 `mode_options.panels` 中保存 `action`、`photo_ids`、`dialogue`、`basis`。B22 保存 `stops: [{id,name,photo_ids}]`；只有实际确认顺序时才写 `ordered_stop_ids` 和 `order_confirmed: true`。B22 的 `travel_poster` 模板、日期/页脚事实、真实底图和路径字段见 [route-photo-map.md](route-photo-map.md)。

素材登记为源文件计算哈希，将方向、色彩归一化和去元数据写入独立 PNG 工作副本，并记录源文件与工作副本哈希。归一化用于一致的输入与验证基准，不能说工作副本字节等同原图；它不替代原生图像工具的生成编辑。

## 3. 准备、调用与导入

```bash
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" prepare --request "/实际路径/request.json" --job-dir "$HAPPYTRIP_JOB"
```

读取 `plan.json` 的状态、错误、阶段、依赖与调用预算。`needs_input` 或 `needs_capability` 时解决明确缺口，不继续生成。准备目录包含：

- `request.json`、`assets.json`、`plan.json`：请求、已解析素材和编辑计划。
- `prompts/<stage>.txt`、`image-requests/<stage>.json`：当前阶段的提示词和内部图像请求。
- `state.json`、`result.json`、`validation.json`：预算、阶段状态、产物与验收记录。

阶段 ID 以计划实际输出为准，不能猜 `stage-1`。每次原生图像调用（含修复）前先预留一次调用：

```bash
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" reserve --job-dir "$HAPPYTRIP_JOB" --stage "实际阶段ID"
```

`reserve` 原子检查阶段依赖、总预算和修复上限，并返回此阶段内部请求。预留成功后，按宿主工具声明将 `prompt` 和已读取的 `references` 映射到原生参数；内部 `output_dir`、`idempotency_key` 等字段不能直接传给 `imagegen`。

获得实际可读图片后导入：

```bash
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" import --job-dir "$HAPPYTRIP_JOB" --stage "实际阶段ID" --image "/实际工具输出/candidate.png"
```

导入必须对应一次预留；导入成功只表示候选已记录。检查候选是否属于当前阶段，不能用原图、另一次结果或占位图填充未完成阶段。

真实调用失败或执行状态未知时分别记录：

```bash
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" record-failure --job-dir "$HAPPYTRIP_JOB" --stage "实际阶段ID" --status failed
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" record-failure --job-dir "$HAPPYTRIP_JOB" --stage "实际阶段ID" --status unknown
```

这两行是二选一的状态示例，不能对同一次调用连续运行。`unknown` 不能自动重试；先核实原请求。失败调用也计入预算。用户取消时使用 `cancel --job-dir "$HAPPYTRIP_JOB"`。

## 4. 本地合成

用户已明确要求本地处理并看过素材后执行；有生成阶段的模式先完成对应生成。B22 排版现有照片与地图无需生图调用。开发或测试本地合成功能可直接验证其实际输出：

```bash
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" compose --recipe "/实际路径/recipe.json" --output "/实际工作目录/final.png"
```

合成使用真实生成资产、原片工作副本、明确版式、有效遮罩与准确文字。输出以无损 PNG 作为核对主文件；CLI 另写 `<输出文件>.json`，如 `final.png.json`，作为 `composition_manifest`。不能把生成工具 JSON 当作合成配方。

配方顶层为 `{base, layers, layout, contract}`。`base` 中的登记资产对象从本任务 `assets.json` 完整读取，保留 `photo_id`、`ref`、`working_path`、`input_sha256`、`working_sha256`；不能拿生成图片改名冒充原片。`layout.output_path` 由命令行 `--output` 设置，输出必须是新的 `.png` 文件。

| 用途 | 配方 |
|---|---|
| 严格局部合成 | `layout.kind: "masked_edit"`；`base` 为原片登记资产；`layers` 恰含一项 `{path: 同画布生成候选, mask_path: 有效灰度遮罩}`。 |
| A12 原片叠加 | `layout.kind: "overlay"`；`base` 为原片登记资产；`layers` 为透明图像层或准确文字层。保持原画布，不传不同的 `size`。 |
| B01 原片对照海报 | `layout.kind: "B01"`、`size: [1200,1600]`、`photo_box: [0.08,0.54,0.84,0.40]`；`base` 为一张登记原片，`layers` 至少包含生成冰箱贴，且不能与原片区域重叠。 |
| B22 旅行地图海报 | `layout.kind: "B22"`、`template: "travel_poster"`（默认）或 `classic`、画布 `size`、`stops`/确认顺序、实际 `font_path` 和 `font_size`；`base` 为登记资产数组，`layers: []`。地理底图通过 `layout.basemap` 指定；详见 [B22 配方与地图命令](route-photo-map.md)。 |
| A05、B16 等明确版式 | `layout.kind: "canvas"`、`base: null`、画布 `size`；通过图像、原片和文字层定义明信片、漫画的实际分区。 |
| A07 箱内平面贴纸 | `layout.kind: "collage"`、`base` 为已生成或用户提供的空箱体；`layout.interior_regions` 恰含上下两块内衬框，各贴纸完整落入其中一块。 |

图像层结构为 `{"kind":"image","path":"实际生成资产路径","box":[0.1,0.05,0.8,0.4],"source_photo_ids":["p01"]}`，按框等比完整放置；保留真实来源映射。原片层用 `kind: "photo"`、完整登记 `asset` 和 `box`。文字层为 `{"kind":"text","text":"实际准确文案","box":[0.1,0.02,0.8,0.05],"font_path":"实际字体文件路径","font_size":28}`，可选 `color`。字体必须真实存在并有需要的字形，中文不使用不可验证的自动回退；文字溢出时扩大文本框或明确调小字号。

框统一为归一化 `[x,y,width,height]`。局部合成的 `contract.allowed_regions` 与 `contract.protected_regions` 可填写框数组，或含 `box` 的对象数组。有效遮罩值 0 表示保护，非零表示允许变化；候选与原片需要同尺寸、同方向。叠加模式裁除被保护区域内的装饰后，检查有效遮罩外是否零像素差异；该检查不表示遮罩内生成内容真实或美观。

B01 默认允许等比缩放，证明照片来自原资产且没有生成式重绘；只有 `contract.original_pixels: true` 且足够大的照片槽才会不缩放插入。记录中的 `contain`、缩放比和放置框是实际变换依据，不宣传字节不变。

B22 的 `unordered_places` 是不连线的地点集；兼容本地配方别名 `collection`，同时 `order_confirmed: false`、`ordered_stop_ids: []`。确认顺序的概念行程使用 `itinerary_schematic`，真实地理版使用 `geographic`。所有选中照片必须对应站点。`map-basemap` 可登记有来源的本地 Web Mercator 栅格图，或从已有 GeoJSON 渲染底图；地理版还需每站已确认坐标。没有真实路径时仅画注明非道路路线的虚线，不提供自动导航或虚构里程。原片、底图与版式变换记录在合成 manifest 中。

A07 的每个贴纸层必须含 `source_photo_ids`；设置 `layout.selected_photo_ids` 后可核对完整覆盖。上下内衬框要根据实际箱体图确定，避免跨铰链与压到箱沿。本地矩形排版没有透视变形能力，不能声称自动拟合任意透视箱体。

执行器也可能给 A05、A07、B16 或准确标题安排 compose 阶段。用户需要明确选择本地制作，宿主再根据生成素材写出可验证的层和版式。不要把阶段名字当成已经完成的自动布局：脚本不会自行猜箱体区域、贴纸位置或漫画分格，不能省略这一步就宣称完成。

## 5. 实图复核与结束

打开最终候选看图，逐项记录模式验收。先做能执行的文件、尺寸、来源、遮罩等确定性检查，再做人脸、地标、文字与视觉质量复核。不要把全局脚本测试结果复制为本图的检查结论。

将实际最终文件的 SHA-256 写入 review。可以使用 `shasum -a 256 "/实际路径/final.png"` 读取哈希。review 格式：

```json
{
  "reviewer": "实际执行复核的人或代理",
  "image_sha256": "实际待交付文件的SHA-256",
  "visual_status": "pass",
  "checks": [
    {"name": "mode_visual", "status": "pass", "reason": "按模式卡实际看图记录效果和布局"},
    {"name": "identity_and_subjects", "status": "pass", "reason": "实际核对人物、目标和受保护主体"},
    {"name": "facts_and_text", "status": "pass", "reason": "实际核对文字、来源和已确认事实；无文字时说明"},
    {"name": "edit_scope", "status": "pass", "reason": "实际核对允许修改范围及所需来源或像素证据"}
  ],
  "composition_manifest": "/实际合成记录路径.json"
}
```

这只是格式示例，四个必需检查名为 `mode_visual`、`identity_and_subjects`、`facts_and_text`、`edit_scope`，每项写具体证据；不能原样复制示例理由冒充已检查。未看图时写 `visual_status: "not_run"`；存在问题用 `warn` 或 `fail`。`finalize` 只接受已完成的 `pass` 或 `warn`，不会把失败/未运行变成成功。无合成任务省略 `composition_manifest`；计划含任何 compose 阶段都需要真实合成来源记录，不能手写虚构记录让任务通过。

```bash
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" finalize --job-dir "$HAPPYTRIP_JOB" --image "/实际工作目录/final.png" --review "/实际路径/review.json"
```

收尾验证未完成生成阶段、图片哈希、模拟标记与必要合成记录，再将最终图去元数据导出为 `output/image-001.png`。review 的 `image_sha256` 对应复核输入，结果记录中的 `source_sha256` 关联该输入；交付 PNG 另有实际文件哈希。只有实际检查支持时才记录成功。最终向用户提供实际图片与必要的限制，不展示整套内部调试 JSON。用户对艺术效果的认可与本次技术/代理复核分别保留。

## 6. 模拟验证

```bash
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" run --request "/实际路径/request.json" --job-dir "/独立的模拟任务目录" --adapter mock
```

模拟适配器用于验证程序状态、依赖和预算；所有产物标为 simulated，不能作为真实生图、宿主工具兼容性或视觉验收证据。本项目未提供实际照片时，每种模式的实图验收均为 `not_run`。
