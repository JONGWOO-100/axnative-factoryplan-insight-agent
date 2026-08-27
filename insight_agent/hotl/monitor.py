"""HOTL 모니터 -- 리전x카테고리 시장점유율 추이를 상시 스냅샷으로 남기고,
전분기 대비 급락 구간에만 사람이 확인하도록 알림 플래그를 세운다.

HITL과 달리 여기엔 승인 대기가 없다 -- 항상 계산되고 항상 노출되며,
사람은 필요할 때만(alert가 뜰 때만) 개입한다.
"""
from __future__ import annotations

import json

import pandas as pd

from insight_agent import domain
from insight_agent.config import MARKET_SHARE_DROP_ALERT_PP, OUTPUTS_DIR


def build_snapshot(tables: domain.Tables) -> dict:
    sales = tables.fact_market_sales
    grouped = (
        sales.groupby(["region", "category", "quarter"], as_index=False)["market_share_est_pct"]
        .mean()
        .sort_values(["region", "category", "quarter"])
        .reset_index(drop=True)
    )

    alerts: list[dict] = []
    for (region, category), group in grouped.groupby(["region", "category"]):
        group = group.sort_values("quarter").reset_index(drop=True)
        group["delta_pp"] = group["market_share_est_pct"].diff()
        for _, row in group.iterrows():
            if pd.notna(row["delta_pp"]) and row["delta_pp"] <= MARKET_SHARE_DROP_ALERT_PP:
                alerts.append({
                    "region": region,
                    "category": category,
                    "quarter": row["quarter"],
                    "delta_pp": round(float(row["delta_pp"]), 2),
                })

    snapshot = {
        "trend": domain.df_to_records(grouped),
        "alerts": alerts,
        "alert_threshold_pp": MARKET_SHARE_DROP_ALERT_PP,
    }
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / "hotl_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return snapshot
