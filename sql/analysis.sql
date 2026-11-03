-- 전국 시도별 이용량
SELECT sido_name, SUM(usage_count) AS total_usage
FROM transport_usage
GROUP BY sido_name
ORDER BY total_usage DESC;

-- 부산 구·군별 이용량
SELECT sigungu_name, SUM(usage_count) AS total_usage
FROM transport_usage
WHERE sido_name = '부산광역시'
  AND sigungu_code != 26000
GROUP BY sigungu_name
ORDER BY total_usage DESC;

-- 부산 구·군별 교통수단 구성
SELECT sigungu_name, transport_type, SUM(usage_count) AS total_usage
FROM transport_usage
WHERE sido_name = '부산광역시'
  AND sigungu_code != 26000
GROUP BY sigungu_name, transport_type
ORDER BY sigungu_name, total_usage DESC;

-- 전국 교통수단별 이용량
SELECT transport_type, SUM(usage_count) AS total_usage
FROM transport_usage
GROUP BY transport_type
ORDER BY total_usage DESC;

-- 전국 월별 이용량
SELECT strftime('%Y-%m', operation_date) AS month,
       SUM(usage_count) AS total_usage
FROM transport_usage
GROUP BY month
ORDER BY month;

-- 시군구별 이용량 상위 20개
SELECT sido_name, sigungu_name, SUM(usage_count) AS total_usage
FROM transport_usage
WHERE sigungu_code NOT IN (11000, 26000, 27000, 28000, 29000, 30000, 31000,
                           36000, 41000, 43000, 44000, 46000, 47000, 48000,
                           50000, 51000, 52000)
GROUP BY sido_name, sigungu_name
ORDER BY total_usage DESC
LIMIT 20;

-- 부산 시간대별 이용량
SELECT hour, SUM(usage_count) AS total_usage
FROM transport_hourly
WHERE sido_code = 26
  AND sigungu_code != 26000
GROUP BY hour
ORDER BY hour;

-- 시도별 총 이용인원
SELECT sido_name, SUM(person_count) AS total_person_count
FROM transport_person
GROUP BY sido_name
ORDER BY total_person_count DESC;
