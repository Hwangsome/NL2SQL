import argparse
import asyncio
import csv
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import text

from app.clients.mysql_client_manager import dw_mysql_client_manager


@dataclass
class GenerateConfig:
    output_dir: Path
    seed: int
    customer_count: int
    product_count: int
    order_count: int
    start_date: date
    end_date: date
    load_db: bool
    truncate: bool


REGIONS: list[dict[str, str | int]] = [
    {"region_id": 1, "province": "北京", "region_name": "华北", "country": "中国"},
    {"region_id": 2, "province": "天津", "region_name": "华北", "country": "中国"},
    {"region_id": 3, "province": "河北", "region_name": "华北", "country": "中国"},
    {"region_id": 4, "province": "上海", "region_name": "华东", "country": "中国"},
    {"region_id": 5, "province": "江苏", "region_name": "华东", "country": "中国"},
    {"region_id": 6, "province": "浙江", "region_name": "华东", "country": "中国"},
    {"region_id": 7, "province": "山东", "region_name": "华东", "country": "中国"},
    {"region_id": 8, "province": "广东", "region_name": "华南", "country": "中国"},
    {"region_id": 9, "province": "福建", "region_name": "华南", "country": "中国"},
    {"region_id": 10, "province": "广西", "region_name": "华南", "country": "中国"},
    {"region_id": 11, "province": "湖北", "region_name": "华中", "country": "中国"},
    {"region_id": 12, "province": "湖南", "region_name": "华中", "country": "中国"},
    {"region_id": 13, "province": "河南", "region_name": "华中", "country": "中国"},
    {"region_id": 14, "province": "四川", "region_name": "西南", "country": "中国"},
    {"region_id": 15, "province": "重庆", "region_name": "西南", "country": "中国"},
    {"region_id": 16, "province": "云南", "region_name": "西南", "country": "中国"},
    {"region_id": 17, "province": "陕西", "region_name": "西北", "country": "中国"},
    {"region_id": 18, "province": "甘肃", "region_name": "西北", "country": "中国"},
    {"region_id": 19, "province": "辽宁", "region_name": "东北", "country": "中国"},
    {"region_id": 20, "province": "吉林", "region_name": "东北", "country": "中国"},
    {"region_id": 21, "province": "黑龙江", "region_name": "东北", "country": "中国"},
]

REGION_WEIGHTS = {
    "华东": 1.36,
    "华南": 1.22,
    "华北": 1.08,
    "华中": 0.98,
    "西南": 0.91,
    "西北": 0.78,
    "东北": 0.72,
}

MEMBER_LEVELS = [
    ("普通", 0.33, 0.94),
    ("白银", 0.22, 1.0),
    ("黄金", 0.19, 1.08),
    ("铂金", 0.13, 1.16),
    ("钻石", 0.09, 1.28),
    ("黑金", 0.04, 1.42),
]

