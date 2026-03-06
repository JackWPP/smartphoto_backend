from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformProfile:
    id: str
    name: str
    support_level: str
    default_image_count: int
    default_aspect_ratio: str


PLATFORMS: dict[str, PlatformProfile] = {
    "1688": PlatformProfile("1688", "1688", "tuned", 5, "1:1"),
    "taobao": PlatformProfile("taobao", "淘宝", "tuned", 5, "1:1"),
    "amazon": PlatformProfile("amazon", "Amazon", "tuned", 7, "1:1"),
    "douyin": PlatformProfile("douyin", "抖音", "tuned", 5, "1:1"),
    "temu": PlatformProfile("temu", "Temu", "tuned", 5, "1:1"),
    "alibaba_intl": PlatformProfile("alibaba_intl", "Alibaba Intl", "generic", 5, "1:1"),
    "jd": PlatformProfile("jd", "京东", "generic", 5, "1:1"),
    "pdd": PlatformProfile("pdd", "拼多多", "generic", 5, "1:1"),
    "xiaohongshu": PlatformProfile("xiaohongshu", "小红书", "generic", 5, "1:1"),
    "tiktok": PlatformProfile("tiktok", "TikTok", "generic", 5, "1:1"),
    "official_site": PlatformProfile("official_site", "独立站", "generic", 5, "1:1"),
    "custom": PlatformProfile("custom", "自定义", "custom", 5, "1:1"),
}


def get_platform_or_none(platform_id: str | None) -> PlatformProfile | None:
    if not platform_id:
        return None
    return PLATFORMS.get(platform_id)


def list_platforms() -> list[dict]:
    return [profile.__dict__ for profile in PLATFORMS.values()]
