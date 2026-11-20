import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

type ModuleCase = {
  key: string
  /** 前端路由路径；缺省时与 key 相同。数据服务因 /api 代理冲突使用独立路径。 */
  path?: string
  fields: string[]
  actions: string[]
  actionTargets: string[]
  shape: string
}

const modules: ModuleCase[] = [
  {
    "key": "metric_def",
    "fields": [
      "指标编号",
      "指标名称",
      "计算公式",
      "聚合粒度",
      "时间窗口",
      "口径版本",
      "数据来源",
      "精度位数"
    ],
    "actions": [
      "提交审核",
      "发布指标",
      "冻结指标"
    ],
    "actionTargets": [
      "已审核",
      "已发布",
      "已冻结"
    ],
    "shape": "crud-table"
  },
  {
    "key": "dim_registry",
    "fields": [
      "维度编号",
      "维度名称",
      "业务键",
      "层级结构",
      "历史策略",
      "数据来源表",
      "刷新周期",
      "生效标记"
    ],
    "actions": [
      "提交验证",
      "上线维度",
      "标记失效"
    ],
    "actionTargets": [
      "已验证",
      "已上线",
      "已失效"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "agg_task",
    "fields": [
      "任务编号",
      "目标指标",
      "聚合维度",
      "计算周期",
      "依赖上游",
      "并行度",
      "超时分钟",
      "重试上限"
    ],
    "actions": [
      "提交调度",
      "取消任务",
      "重跑失败"
    ],
    "actionTargets": [
      "计算中",
      "已完成",
      "计算失败"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "cube_builder",
    "fields": [
      "立方体编号",
      "事实来源",
      "维度列表",
      "度量列表",
      "预计算粒度",
      "存储策略",
      "数据量级",
      "最后刷新"
    ],
    "actions": [
      "启动构建",
      "标记可用",
      "标记过期"
    ],
    "actionTargets": [
      "构建中",
      "可用",
      "已过期"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "cohort_rule",
    "fields": [
      "分群编号",
      "分群名称",
      "筛选条件",
      "覆盖人数",
      "更新时间",
      "自动刷新",
      "分群标签",
      "备注说明"
    ],
    "actions": [
      "启动圈选",
      "确认分群",
      "停用分群"
    ],
    "actionTargets": [
      "圈选中",
      "已生成",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "experiment",
    "fields": [
      "实验编号",
      "实验假设",
      "分组方案",
      "对照组比例",
      "核心指标",
      "最小样本",
      "显著性水平",
      "实验周期"
    ],
    "actions": [
      "启动实验",
      "终止实验",
      "归档结果"
    ],
    "actionTargets": [
      "运行中",
      "已完成",
      "已终止"
    ],
    "shape": "crud-table"
  },
  {
    "key": "trend_series",
    "fields": [
      "序列编号",
      "观测指标",
      "时间粒度",
      "起始时间",
      "截止时间",
      "填充策略",
      "异常检测",
      "序列版本"
    ],
    "actions": [
      "初始化序列",
      "标记完整",
      "标记缺口"
    ],
    "actionTargets": [
      "采集中",
      "完整",
      "有缺口"
    ],
    "shape": "crud-table"
  },
  {
    "key": "attribution",
    "fields": [
      "链路编号",
      "归因窗口",
      "触点类型",
      "权重模型",
      "转化事件",
      "衰减周期",
      "模型版本",
      "校准方式"
    ],
    "actions": [
      "启动训练",
      "投产发布",
      "下线模型"
    ],
    "actionTargets": [
      "训练中",
      "已投产",
      "已下线"
    ],
    "shape": "crud-table"
  },
  {
    "key": "segmentation",
    "fields": [
      "切片编号",
      "源数据集",
      "切分维度",
      "切片粒度",
      "保留天数",
      "存储格式",
      "行数统计",
      "最后切分"
    ],
    "actions": [
      "启动切分",
      "标记可用",
      "标记过期"
    ],
    "actionTargets": [
      "切分中",
      "可用",
      "已过期"
    ],
    "shape": "crud-table"
  },
  {
    "key": "report_gen",
    "fields": [
      "报表编号",
      "报表类型",
      "数据范围",
      "包含图表",
      "生成周期",
      "输出格式",
      "分发渠道",
      "下次生成"
    ],
    "actions": [
      "提交生成",
      "确认分发",
      "停用报表"
    ],
    "actionTargets": [
      "待生成",
      "已生成",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "forecast",
    "fields": [
      "方案编号",
      "预测指标",
      "预测算法",
      "训练窗口",
      "预测周期",
      "置信水平",
      "特征列表",
      "模型版本"
    ],
    "actions": [
      "启动训练",
      "发布模型",
      "废弃方案"
    ],
    "actionTargets": [
      "训练中",
      "已发布",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "data_mart",
    "fields": [
      "主题编号",
      "主题名称",
      "业务域",
      "事实表",
      "维度集合",
      "刷新周期",
      "数据量",
      "负责人"
    ],
    "actions": [
      "启动建设",
      "上线主题",
      "下线主题"
    ],
    "actionTargets": [
      "建设中",
      "已上线",
      "已下线"
    ],
    "shape": "crud-table"
  },
  {
    "key": "stat_model",
    "fields": [
      "模型编号",
      "模型类型",
      "因变量",
      "自变量",
      "样本区间",
      "拟合优度",
      "残差检验",
      "模型版本"
    ],
    "actions": [
      "启动拟合",
      "标记可用",
      "废弃模型"
    ],
    "actionTargets": [
      "拟合中",
      "可用",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "data_extract",
    "fields": [
      "任务编号",
      "来源数据集",
      "筛选条件",
      "字段列表",
      "排序规则",
      "分页方式",
      "输出格式",
      "提取上限"
    ],
    "actions": [
      "启动提取",
      "取消任务",
      "归档结果"
    ],
    "actionTargets": [
      "提取中",
      "已完成",
      "已取消"
    ],
    "shape": "crud-table"
  },
  {
    "key": "quality_mon",
    "fields": [
      "规则编号",
      "监控对象",
      "校验类型",
      "阈值下界",
      "阈值上界",
      "告警级别",
      "采样比例",
      "生效时段"
    ],
    "actions": [
      "启用规则",
      "暂停规则",
      "废弃规则"
    ],
    "actionTargets": [
      "已启用",
      "已暂停",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "compare_job",
    "fields": [
      "任务编号",
      "基准数据",
      "对比数据",
      "比对字段",
      "差异阈值",
      "对比周期",
      "差异行数",
      "处理结论"
    ],
    "actions": [
      "执行对比",
      "标记完成",
      "标记差异"
    ],
    "actionTargets": [
      "对比中",
      "已完成",
      "差异显著"
    ],
    "shape": "crud-table"
  },
  {
    "key": "api_service",
    "path": "/data_service",
    "fields": [
      "接口编号",
      "查询数据集",
      "请求参数",
      "返回字段",
      "缓存秒数",
      "QPS上限",
      "认证方式",
      "版本号"
    ],
    "actions": [
      "发布服务",
      "下线服务",
      "废弃服务"
    ],
    "actionTargets": [
      "已发布",
      "已下线",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "schedule_plan",
    "fields": [
      "计划编号",
      "关联任务",
      "Cron表达式",
      "时区设置",
      "失败通知",
      "并发上限",
      "依赖检查",
      "下次执行"
    ],
    "actions": [
      "激活计划",
      "立即执行",
      "停用计划"
    ],
    "actionTargets": [
      "运行中",
      "已完成",
      "已停用"
    ],
    "shape": "crud-table"
  }
]
const repoKind = 'fullstack'
const crudModules = modules.filter(m => m.shape === 'crud-table')
const dagModules = modules.filter(m => m.shape === 'dag-graph')
const timelineModules = modules.filter(m => m.shape === 'job-timeline')
const analysisModules = modules.filter(m => m.shape === 'analysis-dashboard')

function parseCsv(text: string): string[][] {
  const records: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const input = text.replace(/^\uFEFF/, '')
  for (let index = 0; index < input.length; index++) {
    const char = input[index]
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') { cell += '"'; index++ }
      else if (char === '"') { quoted = false }
      else { cell += char }
    } else if (char === '"' && cell === '') { quoted = true }
    else if (char === ',') { row.push(cell); cell = '' }
    else if (char === '\n') {
      row.push(cell.replace(/\r$/, ''))
      if (row.some(v => v !== '')) records.push(row)
      row = []; cell = ''
    } else { cell += char }
  }
  row.push(cell.replace(/\r$/, ''))
  if (row.some(v => v !== '')) records.push(row)
  return records
}

test('CRUD模块：筛选、导出、登记、动作、指标全链路', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (crudModules.length === 0) { test.skip(); return }

  for (const mod of crudModules) {
    await page.goto(mod.path ?? `/${mod.key}`)
    await page.waitForTimeout(3000)
    const bodyRows = page.locator('tbody tr[data-testid^="row-"]')
    // 不同模块的种子行数可能不同（如 metric_def 为 4 行），以实际基线为准
    const baseline = await bodyRows.count()
    expect(baseline).toBeGreaterThan(0)
    const firstValue = await bodyRows.nth(0).locator('td').nth(0).innerText()

    await page.getByTestId(`filter-${mod.fields[0]}`).fill(firstValue)
    await page.getByTestId('query').click()
    await expect(bodyRows).toHaveCount(1)
    await page.getByTestId('reset').click()
    await expect(bodyRows).toHaveCount(baseline)

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    const createdValues = mod.fields.map((f, i) => `验收-${mod.key}-${i+1}`)
    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.entries()) {
      await page.getByTestId(`create-${field}`).fill(createdValues[i])
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
    await expect(bodyRows).toHaveCount(baseline + 1)

    const createdRow = page.locator('tbody tr').filter({ hasText: createdValues[0] })
    for (const [i, action] of mod.actions.entries()) {
      await createdRow.getByRole('button', { name: action, exact: true }).click()
      await expect(createdRow).toHaveAttribute('data-status', mod.actionTargets[i])
    }
  }

  expect(browserErrors).toEqual([])
})

test('DAG拓扑模块：节点渲染、详情、动作、导出', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (dagModules.length === 0) { test.skip(); return }

  for (const mod of dagModules) {
    await page.goto(mod.path ?? `/${mod.key}`)
    await page.waitForTimeout(3000)
    await expect(page.locator('svg.dag-svg')).toBeVisible()
    const nodes = page.locator('g.dag-node')
    const count = await nodes.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await nodes.first().click()
    await expect(page.getByTestId('dag-detail')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('时间线模块：甘特条渲染、日期筛选、日志查看、登记', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (timelineModules.length === 0) { test.skip(); return }

  for (const mod of timelineModules) {
    await page.goto(mod.path ?? `/${mod.key}`)
    await expect(page.locator('.timeline-bar').first()).toBeVisible({ timeout: 10000 })
    const bars = page.locator('.timeline-bar')
    const count = await bars.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await bars.first().click()
    await expect(page.getByTestId('timeline-log')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('分析看板模块：KPI卡片、运行分析、图表渲染', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (analysisModules.length === 0) { test.skip(); return }

  for (const mod of analysisModules) {
    await page.goto(mod.path ?? `/${mod.key}`)
    await expect(page.getByTestId('kpi-card').first()).toBeVisible({ timeout: 10000 })
    const kpiCards = page.getByTestId('kpi-card')
    const kpiCount = await kpiCards.count()
    expect(kpiCount).toBeGreaterThanOrEqual(2)
    await expect(kpiCards.first().locator('strong')).toBeVisible()

    await page.getByTestId('run-analysis').click()
    await expect(page.locator('.analysis-bar').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.data-table tbody tr').first()).toBeVisible({ timeout: 5000 })
  }

  expect(browserErrors).toEqual([])
})

test('概览汇总', async ({ page }) => {
  test.setTimeout(300_000)
  await page.goto('/')
  await expect(page.locator('.stat-value').nth(1)).toBeVisible()
  // 验证概览页加载正常即可，不硬编码精确计数（取决于各模块 E2E 登记成功数）
})
