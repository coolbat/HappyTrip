# HappyTrip Skill V1 文档与 Skill 包

日期：2026-09-29。范围：已确认的十八种静态玩法，原文 A01–A12 加 B01、B03、B04、B14、B16、B22。

## 从哪里开始

阅读 [产品需求文档](docs/01-PRD.md) 和 [开发方案](docs/02-TECHNICAL-DESIGN.md)；开发 Agent 继续阅读 [实施计划](docs/03-IMPLEMENTATION-PLAN.md) 与 [验收清单](docs/04-ACCEPTANCE.md)。[来源说明](docs/05-SOURCE-NOTES.md) 区分原文、已确认扩展与工程设计。

文本型 Skill 从 [happytrip/SKILL.md](happytrip/SKILL.md) 进入；十八张独立模式卡位于 happytrip/modes，公共配置位于 [模式注册表](happytrip/references/catalog.json)。JSON 请求样例位于 examples，均显式标记为示例，不是实际用户照片引用。

## 目录

```text
README.md
docs/
  01-PRD.md
  02-TECHNICAL-DESIGN.md
  03-IMPLEMENTATION-PLAN.md
  04-ACCEPTANCE.md
  05-SOURCE-NOTES.md
happytrip/
  SKILL.md
  references/
    catalog.json
    routing.md
    execution-and-quality.md
  modes/
    18 个模式卡，每张都含独立提示词与验收要求
examples/
  6 个内部请求示例
checks/
  validate_package.py
  VALIDATION-REPORT.md
```

## 如何使用

在支持加载文本型 Skill 的宿主中，按该宿主实际要求放置完整 happytrip 目录，保留子目录。不要只复制 SKILL.md 而遗漏模式卡。也可以直接把相关文档与选中卡片作为开发 Agent 的上下文。

本包没有假定具体宿主的安装路径、没有替你安装到本机、没有连接 API 或创建在线站点。仅复制文件不会自动获得看图、生图或合成能力。使用前先核对宿主能做什么。

例如：“用 happytrip 的 A05，将我上传的这张照片做成景点明信片，日期先不要写。”这个例子必须配合实际上传的照片，不能把示例中的逻辑 ID 直接交给图像工具。

## 校验

在包目录中运行：

```bash
python checks/validate_package.py
```

静态校验只验证文档和配置，不验证生图效果。真实视觉测试和宿主集成状态见 checks/VALIDATION-REPORT.md；本次交付不包含实图验收证据。十八张模板完整不等于十八种视觉效果均已稳定。

## 文档与模式范围

原文的三组章节和关键视觉约束保留；四类产品入口是已确认设计。P0 八种是优先打磨顺序，P1 十种仍在 V1 包内。未选择的盒装手办、独立贴纸包、实时相机、动态 GIF 和视频不在本包功能范围。

原片与个人信息默认不公开，本包不重新分发用户上传的原文 PDF、照片、字体文件或供应商密钥。
