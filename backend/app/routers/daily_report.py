"""日报接口：每轮指标只从数据服务当前版本的已发布快照计算。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import ActionResult
from app.services.daily_report import daily_report_service

router = APIRouter(prefix="/api/daily_report", tags=["日报计算"])


@router.post("/run", response_model=ActionResult)
def run_round(
    service_code: str = Query(description="数据服务编号，如 API-METRIC"),
    round_label: str | None = Query(default=None, description="可选的本轮标签"),
) -> ActionResult:
    """触发一轮日报计算，记录实际使用的服务版本与指标金额。"""
    try:
        round_row = daily_report_service.run_round(service_code, round_label=round_label)
    except ValueError as exc:
        return ActionResult(ok=False, message=str(exc))
    return ActionResult(ok=round_row["ok"], message=round_row["message"], entry=round_row)


@router.get("/rounds")
def list_rounds(service_code: str | None = Query(default=None)) -> dict[str, object]:
    """查看历轮日报及其实际使用的服务版本。"""
    return {"items": daily_report_service.list_rounds(service_code)}
