"""GA4 Sample Dataset 5개 쿼리 자동 실행 + CSV 저장."""
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # /41r/
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(_PROJECT_ROOT / 'secrets' / 'gcp-bigquery.json')

from google.cloud import bigquery
from google.api_core.exceptions import Forbidden

import json
with open(os.environ['GOOGLE_APPLICATION_CREDENTIALS']) as f:
    PROJECT = json.load(f)['project_id']

OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

QUERIES = {
    "q1_funnel_drop": """
        SELECT
          event_name,
          COUNT(DISTINCT user_pseudo_id) AS users,
          COUNT(*) AS event_count
        FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
        WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
          AND event_name IN ('session_start', 'page_view', 'view_item',
                             'add_to_cart', 'begin_checkout', 'purchase')
        GROUP BY event_name
        ORDER BY users DESC
    """,

    "q2_device_metrics": """
        SELECT
          device.category AS device,
          COUNT(DISTINCT user_pseudo_id) AS users,
          COUNTIF(event_name = 'page_view') AS pageviews,
          COUNTIF(event_name = 'add_to_cart') AS add_to_carts,
          COUNTIF(event_name = 'purchase') AS purchases,
          ROUND(SAFE_DIVIDE(COUNTIF(event_name = 'purchase'),
                            COUNT(DISTINCT user_pseudo_id)) * 100, 3) AS conversion_pct
        FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
        WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
        GROUP BY device
        ORDER BY users DESC
    """,

    "q3_country_conversion": """
        SELECT
          geo.country,
          COUNT(DISTINCT user_pseudo_id) AS users,
          COUNTIF(event_name = 'purchase') AS purchases,
          ROUND(SAFE_DIVIDE(COUNTIF(event_name = 'purchase'),
                            COUNT(DISTINCT user_pseudo_id)) * 100, 3) AS conversion_pct
        FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
        WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
        GROUP BY country
        HAVING users >= 100
        ORDER BY users DESC
        LIMIT 30
    """,

    "q4_session_metrics": """
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
        WHERE session_id IS NOT NULL
        GROUP BY device
    """,

    "q5_hour_conversion": """
        SELECT
          EXTRACT(HOUR FROM TIMESTAMP_MICROS(event_timestamp)) AS hour_utc,
          COUNT(DISTINCT user_pseudo_id) AS users,
          COUNTIF(event_name = 'purchase') AS purchases,
          ROUND(SAFE_DIVIDE(COUNTIF(event_name = 'purchase'),
                            COUNT(DISTINCT user_pseudo_id)) * 100, 3) AS conversion_pct
        FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
        WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
        GROUP BY hour_utc
        ORDER BY hour_utc
    """,
}


def main():
    client = bigquery.Client(project=PROJECT)
    print(f"BigQuery client: {PROJECT}\n")

    summary = {}
    for name, sql in QUERIES.items():
        out_csv = OUT_DIR / f"{name}.csv"
        print(f"→ {name} ...", end=" ", flush=True)
        try:
            t0 = time.time()
            df = client.query(sql).to_dataframe()
            df.to_csv(out_csv, index=False)
            elapsed = time.time() - t0
            summary[name] = {"rows": len(df), "elapsed_sec": round(elapsed, 1), "status": "ok"}
            print(f"✓ {len(df):,} rows ({elapsed:.1f}s)")
        except Forbidden as e:
            summary[name] = {"status": "forbidden", "error": str(e)[:200]}
            print(f"✗ Forbidden — API/권한 확인")
        except Exception as e:
            summary[name] = {"status": "error", "error": str(e)[:200]}
            print(f"✗ Error: {str(e)[:100]}")

    summary_path = OUT_DIR / "_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n결과 요약: {summary_path}")
    return summary


if __name__ == "__main__":
    main()
