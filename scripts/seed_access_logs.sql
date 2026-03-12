-- 출입 로그(access_logs) 임의 데이터 추가
-- 실행 전 workers 테이블에 최소 1명의 작업자가 있어야 합니다.
-- 사용: mysql -u user -p database < scripts/seed_access_logs.sql
-- 또는 Docker: docker exec -i soy-db-mysql mysql -u root -p soy < scripts/seed_access_logs.sql

INSERT INTO `access_logs` (`worker_id`, `checked_at`, `direction`)
SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 5 HOUR), 'in'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 4 HOUR), 'out'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 3 HOUR), 'in'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 2 HOUR), 'out'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 1 HOUR), 'in'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 30 MINUTE), 'out'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 1 DAY), 'in'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_ADD(DATE_SUB(NOW(), INTERVAL 1 DAY), INTERVAL 8 HOUR), 'out'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_SUB(NOW(), INTERVAL 2 DAY), 'in'
UNION ALL SELECT (SELECT worker_id FROM workers ORDER BY worker_id LIMIT 1), DATE_ADD(DATE_SUB(NOW(), INTERVAL 2 DAY), INTERVAL 9 HOUR), 'out';
