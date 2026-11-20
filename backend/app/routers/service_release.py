"""数据服务发布管理接口：产物交付、就绪校验、版本发布、快照切换与版本化取数。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas import ActionResult
from app.services.service_release import ServiceReleaseError, manager

router = APIRouter(prefix="/api/service_release", tags=["数据服务发布"])


class ArtifactPayload(BaseModel):
    metric_code: str
    version: str
    payload: dict
    complete: bool | None = None


class ReleasePayload(BaseModel):
    service_code: str
    version: str
    metric_code: str
    entry_id: int | None = None


@router.post("/artifacts", response_model=ActionResult)
def deliver_artifact(body: ArtifactPayload) -> ActionResult:
    """聚合管道交付指标产物；不完整或迟到的产物只登记，不会被服务直接读取。"""
    try:
        artifact = manager.deliver_artifact(
            body.metric_code, body.version, body.payload, complete=body.complete)
    except ServiceReleaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    message = "聚合产物已交付并通过完整性校验" if artifact["complete"] else "聚合产物已登记但未通过完整性校验，暂不可发布"
    return ActionResult(ok=artifact["complete"], message=message, entry=artifact)


@router.get("/artifacts")
def list_artifacts(metric_code: str | None = Query(default=None)) -> dict[str, object]:
    """查看已交付的聚合产物及其完整性校验结果。"""
    return {"items": manager.list_artifacts(metric_code)}


@router.post("/releases", response_model=ActionResult)
def submit_release(body: ReleasePayload) -> ActionResult:
    """提交服务版本发布：校验产物就绪后才固化快照并切换当前版本。"""
    try:
        view = manager.submit_release(
            body.service_code, body.version, body.metric_code, entry_id=body.entry_id)
    except ServiceReleaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if view["lifecycle"] == "已发布":
        message = f"版本 {body.version} 产物就绪，已发布并切换为当前服务版本"
    else:
        message = f"版本 {body.version} 已提交发布但产物未就绪，继续保留旧版本对外服务"
    return ActionResult(ok=True, message=message, entry=view)


@router.post("/check-readiness", response_model=ActionResult)
def check_readiness(service_code: str | None = Query(default=None)) -> ActionResult:
    """服务接口校验生效状态：把产物迟到后已就绪的待发布版本切换上线。"""
    promoted = manager.check_readiness(service_code)
    if promoted:
        message = f"已切换 {len(promoted)} 个就绪版本：" + "、".join(v["version"] for v in promoted)
    else:
        message = "暂无新就绪版本，当前服务版本保持不变"
    return ActionResult(ok=True, message=message, entry={"promoted": promoted})


@router.get("/releases")
def list_releases(service_code: str | None = Query(default=None)) -> dict[str, object]:
    """服务版本登记列表：生命周期、就绪状态、当前版本与访问身份。"""
    return {"items": manager.list_versions(service_code)}


@router.post("/services/{service_code}/versions/{version}/offline", response_model=ActionResult)
def offline_version(service_code: str, version: str) -> ActionResult:
    """下线服务版本：不再作为当前服务，快照保留为历史可查。"""
    try:
        view = manager.offline_version(service_code, version)
    except ServiceReleaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ActionResult(ok=True, message=f"版本 {version} 已下线，不再作为当前服务提供", entry=view)


@router.get("/services/{service_code}/current")
def current_snapshot(service_code: str) -> dict[str, object]:
    """读取端取数：当前、已发布、就绪版本的版本化指标快照。"""
    view = manager.current_snapshot(service_code)
    if view is None:
        raise HTTPException(status_code=409, detail=f"服务 {service_code} 当前没有可读的已发布版本快照")
    return view


@router.get("/services/{service_code}/versions/{version}")
def version_snapshot(service_code: str, version: str) -> dict[str, object]:
    """按版本号查询历史结果，返回内容会标明当前版本、历史版本或已下线版本。"""
    try:
        return manager.version_snapshot(service_code, version)
    except ServiceReleaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
