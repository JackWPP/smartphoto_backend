const API_BASE = import.meta.env.VITE_ADMIN_API_BASE || '/api/admin/v1'

let accessToken = ''

function headers(extra = {}) {
  return {
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...extra,
  }
}

async function request(method, path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers(),
    },
    credentials: 'include',
    body: body && method !== 'GET' ? JSON.stringify(body) : undefined,
  })
  const rawText = await response.text()
  let data = null
  if (rawText) {
    try {
      data = JSON.parse(rawText)
    } catch {
      throw new Error(`Invalid ${response.status} response from admin API`)
    }
  }
  if (!data) {
    throw new Error(`Empty ${response.status} response from admin API`)
  }
  if (!response.ok || data.code !== 0) {
    throw new Error(data.message || 'Request failed')
  }
  return data.data
}

export const adminApi = {
  setAccessToken(token) {
    accessToken = token || ''
  },
  login(payload) {
    return request('POST', '/auth/login', payload)
  },
  me() {
    return request('GET', '/auth/me')
  },
  logout() {
    return request('POST', '/auth/logout')
  },
  dashboard() {
    return request('GET', '/dashboard/summary')
  },
  listSessions(params = '') {
    return request('GET', `/sessions${params ? `?${params}` : ''}`)
  },
  getSession(sessionId) {
    return request('GET', `/sessions/${sessionId}`)
  },
  updateCopy(sessionId, payload) {
    return request('PUT', `/sessions/${sessionId}/copy`, payload)
  },
  listJobs(params = '') {
    return request('GET', `/jobs${params ? `?${params}` : ''}`)
  },
  getJob(jobId) {
    return request('GET', `/jobs/${jobId}`)
  },
  retryJob(jobId) {
    return request('POST', `/jobs/${jobId}/retry`)
  },
  listAssets(params = '') {
    return request('GET', `/assets${params ? `?${params}` : ''}`)
  },
  getAsset(assetId) {
    return request('GET', `/assets/${assetId}`)
  },
  archiveAsset(assetId, reason) {
    return request('POST', `/assets/${assetId}/archive`, { reason })
  },
  restoreAsset(assetId) {
    return request('POST', `/assets/${assetId}/restore`)
  },
  regenerateAsset(assetId, reason) {
    return request('POST', `/assets/${assetId}/actions/regenerate`, { reason })
  },
  listPromptPresets(params = '') {
    return request('GET', `/prompt-presets${params ? `?${params}` : ''}`)
  },
  listRulePacks(params = '') {
    return request('GET', `/rule-packs${params ? `?${params}` : ''}`)
  },
  getRulePack(id) {
    return request('GET', `/rule-packs/${id}`)
  },
  publishRulePack(id) {
    return request('POST', `/rule-packs/${id}/publish`)
  },
  listAuditLogs(params = '') {
    return request('GET', `/audit-logs${params ? `?${params}` : ''}`)
  },
}
