"""日报指标计算：只使用数据服务当前版本的已发布快照取数。

每一轮日报都先触发一次服务生效状态校验（处理聚合产物迟到后的版本切换），
随后只读取当前版本快照。若服务没有任何当前可读版本，则本轮日报无法产出指标，
显式返回阻塞原因，而不是回退到草稿/待发布产物或自行重算，保证
「服务只对外提供用同一口径完整计算的数据」。
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from app.services.service_release import manager
from app.store import store

DAILY_TABLE = "_daily_report_rounds"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DailyReportService:
    def run_round(self, service_code: str, *, round_label: str | None = None) -> dict[str, Any]:
        """计算一轮日报指标，并固化当轮实际使用的服务版本与金额。"""
        if not service_code:
            raise ValueError("生成日报必须指定数据服务编号")

        # 聚合管道可能在本轮之前刚交付完产物：先校验生效状态再取数
        promoted = manager.check_readiness(service_code)
        current = manager.current_snapshot(service_code)

        label = round_label or datetime.now().strftime("ROUND-%Y%m%d%H%M%S")
        round_row: dict[str, Any] = {
            "round_label": label,
            "service_code": service_code,
            "generated_at": _now(),
            "promoted_versions": [item["version"] for item in promoted],
        }

        if current is None or not current.get("snapshot"):
            pending = manager.list_versions(service_code)
            waiting = [v["version"] for v in pending if v["lifecycle"] == "待发布"]
            round_row.update({
                "status": "阻塞",
                "ok": False,
                "message": "服务当前没有可读的已发布版本快照，日报本轮不产出指标",
                "used_version": None,
                "metric_value": None,
                "waiting_versions": waiting,
            })
        else:
            snapshot = current["snapshot"]
            round_row.update({
                "status": "已生成",
                "ok": True,
                "message": "日报已按当前服务版本快照计算",
                "used_version": current["version"],
                "metric_code": snapshot.get("metric_code"),
                "metric_value": snapshot.get("value"),
                "unit": snapshot.get("unit"),
                "point_count": snapshot.get("point_count"),
                "snapshot_at": snapshot.get("snapshot_at"),
                "waiting_versions": current.get("pending_versions", []),
            })

        store.rows(DAILY_TABLE).append(round_row)
        return copy.deepcopy(round_row)

    def list_rounds(self, service_code: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(DAILY_TABLE)
        if service_code is not None:
            rows = [row for row in rows if row.get("service_code") == service_code]
        return [copy.deepcopy(row) for row in rows]


daily_report_service = DailyReportService()
