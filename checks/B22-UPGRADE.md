# B22 旅行地图海报升级验证

日期：2026-10-01。版本：1.1.0。仅升级 B22 与相关本地执行路径；原始 `HappyTrip_V1_Package/` 保持不变。

## 实现

- `travel_poster` 为默认模板：城市/日期标题、按原片比例适配的倾斜拍立得、站点编号、照片地点卡、确认信息栏。2–15 张原照片具有完整来源映射，缩放/旋转记录可查；`classic` 保留旧示意版。
- 本地 `map-basemap` 登记有来源的 Web Mercator 栅格，或从 WGS84 GeoJSON 渲染底图。支持多边形孔洞、道路与已有 Point 标签；按投影宽高比保留地图几何，站点投影与底图共用视口。
- 已确认的计划路线和记录轨迹分别标识；无路径数据的路段显示虚线关联。坐标、日期、距离、页脚的事实来源有校验，地图署名必须可见。
- 原片与底图哈希、地图范围、路线端点与站点对应关系、完整照片覆盖均有检查。最终导出还比较海报事实与计划的数据指纹，防止只核对顺序却替换地图或文案。
- CLI 无联网下载、地址搜索、天气查询或道路导航服务。地理数据由使用者或宿主提供；不把生成地图纹理当作真实街道。

## 已验证

- 全套 unittest 通过，最新次数见 [测试日志](b22-unittest.log)。覆盖旧 18 模式回归、新海报、地理投影、事实来源、原片映射、2/15 张边界和合成至导出流程。
- Skill 规范与原始需求包校验通过；新版归档解包及 CLI 检查见 [安装包记录](package-install.json)。
- 独立代理按文档执行示意版与地理版：`prepare → recipe → compose`，图片生成能力设为 false 仍可完成，生图调用数为零；包括 GeoJSON 绘图和栅格登记往返。[验证记录](b22-docs-summary.json)、[复现脚本](b22-docs-workflow.py)。
- 风景原片预览（本地 `outputs/b22-upgrade/travel-poster-preview-v2.png`，用户照片不随仓库上传）：使用本次对话中的湖畔、灯塔、荷塘鸟照片，只作原片排版。预览显著说明站点顺序为演示，不代表实际旅程。已目视检查照片完整、标题/标签可读、无灰色占位边。
- 真实地理渲染开发预览（本地 `outputs/b22-upgrade/geographic-preview-v3.png`）采用旧金山小范围街道数据和明确标注的测试照片卡；不是用户旅程。保留来源署名，不显示未提供的日期、天气或里程。坐标与卡片排版检查记录在对应 PNG 的合成 manifest。本地实际复核记录 `outputs/b22-upgrade/geographic.review.json`已通过 `finalize`，导出生成无元数据 PNG，生图调用数为 0。

开发时曾发现地理卡片经度被拆行；已按实际看图结果修复，数值分行保持完整。程序测试与人工看图分别进行，不以日志替代视觉检查。

## 地图开发素材来源

- 原始数据：[OpenStreetMap API 范围导出](https://api.openstreetmap.org/api/0.6/map?bbox=-122.405,37.803,-122.399,37.809)，本地保存在 `outputs/b22-upgrade/osm-response.txt`。
- 路径几何验证使用 [OSM way 88142685](https://www.openstreetmap.org/way/88142685) 上的测试点，不声称用户走过该路线。
- 数据及衍生 GeoJSON 使用 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)，署名遵循 [OpenStreetMap Copyright](https://www.openstreetmap.org/copyright)。测试地图仅绘制抽取的数据，未补造缺失地物。没有抓取或打包 OSM 标准瓦片。
- 投影依据：[OSM Web Mercator / Slippy map 坐标说明](https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames)。

## 验收范围

本轮证明 B22 的程序流程、确定性原片排版和给定地理数据的渲染可运行；已检查具体开发预览。照片版使用真实原片，地理版使用真实数据加合成测试卡，二者不能合称真实用户旅行成品。用户艺术效果认可、自动地图检索及十八种模式完整视觉矩阵不在本次已通过结论中。
