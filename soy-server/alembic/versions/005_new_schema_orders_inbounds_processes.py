"""new schema: products(item_code), orders, order_items, inbounds, processes, item_sorting_logs, process_results, alerts, inventory

ER 다이어그램(docs/er-diagram.md) 반영:
  - products: item_code PK, name, brand, category, capacity (기존 product_id 스키마 제거)
  - orders / order_items: 발주·발주상세
  - inbounds: 입고번호 PK, order_id FK (기존 inbounds/inbound_items 제거)
  - processes: 공정 작업 (inbound_id FK)
  - item_sorting_logs: 상자 단위 인식·분류 로그
  - process_results: 공정 최종 결과 (1:1 process)
  - alerts: 시스템 알림/경고
  - inventory: 창고 재고

Revision ID: 005
Revises: 004
Create Date: 2025-02-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET NAMES utf8mb4")
    op.execute("SET FOREIGN_KEY_CHECKS = 0")

    # 1) 기존 테이블 제거 (FK 의존 순서)
    op.execute("DROP TABLE IF EXISTS `inbound_items`")
    op.execute("DROP TABLE IF EXISTS `inbounds`")
    op.execute("DROP TABLE IF EXISTS `products`")

    # 2) 물품 마스터 (item_code PK)
    op.execute("""
        CREATE TABLE `products` (
            `item_code` VARCHAR(50)  NOT NULL COMMENT '물품 코드',
            `name`      VARCHAR(100) NOT NULL COMMENT '물품명',
            `brand`     VARCHAR(50)  NOT NULL COMMENT '브랜드',
            `category`  VARCHAR(50)  NULL COMMENT '종류',
            `capacity`  VARCHAR(30)  NULL COMMENT '용량',
            PRIMARY KEY (`item_code`),
            KEY `idx_products_brand` (`brand`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 3) 발주
    op.execute("""
        CREATE TABLE `orders` (
            `order_id`   INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '발주 ID',
            `order_date` DATETIME     NOT NULL COMMENT '발주 일자',
            `status`     VARCHAR(20)  NOT NULL COMMENT 'PENDING, DELIVERED',
            PRIMARY KEY (`order_id`),
            KEY `idx_orders_status` (`status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 4) 발주 상세
    op.execute("""
        CREATE TABLE `order_items` (
            `order_item_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '발주 상세 ID',
            `order_id`     INT UNSIGNED NOT NULL COMMENT '발주 ID',
            `item_code`    VARCHAR(50)  NOT NULL COMMENT '주문 물품 코드',
            `expected_qty` INT UNSIGNED NOT NULL COMMENT '주문 수량',
            PRIMARY KEY (`order_item_id`),
            KEY `idx_order_items_order_id` (`order_id`),
            KEY `idx_order_items_item_code` (`item_code`),
            CONSTRAINT `fk_order_items_order`   FOREIGN KEY (`order_id`)   REFERENCES `orders`   (`order_id`)   ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT `fk_order_items_product` FOREIGN KEY (`item_code`) REFERENCES `products` (`item_code`) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 5) 입고 (입고번호 PK)
    op.execute("""
        CREATE TABLE `inbounds` (
            `inbound_id`   VARCHAR(50)  NOT NULL COMMENT '입고번호',
            `order_id`     INT UNSIGNED NOT NULL COMMENT '발주 ID',
            `inbound_date` DATETIME     NOT NULL COMMENT '입고 일시',
            `status`       VARCHAR(20)  NOT NULL COMMENT 'WAITING, PROCESSING, COMPLETED',
            PRIMARY KEY (`inbound_id`),
            KEY `idx_inbounds_order_id` (`order_id`),
            KEY `idx_inbounds_status` (`status`),
            CONSTRAINT `fk_inbounds_order` FOREIGN KEY (`order_id`) REFERENCES `orders` (`order_id`) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 6) 창고 재고 (processes보다 먼저: item_sorting_logs가 inventory 참조)
    op.execute("""
        CREATE TABLE `inventory` (
            `inventory_id`   INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '창고 ID',
            `inventory_name` VARCHAR(100) NOT NULL COMMENT '창고 이름',
            `current_qty`    INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '현재 재고 수량',
            `updated_at`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`inventory_id`),
            KEY `idx_inventory_name` (`inventory_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 7) 공정 작업
    op.execute("""
        CREATE TABLE `processes` (
            `process_id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '공정 작업 ID',
            `inbound_id` VARCHAR(50)  NOT NULL COMMENT '입고번호',
            `start_time` DATETIME     NOT NULL COMMENT '공정 시작 일시',
            `end_time`   DATETIME     NULL COMMENT '공정 종료 일시',
            `status`     VARCHAR(20)  NOT NULL COMMENT 'RUNNING, PAUSED, COMPLETED, ERROR',
            PRIMARY KEY (`process_id`),
            KEY `idx_processes_inbound_id` (`inbound_id`),
            KEY `idx_processes_status` (`status`),
            CONSTRAINT `fk_processes_inbound` FOREIGN KEY (`inbound_id`) REFERENCES `inbounds` (`inbound_id`) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 8) 물품 인식·분류 로그 (상자 단위)
    op.execute("""
        CREATE TABLE `item_sorting_logs` (
            `log_id`            INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '물품 인식 로그 ID',
            `process_id`        INT UNSIGNED NOT NULL COMMENT '공정 작업 ID',
            `inbound_id`        VARCHAR(50)  NOT NULL COMMENT '입고번호',
            `box_qr_code`       VARCHAR(255) NULL COMMENT '상자 부착 QR 정보',
            `item_code`         VARCHAR(50)  NULL COMMENT '인식된 물품 코드',
            `expiration_date`   DATE         NULL COMMENT '인식된 유통기한',
            `inventory_id`      INT UNSIGNED NULL COMMENT '분류 판정(창고)',
            `is_error`          TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '오류 여부',
            `timestamp`         DATETIME     NOT NULL COMMENT '인식 일시',
            PRIMARY KEY (`log_id`),
            KEY `idx_item_sorting_logs_process_id` (`process_id`),
            KEY `idx_item_sorting_logs_inbound_id` (`inbound_id`),
            KEY `idx_item_sorting_logs_timestamp` (`timestamp`),
            CONSTRAINT `fk_item_sorting_logs_process`   FOREIGN KEY (`process_id`)   REFERENCES `processes` (`process_id`)   ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT `fk_item_sorting_logs_inbound`  FOREIGN KEY (`inbound_id`)   REFERENCES `inbounds`   (`inbound_id`)   ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT `fk_item_sorting_logs_product`  FOREIGN KEY (`item_code`)    REFERENCES `products`   (`item_code`)    ON DELETE SET NULL ON UPDATE CASCADE,
            CONSTRAINT `fk_item_sorting_logs_inventory` FOREIGN KEY (`inventory_id`) REFERENCES `inventory`  (`inventory_id`) ON DELETE SET NULL ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 9) 공정 최종 결과 (process 1:1)
    op.execute("""
        CREATE TABLE `process_results` (
            `result_id`        INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '결과 로그 ID',
            `process_id`       INT UNSIGNED NOT NULL COMMENT '공정 작업 ID',
            `total_qty`        INT UNSIGNED NOT NULL COMMENT '총 처리 수량',
            `success_1l_qty`   INT UNSIGNED NOT NULL COMMENT '1L 정상 분류 수량',
            `success_2l_qty`   INT UNSIGNED NOT NULL COMMENT '2L 정상 분류 수량',
            `unclassified_qty` INT UNSIGNED NOT NULL COMMENT '미분류 수량',
            `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`result_id`),
            UNIQUE KEY `uk_process_results_process_id` (`process_id`),
            CONSTRAINT `fk_process_results_process` FOREIGN KEY (`process_id`) REFERENCES `processes` (`process_id`) ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 10) 시스템 알림/경고
    op.execute("""
        CREATE TABLE `alerts` (
            `alert_id`   INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '알림 ID',
            `process_id` INT UNSIGNED NOT NULL COMMENT '공정 작업 ID',
            `alert_type` VARCHAR(50)  NOT NULL COMMENT '미분류, 오류, 정지 등',
            `message`    TEXT         NULL COMMENT '경고 메시지',
            `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`alert_id`),
            KEY `idx_alerts_process_id` (`process_id`),
            KEY `idx_alerts_created_at` (`created_at`),
            CONSTRAINT `fk_alerts_process` FOREIGN KEY (`process_id`) REFERENCES `processes` (`process_id`) ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    op.execute("SET FOREIGN_KEY_CHECKS = 1")


def downgrade() -> None:
    op.execute("SET FOREIGN_KEY_CHECKS = 0")

    op.execute("DROP TABLE IF EXISTS `alerts`")
    op.execute("DROP TABLE IF EXISTS `process_results`")
    op.execute("DROP TABLE IF EXISTS `item_sorting_logs`")
    op.execute("DROP TABLE IF EXISTS `processes`")
    op.execute("DROP TABLE IF EXISTS `inventory`")
    op.execute("DROP TABLE IF EXISTS `inbounds`")
    op.execute("DROP TABLE IF EXISTS `order_items`")
    op.execute("DROP TABLE IF EXISTS `orders`")
    op.execute("DROP TABLE IF EXISTS `products`")

    # 004 스키마 복원 (기존 inbounds, inbound_items, 003 products)
    op.execute("""
        CREATE TABLE `products` (
            `product_id`           INT UNSIGNED NOT NULL AUTO_INCREMENT,
            `product_name`         VARCHAR(100) NOT NULL COMMENT '물품명',
            `brand`                VARCHAR(50)  NOT NULL COMMENT '브랜드',
            `shipping_destination` ENUM('국내', '해외') NOT NULL COMMENT '배송지',
            PRIMARY KEY (`product_id`),
            KEY `idx_products_brand` (`brand`),
            KEY `idx_products_shipping_destination` (`shipping_destination`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    op.execute("""
        CREATE TABLE `inbounds` (
            `inbound_id`                  INT UNSIGNED NOT NULL COMMENT '입고 id',
            `status`                      ENUM('등록됨', '분류중', '완료') NOT NULL DEFAULT '등록됨',
            `created_at`                  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `classification_completed_at` DATETIME    NULL,
            PRIMARY KEY (`inbound_id`),
            KEY `idx_inbounds_status` (`status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    op.execute("""
        CREATE TABLE `inbound_items` (
            `inbound_item_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
            `inbound_id`      INT UNSIGNED NOT NULL,
            `product_id`      INT UNSIGNED NOT NULL,
            `status`          ENUM('미분류', '분류완료', '출고됨') NOT NULL DEFAULT '미분류',
            `classified_at`   DATETIME    NULL,
            `warehouse`       ENUM('국내', '해외', '미분류') NULL,
            `outbound_at`     DATETIME    NULL,
            PRIMARY KEY (`inbound_item_id`),
            CONSTRAINT `fk_inbound_items_inbound`  FOREIGN KEY (`inbound_id`) REFERENCES `inbounds` (`inbound_id`) ON DELETE CASCADE,
            CONSTRAINT `fk_inbound_items_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`product_id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    op.execute("SET FOREIGN_KEY_CHECKS = 1")
