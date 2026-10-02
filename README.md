# HappyTrip

旅行照片创意 Skill，包含 A01–A12 与 B01、B03、B04、B14、B16、B22 共 18 种静态玩法。

开发结果在 [happytrip/SKILL.md](happytrip/SKILL.md)。原始需求、设计、模式来源与验收要求保留在 [HappyTrip_V1_Package](HappyTrip_V1_Package/README.md)，没有覆盖原始交接文档。

## 使用

完整 `happytrip/` 目录为可安装技能，不能只复制 `SKILL.md`。本机 Codex 通过 `~/.codex/skills/happytrip` 链接到此目录。新建会话后可输入：

> 用 $happytrip 的 A05，把这张旅行照片做成水彩明信片，不写日期。

需要同时提供实际照片。原生生图和编辑使用宿主当前工具；本地执行器不包含第三方 API 客户端，也不假定某个模型名称或报价。严格原片合成、准确文字排版等操作遵守当前宿主的本地处理授权规则，详见 [Codex 接入](happytrip/references/codex-host.md)。

## 已实现

- 18 种模式与中文意图路由、最少追问、事实来源与编辑范围检查。
- 素材只读登记、方向/色彩归一化工作副本、哈希与多图来源映射。
- 计划、分单元提示词、默认四次调用预算、超时不自动重试、失败单元返工。
- 原生工具交接与候选导入；原片海报、遮罩、注释、照片地图及通用图层的本地合成。
- 明确复核后的无元数据 PNG 导出、真实状态与来源记录。

### B22 旅行地图海报（1.1.1）

支持城市与日期标题、倾斜拍立得、编号站点、原片地点卡和已确认信息栏；2–15 张照片完整保留来源映射。默认使用 `travel_poster`，原简洁版可选择 `classic`。

地理版可导入带范围与署名的 Web Mercator 栅格，或从已有 WGS84 GeoJSON 绘制底图。提供有来源的轨迹/计划路线时绘制对应路径；没有路径时只画明确标注的虚线站点关联。日期、天气与里程缺失时省略，不自动猜测。地图检索、在线导航与天气服务不在此次实现中。

用法与完整本地制作流程见 [B22 旅行地图海报](happytrip/references/route-photo-map.md)。[真实地图海报预览](docs/examples/b22-map-preview.png) 使用 USGS 旧金山底图与公开授权地标照片，仅为效果示例，不代表用户旅程；[素材署名](docs/examples/CREDITS.md)。地理版默认下部全宽地图和浮动照片卡，2–4 个照片地点绑定使用该布局，更多绑定保留全部照片并回退地图＋侧栏。用户要求真实地图时，不能交付无底图的行程示意图。

命令用法与 JSON 数据结构见 [本地执行器说明](happytrip/references/runtime.md)。直接运行：

```bash
python3 happytrip/scripts/happytrip.py doctor
python3 happytrip/scripts/happytrip.py catalog
```

本地程序需要 Python 3.10+、Pillow 12.2.0。开发验证另用 PyYAML 6.0.3，可安装在独立虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHONPATH=happytrip/scripts .venv/bin/python -m unittest discover -s tests -v
```

## 验收状态

详见 [验证报告](checks/VALIDATION-REPORT.md)、[B22 升级验证](checks/B22-UPGRADE.md) 与 [真实地图交付修正](checks/B22-MAP-CORRECTION.md)。自动测试、开发预览、宿主生图和用户艺术效果认可分别记录。B22 已制作原照片示意版及真实地图数据的开发预览；这不代表十八种模式的完整视觉测试矩阵通过。

未增加网站、账号、支付、自动社交发布或地图导航服务。
