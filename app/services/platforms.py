from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformProfile:
    id: str
    name: str
    support_level: str
    default_image_count: int
    default_aspect_ratio: str
    main_rule_pack_id: str
    detail_rule_pack_id: str
    locale: str


PLATFORMS: dict[str, PlatformProfile] = {
    "1688": PlatformProfile("1688", "1688", "tuned", 5, "1:1", "alibaba_core_5_slot", "alibaba_detail_v1", "zh-CN"),
    "taobao": PlatformProfile("taobao", "淘宝", "tuned", 5, "1:1", "alibaba_core_5_slot", "alibaba_detail_v1", "zh-CN"),
    "amazon": PlatformProfile("amazon", "Amazon", "tuned", 7, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "en-US"),
    "douyin": PlatformProfile("douyin", "抖音", "tuned", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "zh-CN"),
    "temu": PlatformProfile("temu", "Temu", "tuned", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "en-US"),
    "alibaba_intl": PlatformProfile("alibaba_intl", "Alibaba Intl", "generic", 5, "1:1", "alibaba_core_5_slot", "ecommerce_detail_v2", "en-US"),
    "jd": PlatformProfile("jd", "京东", "generic", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "zh-CN"),
    "pdd": PlatformProfile("pdd", "拼多多", "generic", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "zh-CN"),
    "xiaohongshu": PlatformProfile("xiaohongshu", "小红书", "generic", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "zh-CN"),
    "tiktok": PlatformProfile("tiktok", "TikTok", "generic", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "en-US"),
    "official_site": PlatformProfile("official_site", "独立站", "generic", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "en-US"),
    "custom": PlatformProfile("custom", "自定义", "custom", 5, "1:1", "default_main_gallery_v2", "ecommerce_detail_v2", "zh-CN"),
}


def get_platform_or_none(platform_id: str | None) -> PlatformProfile | None:
    if not platform_id:
        return None
    return PLATFORMS.get(platform_id)


def list_platforms() -> list[dict]:
    return [profile.__dict__ for profile in PLATFORMS.values()]
