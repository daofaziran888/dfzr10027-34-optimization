import { expect, test } from '@playwright/test'

/**
 * 服务版本发布就绪与版本化快照的端到端剧本：
 * 200 元旧版发布 -> 新版先发布但无产物（旧版继续服务）->
 * 240 元产物迟到、校验生效后切换 -> 下线旧版 -> 当前/历史访问状态与金额核对。
 */
async function callApi(method: string, path: string, body?: unknown) {
  const resp = await fetch(`http://127.0.0.1:5173${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return resp.json()
}

function gmv(metric: string, value: number) {
  return { metric_code: metric, granularity: '日', value, unit: '元', point_count: 30 }
}

test.describe('数据服务版本发布交接', () => {
  test('产物迟到期间旧版继续服务，就绪后切换，下线后历史可查', async ({ page }) => {
    const code = `API-E2E-${Date.now()}`
    const metric = `METR-E2E-${Date.now()}`

    // 1) v1.0 携带 200 元产物发布
    await callApi('POST', '/api/service_release/artifacts',
      { metric_code: metric, version: 'v1.0', payload: gmv(metric, 200) })
    const r1 = await callApi('POST', '/api/service_release/releases',
      { service_code: code, version: 'v1.0', metric_code: metric })
    expect(r1.entry.lifecycle).toBe('已发布')
    expect(r1.entry.snapshot.value).toBe(200)

    // 2) v2.0 提交发布但不给产物
    const r2 = await callApi('POST', '/api/service_release/releases',
      { service_code: code, version: 'v2.0', metric_code: metric })
    expect(r2.entry.lifecycle).toBe('待发布')
    expect(r2.entry.readiness).toBe('待产物')

    // 3) 打开数据服务页面，面板应展示两个版本且旧版仍为当前
    await page.goto('/data_service')
    await expect(page.getByTestId('release-panel')).toBeVisible()
    const panel = page.getByTestId('release-panel')
    const rowFor = (version: string) =>
      panel.getByTestId(`release-row-${version}`).filter({ hasText: code })
    await expect(rowFor('v1.0')).toHaveAttribute('data-access', '当前版本')
    await expect(rowFor('v2.0')).toHaveAttribute('data-access', '历史版本')
    expect(await rowFor('v1.0').locator('td').nth(5).innerText()).toBe('200')

    // 4) 240 元新产物迟到交付，点击「校验生效状态」后切换
    await callApi('POST', '/api/service_release/artifacts',
      { metric_code: metric, version: 'v2.0', payload: gmv(metric, 240) })
    await page.getByTestId('check-readiness').click()
    await expect(rowFor('v2.0')).toHaveAttribute('data-access', '当前版本')
    await expect(rowFor('v1.0')).toHaveAttribute('data-access', '历史版本')
    expect(await rowFor('v2.0').locator('td').nth(5).innerText()).toBe('240')

    // 5) 下线旧版 v1.0
    await rowFor('v1.0').getByTestId('offline-v1.0').click()
    await expect(rowFor('v1.0')).toHaveAttribute('data-access', '已下线版本')
    // 当前版本仍是 240 的 v2.0
    await expect(rowFor('v2.0')).toHaveAttribute('data-access', '当前版本')

    // 6) 接口侧核对当前与历史访问的状态和金额
    const current = await callApi('GET', `/api/service_release/services/${code}/current`)
    expect(current.version).toBe('v2.0')
    expect(current.snapshot.value).toBe(240)
    const old = await callApi('GET', `/api/service_release/services/${code}/versions/v1.0`)
    expect(old.access).toBe('已下线版本')
    expect(old.snapshot.value).toBe(200)

    // 7) 切换完成后日报使用当前版本 v2.0/240
    const daily = await callApi('POST', `/api/daily_report/run?service_code=${code}&round_label=e2e-after`)
    expect(daily.entry.used_version).toBe('v2.0')
    expect(daily.entry.metric_value).toBe(240)
  })

  test('日报在产物未就绪时使用旧版本，且登记记录标明待发布', async ({ page }) => {
    const code = `API-E2E-${Date.now()}`
    const metric = `METR-E2E-${Date.now()}`
    const label = `e2e-wait-${Date.now()}`
    await callApi('POST', '/api/service_release/artifacts',
      { metric_code: metric, version: 'v1.0', payload: gmv(metric, 200) })
    await callApi('POST', '/api/service_release/releases',
      { service_code: code, version: 'v1.0', metric_code: metric, entry_id: 1 })
    // v2.0 只提交发布，刻意不交付产物
    await callApi('POST', '/api/service_release/releases',
      { service_code: code, version: 'v2.0', metric_code: metric, entry_id: 1 })

    const round = await callApi('POST', `/api/daily_report/run?service_code=${code}&round_label=${label}`)
    expect(round.entry.used_version).toBe('v1.0')
    expect(round.entry.metric_value).toBe(200)
    expect(round.entry.waiting_versions).toContain('v2.0')

    // 报表页日报面板能看到这一轮
    await page.goto('/report_gen')
    await expect(page.getByTestId('daily-panel')).toBeVisible()
    const row = page.getByTestId(`daily-row-${label}`)
    await expect(row).toHaveCount(1)
    expect(await row.innerText()).toContain('v1.0')
  })
})
