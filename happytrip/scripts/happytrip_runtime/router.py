"""Deterministic intent routing; recommendations do not authorize generation."""
import re
from .types import HappyTripError

ALIASES = {
    "A01": ("去路人", "清掉背景游客", "消除背景游客", "移除路人", "清掉其他人"),
    "A02": ("只调光", "调光", "曝光太过", "自然后期", "曝光问题"),
    "A03": ("稍微美颜", "自然修肤", "专业美颜", "自然美颜"),
    "A04": ("拍立得公仔", "q版出框", "拍立得 3d 公仔", "公仔"),
    "A05": ("水彩明信片", "景点明信片"),
    "A06": ("原位贴纸", "变贴纸", "主体转贴纸"),
    "A07": ("行李箱", "旅途碎片", "旅游碎片"),
    "A08": ("人物旅游海报", "城市旅行海报", "宠物公路海报", "人物旅行海报"),
    "A09": ("演唱会大片", "音乐节氛围重构", "演唱会氛围"),
    "A10": ("饮品飞溅", "美食炸弹"),
    "A11": ("词组成", "文字涂鸦", "物体转文字", "文字构物"),
    "A12": ("白色手写注释", "箭头涂鸦", "画面注释", "照片涂鸦"),
    "B01": ("冰箱贴", "原片对照海报"),
    "B03": ("纸面立起", "立体纸雕", "纸雕明信片"),
    "B04": ("旅行玻璃球", "雪景球", "玻璃球"),
    "B14": ("人像轮廓", "双重曝光"),
    "B16": ("三格漫画", "四格旅行故事", "四格漫画", "旅行漫画"),
    "B22": ("照片串路线", "行程地图", "路线照片地图", "路线地图"),
}


def _explicit(value, catalog):
    if not isinstance(value, str):
        raise HappyTripError("MODE_UNKNOWN", "Mode must be a V1 ID or name")
    value = value.strip()
    for mode in catalog["modes"]:
        if value.casefold() in {mode["id"].casefold(), mode["slug"].casefold(), mode["name_zh"].casefold()}:
            return mode["id"]
    for mode_id, aliases in ALIASES.items():
        if value.casefold() in aliases:
            return mode_id
    raise HappyTripError("MODE_UNKNOWN", f"Unknown mode: {value}; choose an exact V1 ID or name")


def recommend(request, assets, catalog):
    def result(ids, reason, selection="suggestion"):
        # Routing uses registry metadata only; the caller reads the chosen card.
        return [{"mode": mode_id, "reason": reason, "selection": selection} for mode_id in ids]
    if request.get("mode") and request["mode"] != "auto":
        return result([_explicit(request["mode"], catalog)], "用户已明确选择该模式；素材缺口由计划检查。", "explicit")
    text = str(request.get("user_goal", request.get("intent", ""))).casefold()
    found = re.findall(r"(?<![a-z0-9])[ab]\d{2}(?![a-z0-9])", text)
    if found:
        ids = list(dict.fromkeys(_explicit(value, catalog) for value in found))
        return result(ids, "文字中明确指定的模式优先。", "explicit")
    if "只调光" in text or "仅调光" in text:
        return result(["A02"], "用户仅要求调整光线，不额外添加美颜。", "intent")
    if "独立贴纸包" in text:
        raise HappyTripError("MODE_UNSUPPORTED", "独立贴纸包不在 V1 范围；可选择 A06 原位贴纸或 A07 行李箱拼贴。")
    matched = [(mode_id, max((len(a) for a in aliases if a in text), default=0)) for mode_id, aliases in ALIASES.items()]
    matched = [(m, length) for m, length in matched if length]
    if matched:
        # Specific phrases beat generic words such as 公仔 or 行李箱.
        matched.sort(key=lambda x: -x[1])
        return result([matched[0][0]], "文字意图与模式匹配；尚未声明已查看或处理照片。", "intent")
    if "贴纸" in text:
        return result(["A06", "A07"], "贴纸载体尚不明确：可选原位主体贴纸或行李箱拼贴。")
    if not assets:
        return []
    options = request.get("mode_options", {})
    if not isinstance(options, dict):
        raise HappyTripError("INPUT_INVALID", "mode_options must be an object")
    roles = {role for asset in assets for role in asset.get("roles", [])}
    features = request.get("photo_features", {})
    if isinstance(features, dict):
        roles.update(key for key, value in features.items() if value is True)
    elif isinstance(features, list):
        roles.update(value for value in features if isinstance(value, str))
    if len(assets) > 1:
        has_order = options.get("order_confirmed") is True and bool(options.get("ordered_stop_ids"))
        ids = ["B22", "A07"] if has_order else ["A07"]
        if options.get("panels") or options.get("story") or request.get("story"):
            ids.append("B16")
        return result(ids, "多张素材可制作旅行合集；路线连接仍需确认站点与顺序。")
    if roles & {"food", "drink"}:
        return result(["A10", "A12"], "已标注的食物或饮品素材适合效果创作与注释。")
    if roles & {"person", "portrait", "identity"}:
        return result(["A04", "A08", "B14"], "已标注的人物或宠物参考适合角色旅行创作。")
    if "pet" in roles:
        return result(["A08", "A12"], "宠物素材可选择 A08 宠物公路海报变体或照片注释。")
    if roles & {"scene", "landmark", "landscape", "background"}:
        return result(["A05", "B01", "B03"], "已标注的景点素材适合制作旅行纪念品。")
    return result(["A05", "B01", "A12"], "根据单张素材数量提供候选；照片内容尚未确认。")
