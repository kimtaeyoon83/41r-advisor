# GA4 Sample Dataset — 추출 가이드 (사용자 실행)

> **데이터셋**: `bigquery-public-data.ga4_obfuscated_sample_ecommerce`
> **출처**: Google Merchandise Store (2020-11-01 ~ 2021-01-31)
> **라이선스**: Google Cloud Public Datasets (상업 분석 가능)
> **목적**: 페르소나 시뮬의 절대 수치 grounding (실제 e-commerce 세그먼트별 전환율 baseline)

---

## 사전 준비 (사용자가 한 번만)

1. GCP 계정 생성 (gmail로 무료): https://console.cloud.google.com
2. BigQuery sandbox 활성화 (무료 티어 1TB/월)
3. `bigquery-public-data` 프로젝트는 자동 추가됨
4. 또는 gcloud CLI:
   ```bash
   curl https://sdk.cloud.google.com | bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

## 추출 SQL 쿼리 (5가지)

### 1. Device × User Type별 전환율
```sql
SELECT
  device.category AS device,
  CASE WHEN total_users.is_first_visit = 0 THEN 'returning' ELSE 'new' END AS user_type,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNTIF(event_name = 'purchase') AS purchases,
  ROUND(SAFE_DIVIDE(COUNTIF(event_name = 'purchase'),
                    COUNT(DISTINCT user_pseudo_id)) * 100, 3) AS conversion_pct
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
LEFT JOIN UNNEST([STRUCT(
  IF(MIN(IF(event_name='first_visit', event_timestamp, NULL)) OVER (PARTITION BY user_pseudo_id) IS NOT NULL, 0, 1) AS is_first_visit
)]) AS total_users
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
GROUP BY device, user_type
ORDER BY users DESC
```

### 2. Country × Device 세그먼트별 전환율
```sql
SELECT
  geo.country,
  device.category AS device,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNTIF(event_name = 'purchase') AS purchases,
  ROUND(SAFE_DIVIDE(COUNTIF(event_name = 'purchase'),
                    COUNT(DISTINCT user_pseudo_id)) * 100, 3) AS conversion_pct
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
GROUP BY country, device
HAVING users >= 100
ORDER BY users DESC
LIMIT 50
```

### 3. 세션당 평균 페이지뷰 + 이탈률
```sql
WITH sessions AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
    device.category AS device,
    COUNTIF(event_name = 'page_view') AS page_views,
    COUNTIF(event_name = 'purchase') AS purchased
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
  GROUP BY user_pseudo_id, session_id, device
)
SELECT
  device,
  COUNT(*) AS sessions,
  ROUND(AVG(page_views), 2) AS avg_pageviews,
  ROUND(SUM(IF(page_views = 1, 1, 0)) / COUNT(*) * 100, 2) AS bounce_rate_pct,
  ROUND(SUM(IF(purchased > 0, 1, 0)) / COUNT(*) * 100, 3) AS conversion_pct
FROM sessions
GROUP BY device
```

### 4. 이탈 단계 (어디서 떠나는지)
```sql
SELECT
  event_name,
  COUNT(DISTINCT user_pseudo_id) AS users,
  ROUND(COUNT(DISTINCT user_pseudo_id) /
        FIRST_VALUE(COUNT(DISTINCT user_pseudo_id)) OVER (
          ORDER BY (CASE event_name
                    WHEN 'session_start' THEN 1
                    WHEN 'page_view' THEN 2
                    WHEN 'view_item' THEN 3
                    WHEN 'add_to_cart' THEN 4
                    WHEN 'begin_checkout' THEN 5
                    WHEN 'purchase' THEN 6
                    ELSE 99 END)
        ) * 100, 2) AS pct_of_total
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
  AND event_name IN ('session_start', 'page_view', 'view_item',
                     'add_to_cart', 'begin_checkout', 'purchase')
GROUP BY event_name
ORDER BY 1
```

### 5. 시간대별 전환율 (페르소나 timing 검증용)
```sql
SELECT
  EXTRACT(HOUR FROM TIMESTAMP_MICROS(event_timestamp)) AS hour,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNTIF(event_name = 'purchase') AS purchases,
  ROUND(SAFE_DIVIDE(COUNTIF(event_name = 'purchase'),
                    COUNT(DISTINCT user_pseudo_id)) * 100, 3) AS conversion_pct
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
GROUP BY hour
ORDER BY hour
```

## 결과 → 41R 통합

위 5개 쿼리 실행 후 결과를 다음 파일로 저장:

```
experiments/datasets/ga4_sample/
  ├── q1_device_usertype.csv
  ├── q2_country_device.csv
  ├── q3_session_metrics.csv
  ├── q4_funnel_drop.csv
  ├── q5_hour_conversion.csv
  └── README.md (각 쿼리 실행 일시, 행 수)
```

이걸 41R에 통합:

1. **`modules/benchmark_loader.py` 신설** — GA4 baseline 로드
2. **`cohort_report.py` 확장** — 우리 시뮬 결과 옆에 GA4 baseline 동시 표시
3. **disclaimer**: "우리 시뮬은 'shopping intent 있음' 가정 코호트, 실제 GA 평균 전환율은 X%"

## 예상 결과 (Google Merchandise Store 알려진 수치)

- 전체 평균 전환율: **~1.4%** (e-commerce 평균 2~3%보다 낮음 — 무료 굿즈 사이트 특성)
- Mobile vs Desktop: Desktop 전환율 더 높음 (2~3배)
- 신규 vs 재방문: 재방문 5~10배 높은 전환율
- 미국 vs 그 외 국가: 큰 격차

이 수치들이 현재 41R 시뮬 결과 ("29CM 30% 전환" 등)와 절대 수치 비교 시 reality check.

## 비용

- BigQuery sandbox 무료 (1TB/월)
- 위 5개 쿼리 합쳐서 약 50MB 처리 예상 → **무료 한도 안**

## 다음 액션 (사용자)

1. GCP 계정 활성화 → BigQuery 콘솔 접속
2. 위 5개 SQL 복사 → 실행 → CSV 다운로드
3. CSV 5개를 `experiments/datasets/ga4_sample/` 에 업로드
4. 알려주시면 `benchmark_loader.py` 통합 작업
