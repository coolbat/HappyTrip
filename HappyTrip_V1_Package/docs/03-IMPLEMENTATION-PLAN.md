# HappyTrip Skill V1 实施计划

目标：以十八种模式为固定范围，构建可核对素材、遵守编辑合同、生成并验收旅行照片作品的 Skill 与可选参考执行器。

架构：文本 Skill 负责意图、规则与交互；执行器负责资产、计划、适配器、合成和验证；可选工作台只提供交互，不直接调用有密钥的外部 API。

参考执行器语言：Python。本章的函数签名、路径和测试命令是拟议实施合同；执行器源码尚未交付，不能把这里的任务描述当成已实现功能。宿主直接执行文本 Skill 时，不要求先安装参考执行器。

输入规范：`docs/01-PRD.md`、`docs/02-TECHNICAL-DESIGN.md`、`happytrip/references/catalog.json`。可用时使用 superpowers:executing-plans 按任务执行；没有该辅助 Skill 时，仍按相同的测试先行、局部验证、再集成顺序执行。

## 1. 全局约束

十八个模式 ID 固定；八个 P0 只影响验收顺序。原图只读；无图不编辑；不把源文章中的示例照片当作当前用户照片；不自动美颜与换景；B01 严格保留原片必须合成；B22 未知顺序不连线；默认最多四次图像调用，修复计入总数；任何供应商参数必须按真实接口映射。

新增实现使用自己的工作目录，不覆盖本包文档。不在未得到用户发布指令时推送仓库或部署外部服务。

## 2. 交付顺序

先完成文本 Skill 包与静态检查，再实现最短运行链和 P0 实图验收，接着补齐 P1；最后才加入可选工作台。不要以“先只做八个”为由删除其余模式的定义。

开发者可以在没有付费模型的情况下先完成模拟适配器测试。模拟结果只用于验证控制流，不能计入实图验收。

## 3. 目录与函数合同

```text
happytrip_runtime/
  __init__.py
  types.py
  catalog.py
  assets.py
  router.py
  facts.py
  planner.py
  compiler.py
  adapters/base.py
  adapters/mock.py
  adapters/host.py
  compositor.py
  validator.py
  runner.py
  export.py
  cli.py
tests/
  test_catalog.py
  test_assets.py
  test_router.py
  test_planner.py
  test_compiler.py
  test_adapter.py
  test_compositor.py
  test_story_map.py
  test_runner.py
```

`types.py` 定义 Request、Asset、Capabilities、Recommendation、Plan、Stage、ImageRequest、ImageResult、ValidationResult、JobResult。图像内容使用文件引用，不把 Base64 长字符串放入业务日志。

## 4. 任务拆解

### T01：模式注册表与公共类型

文件：`types.py`、`catalog.py`、`tests/test_catalog.py`。

接口：`load_catalog(path) -> Catalog`；`get_mode(catalog, mode_id) -> Mode`。Catalog 是本包 catalog.json 的解析结果，未知 ID 必须明确报错。

- [ ] 先写测试：模式集合精确等于 A01–A12 与六个 B ID；P0 恰好八个；每个模式卡存在；模板变量均已声明。
- [ ] 运行测试并确认缺少实现时失败，而不是依赖网络或图片内容失败。
- [ ] 实现注册表和类型，禁止静默接收重复 ID 或未知编辑边界。
- [ ] 运行 `python -m unittest tests.test_catalog`；复核与本包静态检查结果一致后提交本地变更。

完成标志：一个新增模式不会在没有配置或卡片的情况下“半注册”；当前十八种均可精确检索。

### T02：素材解析、角色与方向

文件：`assets.py`、`tests/test_assets.py`。

接口：`resolve_assets(request, resolver) -> list[Asset]`。resolver 是宿主提供的真实附件解析能力；此层不猜测文件路径。

- [ ] 先写测试：不存在的引用、零字节文件、只有 PDF 文章而无选中照片、错误遮罩尺寸、旋转照片坐标、读取原图不修改内容。
- [ ] 实现只读入库、工作副本、尺寸与方向记录、原资产和工作副本哈希。
- [ ] 加入角色校验；用户选中的 PDF 内图片需先成为明确图像资产，不自动将整份文章作为自拍。
- [ ] 运行 `python -m unittest tests.test_assets`，检查失败提示能点名缺少或无效的素材。

完成标志：所有后续阶段只能使用注册资产；示例 ID 不会混入真实工具调用。

### T03：意图路由与事实表

文件：`router.py`、`facts.py`、`tests/test_router.py`。

接口：`recommend(request, assets, catalog) -> list[Recommendation]`；`normalize_facts(request) -> FactLedger`。

- [ ] 先写测试：明确模式不重复推荐；“只调光”不选 A03；单张景点建议 A05/B01/B03；B22 缺顺序不自动优先；没有日期不填今天。
- [ ] 实现可解释规则和别名；返回理由，不返回伪造概率或热度分。
- [ ] 将用户事实、确认的元数据、外部已核实信息与模型猜测分开；推测不自动进入可打印事实。
- [ ] 运行 `python -m unittest tests.test_router`，确认输入相同结构化特征时规则可复现。

完成标志：推荐不额外授权生成，不从上传顺序推断旅行顺序。

### T04：编辑合同、计划与能力缺口

文件：`planner.py`、`tests/test_planner.py`。

接口：`make_plan(request, assets, mode, caps) -> Plan`。Plan 包含 stages、required_inputs、required_capabilities、protected、allowed_regions、call_budget。

