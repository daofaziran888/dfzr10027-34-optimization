<template>
  <section class="page" data-module="api_service">
    <header class="page-head">
      <div>
        <h2>数据服务管理</h2>
        <p class="page-desc">维护分析数据对外查询服务的版本管理、缓存策略和访问控制。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记服务接口</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出数据服务清单</button>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无数据服务数据，可先登记服务接口</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记服务接口</h3>
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

    <section class="release-panel" data-testid="release-panel">
      <header class="page-head">
        <div>
          <h3>服务版本发布与数据快照</h3>
          <p class="page-desc">发布前校验聚合产物完整性，就绪后固化版本快照并切换当前版本；产物迟到期间旧版本继续提供同口径数据。</p>
        </div>
        <div class="page-actions">
          <button class="btn" data-testid="release-refresh" type="button" @click="loadReleases">刷新发布状态</button>
          <button class="btn primary" data-testid="check-readiness" type="button" @click="checkReadiness">校验生效状态</button>
        </div>
      </header>

      <form class="filter-bar" data-testid="release-form" @submit.prevent="submitRelease">
        <label class="filter-item">
          <span>服务编号</span>
          <input v-model="releaseForm.service_code" data-testid="release-service-code" placeholder="如 API-METRIC" required />
        </label>
        <label class="filter-item">
          <span>版本号</span>
          <input v-model="releaseForm.version" data-testid="release-version" placeholder="如 v2.0" required />
        </label>
        <label class="filter-item">
          <span>指标编号</span>
          <input v-model="releaseForm.metric_code" data-testid="release-metric-code" placeholder="如 METR-GMV" required />
        </label>
        <button class="btn primary" data-testid="submit-release" type="submit" :disabled="releasing">
          {{ releasing ? '提交中…' : '提交发布' }}
        </button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>服务编号</th>
            <th>版本号</th>
            <th>生命周期</th>
            <th>产物就绪</th>
            <th>访问身份</th>
            <th>快照金额</th>
            <th>待发布版本</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in releaseRows" :key="`${item.service_code}-${item.version}`"
              :data-testid="`release-row-${item.version}`" :data-access="String(item.access)">
            <td>{{ item.service_code }}</td>
            <td>{{ item.version }}</td>
            <td>{{ item.lifecycle }}</td>
            <td>{{ item.readiness }}</td>
            <td>{{ item.access }}</td>
            <td>{{ item.snapshot?.value ?? '—' }}</td>
            <td>{{ item.pending_versions?.join(',') || '—' }}</td>
            <td class="row-actions">
              <button class="link" type="button" :data-testid="`offline-${item.version}`"
                      :disabled="item.lifecycle === '已下线'"
                      @click="offlineVersion(item)">下线版本</button>
            </td>
          </tr>
          <tr v-if="!releaseRows.length">
            <td colspan="8" class="empty-state">暂无版本发布记录，提交一次发布后在此观察交接状态</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span v-if="releaseMessage" class="error-text" data-testid="release-message">{{ releaseMessage }}</span>
      </footer>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条数据服务记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/api_service'
const columns = ["接口编号", "查询数据集", "请求参数", "返回字段", "缓存秒数", "QPS上限", "认证方式", "版本号"]
const actions = ["发布服务", "下线服务", "废弃服务"]
const statuses = ["草稿", "已发布", "已下线", "已废弃"]
const metricNames = ["服务总数", "已发布服务", "已下线服务"]

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
    link.download = 'api_service.csv'
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
      throw new Error('数据服务动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据服务操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('服务接口列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据服务列表读取失败'
  }
}

type ReleaseRow = {
  service_code: string
  version: string
  metric_code: string
  lifecycle: string
  readiness: string
  is_current: boolean
  access: string
  snapshot: { value: number | null } | null
  pending_versions: string[]
}

const releaseRows = ref<ReleaseRow[]>([])
const releaseMessage = ref('')
const releasing = ref(false)
const releaseForm = ref({ service_code: 'API-METRIC', version: '', metric_code: 'METR-GMV' })

async function loadReleases() {
  releaseMessage.value = ''
  try {
    const response = await request('/api/service_release/releases')
    if (!response.ok) throw new Error('版本发布状态读取失败')
    const payload = await response.json()
    releaseRows.value = payload.items ?? []
  } catch (error) {
    releaseMessage.value = error instanceof Error ? error.message : '版本发布状态读取失败'
  }
}

async function submitRelease() {
  releasing.value = true
  releaseMessage.value = ''
  try {
    const response = await request('/api/service_release/releases', {
      method: 'POST',
      body: JSON.stringify(releaseForm.value),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || '提交发布失败')
    releaseMessage.value = payload.message
    releaseForm.value.version = ''
    await loadReleases()
    await reload()
  } catch (error) {
    releaseMessage.value = error instanceof Error ? error.message : '提交发布失败'
  } finally {
    releasing.value = false
  }
}

async function checkReadiness() {
  releaseMessage.value = ''
  try {
    const response = await request('/api/service_release/check-readiness', { method: 'POST' })
    const payload = await response.json()
    if (!response.ok) throw new Error('生效状态校验失败')
    releaseMessage.value = payload.message
    await loadReleases()
    await reload()
  } catch (error) {
    releaseMessage.value = error instanceof Error ? error.message : '生效状态校验失败'
  }
}

async function offlineVersion(item: ReleaseRow) {
  releaseMessage.value = ''
  try {
    const response = await request(
      `/api/service_release/services/${encodeURIComponent(item.service_code)}/versions/${encodeURIComponent(item.version)}/offline`,
      { method: 'POST' },
    )
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || '下线失败')
    releaseMessage.value = payload.message
    await loadReleases()
    await reload()
  } catch (error) {
    releaseMessage.value = error instanceof Error ? error.message : '下线失败'
  }
}

onMounted(() => {
  void reload()
  void loadReleases()
})
</script>