CATEGORY_BRANDS: dict[str, dict[str, list[str]]] = {
    "手机": {
        "苹果": ["iPhone 15", "iPhone 15 Pro", "iPhone 16", "iPhone 16 Pro"],
        "华为": ["Mate 60", "Pura 70", "nova 13", "Mate X5"],
        "小米": ["小米 14", "小米 15", "Redmi K70", "Redmi Note 14"],
        "荣耀": ["Magic 6", "荣耀 200", "X50 GT", "Magic V3"],
        "OPPO": ["Find X7", "Reno 12", "A5 Pro", "Find N3"],
        "vivo": ["X100", "S20", "iQOO 13", "X Fold 3"],
    },
    "笔记本": {
        "苹果": ["MacBook Air 13", "MacBook Air 15", "MacBook Pro 14"],
        "华为": ["MateBook X Pro", "MateBook 14", "MateBook D 16"],
        "联想": ["小新 Pro 14", "ThinkBook 16", "拯救者 Y9000P"],
        "戴尔": ["XPS 13", "Inspiron 14", "Latitude 5440"],
        "华硕": ["灵耀 14", "天选 5", "无畏 Pro 16"],
    },
    "平板": {
        "苹果": ["iPad Air", "iPad Pro 11", "iPad mini"],
        "华为": ["MatePad 11.5", "MatePad Pro 13.2", "MatePad Air"],
        "小米": ["小米平板 6", "小米平板 6S Pro", "Redmi Pad Pro"],
        "荣耀": ["荣耀平板 9", "MagicPad 2", "荣耀平板 X9"],
    },
    "耳机": {
        "苹果": ["AirPods Pro", "AirPods 4", "Beats Studio Buds"],
        "华为": ["FreeBuds Pro", "FreeClip", "FreeBuds 6i"],
        "小米": ["Buds 5 Pro", "Redmi Buds 6", "OpenWear Stereo"],
        "索尼": ["WF-1000XM5", "WH-1000XM5", "LinkBuds S"],
    },
    "电视": {
        "小米": ["小米电视 S65", "Redmi MAX 100", "小米电视 EA75"],
        "海信": ["E8N Pro", "U7N", "Vidda X75"],
        "TCL": ["Q10K", "T7K", "X11H"],
        "华为": ["Vision 4", "智慧屏 V5", "Vision Smart Screen 3"],
    },
    "智能穿戴": {
        "苹果": ["Apple Watch S10", "Apple Watch Ultra 2", "Watch SE"],
        "华为": ["WATCH GT 5", "WATCH 4 Pro", "Band 9"],
        "小米": ["Watch S4", "手环 9 Pro", "Watch 2"],
        "荣耀": ["荣耀手表 5", "手环 9", "GS 4"],
    },
    "大家电": {
        "美的": ["风酷空调", "滚筒洗衣机", "对开门冰箱"],
        "海尔": ["云溪洗衣机", "卡萨帝冰箱", "智家空调"],
        "格力": ["云佳空调", "京致空调", "品圆空调"],
        "小米": ["米家空调 Pro", "米家冰箱 510L", "米家洗烘一体"],
    },
}

CATEGORY_PRICE = {
    "手机": (2999, 11999),
    "笔记本": (4599, 16999),
    "平板": (1899, 8999),
    "耳机": (199, 2499),
    "电视": (2199, 19999),
    "智能穿戴": (249, 6999),
    "大家电": (1799, 12999),
}

CATEGORY_QUANTITY = {
    "手机": (1, 2),
    "笔记本": (1, 2),
    "平板": (1, 2),
    "耳机": (1, 4),
    "电视": (1, 1),
    "智能穿戴": (1, 3),
    "大家电": (1, 1),
}

YEAR_FACTOR = {2023: 0.84, 2024: 1.0, 2025: 1.18, 2026: 1.24}
MONTH_FACTOR = {
    1: 0.92,
    2: 0.88,
    3: 0.97,
    4: 1.0,
    5: 1.03,
    6: 1.18,
    7: 0.98,
    8: 0.99,
    9: 1.06,
    10: 1.12,
    11: 1.28,
    12: 1.22,
}

