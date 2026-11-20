"""数据服务发布管理：以聚合产物就绪校验驱动版本化发布与数据快照。

发布状态与聚合产物就绪状态在旧流程里可能互相脱节：新版本提交发布后产物迟到，
登记状态却已经显示「已发布」，读取端也拿不到与登记一致的数据。本模块把发布过程
收敛成一条可校验的流转：

1. 聚合管道交付指标产物时登记到 ``_agg_artifacts``，完整性校验不过的产物不会被视为就绪。
2. 服务版本提交发布时先做产物就绪校验：
   - 产物完整且同口径 -> 固化为该版本的「已发布服务数据快照」并切换为当前版本；
   - 产物缺失或不完整 -> 版本停在「待发布/待产物」，不接管读取流量，旧当前版本继续服务。
3. ``check_readiness`` 供服务接口在产物迟到后重新校验生效状态，完成快照切换。
4. 下线只改版本登记：下线版本不再作为当前服务，其快照仍可按版本号做历史查询，
   并明确标注「当前版本 / 历史版本 / 已下线版本」。

服务只对外提供用同一口径完整计算的数据：快照一旦随发布固化，不会被后续迟到的
同版本产物覆盖；口径切换必须走新版本发布。
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from app.store import store

REGISTRY_TABLE = "_service_versions"
ARTIFACT_TABLE = "_agg_artifacts"

# 版本生命周期
LIFECYCLE_WAITING = "待发布"
LIFECYCLE_PUBLISHED = "已发布"
LIFECYCLE_OFFLINE = "已下线"
# 产物就绪状态
READY_PENDING = "待产物"
READY_READY = "就绪"

# 读取访问身份
ACCESS_CURRENT = "当前版本"
ACCESS_HISTORY = "历史版本"
ACCESS_OFFLINE = "已下线版本"

REQUIRED_PAYLOAD_KEYS = ("metric_code", "value", "unit", "point_count")


class ServiceReleaseError(ValueError):
    """发布流转不满足规则时抛出，消息可直接回给运营侧。"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validate_artifact_payload(payload: Any) -> list[str]:
    """校验指标产物是否按同一口径完整计算。

    完整的判定：结构为字典、必备字段齐全、指标值可计算、数据点数大于 0。
    返回错误说明列表；空列表代表校验通过、产物就绪。
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["聚合产物必须是结构化指标结果"]
    for key in REQUIRED_PAYLOAD_KEYS:
        if key not in payload or payload.get(key) is None:
            errors.append(f"聚合产物缺少必备字段「{key}」")
    if "point_count" in payload and payload.get("point_count") is not None:
        try:
            if int(payload["point_count"]) <= 0:
                errors.append("聚合产物数据点数为 0，未完成完整计算")
        except (TypeError, ValueError):
            errors.append("聚合产物数据点数不是有效整数")
    if "value" in payload and payload.get("value") is not None:
        try:
            float(payload["value"])
        except (TypeError, ValueError):
            errors.append("聚合产物指标值不是可计算的数值")
    return errors


class ServiceReleaseManager:
    """封装服务版本登记、产物就绪校验、快照切换与版本化取数。"""

    # ------------------------------------------------------------------
    # 存储辅助
    # ------------------------------------------------------------------
    def _registry(self) -> list[dict[str, Any]]:
        return store.rows(REGISTRY_TABLE)

    def _artifacts(self) -> list[dict[str, Any]]:
        return store.rows(ARTIFACT_TABLE)

    def _find_version(self, service_code: str, version: str) -> dict[str, Any] | None:
        for row in self._registry():
            if row.get("service_code") == service_code and row.get("version") == version:
                return row
        return None

    def _find_artifact(self, metric_code: str, version: str) -> dict[str, Any] | None:
        for row in self._artifacts():
            if row.get("metric_code") == metric_code and row.get("version") == version:
                return row
        return None

    def _current_row(self, service_code: str) -> dict[str, Any] | None:
        for row in self._registry():
            if row.get("service_code") == service_code and row.get("is_current"):
                return row
        return None

    # ------------------------------------------------------------------
    # 聚合产物交付（可能迟到，可能不完整）
    # ------------------------------------------------------------------
    def deliver_artifact(
        self,
        metric_code: str,
        version: str,
        payload: dict[str, Any],
        *,
        complete: bool | None = None,
    ) -> dict[str, Any]:
        """登记一次聚合管道产物交付。

        ``complete`` 显式声明管道是否交付完毕；缺省时按产物内容校验结果推断。
        同指标同版本重复交付按幂等覆盖处理，但已经发布固化的快照不受影响。
        """
        if not metric_code or not version:
            raise ServiceReleaseError("交付聚合产物必须提供指标编号与版本号")
        errors = validate_artifact_payload(payload)
        is_complete = (not errors) if complete is None else bool(complete) and not errors
        artifact = self._find_artifact(metric_code, version)
        if artifact is None:
            artifact = {
                "metric_code": metric_code,
                "version": version,
                "created_at": _now(),
            }
            self._artifacts().append(artifact)
        artifact.update({
            "payload": copy.deepcopy(payload),
            "complete": is_complete,
            "validation_errors": errors,
            "updated_at": _now(),
        })
        return copy.deepcopy(artifact)

    def list_artifacts(self, metric_code: str | None = None) -> list[dict[str, Any]]:
        rows = self._artifacts()
        if metric_code:
            rows = [row for row in rows if row.get("metric_code") == metric_code]
        return [copy.deepcopy(row) for row in rows]

    # ------------------------------------------------------------------
    # 版本发布流转
    # ------------------------------------------------------------------
    def submit_release(
        self,
        service_code: str,
        version: str,
        metric_code: str,
        *,
        entry_id: int | None = None,
    ) -> dict[str, Any]:
        """登记一次服务版本发布申请并立即做产物就绪校验。

        产物就绪则固化快照、切换当前版本；否则版本保持「待发布/待产物」，
        旧当前版本继续承担读取流量。
        """
        if not service_code or not version or not metric_code:
            raise ServiceReleaseError("提交发布必须提供服务编号、版本号与指标编号")
        if self._find_version(service_code, version) is not None:
            raise ServiceReleaseError(f"服务 {service_code} 的版本 {version} 已登记发布，不能重复提交")

        row: dict[str, Any] = {
            "service_code": service_code,
            "version": version,
            "metric_code": metric_code,
            "entry_id": entry_id,
            "lifecycle": LIFECYCLE_WAITING,
            "readiness": READY_PENDING,
            "is_current": False,
            "snapshot": None,
            "snapshot_at": None,
            "created_at": _now(),
            "published_at": None,
            "offline_at": None,
            "ready_errors": [],
        }
        self._registry().append(row)
        self._sync_entry(row)
        # 立即校验一次：产物已先行交付时发布即生效
        self._try_promote(row)
        return self.describe_version(row)

    def _try_promote(self, row: dict[str, Any]) -> bool:
        """产物就绪则把待发布版本提升为当前版本并固化快照。"""
        if row["lifecycle"] != LIFECYCLE_WAITING:
            return False
        artifact = self._find_artifact(row["metric_code"], row["version"])
        if artifact is None:
            row["readiness"] = READY_PENDING
            row["ready_errors"] = [f"指标 {row['metric_code']} 版本 {row['version']} 的聚合产物尚未交付"]
            self._sync_entry(row)
            return False
        if not artifact.get("complete"):
            row["readiness"] = READY_PENDING
            row["ready_errors"] = list(artifact.get("validation_errors", [])) or ["聚合产物未完整交付"]
            self._sync_entry(row)
            return False

        payload = artifact.get("payload") or {}
        if payload.get("metric_code") and payload["metric_code"] != row["metric_code"]:
            row["readiness"] = READY_PENDING
            row["ready_errors"] = [
                f"产物口径 {payload['metric_code']} 与服务绑定口径 {row['metric_code']} 不一致"
            ]
            self._sync_entry(row)
            return False

        # 固化快照：发布后不受同版本产物后续变化影响
        snapshot = copy.deepcopy(payload)
        snapshot.update({
            "service_code": row["service_code"],
            "version": row["version"],
            "metric_code": row["metric_code"],
            "snapshot_at": _now(),
        })
        # 同服务的其他版本让出当前版本身份（旧版本转为历史，但仍处于已发布）
        for other in self._registry():
            if other is row:
                continue
            if other.get("service_code") == row["service_code"] and other.get("is_current"):
                other["is_current"] = False
                self._sync_entry(other)
        row.update({
            "lifecycle": LIFECYCLE_PUBLISHED,
            "readiness": READY_READY,
            "is_current": True,
            "snapshot": snapshot,
            "snapshot_at": snapshot["snapshot_at"],
            "published_at": _now(),
            "ready_errors": [],
        })
        self._sync_entry(row)
        return True

    def check_readiness(self, service_code: str | None = None) -> list[dict[str, Any]]:
        """服务接口校验生效状态：把产物迟到后已就绪的待发布版本切换上线。

        返回本次实际发生切换的版本说明列表，供接口与日报侧观察交接结果。
        """
        promoted: list[dict[str, Any]] = []
        for row in self._registry():
            if service_code is not None and row.get("service_code") != service_code:
                continue
            if row.get("lifecycle") != LIFECYCLE_WAITING:
                continue
            if self._try_promote(row):
                promoted.append(self.describe_version(row))
        return promoted

    def offline_version(self, service_code: str, version: str) -> dict[str, Any]:
        """下线指定版本：不再作为当前服务，快照保留用于历史查询。"""
        row = self._find_version(service_code, version)
        if row is None:
            raise ServiceReleaseError(f"服务 {service_code} 不存在版本 {version}")
        if row["lifecycle"] == LIFECYCLE_OFFLINE:
            raise ServiceReleaseError(f"服务 {service_code} 版本 {version} 已经下线")
        was_current = bool(row.get("is_current"))
        row.update({
            "lifecycle": LIFECYCLE_OFFLINE,
            "is_current": False,
            "offline_at": _now(),
        })
        self._sync_entry(row)
        # 下线的正是当前版本时，提升另一个已发布就绪版本兜底，避免读取端无版本可用
        if was_current:
            fallback = self._pick_fallback(service_code, exclude=version)
            if fallback is not None:
                fallback["is_current"] = True
                self._sync_entry(fallback)
        return self.describe_version(row)

    def _pick_fallback(
        self, service_code: str, *, exclude: str
    ) -> dict[str, Any] | None:
        candidates = [
            row for row in self._registry()
            if row.get("service_code") == service_code
            and row.get("version") != exclude
            and row.get("lifecycle") == LIFECYCLE_PUBLISHED
            and row.get("readiness") == READY_READY
        ]
        # 优先选择发布时间最晚的版本
        candidates.sort(key=lambda r: r.get("published_at") or "", reverse=True)
        return candidates[0] if candidates else None

    # ------------------------------------------------------------------
    # 版本化取数
    # ------------------------------------------------------------------
    def current_snapshot(self, service_code: str) -> dict[str, Any] | None:
        """读取端取数入口：只返回当前、已发布、就绪版本的快照。"""
        row = self._current_row(service_code)
        if row is None or row["lifecycle"] != LIFECYCLE_PUBLISHED:
            return None
        return self.describe_version(row)

    def version_snapshot(self, service_code: str, version: str) -> dict[str, Any]:
        """按版本号查询（含历史），并明确该版本当前是当前、历史还是已下线。"""
        row = self._find_version(service_code, version)
        if row is None:
            raise ServiceReleaseError(f"服务 {service_code} 不存在版本 {version}")
        return self.describe_version(row)

    def list_versions(self, service_code: str | None = None) -> list[dict[str, Any]]:
        rows = self._registry()
        if service_code is not None:
            rows = [row for row in rows if row.get("service_code") == service_code]
        return [self.describe_version(row) for row in rows]

    def find_by_entry(self, entry_id: int) -> dict[str, Any] | None:
        """找到数据服务登记记录最近一次提交发布的版本行（用于动作联动）。"""
        matches = [row for row in self._registry() if row.get("entry_id") == entry_id]
        if not matches:
            return None
        matches.sort(key=lambda r: r.get("created_at") or "")
        return matches[-1]

    def describe_version(self, row: dict[str, Any]) -> dict[str, Any]:
        """对外版本视图：状态、就绪情况、访问身份与快照一次讲清。"""
        if row.get("is_current") and row.get("lifecycle") == LIFECYCLE_PUBLISHED:
            access = ACCESS_CURRENT
        elif row.get("lifecycle") == LIFECYCLE_OFFLINE:
            access = ACCESS_OFFLINE
        else:
            access = ACCESS_HISTORY
        return {
            "service_code": row.get("service_code"),
            "version": row.get("version"),
            "metric_code": row.get("metric_code"),
            "entry_id": row.get("entry_id"),
            "lifecycle": row.get("lifecycle"),
            "readiness": row.get("readiness"),
            "is_current": bool(row.get("is_current")),
            "access": access,
            "snapshot": copy.deepcopy(row.get("snapshot")),
            "snapshot_at": row.get("snapshot_at"),
            "published_at": row.get("published_at"),
            "offline_at": row.get("offline_at"),
            "ready_errors": list(row.get("ready_errors", [])),
            "pending_versions": self._pending_versions(row.get("service_code")),
        }

    def _pending_versions(self, service_code: str) -> list[str]:
        return [
            row["version"] for row in self._registry()
            if row.get("service_code") == service_code and row.get("lifecycle") == LIFECYCLE_WAITING
        ]

    # ------------------------------------------------------------------
    # 与 api_service 登记记录联动
    # ------------------------------------------------------------------
    def _sync_entry(self, row: dict[str, Any]) -> None:
        """把服务实际可读状态回写到数据服务登记记录。

        一个服务可能有多个版本共用同一条登记记录，因此登记状态始终按
        「当前可读版本」对账；没有当前版本时才展示本次动作版本自身的状态，
        同时保留待发布版本列表，让交接期在登记上也可见。
        """
        entry_id = row.get("entry_id")
        if entry_id is None:
            return
        entry = store.find("api_service", int(entry_id))
        if entry is None:
            return
        service_code = row["service_code"]
        current = self._current_row(service_code)
        entry["待发布版本"] = ",".join(self._pending_versions(service_code))
        if current is not None:
            entry["版本号"] = current["version"]
            entry["就绪状态"] = current["readiness"]
            entry["当前版本"] = "是"
            entry["访问身份"] = self.describe_version(current)["access"]
            snapshot = current.get("snapshot")
            entry["快照金额"] = snapshot.get("value") if snapshot else None
            entry["status"] = "已发布"
            entry["pending"] = False
            # 有待发布版本在交接中时给出异常提示，便于运营看板发现
            entry["abnormal"] = bool(entry["待发布版本"])
            return

        view = self.describe_version(row)
        entry["版本号"] = row["version"]
        entry["就绪状态"] = row["readiness"]
        entry["当前版本"] = "否"
        entry["访问身份"] = view["access"]
        snapshot = row.get("snapshot")
        entry["快照金额"] = snapshot.get("value") if snapshot else None
        if row["lifecycle"] == LIFECYCLE_OFFLINE:
            entry["status"] = "已下线"
            entry["pending"] = False
            entry["abnormal"] = True
        else:
            # 已提交发布但产物未就绪、且无其他可读版本：如实显示待发布
            entry["status"] = LIFECYCLE_WAITING
            entry["pending"] = True
            entry["abnormal"] = True


manager = ServiceReleaseManager()
