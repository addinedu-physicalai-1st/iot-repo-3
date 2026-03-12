-- ITEM_SORTING_LOGS 테이블 테스트 데이터 삽입 스크립트 (공정 1, 2, 3 반영 버전)

-- 1. 필수 선행 데이터 확인 및 삽입 (발주 및 공정 1, 2, 3)
INSERT INTO `orders` (`order_id`, `order_date`, `status`)
SELECT 1, NOW(), 'DELIVERED'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `orders` WHERE `order_id` = 1);

-- 공정 1 (최근 작업용)
INSERT INTO `processes` (`process_id`, `order_id`, `status`, `total_qty`)
SELECT 1, 1, 'COMPLETED', 3
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `processes` WHERE `process_id` = 1);

-- 공정 2 (어제 작업용)
INSERT INTO `processes` (`process_id`, `order_id`, `status`, `total_qty`)
SELECT 2, 1, 'COMPLETED', 2
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `processes` WHERE `process_id` = 2);

-- 공정 3 (이전 작업용)
INSERT INTO `processes` (`process_id`, `order_id`, `status`, `total_qty`)
SELECT 3, 1, 'COMPLETED', 3
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `processes` WHERE `process_id` = 3);

-- 2. ITEM_SORTING_LOGS 데이터 삽입
-- 컬럼 순서: process_id, box_qr_code, item_code, expiration_date, inventory_id, is_error, timestamp

INSERT INTO `item_sorting_logs` 
(`process_id`, `box_qr_code`, `item_code`, `expiration_date`, `inventory_id`, `is_error`, `timestamp`)
VALUES
-- [공정 1] 오늘 데이터 (2026-03-04)
(1, 'BOX-QR-001', 'sampyo_jin_1l', '2027-03-04', NULL, 0, NOW()),
(1, 'BOX-QR-002', 'mongo_jin_1l',  '2027-03-04', NULL, 0, DATE_SUB(NOW(), INTERVAL 1 HOUR)),
(1, 'BOX-QR-003', 'sampyo_guk_1l', '2027-03-04', NULL, 1, DATE_SUB(NOW(), INTERVAL 2 HOUR)),

-- [공정 2] 어제 데이터 (2026-03-03)
(2, 'BOX-QR-004', 'sampyo_jin_1l', '2027-03-03', NULL, 0, DATE_SUB(NOW(), INTERVAL 1 DAY)),
(2, 'BOX-QR-005', 'mongo_jin_1l',  '2027-03-03', NULL, 0, DATE_SUB(DATE_SUB(NOW(), INTERVAL 1 DAY), INTERVAL 2 HOUR)),

-- [공정 3] 이전 데이터 (3일 전 ~ 10일 전)
(3, 'BOX-QR-006', 'sampyo_jin_1l', '2027-03-01', NULL, 0, DATE_SUB(NOW(), INTERVAL 3 DAY)),
(3, 'BOX-QR-007', 'mongo_jin_1l',  '2027-02-25', NULL, 0, DATE_SUB(NOW(), INTERVAL 7 DAY)),
(3, 'BOX-QR-008', 'sampyo_guk_1l', '2027-02-22', NULL, 0, DATE_SUB(NOW(), INTERVAL 10 DAY));

-- 3. 확인 쿼리
SELECT l.log_id, l.process_id, p.name as product_name, l.box_qr_code, l.is_error, l.timestamp 
FROM item_sorting_logs l
LEFT JOIN products p ON l.item_code = p.item_code
ORDER BY l.timestamp DESC;
