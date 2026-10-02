# B22 旅行地图海报

适用于用户提供的“城市标题＋拍立得照片＋地图路线＋地点卡”参考。默认 `travel_poster` 使用这些版式元素；`classic` 仅保留简洁示意路线照片图，真实地理版使用 `travel_poster`。照片卡来自实际原片，原片只读；等比缩放、旋转和阴影不等于生成式重绘，也不等于像素不变。示例海报中的人物、旅行日期、地点、天气与里程均不是本次任务事实。

## 选择地图与数据

参考图含实际街道、海岸线或用户明确要地图时，选 `geographic`，不要静默降级为点线示意图。信息不足时具体说明缺少的地点/坐标/底图；只有用户接受时才改交示意版。开发效果示例使用公开素材时明确标记，不能把它说成用户真实旅程。

地理版默认 `map_layout: "full_map"`，下部全宽地图上浮放照片卡，以引线连接地理位置。2–4 个照片地点绑定时使用该版式；更多绑定保留原片完整覆盖并回退 `split`，实际选择及原因写入合成记录。可显式传 `map_layout: "split"` 使用原有地图＋侧栏布局。验收必须检查成图中的真实底图可见且清楚。

| 已有资料 | 输出 |
|---|---|
| 照片、地点，未知顺序 | `unordered_places` 地点集，不连线。 |
| 照片、地点、确认顺序 | `itinerary_schematic`，显示“行程示意，非比例地图”。 |
| 再有核实坐标与有来源底图 | `geographic`，在真实地理位置放置站点；无轨迹时仅用虚线关联。 |
| 再有确认的轨迹或计划路线 | 绘制数据中的路径，标识实际轨迹或计划路线。 |

不从照片文件时间推断行程，不把两地直线当作走过的道路。没有日期、天气或里程就不显示对应信息栏；不用当前日期填补旅行日期。缺少真实底图时可先提供明确标记的示意版，不能将 AI 生成的街道纹理作为真实地图。

本地渲染不包含地址检索、导航规划、在线地图瓦片下载或天气查询。用户提供的已有栅格底图或 GeoJSON 可直接使用；先确认其来源、坐标范围与使用要求，保持署名可见。

## 请求字段

从 [B22 请求示例](../examples/b22-travel-poster.request.json) 开始，替换照片路径、地点、顺序和真实用户要求；示例数据本身不证明任何旅程或用户授权。

`mode_options` 是版式输入；本地配方将这些字段放进 `layout`：

| 字段 | 合同 |
|---|---|
| `template` | `travel_poster`（默认）或 `classic`。 |
| `map_mode` | `itinerary_schematic`、`unordered_places` 或 `geographic`。 |
| `title`、`subtitle` | 用户指定的显示文案；可省略。 |
| `stops` | 2–15 个 `{id,name,photo_ids}`，一站可绑定多张；每张选中原片必须出现。 |
| `ordered_stop_ids`、`order_confirmed` | 只有用户实际确认后才填写完整顺序与 `true`；无序集合使用 `[]` 与 `false`。 |
| `date_range`、`stops[].date` | `{value,source,confirmed:true}`；显示值为非空字符串。 |
| `footer` | 可选的 `[{label,value,source,confirmed:true}]`，例如用户确认的天气、海拔或总距离。 |
| `stops[].coordinates` | 地理版必需：`{lat,lon,source,confirmed:true}`；经纬度为数字。 |
| `basemap` | 地理版必需，来自下节登记命令的 JSON。 |
| `route_segments` | 地理版可选的真实路径数据，详见下文。 |

日期、坐标、距离与页脚事实的 `source` 使用 `user`、`user_confirmed_metadata` 或 `verified_reference`；标注 `verified_reference` 前须实际核实引用资料。可额外保存 `source_reference` 链接或文件说明便于复核。未确认的事实不能进入配方；程序会拒绝而非悄悄印出。底图的 `source` 则使用实际来源链接或文件说明，不是上述事实类别。

## 真实底图输入

支持普通、不跨日期变更线的 `[west,south,east,north]` 范围；纬度在约 ±85.05° 内，渲染采用 Web Mercator。栅格图必须已经是此投影且准确对应给定边界，图像宽高比与投影范围差异超过 2.5% 会报错；扫描纸图、透视照片或屏幕截图不能仅凭填入坐标就变成可用底图。

以下两种方式二选一。将路径、范围、来源和署名替换为本次真实数据；输出 JSON 必须为新文件：

```bash
HAPPYTRIP_SKILL="/实际安装目录/happytrip"
HAPPYTRIP_JOB="/实际工作目录/b22-job"
```

```bash
# 登记已存在的 Web Mercator 栅格图；不下载、不重绘地图。
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" map-basemap \
  --image "/实际地图路径/basemap.png" \
  --bounds -122.52 37.70 -122.35 37.84 \
  --source "实际数据来源链接或文件说明" \
  --attribution "实际地图署名文本" \
  --output "$HAPPYTRIP_JOB/basemap.json"
```

