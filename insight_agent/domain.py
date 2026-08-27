"""데이터 접근 계층.

dataset_1의 스타 스키마(차원 2 + 팩트 4)를 읽어, 품질/생산/시장/통합 에이전트가
공통으로 쓰는 조회·조인 함수를 제공한다. MCP 서버(mymcp/server.py)는 이 모듈의
함수만 호출한다 — 데이터 로직과 프로토콜 계층을 분리해두면 나중에 실제 MCP SDK로
전송 계층만 바꿔도 이 파일은 그대로 재사용할 수 있다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from insight_agent.config import DATASET_DIR

TABLE_FILES = {
    "dim_company_product": "dim_company_product.csv",
    "dim_equipment": "dim_equipment.csv",
    "fact_production_run": "fact_production_run.csv",
    "fact_equipment_sensor": "fact_equipment_sensor.csv",
    "fact_quality_defect": "fact_quality_defect.csv",
    "fact_market_sales": "fact_market_sales.csv",
}


@dataclass
class Tables:
    dim_company_product: pd.DataFrame
    dim_equipment: pd.DataFrame
    fact_production_run: pd.DataFrame
    fact_equipment_sensor: pd.DataFrame
    fact_quality_defect: pd.DataFrame
    fact_market_sales: pd.DataFrame


def load_tables(data_dir: Path | str = DATASET_DIR) -> Tables:
    data_dir = Path(data_dir)
    frames = {
        name: pd.read_csv(data_dir / filename, encoding="utf-8-sig")
        for name, filename in TABLE_FILES.items()
    }
    return Tables(**frames)


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list[dict] (numpy int64/float64를 안전하게 변환)."""
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", force_ascii=False))


def get_production_anomalies(
    tables: Tables,
    factory_code: Optional[str] = None,
    min_oee_pct: float = 90.0,
) -> pd.DataFrame:
    """OEE가 임계치 미만이거나 설비 센서 anomaly_flag가 발생한 생산 실행 목록."""
    runs = tables.fact_production_run
    sensor_anomaly_runs = set(
        tables.fact_equipment_sensor.loc[
            tables.fact_equipment_sensor["anomaly_flag"] == 1, "run_id"
        ]
    )
    mask = (runs["oee_pct"] < min_oee_pct) | runs["run_id"].isin(sensor_anomaly_runs)
    if factory_code:
        mask &= runs["factory_code"] == factory_code
    result = runs.loc[mask].copy()
    result["has_sensor_anomaly"] = result["run_id"].isin(sensor_anomaly_runs)
    return result.sort_values("oee_pct")


def get_quality_defects(
    tables: Tables,
    severity: Optional[str] = None,
    category: Optional[str] = None,
) -> pd.DataFrame:
    """불량 이력에 제품 카테고리를 조인해 필터링."""
    defects = tables.fact_quality_defect.merge(
        tables.dim_company_product[["product_id", "category", "company_name"]],
        on="product_id",
        how="left",
    )
    if severity:
        defects = defects[defects["severity"] == severity]
    if category:
        defects = defects[defects["category"] == category]
    return defects.sort_values("inspection_datetime")


def get_market_impact(
    tables: Tables,
    product_id: str,
    region: Optional[str] = None,
) -> pd.DataFrame:
    """제품 하나의 매출/점유율 추이."""
    sales = tables.fact_market_sales[tables.fact_market_sales["product_id"] == product_id]
    if region:
        sales = sales[sales["region"] == region]
    return sales.sort_values("sales_month")


def build_causal_report(tables: Tables, product_id: str) -> dict:
    """생산 이상 -> 품질 불량 -> 시장 성과를 product_id 기준으로 엮은 통합 리포트.

    이 함수가 이 프로젝트의 핵심 가치다: 4개 팩트 테이블이 product_id/run_id로
    이어져 있어야만 "이 불량이 저 매출 하락의 원인인가"를 한 번에 답할 수 있다.
    """
    product_rows = tables.dim_company_product[tables.dim_company_product["product_id"] == product_id]
    if product_rows.empty:
        raise ValueError(f"unknown product_id: {product_id}")
    product = product_rows.iloc[0]

    runs = tables.fact_production_run[tables.fact_production_run["product_id"] == product_id]

    anomalies = get_production_anomalies(tables)
    anomalies = anomalies[anomalies["product_id"] == product_id]

    defects = tables.fact_quality_defect[tables.fact_quality_defect["product_id"] == product_id]
    critical_defects = defects[defects["severity"] == "Critical"]

    market = get_market_impact(tables, product_id)
    market_share_trend = market[["sales_month", "region", "market_share_est_pct", "revenue_krw"]]

    critical_defect_types = (
        json.loads(critical_defects["defect_type"].value_counts().to_json(force_ascii=False))
        if not critical_defects.empty
        else {}
    )

    return {
        "product_id": product_id,
        "model_name": product["model_name"],
        "category": product["category"],
        "company_name": product["company_name"],
        "production_run_count": int(len(runs)),
        "anomaly_run_count": int(len(anomalies)),
        "defect_count": int(len(defects)),
        "critical_defect_count": int(len(critical_defects)),
        "critical_defect_types": critical_defect_types,
        "market_share_trend": df_to_records(market_share_trend),
        "latest_market_share_pct": (
            float(market_share_trend.iloc[-1]["market_share_est_pct"])
            if not market_share_trend.empty
            else None
        ),
    }


def check_source_consistency(tables: Tables, xlsx_path: Path) -> list[dict]:
    """CSV로 읽은 각 테이블이 번들 xlsx 시트와 행수가 일치하는지 검증하는 하네스 가드레일.

    dataset_1은 현재 CSV와 xlsx가 완전히 일치하지만, 실제 운영 데이터에서는
    소스가 갈라지는 게 흔하다 -- 이 검사가 실패하면 HITL로 넘겨야 할 신호다.
    """
    import openpyxl

    mismatches: list[dict] = []
    if not Path(xlsx_path).exists():
        return [{"table": "*", "issue": "xlsx_not_found", "path": str(xlsx_path)}]

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    for name in TABLE_FILES:
        if name not in wb.sheetnames:
            mismatches.append({"table": name, "issue": "sheet_missing"})
            continue
        ws = wb[name]
        xlsx_row_count = sum(1 for _ in ws.iter_rows(min_row=2))
        csv_row_count = len(getattr(tables, name))
        if xlsx_row_count != csv_row_count:
            mismatches.append({
                "table": name,
                "issue": "row_count_mismatch",
                "csv_rows": csv_row_count,
                "xlsx_rows": xlsx_row_count,
            })
    return mismatches
