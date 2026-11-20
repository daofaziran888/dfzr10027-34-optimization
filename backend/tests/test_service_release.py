"""服务发布就绪与版本化快照测试。

覆盖场景：
- 一版服务携带 200 元结果发布；
- 新版本先提交发布但不给产物，观察指标服务与日报两处仍读旧版本；
- 240 元新产物迟到交付，就绪校验后切换到版本化查询；
- 下线旧版后，当前访问与历史访问的状态、金额各自正确；
- 不完整/口径不一致产物不能发布；已发布快照不可变；无当前版本时日报阻塞。
"""
from __future__ import annotations

import pytest

from app.services.daily_report import daily_report_service
from app.services.pipeline_orchestrator import run_metric_agg_pipeline
from app.services.service_release import (
    ACCESS_CURRENT,
    ACCESS_HISTORY,
    ACCESS_OFFLINE,
    LIFECYCLE_OFFLINE,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_WAITING,
    READY_PENDING,
    READY_READY,
    ServiceReleaseError,
    manager,
)
from app.store import store

SERVICE = "API-METRIC"
METRIC = "METR-GMV"
ENTRY_ID = 1  # seed 中接口编号 API-METRIC 的登记记录


def gmv_payload(value: float, point_count: int = 30) -> dict:
    return {
        "metric_code": METRIC,
        "granularity": "日",
        "value": value,
        "unit": "元",
        "point_count": point_count,
    }


class TestReleaseWithReadyArtifact:
    def test_first_version_publishes_with_snapshot(self):
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        view = manager.submit_release(SERVICE, "v1.0", METRIC, entry_id=ENTRY_ID)

        assert view["lifecycle"] == LIFECYCLE_PUBLISHED
        assert view["readiness"] == READY_READY
        assert view["is_current"] is True
        assert view["access"] == ACCESS_CURRENT
        assert view["snapshot"]["value"] == 200.0
        assert view["snapshot"]["unit"] == "元"

        current = manager.current_snapshot(SERVICE)
        assert current["version"] == "v1.0"
        assert current["snapshot"]["value"] == 200.0

    def test_published_snapshot_is_immutable(self):
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        manager.submit_release(SERVICE, "v1.0", METRIC)
        # 同版本产物迟到重算成别的金额，也不能改动已发布快照
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(999.0))
        manager.check_readiness(SERVICE)
        assert manager.current_snapshot(SERVICE)["snapshot"]["value"] == 200.0

    def test_entry_status_reflects_published_state(self):
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        manager.submit_release(SERVICE, "v1.0", METRIC, entry_id=ENTRY_ID)
        entry = store.find("api_service", ENTRY_ID)
        assert entry["status"] == "已发布"
        assert entry["就绪状态"] == READY_READY
        assert entry["当前版本"] == "是"
        assert entry["快照金额"] == 200.0


