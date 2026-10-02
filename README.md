<p align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="HappyTrip：把旅行照片，变成旅途纪念。18 种旅行照片玩法，适用于 Codex。">
</p>

<p align="center">
  <strong>修好一张旅照，收藏一段旅程。</strong><br>
  从自然调光、去除游客，到明信片、旅行玻璃球和真实地图海报。
</p>

<p align="center">
  <a href="#案例展示">看案例</a> ·
  <a href="#开始使用">开始使用</a> ·
  <a href="#18-种玩法">选一种玩法</a> ·
  <a href="#文档与开发">开发文档</a>
</p>

HappyTrip 是一个 **Codex 旅行照片 Skill**。附上照片，用中文描述想要的效果，它会选择相应模式，整理素材、制作图片并核对结果。

## 案例展示

以下案例使用公开授权的旧金山地标照片。水彩明信片与玻璃球为原生图像工具制作的示例，地图海报由真实底图和原照片排版得到；均不代表个人旅行记录。[查看素材署名与制作记录](docs/examples/README.md)。

### 01 · 把风景画成明信片

**A05 水彩明信片 · 无字版** — 把金门大桥转绘到暖米白纸面，留出题字空间，配上三枚景物色块。

| 场景原片 | 水彩明信片 |
| :---: | :---: |
| <img src="docs/examples/golden-gate-source.jpg" width="420" alt="公开授权原片：从马林岬角望向金门大桥、海湾与前景山坡。"> | <img src="docs/examples/a05-watercolor-postcard.png" width="420" alt="A05 水彩明信片示例：右侧金门大桥水彩，左侧留白与蓝、绿、红三枚色块。"> |

```text
用 $happytrip 的 A05，把这张照片做成水彩明信片。
右侧画景点，左侧留白，保留三枚色块，不加任何文字。
```

### 02 · 把风景装进玻璃球

**B04 旅行玻璃球** — 从 39 号码头的木栈道和临水建筑，提炼一件微缩纪念物。

| 场景原片 | 创意重构 |
| :---: | :---: |
| <img src="docs/examples/pier39-source.jpg" width="360" alt="公开授权原片：旧金山 39 号码头的木栈道、临水建筑与海湾。"> | <img src="docs/examples/b04-travel-globe.png" width="360" alt="B04 生成示例：把 39 号码头的建筑与木栈道微缩到透明旅行玻璃球内。"> |

```text
用 $happytrip 的 B04，把照片中的码头做成旅行玻璃球。
保留建筑和木栈道的特点，不加雪，也不写文字。
```

### 03 · 把照片放回地图

**B22 旅行地图海报** — 三张地标照片，配上真实街道底图、拍立得和编号地点卡。

<p align="center">
  <a href="docs/examples/b22-map-preview.png">
    <img src="docs/examples/b22-map-preview.png" width="680" alt="B22 旧金山旅行地图海报：金门大桥、39 号码头和渡轮大楼照片卡，搭配 USGS 真实街道与海岸线地图。">
  </a>
</p>

示例使用 USGS 底图。红色虚线仅表示站点关联，**不是实际道路路线**。支持 2–15 张照片；所有选中照片都有对应地点卡，缺少的日期、天气和里程不自动补写。

```text
用 $happytrip 的 B22，以本地原片排版制作旅行地图海报。
这三张照片依次对应金门大桥、39 号码头、渡轮大楼。
使用有来源的真实地图；没有道路轨迹就标注为站点连线。
不要添加日期、天气或里程。
```

制作自己的地图时，请提供照片与地点的对应关系、地点坐标或可核实来源，以及需要展示的站点顺序。地图不会根据风格参考图猜测你的行程。[查看地图制作说明](happytrip/references/route-photo-map.md)。

## 开始使用

### 安装到 Codex

在 macOS / Linux 终端运行：

```bash
git clone https://github.com/coolbat/HappyTrip.git
cd HappyTrip
mkdir -p ~/.codex/skills
if [ ! -e ~/.codex/skills/happytrip ] && [ ! -L ~/.codex/skills/happytrip ]; then
  ln -s "$PWD/happytrip" ~/.codex/skills/happytrip
fi
```

