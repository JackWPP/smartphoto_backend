from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import session as db_session
from app.models.category_catalog import CategoryCatalogModel
from app.models.category_parameter_rules import CategoryParameterRuleModel


def _seed(
    *,
    name: str,
    slug: str,
    sort_order: int,
    aliases: list[str],
    sample_keywords: list[str],
    notes: str = "",
    is_featured: bool = False,
    confusion_pairs: list[str] | None = None,
    expected_components: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "slug": slug,
        "sort_order": sort_order,
        "aliases": aliases,
        "sample_keywords": sample_keywords,
        "notes": notes,
        "is_featured": is_featured,
        "confusion_pairs": confusion_pairs or [],
        "expected_components": expected_components or [],
    }


SYSTEM_CATEGORY_CATALOGS: list[dict[str, Any]] = [
    _seed(name="空气净化器", slug="air_purifier", sort_order=10, aliases=["净化器", "空气清新机", "空气消毒机"], sample_keywords=["HEPA", "CADR", "除甲醛", "滤网", "圆柱空气净化器"], notes="空气治理类核心品类", is_featured=True, confusion_pairs=["加湿器", "除湿机"], expected_components=["HEPA滤网", "出风口", "进风口", "控制面板", "滤芯舱"]),
    _seed(name="加湿器", slug="humidifier", sort_order=20, aliases=["空气加湿器", "喷雾加湿器"], sample_keywords=["雾化", "水箱", "恒湿", "桌面加湿"], is_featured=True, confusion_pairs=["空气净化器", "除湿机", "宠物饮水机"], expected_components=["水箱", "雾化口", "出雾孔"]),
    _seed(name="除湿机", slug="dehumidifier", sort_order=30, aliases=["抽湿机"], sample_keywords=["抽湿", "除湿", "水箱", "地下室除湿"], is_featured=True),
    _seed(name="净水器", slug="water_purifier", sort_order=40, aliases=["净水机", "滤水器"], sample_keywords=["RO", "滤芯", "净饮", "家用净水"], is_featured=True, confusion_pairs=["饮水机", "滤水壶"]),
    _seed(name="饮水机", slug="water_dispenser", sort_order=50, aliases=["即热饮水机", "饮水设备"], sample_keywords=["即热", "烧水", "冷热双温", "台式饮水"], is_featured=True, confusion_pairs=["净水器", "养生壶", "电水壶"]),
    _seed(name="小风扇", slug="mini_fan", sort_order=60, aliases=["便携风扇", "桌面风扇"], sample_keywords=["usb 风扇", "手持风扇", "静音风扇"], is_featured=True),
    _seed(name="取暖器", slug="heater", sort_order=70, aliases=["暖风机", "电暖器"], sample_keywords=["暖风", "电热", "冬季取暖"], is_featured=True),
    _seed(name="扫地机", slug="robot_vacuum", sort_order=80, aliases=["扫地机器人", "扫拖机器人"], sample_keywords=["扫拖", "激光导航", "自动回充"], is_featured=True, confusion_pairs=["洗地机", "吸尘器"], expected_components=["激光雷达", "尘盒", "边刷", "主刷"]),
    _seed(name="洗地机", slug="floor_washer", sort_order=90, aliases=["洗拖机"], sample_keywords=["自清洁", "滚刷", "地面清洁"], is_featured=True, confusion_pairs=["扫地机", "吸尘器"], expected_components=["滚刷", "污水箱", "清水箱", "自清洁底座"]),
    _seed(name="吸尘器", slug="vacuum_cleaner", sort_order=100, aliases=["无线吸尘器"], sample_keywords=["除螨", "大吸力", "手持吸尘"], is_featured=True),
    _seed(name="咖啡机", slug="coffee_machine", sort_order=110, aliases=["咖啡壶", "意式咖啡机"], sample_keywords=["萃取", "胶囊", "奶泡", "咖啡"], is_featured=True),
    _seed(name="空气炸锅", slug="air_fryer", sort_order=120, aliases=["炸锅"], sample_keywords=["无油", "烘烤", "炸篮"], is_featured=True),
    _seed(name="电饭煲", slug="rice_cooker", sort_order=130, aliases=["电饭锅"], sample_keywords=["煮饭", "IH", "预约"], is_featured=True),
    _seed(name="破壁机", slug="blender_breaker", sort_order=140, aliases=["破壁料理机"], sample_keywords=["豆浆", "冷热双打", "高速搅打"], is_featured=True, confusion_pairs=["料理机", "榨汁机", "养生壶", "豆浆机"], expected_components=["杯体", "刀头", "底座电机", "杯盖"]),
    _seed(name="料理机", slug="food_processor", sort_order=150, aliases=["多功能料理机"], sample_keywords=["切碎", "搅拌", "辅食"], is_featured=True, confusion_pairs=["破壁机", "榨汁机", "绞肉机"]),
    _seed(name="榨汁机", slug="juicer", sort_order=160, aliases=["原汁机"], sample_keywords=["果汁", "慢榨", "便携榨汁"], is_featured=True),
    _seed(name="电磁炉", slug="induction_cooker", sort_order=170, aliases=["电陶炉"], sample_keywords=["火力", "加热", "烹饪"], is_featured=True),
    _seed(name="微波炉", slug="microwave", sort_order=180, aliases=["微波加热器"], sample_keywords=["解冻", "加热", "厨房电器"], is_featured=True),
    _seed(name="烤箱", slug="oven", sort_order=190, aliases=["电烤箱"], sample_keywords=["烘焙", "烤盘", "发酵"], is_featured=True),
    _seed(name="冰箱", slug="refrigerator", sort_order=200, aliases=["冷藏柜"], sample_keywords=["冷藏", "冷冻", "双开门"], is_featured=True),
    _seed(name="洗衣机", slug="washing_machine", sort_order=210, aliases=["洗烘一体机"], sample_keywords=["滚筒", "波轮", "除菌洗"], is_featured=True),
    _seed(name="电视", slug="television", sort_order=220, aliases=["智能电视"], sample_keywords=["4K", "大屏", "家庭影院"], is_featured=True),
    _seed(name="显示器", slug="monitor", sort_order=230, aliases=["电脑显示器"], sample_keywords=["高刷", "IPS", "办公显示器"], is_featured=True),
    _seed(name="投影仪", slug="projector", sort_order=240, aliases=["投影机"], sample_keywords=["家用投影", "激光投影", "便携投影"], is_featured=True),
    _seed(name="音响", slug="speaker", sort_order=250, aliases=["蓝牙音箱"], sample_keywords=["立体声", "低音", "户外音箱"], is_featured=True),
    _seed(name="耳机", slug="headphones", sort_order=260, aliases=["蓝牙耳机"], sample_keywords=["降噪", "入耳式", "头戴式"], is_featured=True),
    _seed(name="摄像头", slug="camera", sort_order=270, aliases=["监控摄像头", "网络摄像头"], sample_keywords=["夜视", "云台", "安防"], is_featured=True),
    _seed(name="路由器", slug="router", sort_order=280, aliases=["无线路由器"], sample_keywords=["Wi-Fi", "mesh", "网络覆盖"], is_featured=True),
    _seed(name="床垫", slug="mattress", sort_order=300, aliases=["记忆棉床垫"], sample_keywords=["软硬适中", "弹簧", "睡眠"], is_featured=True),
    _seed(name="沙发", slug="sofa", sort_order=310, aliases=["布艺沙发", "功能沙发"], sample_keywords=["客厅家具", "靠背", "坐感"], is_featured=True),
    _seed(name="书桌", slug="desk", sort_order=320, aliases=["办公桌"], sample_keywords=["学习桌", "木质桌面", "家居办公"], is_featured=True),
    _seed(name="椅子", slug="chair", sort_order=330, aliases=["办公椅", "餐椅"], sample_keywords=["靠背椅", "人体工学", "座椅"], is_featured=True),
    _seed(name="灯具", slug="lamp", sort_order=340, aliases=["台灯", "落地灯"], sample_keywords=["照明", "护眼灯", "氛围灯"], is_featured=True),
    _seed(name="收纳柜", slug="storage_cabinet", sort_order=350, aliases=["柜子"], sample_keywords=["分层收纳", "抽屉", "置物"], is_featured=True),
    _seed(name="置物架", slug="storage_rack", sort_order=360, aliases=["层架"], sample_keywords=["多层", "厨房收纳", "浴室收纳"], is_featured=True),
    _seed(name="晾衣架", slug="drying_rack", sort_order=370, aliases=["晾衣杆"], sample_keywords=["折叠晾衣", "阳台晾晒"], is_featured=True),
    _seed(name="保温杯", slug="thermos", sort_order=400, aliases=["水杯"], sample_keywords=["保冷", "保温", "316 不锈钢"], is_featured=True),
    _seed(name="收纳盒", slug="storage_box", sort_order=410, aliases=["整理盒"], sample_keywords=["桌面收纳", "分类收纳"], is_featured=True),
    _seed(name="拖把", slug="mop", sort_order=420, aliases=["平板拖把"], sample_keywords=["家务清洁", "免手洗", "拖地"], is_featured=True),
    _seed(name="纸巾盒", slug="tissue_box", sort_order=430, aliases=["纸抽盒"], sample_keywords=["客厅纸巾盒", "桌面摆件"], is_featured=False),
    _seed(name="垃圾桶", slug="trash_bin", sort_order=440, aliases=["废纸篓"], sample_keywords=["脚踏", "感应", "厨卫垃圾桶"], is_featured=True),
    _seed(name="衣架", slug="hanger", sort_order=450, aliases=["裤架"], sample_keywords=["防滑衣架", "收纳挂架"], is_featured=False),
    _seed(name="清洁刷", slug="cleaning_brush", sort_order=460, aliases=["刷子"], sample_keywords=["去污刷", "缝隙刷"], is_featured=False),
    _seed(name="洗发水", slug="shampoo", sort_order=500, aliases=["洗发露"], sample_keywords=["控油", "去屑", "护发"], is_featured=True),
    _seed(name="沐浴露", slug="body_wash", sort_order=510, aliases=["沐浴乳"], sample_keywords=["留香", "滋润", "清洁"], is_featured=True),
    _seed(name="护肤品", slug="skincare", sort_order=520, aliases=["护肤套装"], sample_keywords=["保湿", "修护", "护肤"], is_featured=True),
    _seed(name="精华", slug="serum", sort_order=530, aliases=["精华液"], sample_keywords=["抗老", "补水", "次抛"], is_featured=True),
    _seed(name="面膜", slug="mask", sort_order=540, aliases=["贴片面膜"], sample_keywords=["补水面膜", "修护面膜"], is_featured=True),
    _seed(name="防晒", slug="sunscreen", sort_order=550, aliases=["防晒霜"], sample_keywords=["SPF", "PA", "户外防晒"], is_featured=True),
    _seed(name="牙膏", slug="toothpaste", sort_order=560, aliases=["牙膏套装"], sample_keywords=["清新口气", "美白", "口腔护理"], is_featured=True),
    _seed(name="漱口水", slug="mouthwash", sort_order=570, aliases=["口腔清洁液"], sample_keywords=["口气清新", "便携装"], is_featured=False),
    _seed(name="宠物粮", slug="pet_food", sort_order=600, aliases=["猫粮", "狗粮"], sample_keywords=["冻干", "成犬粮", "成猫粮"], is_featured=True),
    _seed(name="猫砂", slug="cat_litter", sort_order=610, aliases=["豆腐猫砂"], sample_keywords=["除臭", "结团", "宠物清洁"], is_featured=True),
    _seed(name="宠物玩具", slug="pet_toy", sort_order=620, aliases=["逗猫棒", "宠物球"], sample_keywords=["磨牙", "互动", "宠物用品"], is_featured=False),
    _seed(name="宠物饮水机", slug="pet_water_fountain", sort_order=630, aliases=["宠物饮水器"], sample_keywords=["循环过滤", "猫咪饮水"], is_featured=True, confusion_pairs=["饮水机", "加湿器"], expected_components=["饮水碗", "循环水泵", "过滤棉", "水位线"]),
    _seed(name="宠物窝", slug="pet_bed", sort_order=640, aliases=["猫窝", "狗窝"], sample_keywords=["保暖窝", "宠物睡垫"], is_featured=False),
    # 小家电厨房
    _seed(name="养生壶", slug="health_pot", sort_order=650, aliases=["煮茶壶", "电煮壶"], sample_keywords=["煮茶", "慢炖", "养生"], is_featured=True, confusion_pairs=["电水壶", "破壁机", "料理机"]),
    _seed(name="电水壶", slug="electric_kettle", sort_order=660, aliases=["烧水壶", "电热水壶"], sample_keywords=["快煮", "保温", "1.7L"], is_featured=True, confusion_pairs=["养生壶", "饮水机"]),
    _seed(name="豆浆机", slug="soy_milk_maker", sort_order=670, aliases=["全自动豆浆机"], sample_keywords=["免过滤", "豆浆", "全豆"], is_featured=True, confusion_pairs=["破壁机", "料理机"]),
    _seed(name="电蒸锅", slug="electric_steamer", sort_order=680, aliases=["多层蒸锅"], sample_keywords=["蒸鱼", "蒸蛋", "多层蒸"], is_featured=False, confusion_pairs=["电饭煲"]),
    _seed(name="面包机", slug="bread_maker", sort_order=690, aliases=["烤面包机"], sample_keywords=["和面", "发酵", "烤面包"], is_featured=False, confusion_pairs=["烤箱"]),
    _seed(name="电火锅", slug="electric_hot_pot", sort_order=700, aliases=["多功能锅", "一人食锅"], sample_keywords=["火锅", "涮煮", "小火锅"], is_featured=True, confusion_pairs=["电磁炉", "电饭煲"]),
    _seed(name="绞肉机", slug="meat_grinder", sort_order=710, aliases=["多功能绞肉机"], sample_keywords=["绞肉", "搅馅", "辅食研磨"], is_featured=False, confusion_pairs=["料理机", "破壁机"]),
    # 个护
    _seed(name="电动牙刷", slug="electric_toothbrush", sort_order=720, aliases=["声波牙刷"], sample_keywords=["声波震动", "美白", "智能牙刷"], is_featured=True, expected_components=["刷头", "刷柄", "充电底座"]),
    _seed(name="剃须刀", slug="shaver", sort_order=730, aliases=["电动剃须刀", "胡须刀"], sample_keywords=["往复式", "旋转式", "干湿两用"], is_featured=True, expected_components=["刀头", "刀网", "机身", "充电口"], confusion_pairs=["电动牙刷"]),
    _seed(name="吹风机", slug="hair_dryer", sort_order=740, aliases=["电吹风"], sample_keywords=["负离子", "速干", "大功率"], is_featured=True, expected_components=["出风口", "进风口", "风嘴", "手柄"], confusion_pairs=["直发器"]),
    _seed(name="直发器", slug="hair_straightener", sort_order=750, aliases=["直发梳", "卷发棒", "造型棒"], sample_keywords=["陶瓷板", "温度调节", "护发"], is_featured=True, confusion_pairs=["吹风机"]),
    _seed(name="按摩器", slug="massager", sort_order=760, aliases=["筋膜枪", "按摩仪"], sample_keywords=["深层按摩", "放松肌肉", "颈部按摩"], is_featured=True),
    _seed(name="体重秤", slug="scale", sort_order=770, aliases=["智能体脂秤", "电子秤"], sample_keywords=["体脂率", "BMI", "智能秤"], is_featured=False),
    # 大家电
    _seed(name="空调", slug="air_conditioner", sort_order=780, aliases=["分体空调", "挂式空调"], sample_keywords=["制冷", "制热", "变频"], is_featured=True, expected_components=["出风口", "进风口", "面板", "遥控器"]),
    _seed(name="热水器", slug="water_heater", sort_order=790, aliases=["电热水器", "燃气热水器"], sample_keywords=["储水式", "即热式", "安全洗浴"], is_featured=True),
    _seed(name="洗碗机", slug="dishwasher", sort_order=800, aliases=["嵌入式洗碗机", "台式洗碗机"], sample_keywords=["高温除菌", "烘干", "全自动洗碗"], is_featured=True),
    _seed(name="干衣机", slug="dryer", sort_order=810, aliases=["热泵干衣机", "烘干机"], sample_keywords=["热泵", "低温烘干", "护衣"], is_featured=True, confusion_pairs=["洗衣机"]),
    # 数码配件
    _seed(name="充电器", slug="charger", sort_order=820, aliases=["快充充电器", "充电头"], sample_keywords=["氮化镓", "GaN", "多口充电"], is_featured=True, confusion_pairs=["充电宝"]),
    _seed(name="充电宝", slug="power_bank", sort_order=830, aliases=["移动电源"], sample_keywords=["大容量", "快充", "轻薄"], is_featured=True, confusion_pairs=["充电器"]),
    _seed(name="键盘", slug="keyboard", sort_order=840, aliases=["机械键盘", "无线键盘"], sample_keywords=["青轴", "红轴", "RGB背光"], is_featured=True, expected_components=["键帽", "底座", "USB线/接收器"]),
    _seed(name="鼠标", slug="mouse", sort_order=850, aliases=["无线鼠标", "游戏鼠标"], sample_keywords=["DPI", "人体工学", "静音鼠标"], is_featured=True),
    _seed(name="智能手表", slug="smartwatch", sort_order=860, aliases=["运动手表", "健康手表"], sample_keywords=["心率", "血氧", "GPS"], is_featured=True, expected_components=["表盘", "表带", "充电口"]),
    # 智能家居
    _seed(name="智能门锁", slug="smart_lock", sort_order=870, aliases=["指纹锁", "密码锁"], sample_keywords=["指纹识别", "人脸识别", "APP开锁"], is_featured=True, expected_components=["指纹区", "显示屏", "把手", "电池仓"]),
    # 母婴
    _seed(name="婴儿推车", slug="stroller", sort_order=900, aliases=["童车", "宝宝推车"], sample_keywords=["可躺可坐", "轻便折叠", "避震"], is_featured=True),
    _seed(name="奶瓶", slug="baby_bottle", sort_order=910, aliases=["宽口奶瓶", "玻璃奶瓶"], sample_keywords=["防胀气", "宽口径", "硅胶奶嘴"], is_featured=True),
    _seed(name="温奶器", slug="bottle_warmer", sort_order=920, aliases=["暖奶器", "消毒暖奶器"], sample_keywords=["恒温加热", "消毒", "母乳"], is_featured=False, confusion_pairs=["电水壶"]),
    # 户外
    _seed(name="帐篷", slug="tent", sort_order=950, aliases=["户外帐篷", "露营帐篷"], sample_keywords=["防水", "速搭", "双层帐篷"], is_featured=True),
    _seed(name="背包", slug="backpack", sort_order=960, aliases=["双肩包", "登山包"], sample_keywords=["大容量", "防水", "户外背包"], is_featured=True),
    _seed(name="户外水壶", slug="outdoor_bottle", sort_order=970, aliases=["运动水壶", "登山水壶"], sample_keywords=["大容量", "耐摔", "Tritan"], is_featured=False, confusion_pairs=["保温杯"]),
]


