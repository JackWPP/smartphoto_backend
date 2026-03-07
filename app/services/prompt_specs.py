MAIN_GALLERY_ROLES = ["hero", "white_bg", "selling_point", "scene", "detail"]

ROLE_SPECS: dict[str, dict[str, str]] = {
    "hero": {
        "role_label": "主图",
        "goal": "突出商品主体与第一卖点，适合作为电商主图首屏",
        "background_mode": "clean_studio",
        "text_policy": "no_text",
        "composition_hint": "单商品主体清晰，居中或偏中心构图，画面简洁有高级感",
    },
    "selling_point": {
        "role_label": "卖点图",
        "goal": "聚焦一个核心卖点，用画面直接表达功能或优势",
        "background_mode": "simple_feature_bg",
        "text_policy": "no_text",
        "composition_hint": "围绕单一卖点做近景或功能化构图，不做拼贴海报",
    },
    "scene": {
        "role_label": "场景图",
        "goal": "把商品放进真实使用情境，体现人群、空间或使用方式",
        "background_mode": "real_scene",
        "text_policy": "no_text",
        "composition_hint": "真实生活化场景，中景构图，商品与环境关系清晰",
    },
    "detail": {
        "role_label": "细节图",
        "goal": "突出材质、结构、做工或局部细节",
        "background_mode": "soft_focus_bg",
        "text_policy": "no_text",
        "composition_hint": "局部特写或微距构图，强调工艺、纹理与质感",
    },
    "white_bg": {
        "role_label": "白底图",
        "goal": "输出标准电商白底图，方便平台审核与商品展示",
        "background_mode": "pure_white",
        "text_policy": "no_text",
        "composition_hint": "单产品完整展示，纯白无缝背景，轮廓干净无遮挡",
    },
    "detail_page_panel": {
        "role_label": "详情页模块",
        "goal": "用于后续详情页长图模块的版式型图像",
        "background_mode": "layout_panel",
        "text_policy": "layout_text_optional",
        "composition_hint": "预留详情页图文版式结构，不用于本期主图组",
    },
}


def get_prompt_role_spec(role: str) -> dict[str, str]:
    fallback = {
        "role_label": role,
        "goal": "生成适合电商展示的商品图片",
        "background_mode": "clean_studio",
        "text_policy": "no_text",
        "composition_hint": "商品主体清晰，构图简洁",
    }
    return {**fallback, **ROLE_SPECS.get(role, {})}