FIRST_NAMES = ["陈", "林", "黄", "周", "吴", "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "罗", "郑"]
SECOND_NAMES = ["晨", "宇", "欣", "然", "琪", "涛", "敏", "博", "杰", "婷", "怡", "宁", "轩", "妍", "睿", "航"]
THIRD_NAMES = ["阳", "文", "琪", "峰", "佳", "玲", "凯", "雪", "彤", "涵", "豪", "莉", "悦", "珂", "源"]


def daterange(start: date, end: date) -> list[date]:
    current = start
    result: list[date] = []
    while current <= end:
        result.append(current)
        current += timedelta(days=1)
    return result


def weighted_choice(randomizer: random.Random, items: list[tuple[str, float, float]]) -> tuple[str, float]:
    total = sum(weight for _, weight, _ in items)
    threshold = randomizer.random() * total
    current = 0.0
    for label, weight, factor in items:
        current += weight
        if current >= threshold:
            return label, factor
    label, _, factor = items[-1]
    return label, factor


def build_customers(randomizer: random.Random, count: int) -> list[dict[str, str | int]]:
    customers: list[dict[str, str | int]] = []
    for index in range(count):
        customer_id = 100000 + index + 1
        level, _ = weighted_choice(randomizer, MEMBER_LEVELS)
        gender = "男" if randomizer.random() < 0.52 else "女"
        name = f"{randomizer.choice(FIRST_NAMES)}{randomizer.choice(SECOND_NAMES)}{randomizer.choice(THIRD_NAMES)}"
        customers.append(
            {
                "customer_id": customer_id,
                "customer_name": f"{name}{customer_id % 97:02d}",
                "gender": gender,
                "member_level": level,
            }
        )
    return customers


def build_products(randomizer: random.Random, count: int) -> list[dict[str, str | int]]:
    combinations: list[tuple[str, str, str]] = []
    for category, brands in CATEGORY_BRANDS.items():
        for brand, models in brands.items():
            for model in models:
                combinations.append((category, brand, model))

    products: list[dict[str, str | int]] = []
    for index in range(count):
        category, brand, model = combinations[index % len(combinations)]
        product_id = 200000 + index + 1
        products.append(
            {
                "product_id": product_id,
                "product_name": model,
                "category": category,
                "brand": brand,
            }
        )
    randomizer.shuffle(products)
    products.sort(key=lambda item: int(item["product_id"]))
    return products


def build_dates(start: date, end: date) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for current in daterange(start, end):
        quarter = f"Q{((current.month - 1) // 3) + 1}"
        rows.append(
            {
                "date_id": int(current.strftime("%Y%m%d")),
                "year": current.year,
                "quarter": quarter,
                "month": current.month,
                "day": current.day,
            }
        )
    return rows


def pick_region(randomizer: random.Random) -> dict[str, str | int]:
    weighted_regions = [(region, REGION_WEIGHTS[str(region["region_name"])]) for region in REGIONS]
    total = sum(weight for _, weight in weighted_regions)
    threshold = randomizer.random() * total
    current = 0.0
    for region, weight in weighted_regions:
        current += weight
        if current >= threshold:
            return region
    return REGIONS[-1]


def build_orders(
    randomizer: random.Random,
    customers: list[dict[str, str | int]],
    products: list[dict[str, str | int]],
    dates: list[dict[str, str | int]],
    count: int,
) -> list[dict[str, str | int | float]]:
    orders: list[dict[str, str | int | float]] = []
    customer_levels = {int(customer["customer_id"]): str(customer["member_level"]) for customer in customers}

    for order_id in range(1, count + 1):
        customer = randomizer.choice(customers)
        product = randomizer.choice(products)
        order_date = randomizer.choice(dates)
        region = pick_region(randomizer)

        category = str(product["category"])
        brand = str(product["brand"])
        member_level = customer_levels[int(customer["customer_id"])]
        member_factor = next(factor for label, _, factor in MEMBER_LEVELS if label == member_level)

        quantity_min, quantity_max = CATEGORY_QUANTITY[category]
        quantity = randomizer.randint(quantity_min, quantity_max)

        price_min, price_max = CATEGORY_PRICE[category]
        base_price = randomizer.uniform(price_min, price_max)
        brand_factor = 1.0
        if brand in {"苹果", "索尼"}:
            brand_factor = 1.18
        elif brand in {"华为", "戴尔"}:
            brand_factor = 1.08
        elif brand in {"小米", "荣耀"}:
            brand_factor = 0.94

        region_factor = REGION_WEIGHTS[str(region["region_name"])]
        year_factor = YEAR_FACTOR.get(int(order_date["year"]), 1.0)
        month_factor = MONTH_FACTOR[int(order_date["month"])]
        campaign_factor = randomizer.uniform(0.9, 1.12)

        amount = (
            Decimal(str(base_price))
            * Decimal(str(quantity))
            * Decimal(str(brand_factor))
            * Decimal(str(member_factor))
            * Decimal(str(region_factor))
            * Decimal(str(year_factor))
            * Decimal(str(month_factor))
            * Decimal(str(campaign_factor))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        orders.append(
            {
                "order_id": order_id,
                "customer_id": int(customer["customer_id"]),
                "product_id": int(product["product_id"]),
                "date_id": int(order_date["date_id"]),
                "region_id": int(region["region_id"]),
                "order_quantity": quantity,
                "order_amount": float(amount),
            }
        )
    return orders


def write_csv(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, config: GenerateConfig, counts: dict[str, int]) -> None:
    summary = {
        "dataset": "retail_dw_large",
        "generated_at": date.today().isoformat(),
        "config": {
            "seed": config.seed,
            "customer_count": config.customer_count,
            "product_count": config.product_count,
            "order_count": config.order_count,
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
        },
        "counts": counts,
    }
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


async def load_table(table_name: str, csv_path: Path, chunk_size: int = 1000) -> int:
    if dw_mysql_client_manager.session_factory is None:
        raise RuntimeError("DW MySQL client manager is not initialized.")

    with csv_path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        placeholders = ", ".join(f":{column}" for column in columns)
        sql = text(f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})")
        inserted = 0
        batch: list[dict[str, object]] = []

        async with dw_mysql_client_manager.session_factory() as session:
            for row in reader:
                normalized: dict[str, object] = {}
                for key, value in row.items():
                    if value is None:
                        normalized[key] = None
                    elif key == "order_amount":
                        normalized[key] = Decimal(value)
                    elif key.endswith("_id") or key in {"year", "month", "day", "order_quantity"}:
                        normalized[key] = int(value)
                    else:
                        normalized[key] = value
                batch.append(normalized)

                if len(batch) >= chunk_size:
                    await session.execute(sql, batch)
                    await session.commit()
                    inserted += len(batch)
                    batch = []

            if batch:
                await session.execute(sql, batch)
                await session.commit()
                inserted += len(batch)

    return inserted


async def replace_dw_data(output_dir: Path, truncate: bool) -> dict[str, int]:
    dw_mysql_client_manager.init()
    counts: dict[str, int] = {}
    try:
        if dw_mysql_client_manager.session_factory is None:
            raise RuntimeError("DW MySQL client manager is not initialized.")

        async with dw_mysql_client_manager.session_factory() as session:
            if truncate:
                for table_name in ["fact_order", "dim_date", "dim_product", "dim_customer", "dim_region"]:
                    await session.execute(text(f"DELETE FROM {table_name}"))
                await session.commit()

        for table_name in ["dim_region", "dim_customer", "dim_product", "dim_date", "fact_order"]:
            counts[table_name] = await load_table(table_name, output_dir / f"{table_name}.csv")
    finally:
        await dw_mysql_client_manager.close()
    return counts


def generate_dataset(config: GenerateConfig) -> dict[str, int]:
    randomizer = random.Random(config.seed)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    regions = REGIONS
    customers = build_customers(randomizer, config.customer_count)
    products = build_products(randomizer, config.product_count)
    dates = build_dates(config.start_date, config.end_date)
    orders = build_orders(randomizer, customers, products, dates, config.order_count)

    write_csv(config.output_dir / "dim_region.csv", regions)
    write_csv(config.output_dir / "dim_customer.csv", customers)
    write_csv(config.output_dir / "dim_product.csv", products)
    write_csv(config.output_dir / "dim_date.csv", dates)
    write_csv(config.output_dir / "fact_order.csv", orders)

    counts = {
        "dim_region": len(regions),
        "dim_customer": len(customers),
        "dim_product": len(products),
        "dim_date": len(dates),
        "fact_order": len(orders),
    }
    write_summary(config.output_dir / "summary.json", config, counts)
    return counts


def parse_args() -> GenerateConfig:
    parser = argparse.ArgumentParser(description="Generate and optionally load retail DW data.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/retail_dw_large"))
    parser.add_argument("--seed", type=int, default=20260406)
    parser.add_argument("--customers", type=int, default=600)
    parser.add_argument("--products", type=int, default=120)
    parser.add_argument("--orders", type=int, default=18000)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2023, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 3, 31))
    parser.add_argument("--load-db", action="store_true")
    parser.add_argument("--no-truncate", action="store_true")
    args = parser.parse_args()

    return GenerateConfig(
        output_dir=args.output_dir,
        seed=args.seed,
        customer_count=args.customers,
        product_count=args.products,
        order_count=args.orders,
        start_date=args.start_date,
        end_date=args.end_date,
        load_db=args.load_db,
        truncate=not args.no_truncate,
    )


def main() -> None:
    config = parse_args()
    counts = generate_dataset(config)
    print(json.dumps({"generated": counts, "output_dir": str(config.output_dir)}, ensure_ascii=False))

    if config.load_db:
        loaded_counts = asyncio.run(replace_dw_data(config.output_dir, config.truncate))
        print(json.dumps({"loaded": loaded_counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