def ensure_system_category_catalog(db: Session) -> None:
    now = datetime.now(timezone.utc)
    existing_by_slug = {
        item.slug: item
        for item in db.query(CategoryCatalogModel).filter(CategoryCatalogModel.is_system.is_(True)).all()
    }
    changed = False
    for item in SYSTEM_CATEGORY_CATALOGS:
        existing = existing_by_slug.get(item["slug"])
        if existing is None:
            db.add(
                CategoryCatalogModel(
                    **item,
                    is_system=True,
                    is_active=True,
                    created_by=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            changed = True
            continue
        row_changed = False
        for key in ("name", "sort_order", "aliases", "sample_keywords", "notes", "is_featured", "confusion_pairs", "expected_components"):
            if getattr(existing, key) != item[key]:
                setattr(existing, key, item[key])
                row_changed = True
        if existing.is_system is not True:
            existing.is_system = True
            row_changed = True
        if row_changed:
            existing.updated_at = now
            changed = True
    if changed:
        db.flush()


def list_category_catalog(
    db: Session,
    *,
    include_inactive: bool = False,
) -> list[CategoryCatalogModel]:
    ensure_system_category_catalog(db)
    query = db.query(CategoryCatalogModel)
    if not include_inactive:
        query = query.filter(CategoryCatalogModel.is_active.is_(True))
    return query.order_by(
        CategoryCatalogModel.is_featured.desc(),
        CategoryCatalogModel.sort_order.asc(),
        CategoryCatalogModel.name.asc(),
    ).all()


def list_active_category_catalog(
    *,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    def _serialize(items: list[CategoryCatalogModel]) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "slug": item.slug,
                "sort_order": int(item.sort_order or 0),
                "aliases": [str(alias).strip() for alias in (item.aliases or []) if str(alias).strip()],
                "sample_keywords": [str(keyword).strip() for keyword in (item.sample_keywords or []) if str(keyword).strip()],
                "notes": str(item.notes or "").strip(),
                "is_featured": bool(item.is_featured),
                "confusion_pairs": [str(p).strip() for p in (item.confusion_pairs or []) if str(p).strip()],
                "expected_components": [str(c).strip() for c in (item.expected_components or []) if str(c).strip()],
            }
            for item in items
        ]

    if db is not None:
        return _serialize(list_category_catalog(db, include_inactive=False))
    with db_session.SessionLocal() as owned_db:
        return _serialize(list_category_catalog(owned_db, include_inactive=False))


CATEGORY_VIEW_SUGGESTIONS: dict[str, list[dict[str, str]]] = {
    # 家电类
    "air_purifier": [
        {"view": "filter_closeup", "label": "建议补拍滤芯/滤网特写", "priority": "high"},
        {"view": "control_panel", "label": "建议补拍控制面板/显示屏", "priority": "high"},
        {"view": "air_outlet", "label": "建议补拍出风口细节", "priority": "medium"},
    ],
    "humidifier": [
        {"view": "water_tank", "label": "建议补拍透明水箱特写", "priority": "high"},
        {"view": "mist_outlet", "label": "建议补拍喷雾口细节", "priority": "medium"},
    ],
    "water_purifier": [
        {"view": "filter_element", "label": "建议补拍滤芯/滤网特写", "priority": "high"},
        {"view": "control_panel", "label": "建议补拍控制面板", "priority": "medium"},
        {"view": "installation", "label": "建议补拍安装方式", "priority": "medium"},
    ],
    "robot_vacuum": [
        {"view": "bottom_view", "label": "建议补拍底部刷头/轮组", "priority": "high"},
        {"view": "dust_bin", "label": "建议补拍集尘盒", "priority": "medium"},
        {"view": "charging_dock", "label": "建议补拍充电底座", "priority": "medium"},
    ],
    "coffee_machine": [
        {"view": "brewing_group", "label": "建议补拍冲泡组件", "priority": "high"},
        {"view": "water_tank", "label": "建议补拍水箱", "priority": "medium"},
        {"view": "control_panel", "label": "建议补拍操控面板", "priority": "medium"},
    ],
    # 个护美妆类
    "electric_toothbrush": [
        {"view": "brush_head", "label": "建议补拍刷头细节", "priority": "high"},
        {"view": "charging_base", "label": "建议补拍充电底座", "priority": "medium"},
    ],
    "hair_dryer": [
        {"view": "nozzle", "label": "建议补拍风嘴/配件", "priority": "high"},
        {"view": "control_buttons", "label": "建议补拍控制按钮", "priority": "medium"},
    ],
    "perfume": [
        {"view": "bottle_detail", "label": "建议补拍瓶身细节/logo", "priority": "high"},
        {"view": "cap_detail", "label": "建议补拍瓶盖工艺", "priority": "medium"},
        {"view": "packaging", "label": "建议补拍外包装", "priority": "medium"},
    ],
    "skincare": [
        {"view": "texture", "label": "建议补拍产品质地/膏体", "priority": "high"},
        {"view": "ingredients_label", "label": "建议补拍成分表", "priority": "medium"},
        {"view": "packaging_detail", "label": "建议补拍包装细节", "priority": "medium"},
    ],
    # 家居类
    "mattress": [
        {"view": "cross_section", "label": "��议补拍截面/内部结构", "priority": "high"},
        {"view": "fabric_detail", "label": "建议补拍面料细节", "priority": "medium"},
        {"view": "size_reference", "label": "建议补拍尺寸参照", "priority": "medium"},
    ],
    "chair": [
        {"view": "mechanism", "label": "建议补拍升降/调节机构", "priority": "high"},
        {"view": "material_detail", "label": "建议补拍材质细节", "priority": "medium"},
        {"view": "multi_angle", "label": "建议补拍多角度", "priority": "medium"},
    ],
    # 宠物类
    "pet_water_fountain": [
        {"view": "filter", "label": "建议补拍滤芯特写", "priority": "high"},
        {"view": "water_flow", "label": "建议补拍��水方式", "priority": "medium"},
        {"view": "pet_using", "label": "建议补拍宠物使用场景", "priority": "medium"},
    ],
    # 数码配件
    "charger": [
        {"view": "ports", "label": "建议补拍接口细节", "priority": "high"},
        {"view": "size_comparison", "label": "建议补拍尺寸对比", "priority": "medium"},
    ],
    "keyboard": [
        {"view": "keycap_detail", "label": "建议补拍键帽细节", "priority": "high"},
        {"view": "rgb_lighting", "label": "建议补拍灯效展示", "priority": "medium"},
        {"view": "side_profile", "label": "建议补拍侧面高度", "priority": "medium"},
    ],
}

# Fallback by category family
_FAMILY_VIEW_SUGGESTIONS: dict[str, list[dict[str, str]]] = {
    "appliance": [
        {"view": "control_panel", "label": "建议补拍控制面板/按钮区域", "priority": "medium"},
        {"view": "detail_closeup", "label": "建议补拍关键部件特写", "priority": "medium"},
    ],
    "beauty": [
        {"view": "texture_or_ingredient", "label": "建议补拍产品质地或成分信息", "priority": "medium"},
        {"view": "packaging", "label": "建议补拍包装细节", "priority": "medium"},
    ],
    "furniture": [
        {"view": "material_detail", "label": "建议补拍材质/面料细节", "priority": "medium"},
        {"view": "size_reference", "label": "建议补拍尺寸参照", "priority": "medium"},
    ],
    "pet": [
        {"view": "pet_using", "label": "建议补拍宠物使用场景", "priority": "medium"},
    ],
    "digital": [
        {"view": "port_detail", "label": "建议补拍接口/连接细节", "priority": "medium"},
    ],
}

_SLUG_TO_FAMILY: dict[str, str] = {
    "air_purifier": "appliance", "humidifier": "appliance", "water_purifier": "appliance",
    "robot_vacuum": "appliance", "coffee_machine": "appliance", "air_conditioner": "appliance",
    "water_heater": "appliance", "washing_machine": "appliance", "dishwasher": "appliance",
    "microwave": "appliance", "oven": "appliance", "rice_cooker": "appliance",
    "electric_toothbrush": "beauty", "hair_dryer": "beauty", "perfume": "beauty",
    "skincare": "beauty", "shaver": "beauty", "straightener": "beauty",
    "mattress": "furniture", "sofa": "furniture", "desk": "furniture", "chair": "furniture",
    "lamp": "furniture", "storage": "furniture",
    "pet_water_fountain": "pet", "pet_food": "pet", "cat_litter": "pet",
    "charger": "digital", "power_bank": "digital", "keyboard": "digital",
    "mouse": "digital", "smartwatch": "digital",
}


def suggest_supplementary_views(
    category_slug: str | None,
    detected_view_slots: list[str] | None = None,
) -> list[dict[str, str]]:
    """Return category-aware supplementary image suggestions.

    Returns a list of dicts with keys: view, label, priority.
    Filters out views that are already covered by detected_view_slots.
    """
    if not category_slug:
        return []
    slug = category_slug.lower().replace(" ", "_").replace("-", "_")
    suggestions = CATEGORY_VIEW_SUGGESTIONS.get(slug)
    if suggestions is None:
        family = _SLUG_TO_FAMILY.get(slug)
        suggestions = _FAMILY_VIEW_SUGGESTIONS.get(family, []) if family else []
    if not suggestions:
        return []
    detected = set(detected_view_slots or [])
    return [s for s in suggestions if s["view"] not in detected]


# ── Category Parameter Rules ──────────────────────────────────────────

SYSTEM_CATEGORY_PARAMETER_RULES: list[dict[str, Any]] = [
    {
        "category_slug": "air_purifier",
        "platform_id": None,
        "core_purchase_parameters": [
            {"key": "cadr", "label": "CADR值", "unit": "m³/h", "priority": 1},
            {"key": "coverage_area", "label": "适用面积", "unit": "m²", "priority": 2},
            {"key": "filter_grade", "label": "滤网等级", "unit": "", "priority": 1},
            {"key": "noise_level", "label": "噪音", "unit": "dB(A)", "priority": 3},
            {"key": "purification_efficiency", "label": "净化效率", "unit": "%", "priority": 2},
            {"key": "sensor_type", "label": "传感器类型", "unit": "", "priority": 4},
            {"key": "filter_life", "label": "滤网使用寿命", "unit": "月", "priority": 3},
            {"key": "rated_power", "label": "额定功率", "unit": "W", "priority": 5},
        ],
        "parameter_extraction_hints": [
            "优先识别净化性能相关参数（CADR、滤网等级、适用面积）",
            "如有铭牌或参数标贴请重点提取",
            "关注进风口/出风口设计，这关系到净化效率",
        ],
        "anti_patterns": [
            "外观形状（如圆柱型、方形）",
            "按钮布局方式",
            "指示灯颜色",
            "产品高度或直径",
            "进风口格栅样式",
        ],
        "selling_point_themes": [
            {"theme": "宠物家庭适用", "keywords": ["宠物", "毛发", "除味", "猫狗"]},
            {"theme": "母婴级净化", "keywords": ["母婴", "婴��", "安全", "低敏"]},
            {"theme": "除甲醛", "keywords": ["甲醛", "新装修", "装修污染", "除醛"]},
            {"theme": "静音睡眠", "keywords": ["静音", "睡眠", "低噪", "卧室"]},
            {"theme": "大面积覆盖", "keywords": ["大面积", "全屋", "客厅", "大空间"]},
            {"theme": "智能监测", "keywords": ["智能", "传感器", "自动", "APP"]},
        ],
        "category_reasoning_hints": (
            "空气净化器是成熟家电品类。消费者购买决策核心关注：净化效率(CADR值，单位m³/h)、"
            "滤网等级(HEPA H11/H12/H13)与更换成本、噪音水平(dB(A))、适用面积(m²)。"
            "常见消费者场景包括：宠物家庭（毛发过滤+除异味）、新装修除甲醛、母婴防护（低噪+除菌）、"
            "卧室静音运行。核心参数应优先围绕这些维度提取，而非外观描述。"
        ),
    },
]


def ensure_system_category_parameter_rules(db: Session) -> None:
    now = datetime.now(timezone.utc)
    existing_by_slug = {
        item.category_slug: item
        for item in db.query(CategoryParameterRuleModel).all()
    }
    changed = False
    for item in SYSTEM_CATEGORY_PARAMETER_RULES:
        existing = existing_by_slug.get(item["category_slug"])
        if existing is None:
            db.add(
                CategoryParameterRuleModel(
                    **item,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            changed = True
            continue
        row_changed = False
        for key in (
            "platform_id", "core_purchase_parameters", "parameter_extraction_hints",
            "anti_patterns", "selling_point_themes", "category_reasoning_hints",
        ):
            if getattr(existing, key) != item[key]:
                setattr(existing, key, item[key])
                row_changed = True
        if row_changed:
            existing.updated_at = now
            changed = True
    if changed:
        db.flush()


def get_category_parameter_rules(
    db: Session,
    category_slug: str,
    platform_id: str | None = None,
) -> dict[str, Any] | None:
    ensure_system_category_parameter_rules(db)
    query = db.query(CategoryParameterRuleModel).filter(
        CategoryParameterRuleModel.category_slug == category_slug,
        CategoryParameterRuleModel.is_active.is_(True),
    )
    if platform_id:
        query = query.filter(CategoryParameterRuleModel.platform_id == platform_id)
    else:
        query = query.filter(CategoryParameterRuleModel.platform_id.is_(None))
    item = query.first()
    if item is None:
        return None
    return {
        "rule_id": item.id,
        "category_slug": item.category_slug,
        "platform_id": item.platform_id,
        "core_purchase_parameters": item.core_purchase_parameters or [],
        "parameter_extraction_hints": item.parameter_extraction_hints or [],
        "anti_patterns": item.anti_patterns or [],
        "selling_point_themes": item.selling_point_themes or [],
        "category_reasoning_hints": item.category_reasoning_hints or "",
    }