class TestLateArtifactHandoff:
    def _publish_v1(self) -> None:
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        manager.submit_release(SERVICE, "v1.0", METRIC, entry_id=ENTRY_ID)

    def test_new_version_without_artifact_waits_and_old_version_still_serves(self):
        self._publish_v1()
        view = manager.submit_release(SERVICE, "v2.0", METRIC, entry_id=ENTRY_ID)

        # 新版本已提交发布，但产物迟到：不能冒充已发布
        assert view["lifecycle"] == LIFECYCLE_WAITING
        assert view["readiness"] == READY_PENDING
        assert view["is_current"] is False
        assert view["ready_errors"]
        # 旧版本仍是当前可读服务
        current = manager.current_snapshot(SERVICE)
        assert current["version"] == "v1.0"
        assert current["snapshot"]["value"] == 200.0
        # 登记记录仍反映实际可读的已发布版本，同时标明交接中的待发布版本
        entry = store.find("api_service", ENTRY_ID)
        assert entry["status"] == "已发布"
        assert entry["版本号"] == "v1.0"
        assert entry["待发布版本"] == "v2.0"
        assert entry["当前版本"] == "是"

    def test_daily_report_uses_old_version_during_handoff(self):
        self._publish_v1()
        manager.submit_release(SERVICE, "v2.0", METRIC)

        round1 = daily_report_service.run_round(SERVICE, round_label="round-1")
        assert round1["ok"] is True
        assert round1["used_version"] == "v1.0"
        assert round1["metric_value"] == 200.0
        assert "v2.0" in round1["waiting_versions"]

    def test_late_artifact_promotes_new_version_via_readiness_check(self):
        self._publish_v1()
        manager.submit_release(SERVICE, "v2.0", METRIC)

        # 240 元的新产物迟到交付
        manager.deliver_artifact(METRIC, "v2.0", gmv_payload(240.0))
        # 交付本身不自动切换，服务接口校验生效状态后才切换
        assert manager.current_snapshot(SERVICE)["version"] == "v1.0"
        promoted = manager.check_readiness(SERVICE)
        assert [item["version"] for item in promoted] == ["v2.0"]

        current = manager.current_snapshot(SERVICE)
        assert current["version"] == "v2.0"
        assert current["snapshot"]["value"] == 240.0

        # 旧版本转为历史版本，但仍可按版本号查到完整快照
        old = manager.version_snapshot(SERVICE, "v1.0")
        assert old["lifecycle"] == LIFECYCLE_PUBLISHED
        assert old["is_current"] is False
        assert old["access"] == ACCESS_HISTORY
        assert old["snapshot"]["value"] == 200.0

    def test_daily_report_switches_to_new_version_after_promotion(self):
        self._publish_v1()
        manager.submit_release(SERVICE, "v2.0", METRIC)
        manager.deliver_artifact(METRIC, "v2.0", gmv_payload(240.0))

        round2 = daily_report_service.run_round(SERVICE, round_label="round-2")
        assert round2["used_version"] == "v2.0"
        assert round2["metric_value"] == 240.0
        assert round2["promoted_versions"] == ["v2.0"]
        assert round2["waiting_versions"] == []

        rounds = daily_report_service.list_rounds(SERVICE)
        assert [r["used_version"] for r in rounds] == ["v2.0"]
        assert rounds[0]["metric_value"] == 240.0

    def test_offline_old_version_keeps_history_accessible(self):
        self._publish_v1()
        manager.submit_release(SERVICE, "v2.0", METRIC)
        manager.deliver_artifact(METRIC, "v2.0", gmv_payload(240.0))
        manager.check_readiness(SERVICE)

        view = manager.offline_version(SERVICE, "v1.0")
        assert view["lifecycle"] == LIFECYCLE_OFFLINE
        assert view["is_current"] is False
        assert view["access"] == ACCESS_OFFLINE

        # 当前服务不受影响，仍是 240 元的新版本
        current = manager.current_snapshot(SERVICE)
        assert current["version"] == "v2.0"
        assert current["snapshot"]["value"] == 240.0

        # 历史查询能分清已下线版本，且金额仍是下线前的 200
        history = manager.version_snapshot(SERVICE, "v1.0")
        assert history["access"] == ACCESS_OFFLINE
        assert history["snapshot"]["value"] == 200.0

        newest = manager.version_snapshot(SERVICE, "v2.0")
        assert newest["access"] == ACCESS_CURRENT
        assert newest["snapshot"]["value"] == 240.0

        entry = store.find("api_service", ENTRY_ID)
        assert entry["status"] == "已发布"  # 登记记录跟随当前版本 v2.0
        assert entry["快照金额"] == 240.0

    def test_double_offline_rejected(self):
        self._publish_v1()
        manager.offline_version(SERVICE, "v1.0")
        with pytest.raises(ServiceReleaseError):
            manager.offline_version(SERVICE, "v1.0")

    def test_unknown_version_query_raises(self):
        with pytest.raises(ServiceReleaseError):
            manager.version_snapshot(SERVICE, "v9.9")


