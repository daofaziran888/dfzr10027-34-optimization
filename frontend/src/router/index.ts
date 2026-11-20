import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
const MetricDef = () => import('@/views/metric_def/index.vue')
const DimRegistry = () => import('@/views/dim_registry/index.vue')
const AggTask = () => import('@/views/agg_task/index.vue')
const CubeBuilder = () => import('@/views/cube_builder/index.vue')
const CohortRule = () => import('@/views/cohort_rule/index.vue')
const Experiment = () => import('@/views/experiment/index.vue')
const TrendSeries = () => import('@/views/trend_series/index.vue')
const Attribution = () => import('@/views/attribution/index.vue')
const Segmentation = () => import('@/views/segmentation/index.vue')
const ReportGen = () => import('@/views/report_gen/index.vue')
const Forecast = () => import('@/views/forecast/index.vue')
const DataMart = () => import('@/views/data_mart/index.vue')
const StatModel = () => import('@/views/stat_model/index.vue')
const DataExtract = () => import('@/views/data_extract/index.vue')
const QualityMon = () => import('@/views/quality_mon/index.vue')
const CompareJob = () => import('@/views/compare_job/index.vue')
const ApiService = () => import('@/views/api_service/index.vue')
const SchedulePlan = () => import('@/views/schedule_plan/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/metric_def', name: 'metric_def', component: MetricDef },
    { path: '/dim_registry', name: 'dim_registry', component: DimRegistry },
    { path: '/agg_task', name: 'agg_task', component: AggTask },
    { path: '/cube_builder', name: 'cube_builder', component: CubeBuilder },
    { path: '/cohort_rule', name: 'cohort_rule', component: CohortRule },
    { path: '/experiment', name: 'experiment', component: Experiment },
    { path: '/trend_series', name: 'trend_series', component: TrendSeries },
    { path: '/attribution', name: 'attribution', component: Attribution },
    { path: '/segmentation', name: 'segmentation', component: Segmentation },
    { path: '/report_gen', name: 'report_gen', component: ReportGen },
    { path: '/forecast', name: 'forecast', component: Forecast },
    { path: '/data_mart', name: 'data_mart', component: DataMart },
    { path: '/stat_model', name: 'stat_model', component: StatModel },
    { path: '/data_extract', name: 'data_extract', component: DataExtract },
    { path: '/quality_mon', name: 'quality_mon', component: QualityMon },
    { path: '/compare_job', name: 'compare_job', component: CompareJob },
    // 注意：/api_service 与 Vite 的 /api 代理前缀冲突，深链会被转发到后端导致 404；
    // 主路径改用 /data_service，并保留旧路径别名兼容既有书签。
    { path: '/data_service', name: 'api_service', component: ApiService },
    { path: '/api_service', redirect: '/data_service' },
    { path: '/schedule_plan', name: 'schedule_plan', component: SchedulePlan },
  ],
})

export default router
