"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import metric_def as router_metric_def
from app.routers import dim_registry as router_dim_registry
from app.routers import agg_task as router_agg_task
from app.routers import cube_builder as router_cube_builder
from app.routers import cohort_rule as router_cohort_rule
from app.routers import experiment as router_experiment
from app.routers import trend_series as router_trend_series
from app.routers import attribution as router_attribution
from app.routers import segmentation as router_segmentation
from app.routers import report_gen as router_report_gen
from app.routers import forecast as router_forecast
from app.routers import data_mart as router_data_mart
from app.routers import stat_model as router_stat_model
from app.routers import data_extract as router_data_extract
from app.routers import quality_mon as router_quality_mon
from app.routers import compare_job as router_compare_job
from app.routers import api_service as router_api_service
from app.routers import schedule_plan as router_schedule_plan
from app.routers import pipeline as router_pipeline
from app.routers import service_release as router_service_release
from app.routers import daily_report as router_daily_report

ROUTERS = [router_metric_def, router_dim_registry, router_agg_task, router_cube_builder, router_cohort_rule, router_experiment, router_trend_series, router_attribution, router_segmentation, router_report_gen, router_forecast, router_data_mart, router_stat_model, router_data_extract, router_quality_mon, router_compare_job, router_api_service, router_schedule_plan, router_pipeline, router_service_release, router_daily_report]
