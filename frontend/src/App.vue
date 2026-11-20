<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">分析工坊 · 数据分析与数据应用平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向指标口径管理、多维度聚合查询、用户分群圈选、AB实验评估、时序趋势分析与数据服务发布的数据分析与数据应用平台。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "指标定义", path: "/metric_def" }, { label: "维度注册", path: "/dim_registry" }, { label: "聚合任务", path: "/agg_task" }, { label: "多维立方体", path: "/cube_builder" }, { label: "分群规则", path: "/cohort_rule" }, { label: "实验管理", path: "/experiment" }, { label: "时序分析", path: "/trend_series" }, { label: "归因模型", path: "/attribution" }, { label: "数据分层", path: "/segmentation" }, { label: "报表生成", path: "/report_gen" }, { label: "预测分析", path: "/forecast" }, { label: "数据集市", path: "/data_mart" }, { label: "统计建模", path: "/stat_model" }, { label: "数据提取", path: "/data_extract" }, { label: "质量监控", path: "/quality_mon" }, { label: "对比分析", path: "/compare_job" }, { label: "数据服务", path: "/data_service" }, { label: "调度编排", path: "/schedule_plan" }]
</script>
