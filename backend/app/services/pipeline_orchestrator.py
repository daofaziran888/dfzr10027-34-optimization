"""跨模块数据管道编排器：实现 7 条真实数据流。

每条管道都读取上游模块的存储数据或 fixtures，执行真实计算，
把结果写入 store 的 _pipeline_results 命名空间，供下游消费。
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from typing import Any

from app.fixtures import (
    ATTRIBUTION_TOUCHES,
    COHORT_USERS,
    DATA_MART_ROWS,
    DIMENSIONS,
    EXPERIMENT_RESULTS,
    METRIC_DEFS,
    QUALITY_CHECK_SAMPLES,
    TREND_POINTS,
)
from app.store import store

# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _write_result(pipeline_id: str, payload: dict[str, Any]) -> None:
    """把管道产物写入 store._pipeline_results，支持追加与幂等覆盖。"""
    table = store.rows("_pipeline_results")
    # 若同 pipeline_id 已存在则更新，否则追加
    for row in table:
        if row.get("pipeline_id") == pipeline_id:
            row.update(payload)
            row["updated_at"] = datetime.now().isoformat()
            return
    entry = {"pipeline_id": pipeline_id, "created_at": datetime.now().isoformat()}
    entry.update(payload)
    table.append(entry)


def _read_result(pipeline_id: str) -> dict[str, Any] | None:
    for row in store.rows("_pipeline_results"):
        if row.get("pipeline_id") == pipeline_id:
            return dict(row)
    return None


def _to_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _to_int(val: Any) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Pipeline 1: metric_def -> agg_task -> api_service
# ---------------------------------------------------------------------------

def run_metric_agg_pipeline(metric_code: str | None = None, version: str | None = None) -> dict[str, Any]:
    """读取指标定义与 fixtures 时序数据，按口径执行真实聚合，生成 API 产物。

    提供 ``version`` 时，管道同时把产物登记到发布管理器的聚合产物台账，
    作为服务版本就绪校验的输入；未提供版本号时保持原有行为不变。
    """
    # 取指标定义（优先 fixture，再回退 store）
    defs = METRIC_DEFS
    if metric_code is None:
        target = defs[0]
    else:
        target = next((d for d in defs if d.get("指标编号") == metric_code), defs[0])

    formula = target.get("计算公式", "")
    granularity = target.get("聚合粒度", "日")

    points = list(TREND_POINTS)
    result: dict[str, Any] = {"metric_code": target.get("指标编号"), "granularity": granularity}

    if "sum(order_amount)" in formula or "gmv" in target.get("指标名称", "").lower():
        total = sum(p["gmv"] for p in points)
        result["value"] = round(total, _to_int(target.get("精度位数", 2)))
        result["unit"] = "元"
        result["point_count"] = len(points)
    elif "count(distinct user_id)" in formula or "uv" in target.get("指标名称", "").lower():
        total = sum(p["uv"] for p in points)
        result["value"] = total
        result["unit"] = "人"
        result["point_count"] = len(points)
    elif "paid_uv / total_uv" in formula or "转化率" in target.get("指标名称", ""):
        total_paid = sum(p["paid_uv"] for p in points)
        total_uv = sum(p["total_uv"] for p in points)
        cvr = total_paid / total_uv if total_uv else 0.0
        result["value"] = round(cvr, _to_int(target.get("精度位数", 4)))
        result["unit"] = "比率"
        result["point_count"] = len(points)
    elif "gmv / uv" in formula or "平均收入" in target.get("指标名称", ""):
        total_gmv = sum(p["gmv"] for p in points)
        total_uv = sum(p["uv"] for p in points)
        arpu = total_gmv / total_uv if total_uv else 0.0
        result["value"] = round(arpu, _to_int(target.get("精度位数", 2)))
        result["unit"] = "元/人"
        result["point_count"] = len(points)
    else:
        result["value"] = 0.0
        result["unit"] = "未知"
        result["point_count"] = 0

    # 写入 agg_task 与 api_service 可读产物
    _write_result("metric_agg_api", {
        "source_modules": ["metric_def", "agg_task"],
        "target_module": "api_service",
        "payload": result,
    })
    if version:
        # 聚合管道交付完整产物：进入服务版本就绪校验台账
        from app.services.service_release import manager
        manager.deliver_artifact(result["metric_code"], version, result, complete=True)
        result["artifact_version"] = version
    return result


# ---------------------------------------------------------------------------
# 聚合产物显式交付：支持外部按版本投递完整或迟到的指标产物
# ---------------------------------------------------------------------------

def deliver_metric_artifact(
    metric_code: str,
    version: str,
    payload: dict[str, Any],
    *,
    complete: bool | None = None,
) -> dict[str, Any]:
    """把聚合管道的指标产物按版本登记给发布管理器。

    产物迟到或不完整时 ``complete=False``，发布管理器不会把它算作就绪。
    """
    from app.services.service_release import manager
    return manager.deliver_artifact(metric_code, version, payload, complete=complete)


# ---------------------------------------------------------------------------
# Pipeline 2: trend_series -> forecast -> report_gen
# ---------------------------------------------------------------------------

def run_forecast_pipeline(horizon: int = 7) -> dict[str, Any]:
    """基于 fixtures 时序数据做线性趋势外推，生成预测结果供报表消费。"""
    points = list(TREND_POINTS)
    n = len(points)
    if n < 2:
        return {"error": " insufficient data"}

    # 简单线性回归：x = 0..n-1, y = gmv
    xs = list(range(n))
    ys = [p["gmv"] for p in points]
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    slope = num / den if den else 0.0
    intercept = y_mean - slope * x_mean

    last_date = datetime.strptime(points[-1]["日期"], "%Y-%m-%d").date()
    forecasts: list[dict] = []
    for i in range(1, horizon + 1):
        pred = slope * (n - 1 + i) + intercept
        pred_date = last_date + timedelta(days=i)
        forecasts.append({
            "日期": pred_date.isoformat(),
            "预测gmv": round(pred, 2),
            "置信下界": round(pred * 0.92, 2),
            "置信上界": round(pred * 1.08, 2),
        })

    result = {
        "model": "linear_trend",
        "horizon": horizon,
        "slope": round(slope, 4),
        "intercept": round(intercept, 2),
        "last_actual": points[-1]["gmv"],
        "forecasts": forecasts,
    }

    _write_result("forecast_report", {
        "source_modules": ["trend_series", "forecast"],
        "target_module": "report_gen",
        "payload": result,
    })
    return result


# ---------------------------------------------------------------------------
# Pipeline 3: dim_registry -> cube_builder -> api_service
# ---------------------------------------------------------------------------

def run_cube_pipeline(dim_codes: list[str] | None = None) -> dict[str, Any]:
    """按指定维度组合 fixtures 数据集市行，生成多维立方体快照与查询接口产物。"""
    dims = DIMENSIONS
    if dim_codes is None:
        dim_codes = [d["维度编号"] for d in dims[:2]]

    # 映射维度编号到字段名
    dim_field_map = {
        "DIM-REGION": "region",
        "DIM-CHANNEL": "channel",
        "DIM-USER-TAG": "tag",
        "DIM-PRODUCT": "category_id",
    }
    selected_fields = [dim_field_map.get(dc) for dc in dim_codes if dim_field_map.get(dc)]

    rows = list(DATA_MART_ROWS)
    # 按选定维度分组聚合
    groups: dict[tuple, dict] = {}
    for r in rows:
        key = tuple(r.get(f) for f in selected_fields)
        if key not in groups:
            groups[key] = {f: r.get(f) for f in selected_fields}
            groups[key]["订单数"] = 0
            groups[key]["gmv"] = 0.0
            groups[key]["uv"] = 0
        groups[key]["订单数"] += _to_int(r.get("订单数"))
        groups[key]["gmv"] += _to_float(r.get("gmv"))
        groups[key]["uv"] += _to_int(r.get("uv"))

    cells = []
    for g in groups.values():
        cells.append({k: round(v, 2) if isinstance(v, float) else v for k, v in g.items()})

    result = {
        "dimensions": dim_codes,
        "dim_fields": selected_fields,
        "cell_count": len(cells),
        "cells": cells,
    }

    _write_result("cube_api", {
        "source_modules": ["dim_registry", "cube_builder"],
        "target_module": "api_service",
        "payload": result,
    })
    return result


# ---------------------------------------------------------------------------
# Pipeline 4: cohort_rule -> data_extract -> report_gen
# ---------------------------------------------------------------------------

def run_cohort_extract_pipeline(rule: dict[str, Any] | None = None) -> dict[str, Any]:
    """按分群规则过滤 fixtures 用户，执行数据提取，生成分群报表产物。"""
    users = list(COHORT_USERS)
    if rule is None:
        rule = {"region": "华东", "min_ltv": 1000.0}

    filtered = []
    for u in users:
        match = True
        if "region" in rule and u.get("region") != rule["region"]:
            match = False
        if "channel" in rule and u.get("channel") != rule["channel"]:
            match = False
        if "tag" in rule and u.get("tag") != rule["tag"]:
            match = False
        if "min_ltv" in rule and _to_float(u.get("ltv")) < _to_float(rule["min_ltv"]):
            match = False
        if match:
            filtered.append(u)

    # 统计聚合
    total_ltv = sum(_to_float(u["ltv"]) for u in filtered)
    avg_ltv = total_ltv / len(filtered) if filtered else 0.0
    region_dist: dict[str, int] = {}
    for u in filtered:
        region_dist[u["region"]] = region_dist.get(u["region"], 0) + 1

    result = {
        "rule": rule,
        "matched_count": len(filtered),
        "users": filtered,
        "summary": {
            "total_ltv": round(total_ltv, 2),
            "avg_ltv": round(avg_ltv, 2),
            "region_distribution": region_dist,
        },
    }

    _write_result("cohort_extract_report", {
        "source_modules": ["cohort_rule", "data_extract"],
        "target_module": "report_gen",
        "payload": result,
    })
    return result


# ---------------------------------------------------------------------------
# Pipeline 5: experiment -> stat_model -> data_mart
# ---------------------------------------------------------------------------

def run_experiment_stat_pipeline(experiment_code: str | None = None) -> dict[str, Any]:
    """读取实验 fixtures，执行双比例 z 检验与效应量计算，产物写入数据集市。"""
    rows = list(EXPERIMENT_RESULTS)
    if experiment_code is None:
        experiment_code = "EXPE-001"

    exp_rows = [r for r in rows if r.get("实验编号") == experiment_code]
    if len(exp_rows) < 2:
        return {"error": "实验数据不足"}

    control = next((r for r in exp_rows if r.get("分组") == "control"), None)
    treatment = next((r for r in exp_rows if r.get("分组") == "treatment"), None)
    if control is None or treatment is None:
        return {"error": "缺少对照组或实验组"}

    n_c = _to_int(control.get("样本量"))
    n_t = _to_int(treatment.get("样本量"))
    conv_c = _to_int(control.get("转化人数"))
    conv_t = _to_int(treatment.get("转化人数"))

    p_c = conv_c / n_c if n_c else 0.0
    p_t = conv_t / n_t if n_t else 0.0
    p_pool = (conv_c + conv_t) / (n_c + n_t) if (n_c + n_t) else 0.0
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t)) if (n_c + n_t) else 0.0
    z = (p_t - p_c) / se if se else 0.0

    # Cohen's h 效应量
    cohen_h = 2 * (math.asin(math.sqrt(p_t)) - math.asin(math.sqrt(p_c))) if (p_t >= 0 and p_c >= 0) else 0.0

    result = {
        "experiment_code": experiment_code,
        "control_rate": round(p_c, 4),
        "treatment_rate": round(p_t, 4),
        "absolute_lift": round(p_t - p_c, 4),
        "relative_lift": round((p_t - p_c) / p_c, 4) if p_c else None,
        "z_score": round(z, 4),
        "cohen_h": round(cohen_h, 4),
        "significant_at_05": abs(z) > 1.96,
        "sample_size_control": n_c,
        "sample_size_treatment": n_t,
    }

    # 同时写入 data_mart 可消费的统计摘要行
    mart_entry = {
        "主题编号": f"DATA-STAT-{experiment_code}",
        "region": "all",
        "channel": "all",
        "日期": str(date.today()),
        "实验编号": experiment_code,
        "控制组转化率": result["control_rate"],
        "实验组转化率": result["treatment_rate"],
        "相对提升": result["relative_lift"],
        "显著性": result["significant_at_05"],
    }
    store.rows("data_mart").append(mart_entry)

    _write_result("experiment_stat_mart", {
        "source_modules": ["experiment", "stat_model"],
        "target_module": "data_mart",
        "payload": result,
    })
    return result


# ---------------------------------------------------------------------------
# Pipeline 6: quality_mon 跨模块扫描
# ---------------------------------------------------------------------------

def run_quality_scan() -> dict[str, Any]:
    """扫描 fixtures 质量样本与 store 中各模块数据，生成跨模块质量报告。"""
    samples = list(QUALITY_CHECK_SAMPLES)
    issues: list[dict] = []
    total_rows = 0
    total_anomalies = 0

    for s in samples:
        anomaly = _to_int(s.get("异常行数"))
        total_anomalies += anomaly
        # 模拟总行数
        estimated = max(anomaly, 1000)
        total_rows += estimated
        if anomaly > 0:
            issues.append({
                "规则编号": s.get("规则编号"),
                "监控对象": s.get("监控对象"),
                "异常行数": anomaly,
                "空值率": s.get("空值率"),
                "重复率": s.get("重复率"),
            })

    # 扫描 store 各模块的 abnormal 标记
    module_issues: list[dict] = []
    for mod in store.module_names():
        if mod.startswith("_"):
            continue
        rows = store.rows(mod)
        abnormal_count = sum(1 for r in rows if r.get("abnormal"))
        if abnormal_count:
            module_issues.append({"module": mod, "abnormal_count": abnormal_count})

    score = max(0, 100 - int(total_anomalies / max(total_rows, 1) * 10000))
    result = {
        "scan_time": datetime.now().isoformat(),
        "total_rows_estimated": total_rows,
        "total_anomalies": total_anomalies,
        "quality_score": score,
        "sample_issues": issues,
        "module_issues": module_issues,
    }

    _write_result("quality_scan", {
        "source_modules": ["quality_mon"],
        "target_module": "_global",
        "payload": result,
    })
    return result


# ---------------------------------------------------------------------------
# Pipeline 7: attribution -> metric_def -> compare_job
# ---------------------------------------------------------------------------

def run_attribution_compare_pipeline(link_code: str | None = None) -> dict[str, Any]:
    """读取归因 fixtures，按触点类型做首次/末次/线性权重分配，生成指标对比产物。"""
    touches = list(ATTRIBUTION_TOUCHES)
    if link_code is None:
        link_code = "ATTR-001"

    link_touches = [t for t in touches if t.get("链路编号") == link_code]
    if not link_touches:
        return {"error": "链路无数据"}

    # 按 user_id 聚合
    users: dict[str, list[dict]] = {}
    for t in link_touches:
        uid = t["user_id"]
        users.setdefault(uid, []).append(t)

    # 三种归因模型
    first_touch: dict[str, float] = {}
    last_touch: dict[str, float] = {}
    linear_touch: dict[str, float] = {}

    for uid, ts in users.items():
        ts_sorted = sorted(ts, key=lambda x: x["触点序号"])
        conv_amount = _to_float(ts_sorted[-1].get("贡献金额"))
        if conv_amount <= 0:
            continue
        # 首次
        ft = ts_sorted[0]["触点类型"]
        first_touch[ft] = first_touch.get(ft, 0.0) + conv_amount
        # 末次（转化事件前最后一个有效触点）
        lt_candidates = [t for t in ts_sorted if t["触点类型"] != "下单"]
        if lt_candidates:
            lt = lt_candidates[-1]["触点类型"]
            last_touch[lt] = last_touch.get(lt, 0.0) + conv_amount
        # 线性
        n = len([t for t in ts_sorted if t["触点类型"] != "下单"])
        if n > 0:
            share = conv_amount / n
            for t in ts_sorted:
                if t["触点类型"] != "下单":
                    linear_touch[t["触点类型"]] = linear_touch.get(t["触点类型"], 0.0) + share

    # 归一化到指标定义口径
    total_first = sum(first_touch.values())
    total_last = sum(last_touch.values())
    total_linear = sum(linear_touch.values())

    result = {
        "link_code": link_code,
        "user_count": len(users),
        "models": {
            "first_touch": {k: round(v, 2) for k, v in first_touch.items()},
            "last_touch": {k: round(v, 2) for k, v in last_touch.items()},
            "linear": {k: round(v, 2) for k, v in linear_touch.items()},
        },
        "totals": {
            "first_touch": round(total_first, 2),
            "last_touch": round(total_last, 2),
            "linear": round(total_linear, 2),
        },
    }

    # 写入对比任务可消费的差异数据
    diffs: list[dict] = []
    all_types = set(first_touch) | set(last_touch) | set(linear_touch)
    for t in all_types:
        f = first_touch.get(t, 0.0)
        l = last_touch.get(t, 0.0)
        diffs.append({
            "触点类型": t,
            "首次归因": round(f, 2),
            "末次归因": round(l, 2),
            "差异": round(abs(f - l), 2),
        })
    result["compare_rows"] = diffs

    _write_result("attribution_metric_compare", {
        "source_modules": ["attribution", "metric_def"],
        "target_module": "compare_job",
        "payload": result,
    })
    return result


# ---------------------------------------------------------------------------
# 批量入口
# ---------------------------------------------------------------------------

def run_all_pipelines() -> dict[str, Any]:
    """顺序执行全部 7 条管道并返回摘要。"""
    return {
        "metric_agg_api": run_metric_agg_pipeline(),
        "forecast_report": run_forecast_pipeline(),
        "cube_api": run_cube_pipeline(),
        "cohort_extract_report": run_cohort_extract_pipeline(),
        "experiment_stat_mart": run_experiment_stat_pipeline(),
        "quality_scan": run_quality_scan(),
        "attribution_metric_compare": run_attribution_compare_pipeline(),
    }


def list_pipeline_results() -> list[dict[str, Any]]:
    return [dict(r) for r in store.rows("_pipeline_results")]