保留整个 `happytrip/` 目录，它包含模式卡、参考资料和辅助脚本。若已安装同名 Skill，先确认现有路径；上述命令不覆盖旧安装。其他环境也可将整个目录复制到 Codex 的技能目录。

### 附上照片，说出想法

安装后新建 Codex 会话，上传照片并输入：

```text
用 $happytrip 看看这张旅行照片适合怎么处理，给我 2–3 个建议。
```

也可以直接指定目标：

```text
用 $happytrip，把这张照片做成水彩明信片，不写日期。
```

普通生成与编辑需要当前 Codex 会话提供图像工具。地图、原片对照和准确文字排版等本地流程还需要 Python 3.10+ 与 Pillow；[配置方法见下方](#文档与开发)。

## 18 种玩法

不必记住编号，直接描述目标也能选择玩法。编号适合复用喜欢的效果。

| 想做什么 | 可以尝试 |
| --- | --- |
| **修好照片** | A01 去除背景游客 · A02 自动调光 · A03 自然人像修整 |
| **收藏旅途** | A05 水彩明信片 · A07 碎片行李箱 · B01 原片＋冰箱贴 · B03 立体纸雕明信片 · B04 旅行玻璃球 · B22 照片地图 |
| **玩出新意** | A06 主体贴纸化 · A09 演唱会氛围 · A10 美食炸弹 · A11 文字构成物体 · A12 照片注释 |
| **讲述旅程** | A04 拍立得 3D 公仔 · A08 人物旅行海报 · B14 双重曝光 · B16 三格／四格漫画 |

完整输入数量、编辑范围与验收项见 [模式目录](happytrip/references/catalog.json)。

<details>
<summary>更多可以直接复制的提示词</summary>

**去除游客，保留同行人**

```text
用 $happytrip 的 A01，去掉右后方路人，
保留前景牵手的两个人和建筑。
```

**原片变成纪念物**

```text
用 $happytrip 的 B01，把这张照片里的建筑做成冰箱贴，
用本地合成把冰箱贴和完整原照片排成上下对照海报。
```

**一段真实的旅行小故事**

```text
用 $happytrip 的 B16，把这三张照片做成三格旅行漫画。
按上传顺序讲述，不添加我没有提供的经历，不写对白。
```

这些是玩法提示词，未展示成图的模式不代表已完成实图验证。

</details>

## 照片与事实，分别照顾

- **原文件只读**：制作使用工作副本；需要原片对照的模式明确记录原照片的去向。
- **按要求编辑**：调光不自动换天空，去路人先明确保留谁；创意重构与照片修整有不同边界。
- **不知道就省略**：未提供的日期、天气和里程不编造；未确认顺序的地点不画成行程路线。
- **看图后再交付**：文件生成、程序检查、视觉复核和你的审美认可分别记录。

## 文档与开发

| 文档 | 适合什么时候看 |
| --- | --- |
| [Skill 入口](happytrip/SKILL.md) | 了解使用规则与模式选择 |
| [Codex 接入](happytrip/references/codex-host.md) | 了解图像工具与本地合成的配合 |
| [地图海报指南](happytrip/references/route-photo-map.md) | 准备底图、地点、原照片和轨迹 |
| [本地执行器](happytrip/references/runtime.md) | 素材登记、计划、生成交接、合成与导出 |
| [案例来源与记录](docs/examples/README.md) | 查看公开素材许可与实际示例的制作方式 |
| [验证报告](checks/VALIDATION-REPORT.md) | 区分程序验证、开发预览与实图效果 |
| [原始需求与设计](HappyTrip_V1_Package/README.md) | 追溯设计来源与产品边界 |

<details>
<summary>配置本地辅助程序与运行测试</summary>

本地辅助程序不包含第三方生图 API 客户端，图像生成由宿主工具执行。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python happytrip/scripts/happytrip.py doctor
.venv/bin/python happytrip/scripts/happytrip.py catalog
PYTHONPATH=happytrip/scripts .venv/bin/python -m unittest discover -s tests -v
```

当前版本 **1.1.1**；已记录 **111 项程序测试通过**。这些检查不等于 18 种玩法全部通过真实图片验收。地图不提供在线导航，创意案例不代表真实商品或真实行程。

</details>

---

从一张照片开始。新建会话，附上照片，告诉 **`$happytrip`** 你想保留什么、改变什么。