```bash
# 从已有 GeoJSON 渲染实际几何；输出 JSON 与关联 PNG。
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" map-basemap \
  --geojson "/实际地图路径/map.geojson" \
  --bounds -122.52 37.70 -122.35 37.84 --size 1400 1400 \
  --font-path "/实际字体路径/font.ttf" \
  --source "实际数据来源链接或文件说明" \
  --attribution "实际地图署名文本" \
  --output "$HAPPYTRIP_JOB/basemap.json"
```

GeoJSON 使用 WGS84 `FeatureCollection`，支持 `LineString`、`MultiLineString`、`Polygon`、`MultiPolygon`、`Point`；坐标按 GeoJSON 规定使用 `[lon,lat]`。Feature 的 `properties.kind` 可取 `water`、`park`、`road`、`minor_road`、`building`、`boundary`；Point 的 `properties.name` 为可选标签，有标签时须提供 `--font-path`。底图仅呈现数据中已有的几何与名称，不补造街道。渲染会按目标宽高比适度扩大边界，配方必须使用返回记录中的实际 `bounds`，不能改回原输入范围。

底图记录为 `{path,bounds,projection:"web_mercator",source,attribution,sha256}`。`map-basemap` 负责实际图片哈希；合成时再次核对，避免登记后底图被替换。将整个记录写入 `mode_options.basemap`，设置 `map_mode: "geographic"`，为每站补充已确认坐标，并在能力中设置实际可用的 `geographic_rendering: true`。地理版站点顺序仍需确认后才连线。

## 路径与距离

`route_segments` 中每项指定相邻站点 ID、路径、类型及来源：

```json
{
  "from": "s01",
  "to": "s02",
  "coordinates": [[-122.4783, 37.8199], [-122.4177, 37.8080]],
  "kind": "planned_route",
  "source": "user",
  "confirmed": true,
  "distance": {"value": "2.7 km", "source": "user", "confirmed": true}
}
```

这只是字段格式，不能直接当作可走道路或准确里程使用；实际任务必须替换为完整、已核实的路径和距离。`kind` 为 `recorded_track` 时表示实际记录，`planned_route` 表示计划。没有对应路段时使用注明“站点关联，非道路路线”的虚线；不把虚线换成看似经过道路的折线。距离是可选项，不能从示意线或参考海报推算。页脚总距离也需单独确认，程序不会把缺失路段自动补齐。

## 从请求到成图

使用用户已经选择的本地原片排版方式；同一授权不重复询问。开发本功能、运行测试及制作开发预览属于实现工作，不要求额外的制作方式确认。普通图像编辑仍遵循 [Codex 宿主规则](codex-host.md)。

1. 查看照片与地图输入，完成实际请求 `request.json`。`local_composition` 和 `exact_text_rendering` 反映当前执行能力；B22 本身无需生图，`image_generation` 可为 `false`。
2. `prepare` 登记原片并检查映射、事实与顺序；读取 `plan.json`，仅在计划就绪后继续。

```bash
HAPPYTRIP_SKILL="/实际安装目录/happytrip"
HAPPYTRIP_JOB="/实际工作目录/b22-job"
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" prepare \
  --request "/实际工作目录/request.json" --job-dir "$HAPPYTRIP_JOB"
```

3. 从登记资产构造配方，不手写或伪造原片哈希。以下脚本只组装 JSON；字体参数须为实际存在、含所需中文字形的文件。

```bash
python3 - "$HAPPYTRIP_JOB" "/实际字体路径/font.ttf" <<'PY'
import copy
import json
from pathlib import Path
import sys

job = Path(sys.argv[1])
request = json.loads((job / "request.json").read_text())
plan = json.loads((job / "plan.json").read_text())
assert plan["status"] == "ready", plan["status"]
layout = copy.deepcopy(request["mode_options"])
layout.update(kind="B22", size=[1500, 2000], font_path=sys.argv[2], font_size=30)
recipe = {
    "base": json.loads((job / "assets.json").read_text()),
    "layers": [],
    "layout": layout,
    "contract": plan["contract"],
}
(job / "recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2))
PY
python3 "$HAPPYTRIP_SKILL/scripts/happytrip.py" compose \
  --recipe "$HAPPYTRIP_JOB/recipe.json" --output "$HAPPYTRIP_JOB/poster.png"
```

底图文件通常应在 `prepare` 前准备，并将其 JSON 内容嵌入请求；不要把 JSON 路径字符串当成 `basemap` 对象。`layers: []` 表示照片与地图由专用模板处理，不往通用图层塞一个整图重绘结果。

4. 打开 `poster.png` 查看实际布局；`poster.png.json` 是来源、变换、路线与检查记录。所有选中照片均需可见；较多照片时模板扩展照片区，不能只保留最初三张。检查地图署名、图例、文字、路线与卡片是否互相遮挡，再按 [runtime.md](runtime.md#5-实图复核与结束) 写真实 review 并 `finalize`。

程序检查只证明输入与变换关系，不能替代目视检查或用户对艺术效果的认可。某张预览通过不表示十八种模式全部通过实图验收。
