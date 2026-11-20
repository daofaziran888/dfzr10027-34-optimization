"""数据管道接口：触发跨模块计算并查询产物。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import ActionResult
from app.services.pipeline_orchestrator import (
    deliver_metric_artifact,
    list_pipeline_results,
    run_all_pipelines,
    run_attribution_compare_pipeline,
    run_cohort_extract_pipeline,
    run_cube_pipeline,
    run_experiment_stat_pipeline,
    run_forecast_pipeline,
    run_metric_agg_pipeline,
    run_quality_scan,
)

router = APIRouter(prefix="/api/pipeline", tags=["数据管道"])


@router.post("/run-all", response_model=ActionResult)
def trigger_all() -> ActionResult:
    """顺序执行全部 7 条跨模块数据管道。"""
    summary = run_all_pipelines()
    return ActionResult(
        ok=True,
        message="全部管道已执行",
        entry={"pipelines": list(summary.keys()), "count": len(summary)},
    )


@router.post("/metric-agg", response_model=ActionResult)
def trigger_metric_agg(
    metric_code: str | None = Query(default=None, description="指标编号，如 METR-GMV"),
    version: str | None = Query(default=None, description="可选：按版本登记聚合产物，供服务发布就绪校验"),
) -> ActionResult:
    result = run_metric_agg_pipeline(metric_code, version)
    message = "指标聚合管道已执行"
    if version:
        message += f"，产物已按版本 {version} 登记"
    return ActionResult(ok=True, message=message, entry=result)


@router.post("/metric-artifact", response_model=ActionResult)
def deliver_artifact(
    metric_code: str = Query(description="指标编号，如 METR-GMV"),
    version: str = Query(description="服务版本号，如 v2.0"),
    payload: dict | None = None,
    complete: bool | None = Query(default=None, description="管道是否已交付完整产物"),
) -> ActionResult:
    """显式投递某版本的聚合产物（含迟到/不完整场景），交由发布管理器校验。"""
    from fastapi import HTTPException

    from app.services.service_release import ServiceReleaseError, validate_artifact_payload
    body = payload or {}
    errors = validate_artifact_payload(body)
    try:
        artifact = deliver_metric_artifact(metric_code, version, body, complete=complete)
    except ServiceReleaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if artifact["complete"]:
        message = f"版本 {version} 聚合产物完整，已进入就绪台账"
    else:
        message = f"版本 {version} 聚合产物未就绪：{'、'.join(artifact['validation_errors'])}"
    return ActionResult(ok=artifact["complete"], message=message, entry=artifact)


@router.post("/forecast", response_model=ActionResult)
def trigger_forecast(
    horizon: int = Query(default=7, ge=1, le=30, description="预测天数"),
) -> ActionResult:
    result = run_forecast_pipeline(horizon)
    return ActionResult(ok=True, message="预测管道已执行", entry=result)


@router.post("/cube", response_model=ActionResult)
def trigger_cube(
    dim_codes: list[str] | None = Query(default=None, description="维度编号列表"),
) -> ActionResult:
    result = run_cube_pipeline(dim_codes)
    return ActionResult(ok=True, message="立方体构建管道已执行", entry=result)


@router.post("/cohort-extract", response_model=ActionResult)
def trigger_cohort_extract() -> ActionResult:
    result = run_cohort_extract_pipeline()
    return ActionResult(ok=True, message="分群提取管道已执行", entry=result)


@router.post("/experiment-stat", response_model=ActionResult)
def trigger_experiment_stat(
    experiment_code: str | None = Query(default=None, description="实验编号"),
) -> ActionResult:
    result = run_experiment_stat_pipeline(experiment_code)
    return ActionResult(ok=True, message="实验统计管道已执行", entry=result)


@router.post("/quality-scan", response_model=ActionResult)
def trigger_quality_scan() -> ActionResult:
    result = run_quality_scan()
    return ActionResult(ok=True, message="质量扫描管道已执行", entry=result)


@router.post("/attribution-compare", response_model=ActionResult)
def trigger_attribution_compare(
    link_code: str | None = Query(default=None, description="链路编号"),
) -> ActionResult:
    result = run_attribution_compare_pipeline(link_code)
    return ActionResult(ok=True, message="归因对比管道已执行", entry=result)


@router.get("/results")
def get_results() -> dict[str, object]:
    """查询全部管道产物。"""
    return {"items": list_pipeline_results()}
