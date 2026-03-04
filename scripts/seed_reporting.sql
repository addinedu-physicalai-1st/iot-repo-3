-- 창고 재고(inventory) 리포트 시각화용 시드 데이터
-- 창고 ID 1=1L, 2=2L, 3=미분류, 수량은 실행 시점마다 랜덤
-- 사용: mysql -u soy -psoy soydb < scripts/seed_reporting.sql
-- Docker: docker compose exec mysql mysql -usoy -psoy soydb < scripts/seed_reporting.sql

-- inventory 시드 (기존 행 있으면 current_qty, updated_at 갱신)
INSERT INTO `inventory` (`inventory_id`, `inventory_name`, `current_qty`, `updated_at`)
VALUES
  (1, '1L',      FLOOR(15 + RAND() * 86), NOW()),   -- 15~100
  (2, '2L',      FLOOR(10 + RAND() * 71), NOW()),   -- 10~80
  (3, '미분류',  FLOOR(0 + RAND() * 21), NOW())     -- 0~20
ON DUPLICATE KEY UPDATE
  current_qty = VALUES(current_qty),
  updated_at  = VALUES(updated_at);

-- 확인 쿼리 (창고별 재고 수량 시각화용)
SELECT inventory_id, inventory_name, current_qty, updated_at
FROM inventory
ORDER BY inventory_id;
