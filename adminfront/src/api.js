const API_BASE = import.meta.env.VITE_ADMIN_API_BASE || '/api/admin/v1'
const TOKEN_STORAGE_KEY = 'smartphoto_admin_access_token'

let accessToken = localStorage.getItem(TOKEN_STORAGE_KEY) || ''

function persistAccessToken(token) {
  accessToken = token || ''
  if (accessToken) {
    localStorage.setItem(TOKEN_STORAGE_KEY, accessToken)
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  }
}

function buildQuery(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    if (Array.isArray(value)) {
      value.forEach((item) => query.append(key, item))
      return
    }
    query.set(key, String(value))
  })
  const raw = query.toString()
  return raw ? `?${raw}` : ''
}

async function parseResponse(response) {
  const rawText = await response.text()
  if (!rawText) {
    throw new Error(`Empty ${response.status} response from admin API`)
  }
  let payload
  try {
    payload = JSON.parse(rawText)
  } catch {
    throw new Error(`Invalid ${response.status} response from admin API`)
  }
  if (!response.ok || payload.code !== 0) {
    const error = new Error(payload.message || 'Request failed')
    error.status = response.status
    error.code = payload.code
    error.payload = payload
    throw error
  }
  return payload.data
}

async function refreshAccessToken() {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
  })
  const data = await parseResponse(response)
  persistAccessToken(data.access_token)
  return data
}

async function request(method, path, options = {}) {
  const { body, headers = {}, skipRetry = false, signal } = options
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body && method !== 'GET' ? JSON.stringify(body) : undefined,
  })
  if (
    response.status === 401 &&
    !skipRetry &&
    !path.startsWith('/auth/login') &&
    !path.startsWith('/auth/refresh') &&
    !path.startsWith('/auth/logout')
  ) {
    try {
      await refreshAccessToken()
      return request(method, path, { ...options, skipRetry: true })
    } catch (error) {
      persistAccessToken('')
      throw error
    }
  }
  return parseResponse(response)
}

