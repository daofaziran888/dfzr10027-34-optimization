<template>
  <section class="page" data-module="report_gen">
    <header class="page-head">
      <div>
        <h2>报表生成管理</h2>
        <p class="page-desc">维护分析报表的模板定义、数据范围、生成周期和多渠道分发配置。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记分析报表</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出报表生成清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无报表生成数据，可先登记分析报表</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记分析报表</h3>
        <label v-for="field in columns" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <section class="release-panel" data-testid="daily-panel">
      <header class="page-head">
        <div>
          <h3>日报指标取数（按实际可用服务版本）</h3>
          <p class="page-desc">每轮日报先校验服务生效状态，再只读取当前版本的已发布快照；没有可读版本时本轮阻塞，不回退到未就绪产物。</p>
        </div>
        <div class="page-actions">
          <button class="btn" data-testid="daily-refresh" type="button" @click="loadRounds">刷新轮次</button>
          <button class="btn primary" data-testid="run-daily" type="button" @click="runDaily">计算当轮日报</button>
        </div>
      </header>
      <form class="filter-bar" @submit.prevent="runDaily">
        <label class="filter-item">
          <span>数据服务编号</span>
          <input v-model="dailyService" data-testid="daily-service-code" placeholder="如 API-METRIC" required />
        </label>
      </form>
      <table class="data-table">
        <thead>
          <tr>
            <th>轮次</th>
            <th>状态</th>
            <th>实际使用版本</th>
            <th>指标金额</th>
            <th>本轮切换版本</th>
            <th>待发布版本</th>
            <th>生成时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in dailyRounds" :key="item.round_label" :data-testid="`daily-row-${item.round_label}`">
            <td>{{ item.round_label }}</td>
            <td>{{ item.status }}</td>
            <td>{{ item.used_version ?? '—' }}</td>
            <td>{{ item.metric_value ?? '—' }}</td>
            <td>{{ item.promoted_versions?.join(',') || '—' }}</td>
            <td>{{ item.waiting_versions?.join(',') || '—' }}</td>
            <td>{{ item.generated_at }}</td>
          </tr>
          <tr v-if="!dailyRounds.length">
            <td colspan="7" class="empty-state">暂无日报轮次，点击「计算当轮日报」开始</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span v-if="dailyMessage" class="error-text" data-testid="daily-message">{{ dailyMessage }}</span>
      </footer>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条报表生成记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/report_gen'
const columns = ["报表编号", "报表类型", "数据范围", "包含图表", "生成周期", "输出格式", "分发渠道", "下次生成"]
const actions = ["提交生成", "确认分发", "停用报表"]
const statuses = ["草稿", "待生成", "已生成", "已停用"]
const metricNames = ["报表总数", "已生成报表", "待生成报表"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const stats = computed(() => [
  { label: metricNames[0], value: total.value },
  { label: metricNames[1], value: rows.value.filter((row) => row.status === statuses[1]).length },
  { label: metricNames[2], value: rows.value.filter((row) => row.status === statuses[statuses.length - 1]).length },
])

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value).toString()
  try {
    const response = await request(`${ENDPOINT}/export?${query}`)
    if (!response.ok) throw new Error('导出失败，请稍后重试')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = 'report_gen.csv'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(columns.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST', body: JSON.stringify(createValues.value),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '登记失败')
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('报表生成动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '报表生成操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('分析报表列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '报表生成列表读取失败'
  }
}

type DailyRound = {
  round_label: string
  status: string
  used_version: string | null
  metric_value: number | null
  promoted_versions: string[]
  waiting_versions: string[]
  generated_at: string
}

const dailyService = ref('API-METRIC')
const dailyRounds = ref<DailyRound[]>([])
const dailyMessage = ref('')

async function loadRounds() {
  dailyMessage.value = ''
  try {
    const response = await request('/api/daily_report/rounds')
    if (!response.ok) throw new Error('日报轮次读取失败')
    const payload = await response.json()
    dailyRounds.value = payload.items ?? []
  } catch (error) {
    dailyMessage.value = error instanceof Error ? error.message : '日报轮次读取失败'
  }
}

async function runDaily() {
  dailyMessage.value = ''
  try {
    const query = new URLSearchParams({ service_code: dailyService.value }).toString()
    const response = await request(`/api/daily_report/run?${query}`, { method: 'POST' })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || '日报计算失败')
    dailyMessage.value = payload.message
    await loadRounds()
  } catch (error) {
    dailyMessage.value = error instanceof Error ? error.message : '日报计算失败'
  }
}

onMounted(() => {
  void reload()
  void loadRounds()
})
</script>
