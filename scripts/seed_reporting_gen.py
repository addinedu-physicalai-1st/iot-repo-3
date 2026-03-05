#!/usr/bin/env python3
"""
재고 리포트 시각화용 시드 데이터 SQL 생성.
schema_understanding.md 규칙에 따라 orders, order_items, processes, item_sorting_logs, inventory 생성.
실행: uv run python scripts/seed_reporting_gen.py
출력: scripts/seed_reporting.sql
"""
from datetime import datetime, timedelta
import random
from pathlib import Path

PRODUCTS = [
    ("mongo_guk_1l", "몽고 국간장 1L", "몽고", "국간장", "1L"),
    ("mongo_guk_2l", "몽고 국간장 2L", "몽고", "국간장", "2L"),
    ("mongo_jin_1l", "몽고 진간장 1L", "몽고", "진간장", "1L"),
    ("mongo_jin_2l", "몽고 진간장 2L", "몽고", "진간장", "2L"),
    ("sampyo_guk_1l", "샘표 국간장 1L", "샘표", "국간장", "1L"),
    ("sampyo_guk_2l", "샘표 국간장 2L", "샘표", "국간장", "2L"),
    ("sampyo_jin_1l", "샘표 진간장 1L", "샘표", "진간장", "1L"),
    ("sampyo_jin_2l", "샘표 진간장 2L", "샘표", "진간장", "2L"),
]

ITEM_CODES = [p[0] for p in PRODUCTS]
CAPACITY_MAP = {code: p[4] for code, p in zip(ITEM_CODES, PRODUCTS)}