export const adminApi = {
  getAccessToken() {
    return accessToken
  },
  setAccessToken(token) {
    persistAccessToken(token)
  },
  buildQuery,
  login(payload) {
    return request('POST', '/auth/login', { body: payload, skipRetry: true })
  },
  refresh() {
    return refreshAccessToken()
  },
  me() {
    return request('GET', '/auth/me')
  },
  logout() {
    return request('POST', '/auth/logout', { skipRetry: true }).finally(() => {
      persistAccessToken('')
    })
  },
  dashboardSummary() {
    return request('GET', '/dashboard/summary')
  },
  dashboardOverview() {
    return request('GET', '/dashboard/overview')
  },
  dashboardTrends(params = {}) {
    return request('GET', `/dashboard/trends${buildQuery(params)}`)
  },
  listSessions(params = {}) {
    return request('GET', `/sessions${buildQuery(params)}`)
  },
  getSession(sessionId) {
    return request('GET', `/sessions/${sessionId}`)
  },
  updateCopy(sessionId, payload) {
    return request('PUT', `/sessions/${sessionId}/copy`, { body: payload })
  },
  updateParameters(sessionId, payload) {
    return request('PUT', `/sessions/${sessionId}/parameters`, { body: payload })
  },
  updateStrategyOverrides(sessionId, payload) {
    return request('PUT', `/sessions/${sessionId}/strategy/overrides`, { body: payload })
  },
  updateDetailStrategyOverrides(sessionId, payload) {
    return request('PUT', `/sessions/${sessionId}/detail-pages/strategy/overrides`, { body: payload })
  },
  buildSessionStrategyPreview(sessionId, payload = {}) {
    return request('POST', `/sessions/${sessionId}/strategy/preview`, { body: payload })
  },
  buildDetailStrategyPreview(sessionId, payload = {}) {
    return request('POST', `/sessions/${sessionId}/detail-pages/strategy/preview`, { body: payload })
  },
  previewSessionPrompts(sessionId, payload = {}) {
    return request('POST', `/sessions/${sessionId}/prompts/preview`, { body: payload })
  },
  previewDetailPrompts(sessionId, payload = {}) {
    return request('POST', `/sessions/${sessionId}/detail-pages/prompts/preview`, { body: payload })
  },
  getSessionResults(sessionId, params = {}) {
    return request('GET', `/sessions/${sessionId}/results${buildQuery(params)}`)
  },
  getSessionDetailResults(sessionId, params = {}) {
    return request('GET', `/sessions/${sessionId}/detail-pages/results${buildQuery(params)}`)
  },
  reanalyzeSession(sessionId, payload) {
    return request('POST', `/sessions/${sessionId}/actions/reanalyze`, { body: payload })
  },
  extractSessionParameters(sessionId, payload) {
    return request('POST', `/sessions/${sessionId}/actions/extract-parameters`, { body: payload })
  },
  regenerateMainGallery(sessionId, payload) {
    return request('POST', `/sessions/${sessionId}/actions/regenerate-main`, { body: payload })
  },
  regenerateDetailPage(sessionId, payload) {
    return request('POST', `/sessions/${sessionId}/actions/regenerate-detail`, { body: payload })
  },
  listJobs(params = {}) {
    return request('GET', `/jobs${buildQuery(params)}`)
  },
  getJob(jobId) {
    return request('GET', `/jobs/${jobId}`)
  },
  getJobEvents(jobId, params = {}) {
    return request('GET', `/jobs/${jobId}/events/history${buildQuery(params)}`)
  },
  retryJob(jobId, payload) {
    return request('POST', `/jobs/${jobId}/retry`, { body: payload })
  },
  listAssets(params = {}) {
    return request('GET', `/assets${buildQuery(params)}`)
  },
  getAsset(assetId) {
    return request('GET', `/assets/${assetId}`)
  },
  archiveAsset(assetId, payload) {
    return request('POST', `/assets/${assetId}/archive`, { body: payload })
  },
  restoreAsset(assetId, payload) {
    return request('POST', `/assets/${assetId}/restore`, { body: payload })
  },
  regenerateAsset(assetId, payload) {
    return request('POST', `/assets/${assetId}/actions/regenerate`, { body: payload })
  },
  listPromptPresets(params = {}) {
    return request('GET', `/prompt-presets${buildQuery(params)}`)
  },
  getPromptPreset(id) {
    return request('GET', `/prompt-presets/${id}`)
  },
  createPromptPreset(payload) {
    return request('POST', '/prompt-presets', { body: payload })
  },
  updatePromptPreset(id, payload) {
    return request('PUT', `/prompt-presets/${id}`, { body: payload })
  },
  archivePromptPreset(id, payload) {
    return request('POST', `/prompt-presets/${id}/archive`, { body: payload })
  },
  clonePromptPreset(id, payload) {
    return request('POST', `/prompt-presets/${id}/clone`, { body: payload })
  },
  listCategoryCatalog(params = {}) {
    return request('GET', `/category-catalog${buildQuery(params)}`)
  },
  getCategoryCatalog(id) {
    return request('GET', `/category-catalog/${id}`)
  },
  createCategoryCatalog(payload) {
    return request('POST', '/category-catalog', { body: payload })
  },
  updateCategoryCatalog(id, payload) {
    return request('PUT', `/category-catalog/${id}`, { body: payload })
  },
  archiveCategoryCatalog(id, payload) {
    return request('POST', `/category-catalog/${id}/archive`, { body: payload })
  },
  restoreCategoryCatalog(id, payload) {
    return request('POST', `/category-catalog/${id}/restore`, { body: payload })
  },
  listRulePacks(params = {}) {
    return request('GET', `/rule-packs${buildQuery(params)}`)
  },
  getRulePack(id) {
    return request('GET', `/rule-packs/${id}`)
  },
  createRulePack(payload) {
    return request('POST', '/rule-packs', { body: payload })
  },
  updateRulePack(id, payload) {
    return request('PUT', `/rule-packs/${id}`, { body: payload })
  },
  publishRulePack(id, payload) {
    return request('POST', `/rule-packs/${id}/publish`, { body: payload })
  },
  cloneRulePack(id, payload) {
    return request('POST', `/rule-packs/${id}/clone`, { body: payload })
  },
  archiveRulePack(id, payload) {
    return request('POST', `/rule-packs/${id}/archive`, { body: payload })
  },
  listAuditLogs(params = {}) {
    return request('GET', `/audit-logs${buildQuery(params)}`)
  },
  getSystemRuntime() {
    return request('GET', '/system/runtime')
  },
  listPlatformConfigs(params = {}) {
    return request('GET', `/platform-configs${buildQuery(params)}`)
  },
  getPlatformConfig(id) {
    return request('GET', `/platform-configs/${id}`)
  },
  createPlatformConfig(payload) {
    return request('POST', '/platform-configs', { body: payload })
  },
  updatePlatformConfig(id, payload) {
    return request('PUT', `/platform-configs/${id}`, { body: payload })
  },
  deletePlatformConfig(id) {
    return request('DELETE', `/platform-configs/${id}`)
  },
}