class TestArtifactValidation:
    def test_incomplete_artifact_blocks_release(self):
        # 数据点数为 0：未完成完整计算
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0, point_count=0))
        view = manager.submit_release(SERVICE, "v1.0", METRIC)
        assert view["lifecycle"] == LIFECYCLE_WAITING
        assert view["readiness"] == READY_PENDING
        assert manager.current_snapshot(SERVICE) is None

        # 补交付完整产物后再校验即可上线
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        promoted = manager.check_readiness(SERVICE)
        assert [v["version"] for v in promoted] == ["v1.0"]
        assert manager.current_snapshot(SERVICE)["snapshot"]["value"] == 200.0

    def test_missing_field_artifact_not_ready(self):
        artifact = manager.deliver_artifact(
            METRIC, "v1.0", {"metric_code": METRIC, "value": 200.0}, complete=True)
        assert artifact["complete"] is False
        assert artifact["validation_errors"]

    def test_explicit_incomplete_flag_respected(self):
        artifact = manager.deliver_artifact(
            METRIC, "v1.0", gmv_payload(200.0), complete=False)
        assert artifact["complete"] is False
        view = manager.submit_release(SERVICE, "v1.0", METRIC)
        assert view["lifecycle"] == LIFECYCLE_WAITING

    def test_caliber_mismatch_blocks_promotion(self):
        payload = gmv_payload(240.0)
        payload["metric_code"] = "METR-UV"  # 口径与服务绑定指标不一致
        manager.deliver_artifact(METRIC, "v1.0", payload)
        view = manager.submit_release(SERVICE, "v1.0", METRIC)
        assert view["lifecycle"] == LIFECYCLE_WAITING
        assert any("口径" in err for err in view["ready_errors"])

    def test_duplicate_release_rejected(self):
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        manager.submit_release(SERVICE, "v1.0", METRIC)
        with pytest.raises(ServiceReleaseError):
            manager.submit_release(SERVICE, "v1.0", METRIC)


class TestDailyReportBlocking:
    def test_report_blocked_without_current_version(self):
        # 提交了发布但没有任何产物
        manager.submit_release(SERVICE, "v1.0", METRIC)
        round_row = daily_report_service.run_round(SERVICE, round_label="blocked")
        assert round_row["ok"] is False
        assert round_row["status"] == "阻塞"
        assert round_row["used_version"] is None
        assert round_row["waiting_versions"] == ["v1.0"]

    def test_report_recovers_after_artifact_arrives(self):
        manager.submit_release(SERVICE, "v1.0", METRIC)
        daily_report_service.run_round(SERVICE, round_label="blocked")
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        round_row = daily_report_service.run_round(SERVICE, round_label="recovered")
        assert round_row["ok"] is True
        assert round_row["used_version"] == "v1.0"
        assert round_row["metric_value"] == 200.0


class TestPipelineIntegration:
    def test_metric_pipeline_registers_versioned_artifact(self):
        result = run_metric_agg_pipeline(METRIC, version="v1.0")
        assert result["artifact_version"] == "v1.0"
        artifacts = manager.list_artifacts(METRIC)
        assert len(artifacts) == 1
        assert artifacts[0]["version"] == "v1.0"
        assert artifacts[0]["complete"] is True

        view = manager.submit_release(SERVICE, "v1.0", METRIC)
        assert view["lifecycle"] == LIFECYCLE_PUBLISHED
        # 快照金额与管道真实聚合结果一致
        assert view["snapshot"]["value"] == result["value"]

    def test_pipeline_without_version_keeps_legacy_behavior(self):
        result = run_metric_agg_pipeline(METRIC)
        assert "artifact_version" not in result
        assert manager.list_artifacts() == []


class TestApiServiceActionIntegration:
    def _publish_v1(self) -> None:
        manager.deliver_artifact(METRIC, "v1.0", gmv_payload(200.0))
        manager.submit_release(SERVICE, "v1.0", METRIC, entry_id=ENTRY_ID)

    def test_publish_action_reports_waiting_when_artifact_absent(self):
        from app.services.api_service import ApiServiceService

        self._publish_v1()
        manager.submit_release(SERVICE, "v2.0", METRIC, entry_id=ENTRY_ID)
        entry, message = ApiServiceService().run_action(ENTRY_ID, "发布服务")
        assert "旧版本继续对外服务" in message
        # 登记状态反映实际可读产物（v1.0 已发布），新版本留在待发布字段里
        assert entry["status"] == "已发布"
        assert entry["待发布版本"] == "v2.0"
        # 读取端仍然拿到 v1.0 的 200 元
        assert manager.current_snapshot(SERVICE)["version"] == "v1.0"

    def test_offline_action_goes_through_release_manager(self):
        from app.services.api_service import ApiServiceService

        self._publish_v1()
        entry, message = ApiServiceService().run_action(ENTRY_ID, "下线服务")
        assert "已下线" in message
        view = manager.version_snapshot(SERVICE, "v1.0")
        assert view["access"] == ACCESS_OFFLINE
        assert entry["status"] == "已下线"
