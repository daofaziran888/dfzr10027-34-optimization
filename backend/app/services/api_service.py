"""数据服务业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.services.service_release import (
    LIFECYCLE_WAITING,
    ServiceReleaseError,
    manager,
)
from app.store import store

MODULE = "api_service"
LIST_FIELDS = ["接口编号", "查询数据集", "请求参数", "返回字段", "缓存秒数", "QPS上限", "认证方式", "版本号"]
REQUIRED_FIELDS = ["接口编号", "查询数据集", "请求参数"]
STATUS_ORDER = ["草稿", "待发布", "已发布", "已下线", "已废弃"]
ACTION_RULES = {"发布服务": "已发布", "下线服务": "已下线", "废弃服务": "已废弃"}
NEGATIVE_ACTIONS = ["下线服务"]


class ApiServiceService:
    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for field, expected in (filters or {}).items():
            rows = [row for row in rows if expected.casefold() in str(row.get(field, "")).casefold()]
        if keyword:
            rows = [row for row in rows if keyword.casefold() in str(row.get("接口编号", "")).casefold()]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = (page - 1) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in LIST_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"服务接口 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据服务可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        # 纳入版本化发布管理的服务：发布/下线动作交给发布管理器，
        # 状态必须与聚合产物就绪状态、当前可读快照保持一致。
        bound = manager.find_by_entry(entry_id)
        if bound is not None and action in ("发布服务", "下线服务"):
            try:
                if action == "发布服务":
                    manager.check_readiness(bound["service_code"])
                    view = manager.version_snapshot(bound["service_code"], bound["version"])
                    if view["lifecycle"] == LIFECYCLE_WAITING:
                        reason = "；".join(view["ready_errors"]) or "聚合产物尚未就绪"
                        return entry, f"发布申请已受理，但{reason}，旧版本继续对外服务"
                else:
                    view = manager.offline_version(bound["service_code"], bound["version"])
            except ServiceReleaseError as exc:
                return None, str(exc)
            entry = store.find(MODULE, entry_id) or entry
            return entry, f"服务接口已{action}：{view['version']} 当前为{view['lifecycle']}/{view['access']}"

        # 未纳入发布管理的登记记录保持原有直接流转
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"服务接口已{action}"