def escape_sql(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def main() -> None:
    random.seed(42)
    out: list[str] = []
    out.append("-- 재고 리포트 시각화용 시드 데이터 (seed_reporting_gen.py로 생성)")
    out.append("SET NAMES utf8mb4;")
    out.append("ALTER DATABASE soydb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    out.append("ALTER TABLE products CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    out.append("ALTER TABLE inventory CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    out.append("-- products, orders, order_items, processes, item_sorting_logs, inventory")
    out.append("-- 사용: mysql -u soy -psoy soydb < scripts/seed_reporting.sql")
    out.append("-- Docker: docker compose exec mysql mysql -usoy -psoy soydb < scripts/seed_reporting.sql")
    out.append("")

    # 1. products
    out.append("-- products 시드")
    out.append(
        "INSERT INTO `products` (`item_code`, `name`, `brand`, `category`, `capacity`) VALUES"
    )
    rows = [
        f"  ('{code}', '{escape_sql(name)}', '{escape_sql(brand)}', '{escape_sql(cat)}', '{cap}')"
        for code, name, brand, cat, cap in PRODUCTS
    ]
    out.append(",\n".join(rows))
    out.append("ON DUPLICATE KEY UPDATE name=VALUES(name), brand=VALUES(brand), category=VALUES(category), capacity=VALUES(capacity);")
    out.append("")

    # 2. orders (2025-03-01 ~ 2026-03-20, every 3 days)
    start = datetime(2025, 3, 1)
    end = datetime(2026, 3, 20)
    order_dates: list[datetime] = []
    d = start
    while d <= end:
        order_dates.append(d)
        d += timedelta(days=3)
    delivered_from = datetime(2026, 3, 8)

    out.append("-- 기존 시드 정리 (FK 순서)")
    out.append("DELETE FROM `item_sorting_logs`;")
    out.append("DELETE FROM `processes`;")
    out.append("DELETE FROM `order_items`;")
    out.append("DELETE FROM `orders`;")
    out.append("ALTER TABLE `orders` AUTO_INCREMENT = 1;")
    out.append("ALTER TABLE `processes` AUTO_INCREMENT = 1;")
    out.append("")

    out.append("-- orders 시드")
    out.append("INSERT INTO `orders` (`order_date`, `status`) VALUES")
    order_rows = []
    for d in order_dates:
        status = "PENDING" if d >= delivered_from else "DELIVERED"
        order_rows.append(f"  ('{d.strftime('%Y-%m-%d')} 00:00:00', '{status}')")
    out.append(",\n".join(order_rows))
    out.append(";")
    out.append("")

    # 3. order_items (10 rows per order, sum expected_qty = 10, random item_code)
    order_items_data: list[tuple[int, str, int]] = []
    for order_id in range(1, len(order_dates) + 1):
        for _ in range(10):
            item_code = random.choice(ITEM_CODES)
            order_items_data.append((order_id, item_code, 1))

    out.append("-- order_items 시드 (order당 10개, 합계 10)")
    out.append("INSERT INTO `order_items` (`order_id`, `item_code`, `expected_qty`) VALUES")
    oi_rows = [
        f"  ({oid}, '{code}', {qty})" for oid, code, qty in order_items_data
    ]
    out.append(",\n".join(oi_rows))
    out.append(";")
    out.append("")

    # 4. processes (order_date <= 2026-03-01 인 주문만)
    cutoff = datetime(2026, 3, 1, 23, 59, 59)
    process_order_ids = [i + 1 for i, d in enumerate(order_dates) if d <= cutoff]

    out.append("-- processes 시드 (3월 1일까지 주문 대상)")
    out.append(
        "INSERT INTO `processes` (`order_id`, `start_time`, `end_time`, `status`, `total_qty`, `success_1l_qty`, `success_2l_qty`, `unclassified_qty`) VALUES"
    )
    proc_rows = []
    for oid in process_order_ids:
        od = order_dates[oid - 1]
        dt = od.strftime("%Y-%m-%d 09:00:00")
        proc_rows.append(f"  ({oid}, '{dt}', '{dt}', 'COMPLETED', 10, 0, 0, 0)")
    out.append(",\n".join(proc_rows))
    out.append(";")
    out.append("")

    # 4b. inventory 행 생성 (item_sorting_logs FK용, current_qty는 나중에 UPDATE)
    out.append("-- inventory 행 (item_sorting_logs FK용)")
    out.append(
        "INSERT INTO `inventory` (`inventory_id`, `inventory_name`, `current_qty`, `updated_at`) VALUES"
    )
    out.append("  (1, '1L창고', 0, NOW()),")
    out.append("  (2, '2L창고', 0, NOW()),")
    out.append("  (3, '미분류 창고', 0, NOW())")
    out.append(
        "ON DUPLICATE KEY UPDATE inventory_name = VALUES(inventory_name), updated_at = NOW();"
    )
    out.append("")

    # 5. item_sorting_logs
    order_to_process: dict[int, int] = {
        oid: pid for pid, oid in enumerate(process_order_ids, start=1)
    }
    process_order_set = set(process_order_ids)

    log_rows: list[str] = []
    log_idx = 0
    for oid, item_code, qty in order_items_data:
        if oid not in process_order_set:
            continue
        process_id = order_to_process[oid]
        od = order_dates[oid - 1]
        for _ in range(qty):
            log_idx += 1
            r = random.random()
            if r < 0.05:
                inv_id = "NULL"
                is_err = 1
            elif r < 0.05 + 0.1056:
                inv_id = "3"
                is_err = 0
            else:
                cap = CAPACITY_MAP[item_code]
                inv_id = "1" if cap == "1L" else "2"
                is_err = 0

            exp_start = datetime(2026, 4, 1)
            exp_end = datetime(2028, 4, 30)
            exp_date = exp_start + timedelta(
                days=random.randint(0, (exp_end - exp_start).days)
            )
            ts = od.strftime("%Y-%m-%d") + f" 10:{log_idx % 60:02d}:{log_idx % 60:02d}"
            log_rows.append(
                f"  ({process_id}, '{item_code}', '{exp_date.strftime('%Y-%m-%d')}', {inv_id}, {is_err}, '{ts}')"
            )

    out.append("-- item_sorting_logs 시드")
    out.append(
        "INSERT INTO `item_sorting_logs` (`process_id`, `item_code`, `expiration_date`, `inventory_id`, `is_error`, `timestamp`) VALUES"
    )
    out.append(",\n".join(log_rows))
    out.append(";")
    out.append("")

    # 6. processes 업데이트 (success_1l, success_2l, unclassified 집계)
    # process별로 로그 카운트가 필요하지만, 이미 INSERT 후라 서브쿼리로 불가.
    # 대신 inventory의 current_qty는 item_sorting_logs 집계로 계산.
    # processes의 qty는 시드에서 0으로 두고, 필요시 애플리케이션에서 갱신한다고 가정.
    out.append("-- processes 수량 업데이트 (item_sorting_logs 집계 반영)")
    out.append("UPDATE processes p SET")
    out.append("  success_1l_qty = (SELECT COUNT(*) FROM item_sorting_logs l WHERE l.process_id = p.process_id AND l.inventory_id = 1),")
    out.append("  success_2l_qty = (SELECT COUNT(*) FROM item_sorting_logs l WHERE l.process_id = p.process_id AND l.inventory_id = 2),")
    out.append("  unclassified_qty = (SELECT COUNT(*) FROM item_sorting_logs l WHERE l.process_id = p.process_id AND l.inventory_id = 3);")
    out.append("")

    # 7. inventory current_qty 업데이트
    out.append("-- inventory current_qty 업데이트 (item_sorting_logs 건수 반영)")
    out.append(
        "UPDATE inventory i SET i.current_qty = (SELECT COUNT(*) FROM item_sorting_logs l WHERE l.inventory_id = i.inventory_id), i.updated_at = NOW() WHERE i.inventory_id IN (1, 2, 3);"
    )
    out.append("")

    out.append("-- 확인 쿼리")
    out.append("SELECT item_code, name, brand, category, capacity FROM products ORDER BY item_code;")
    out.append("SELECT inventory_id, inventory_name, current_qty, updated_at FROM inventory ORDER BY inventory_id;")

    sql_path = Path(__file__).resolve().parent / "seed_reporting.sql"
    sql_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Generated {sql_path}")


if __name__ == "__main__":
    main()