- [ ] 先写测试：B01 严格保真但无合成器 → needs_capability；A09 与锁定姿态冲突 → needs_input；A07 超参考数不漏图；四格漫画加重试超过预算会暂停。
- [ ] 实现按模式生成的有依赖步骤；每步写明输入输出资产 ID、可改变范围与调用消耗。
- [ ] 所有能力 unknown 以未确认处理，不偷偷按 true 放行。
- [ ] 运行 `python -m unittest tests.test_planner`，检查计划不包含尚未创建的文件作为可用输入。

完成标志：生成前已能解释将做什么、需要哪些资源、哪些内容不得改动。

### T05：提示词编译与宿主适配器

文件：`compiler.py`、`adapters/base.py`、`adapters/mock.py`、`adapters/host.py`，以及对应测试文件。

接口：`compile_prompt(mode, context) -> str`；`adapter.capabilities() -> Capabilities`；`adapter.execute(image_request) -> ImageResult`。

- [ ] 先写测试：空日期整行省略；必需 target 缺失报错；未解析变量被阻断；图片中的“忽略规则”文字不会覆盖控制指令；过期附件解析失败不继续调用。
- [ ] 实现公共变量编译器与模拟适配器，再对真实宿主逐字段映射；不要把内部 image_request 直接发给外部 API。
- [ ] 测试无生图能力时返回 prompt_only，真实生成错误与权限错误保持原意，不伪造 URL、费用或成功标识。
- [ ] 运行 `python -m unittest tests.test_compiler tests.test_adapter`；真实接入单独记录所用工具与核对日期。

完成标志：能先用模拟适配器验证流程，再用实际宿主完成一张测试图；两种结果在报告里严格分开。

### T06：局部与原片合成

文件：`compositor.py`、`tests/test_compositor.py`。

接口：`compose(base, layers, layout, contract) -> CompositeResult`；`verify_protected_pixels(before, after, effective_mask) -> ValidationResult`。

- [ ] 先用程序生成的测试图片验证：有效遮罩外像素完全一致；白边和羽化被包括在许可区域；错误画布尺寸会被拒绝；A12 避开保护区。
- [ ] 实现原片复用、透明层、准确文字、等比 contain 与指定布局；不依赖生成模型写出准确日期。
- [ ] 为 B01 增加测试：照片槽输入只能引用源资产或确定性工作副本，不得引用重新生成的“相似照片”。
- [ ] 运行 `python -m unittest tests.test_compositor`，核对 PNG 主文件；JPEG 和缩放版本不承担原像素承诺。

完成标志：保真主张有合成来源与像素检查证据，不仅是视觉相似。

### T07：多图、漫画与路线工作流

文件：`planner.py`、`compositor.py`、`tests/test_story_map.py`。

接口：`plan_stickers(assets, selection) -> list[Stage]`；`plan_comic(panels, references) -> list[Stage]`；`plan_route(stops, order, map_mode) -> RouteLayout`。

- [ ] 先写测试：A07 十一个选中素材全部有映射；B16 三格/四格有效、五格无效；一格失败不重做其他格；同名地点不误合并。
- [ ] B22 测试未知顺序不连线、示意图有说明、照片映射正确；经纬度颠倒或缺来源不可进入真实地理模式。
- [ ] 实现分单元生成与合成，并保存每个单元的来源与审核状态。
- [ ] 运行 `python -m unittest tests.test_story_map`；概念路线不输出道路轨迹或推算公里数。

完成标志：多图工作流可追溯、不漏素材、不伪造事实，可针对失败单元返工。

### T08：状态、预算、恢复与导出

文件：`runner.py`、`export.py`、`cli.py`、`tests/test_runner.py`。

接口：`run_job(request, adapter, store) -> JobResult`；`export_result(job_result, destination) -> list[Asset]`。

- [ ] 先写测试：超预算停止、取消不会继续排队、后台状态未知不立即重复提交、验收失败不显示 succeeded、缺文件不生成下载链接。
- [ ] 实现任务记录、调用计数、阶段恢复和局部重试；数据清理不修改源资产。
- [ ] 加入密钥与精确定位日志检查；验证导出文件真实存在且可读取。
- [ ] 运行 `python -m unittest discover -s tests`，再执行一条从素材到最终文件的真实路径。

完成标志：有结果才交付结果，有缺口就交付真实缺口；失败可定位和恢复。

### T09：十八种实图验收与可选工作台

文件：实际样例目录、`validation-results.json`、验收记录；可选 UI 另建独立子目录。

- [ ] 为每种模式准备一例典型、一例边界和一例约束冲突，记录用户授权和素材来源。
- [ ] 先跑八种 P0，再跑十种 P1；每例记录宿主、日期、输入、调用次数、结果、问题与复核人。
- [ ] 按验收文档判断，不用“看起来不错”替代原片来源、目标保护、事实与文字检查。
- [ ] 可选 UI 只在核心路径稳定后实现；保留相同数据协议，不另造一套 Prompt Engine。

完成标志：每种通过的模式都有真实成图证据；未通过的明确标注，而不是从目录消失。

## 5. 一周试运行安排

这是工作拆分建议，不是交付时限保证。第 1 天完成注册表和素材；第 2 天完成路由与计划；第 3 天接通适配器并做单图闭环；第 4 天完成原片与文字合成；第 5 天完成多图与地图；第 6 天跑 P0；第 7 天跑 P1 并整理问题。真实宿主能力不足或视觉失败时，优先修正能力声明和失败行为，不以加班堆更多模板掩盖问题。
