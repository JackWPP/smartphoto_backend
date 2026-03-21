/**
 * SmartPhoto Backend API Service
 * 调试前端统一 API 调用封装
 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v2'
const ACCESS_TOKEN_KEY = 'smartphoto_access_token'

let accessToken = localStorage.getItem(ACCESS_TOKEN_KEY) || ''
let refreshPromise = null

export const GENERATION_MODES = [
  { value: 'main_gallery', label: '主图组' },
  { value: 'detail_page', label: '详情页' },
]

function isAuthPath(path) {
  return path.startsWith('/auth/')
}

function emitApiLog(log) {
  window.dispatchEvent(new CustomEvent('api-log', { detail: log }))
}

function setAccessToken(token) {
  accessToken = token || ''
  if (accessToken) {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    return
  }
  localStorage.removeItem(ACCESS_TOKEN_KEY)
}

function buildHeaders(options = {}) {
  const headers = { ...(options.headers || {}) }
  if (!options.formData && headers['Content-Type'] !== null) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json'
  }
  if (accessToken && !options.skipAuth) {
    headers.Authorization = `Bearer ${accessToken}`
  }
  if (headers['Content-Type'] === null) {
    delete headers['Content-Type']
  }
  return headers
}

async function parseResponseBody(response) {
  const rawText = await response.text()
  if (!rawText) {
    return null
  }
  try {
    return JSON.parse(rawText)
  } catch {
    return { code: response.status, message: rawText }
  }
}

async function rawRequest(method, path, options = {}) {
  const url = `${API_BASE}${path}`
  const config = {
    method,
    headers: buildHeaders(options),
    credentials: 'include',
    signal: options.signal,
  }

  if (options.body && method !== 'GET') {
    config.body = JSON.stringify(options.body)
  }

  if (options.formData) {
    delete config.headers['Content-Type']
    config.body = options.formData
  }

  const startTime = Date.now()
  let response = null
  let data = null
  let error = null

  try {
    response = await fetch(url, config)
    data = await parseResponseBody(response)
    if (!response.ok || (data && data.code !== 0)) {
      error = {
        status: response.status,
        code: data?.code || response.status,
        message: data?.message || 'Request failed',
      }
    }
  } catch (e) {
    error = {
      status: 0,
      code: 0,
      message: e.message || 'Network error',
    }
  }

  const log = {
    timestamp: new Date().toISOString(),
    method,
    path,
    status: response?.status || error?.status || 0,
    duration: Date.now() - startTime,
    request: options.body || options.formData ? options : null,
    response: data,
    error,
  }
  emitApiLog(log)
  return { response, data, error }
}

async function tryRefreshToken() {
  if (refreshPromise) {
    return refreshPromise
  }
  refreshPromise = (async () => {
    const { data, error } = await rawRequest('POST', '/auth/refresh', {
      skipAuth: true,
      skipRefresh: true,
    })
    if (error || !data?.data?.access_token) {
      setAccessToken('')
      return false
    }
    setAccessToken(data.data.access_token)
    return true
  })()

  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

async function request(method, path, options = {}) {
  const { data, error } = await rawRequest(method, path, options)
  if (error?.status === 401 && !options.skipRefresh && !isAuthPath(path)) {
    const refreshed = await tryRefreshToken()
    if (refreshed) {
      return request(method, path, { ...options, skipRefresh: true })
    }
  }
  if (error) {
    throw error
  }
  return data?.data
}

async function uploadWithPresign(sessionId, file, uploadKind, extra = {}) {
  const normalizedDisplayOrder = Math.max(1, Number(extra.display_order) || 1)
  const presign = await request('POST', '/uploads/presign', {
    body: {
      session_id: sessionId,
      upload_kind: uploadKind,
      original_name: file.name,
      content_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
      display_order: normalizedDisplayOrder,
      slot_type: extra.slot_type || null,
    },
  })

  const uploadUrl = /^https?:\/\//i.test(presign.upload_url) ? presign.upload_url : presign.upload_url
  const uploadHeaders = { ...(presign.headers || {}) }
  const includeCredentials =
    !/^https?:\/\//i.test(uploadUrl) || uploadUrl.startsWith(window.location.origin)
  let uploadResponse

  if (presign.method === 'POST' && presign.form_fields && Object.keys(presign.form_fields).length > 0) {
    const formData = new FormData()
    Object.entries(presign.form_fields).forEach(([key, value]) => {
      formData.append(key, value)
    })
    formData.append('file', file)
    uploadResponse = await fetch(uploadUrl, {
      method: 'POST',
      body: formData,
      credentials: includeCredentials ? 'include' : 'omit',
    })
  } else {
    uploadResponse = await fetch(uploadUrl, {
      method: presign.method || 'PUT',
      headers: uploadHeaders,
      body: file,
      credentials: includeCredentials ? 'include' : 'omit',
    })
  }

  if (!uploadResponse.ok) {
    throw {
      status: uploadResponse.status,
      code: uploadResponse.status,
      message: 'Direct upload failed',
    }
  }

  return request('POST', '/uploads/complete', {
    body: { upload_id: presign.upload_id },
  })
}

function buildQuery(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return
    }
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== null && item !== undefined && item !== '') {
          query.append(key, item)
        }
      })
      return
    }
    query.append(key, value)
  })
  const suffix = query.toString()
  return suffix ? `?${suffix}` : ''
}

function normalizeSseEventPayload(rawEvent, eventName = '') {
  if (rawEvent && typeof rawEvent === 'object' && !Array.isArray(rawEvent)) {
    if (eventName && !rawEvent.event) {
      return { ...rawEvent, event: eventName }
    }
    return rawEvent
  }
  return {
    event: eventName || 'message',
    payload: rawEvent,
  }
}

function parseSseBlock(block) {
  const lines = block.split('\n')
  const dataLines = []
  let eventName = ''

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    if (!line || line.startsWith(':')) {
      continue
    }
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (!dataLines.length) {
    return null
  }

  const payloadText = dataLines.join('\n')
  try {
    return normalizeSseEventPayload(JSON.parse(payloadText), eventName)
  } catch {
    return normalizeSseEventPayload(payloadText, eventName)
  }
}

async function downloadFile(path, fallbackFilename) {
  const url = `${API_BASE}${path}`
  const buildConfig = () => ({
    method: 'GET',
    headers: buildHeaders({ headers: { 'Content-Type': null } }),
    credentials: 'include',
  })
  let config = buildConfig()
  let response = await fetch(url, config)
  if (response.status === 401) {
    const refreshed = await tryRefreshToken()
    if (!refreshed) {
      throw { status: 401, code: 401, message: '登录已失效，请重新登录' }
    }
    config = buildConfig()
    response = await fetch(url, config)
  }
  if (!response.ok) {
    const data = await parseResponseBody(response)
    throw {
      status: response.status,
      code: data?.code || response.status,
      message: data?.message || 'Download failed',
    }
  }
  const blob = await response.blob()
  const blobUrl = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const contentDisposition = response.headers.get('content-disposition') || ''
  const matched = /filename="?([^"]+)"?/i.exec(contentDisposition)
  anchor.href = blobUrl
  anchor.download = matched?.[1] || fallbackFilename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(blobUrl)
}

async function openSseStream(path, onEvent, onError, onComplete, allowRefresh = true) {
  const controller = new AbortController()
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'GET',
    headers: buildHeaders({ headers: { 'Content-Type': null } }),
    credentials: 'include',
    signal: controller.signal,
  })

  if (response.status === 401 && allowRefresh) {
    const refreshed = await tryRefreshToken()
    if (refreshed) {
      return openSseStream(path, onEvent, onError, onComplete, false)
    }
  }

  if (!response.ok || !response.body) {
    const data = await parseResponseBody(response)
    throw {
      status: response.status,
      code: data?.code || response.status,
      message: data?.message || 'SSE request failed',
    }
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let closed = false

  const close = () => {
    if (closed) {
      return
    }
    closed = true
    controller.abort()
    reader.cancel().catch(() => {})
  }

  ;(async () => {
    try {
      while (!closed) {
        const { value, done } = await reader.read()
        if (done) {
          break
        }
        buffer += decoder.decode(value, { stream: true })
        buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
        while (buffer.includes('\n\n')) {
          const boundary = buffer.indexOf('\n\n')
          const chunk = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          const event = parseSseBlock(chunk)
          if (!event) {
            continue
          }
          onEvent?.(event)
          if (['job_succeeded', 'job_failed'].includes(event.event)) {
            close()
            onComplete?.(event)
            return
          }
        }
      }
      if (!closed) {
        onComplete?.()
      }
    } catch (error) {
      if (!closed && error?.name !== 'AbortError') {
        onError?.(error)
      }
    }
  })()

  return close
}

export const api = {
  setAccessToken,
  getAccessToken: () => accessToken,
  hasAccessToken: () => Boolean(accessToken),

  // ===== Auth =====
  register: (payload) => request('POST', '/auth/register', { body: payload, skipAuth: true, skipRefresh: true }),
  login: (payload) => request('POST', '/auth/login', { body: payload, skipAuth: true, skipRefresh: true }),
  refresh: () => request('POST', '/auth/refresh', { skipAuth: true, skipRefresh: true }),
  logout: () => request('POST', '/auth/logout', { skipRefresh: true }),
  me: () => request('GET', '/auth/me', { skipRefresh: false }),

  // ===== Account =====
  getAccountOverview: () => request('GET', '/account/overview'),
  getAccountProfile: () => request('GET', '/account/profile'),
  updateAccountProfile: (payload) => request('PUT', '/account/profile', { body: payload }),
  getAccountAssets: (params = {}) => request('GET', `/account/assets${buildQuery(params)}`),
  getAccountNotifications: (limit = 20) => request('GET', `/account/notifications${buildQuery({ limit })}`),
  markNotificationRead: (notificationId) => request('POST', `/account/notifications/${notificationId}/read`),
  markAllNotificationsRead: () => request('POST', '/account/notifications/read-all'),
  changePassword: (payload) => request('POST', '/account/security/change-password', { body: payload }),
  getAccountSettings: () => request('GET', '/account/settings'),
  updateAccountSettings: (payload) => request('PUT', '/account/settings', { body: payload }),
  getPurchases: () => request('GET', '/account/purchases'),
  getWallet: () => request('GET', '/account/wallet'),
  getWalletTransactions: () => request('GET', '/account/wallet/transactions'),
  getAccountPricing: () => request('GET', '/account/pricing'),

  // ===== Health =====
  health: () => request('GET', '/healthz', { skipRefresh: true }),

  // ===== Platforms =====
  getPlatforms: () => request('GET', '/platforms', { skipRefresh: true }),

  // ===== Sessions =====
  createSession: () => request('POST', '/sessions'),
  getSession: (sessionId) => request('GET', `/sessions/${sessionId}`),

  // ===== Images =====
  uploadImage: (sessionId, file, slotType, displayOrder) => {
    return uploadWithPresign(sessionId, file, 'session_image', { slot_type: slotType, display_order: displayOrder }).then(
      async (complete) => {
        const images = await request('GET', `/sessions/${sessionId}/images`)
        return {
          image_id: complete.resource_id,
          session_id: sessionId,
          uploaded_images: (images.images || []).map((img) => ({
            image_id: img.image_id,
            slot_type: img.slot_type,
            display_order: img.display_order,
            url: img.url,
          })),
        }
      },
    )
  },

  deleteImage: (sessionId, imageId) => request('DELETE', `/sessions/${sessionId}/images/${imageId}`),

  getSessionImages: (sessionId) => request('GET', `/sessions/${sessionId}/images`),

  // ===== Detail Style Images =====
  uploadDetailStyleImage: (sessionId, file, displayOrder) => {
    return uploadWithPresign(sessionId, file, 'detail_style_image', { display_order: displayOrder }).then(async (complete) => {
      const images = await request('GET', `/sessions/${sessionId}/detail-pages/style-images`)
      return {
        image_id: complete.resource_id,
        session_id: sessionId,
        uploaded_images: (images.images || []).map((img) => ({
          image_id: img.image_id,
          display_order: img.display_order,
          url: img.url,
        })),
      }
    })
  },

  deleteDetailStyleImage: (sessionId, imageId) =>
    request('DELETE', `/sessions/${sessionId}/detail-pages/style-images/${imageId}`),

  getDetailStyleImages: (sessionId) =>
    request('GET', `/sessions/${sessionId}/detail-pages/style-images`),

  // ===== Parameter Attachments =====
  uploadParameterAttachment: (sessionId, file, displayOrder) => {
    return uploadWithPresign(sessionId, file, 'parameter_attachment', { display_order: displayOrder }).then(async (complete) => {
      const attachments = await request('GET', `/sessions/${sessionId}/parameter-attachments`)
      return {
        attachment_id: complete.resource_id,
        session_id: sessionId,
        uploaded_attachments: attachments.attachments || [],
      }
    })
  },

  deleteParameterAttachment: (sessionId, attachmentId) =>
    request('DELETE', `/sessions/${sessionId}/parameter-attachments/${attachmentId}`),

  getParameterAttachments: (sessionId) =>
    request('GET', `/sessions/${sessionId}/parameter-attachments`),

  extractParameters: (sessionId) =>
    request('POST', `/sessions/${sessionId}/parameters/extract`),

  getParameters: (sessionId) =>
    request('GET', `/sessions/${sessionId}/parameters`),

  saveParameters: (sessionId, parameterSnapshot) =>
    request('PUT', `/sessions/${sessionId}/parameters`, { body: parameterSnapshot }),

  // ===== Strategy Reference Images =====
  uploadStrategyReferenceImage: (sessionId, file, displayOrder) => {
    return uploadWithPresign(sessionId, file, 'strategy_reference_image', { display_order: displayOrder }).then(async (complete) => {
      const images = await request('GET', `/sessions/${sessionId}/strategy-reference-images`)
      return {
        image_id: complete.resource_id,
        session_id: sessionId,
        uploaded_images: (images.images || []).map((img) => ({
          image_id: img.image_id,
          display_order: img.display_order,
          url: img.url,
        })),
      }
    })
  },

  deleteStrategyReferenceImage: (sessionId, imageId) =>
    request('DELETE', `/sessions/${sessionId}/strategy-reference-images/${imageId}`),

  getStrategyReferenceImages: (sessionId) =>
    request('GET', `/sessions/${sessionId}/strategy-reference-images`),

  // ===== Analysis =====
  triggerAnalysis: (sessionId, idempotencyKey) =>
    request('POST', `/sessions/${sessionId}/analysis`, {
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),

  getAnalysis: (sessionId) => request('GET', `/sessions/${sessionId}/analysis`),

  // ===== Platform Selection =====
  setPlatformSelection: (sessionId, selectedIds, activeId) =>
    request('PUT', `/sessions/${sessionId}/platform-selection`, {
      body: { selected_platform_ids: selectedIds, active_platform_id: activeId },
    }),

  // ===== Copy =====
  getCopy: (sessionId) => request('GET', `/sessions/${sessionId}/copy`),

  saveCopy: (sessionId, copyData) =>
    request('PUT', `/sessions/${sessionId}/copy`, { body: copyData }),

  regenerateCopy: (sessionId, targets, instruction, idempotencyKey) =>
    request('POST', `/sessions/${sessionId}/copy/regenerate`, {
      body: { targets, instruction, based_on_current_values: true },
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),

  getCopyRegenerateResult: (sessionId, jobId) =>
    request('GET', `/sessions/${sessionId}/copy/regenerate/${jobId}`),

  // ===== Strategy =====
  buildStrategy: (sessionId, plannerInstruction = null, slotPreferences = []) =>
    request('POST', `/sessions/${sessionId}/strategy/preview`, {
      body: { planner_instruction: plannerInstruction, slot_preferences: slotPreferences },
    }),

  previewPrompts: (sessionId, instruction, includeLatestAssets = true) =>
    request('POST', `/sessions/${sessionId}/prompts/preview`, {
      body: { instruction, include_latest_assets: includeLatestAssets },
    }),

  buildDetailStrategy: (sessionId, plannerInstruction = null, panelPreferences = []) =>
    request('POST', `/sessions/${sessionId}/detail-pages/strategy/preview`, {
      body: { planner_instruction: plannerInstruction, panel_preferences: panelPreferences },
    }),

  getDetailStrategyOverrides: (sessionId) =>
    request('GET', `/sessions/${sessionId}/detail-pages/strategy/overrides`),

  saveDetailStrategyOverrides: (sessionId, overrides) =>
    request('PUT', `/sessions/${sessionId}/detail-pages/strategy/overrides`, {
      body: { overrides },
    }),

  getStrategyOverrides: (sessionId) =>
    request('GET', `/sessions/${sessionId}/strategy/overrides`),

  saveStrategyOverrides: (sessionId, overrides) =>
    request('PUT', `/sessions/${sessionId}/strategy/overrides`, {
      body: { overrides },
    }),

  previewDetailPrompts: (sessionId, instruction, includeLatestAssets = true) =>
    request('POST', `/sessions/${sessionId}/detail-pages/prompts/preview`, {
      body: { instruction, include_latest_assets: includeLatestAssets },
    }),

  // ===== Generation =====
  generateGallery: (sessionId, instruction, idempotencyKey, slotIds = []) =>
    request('POST', `/sessions/${sessionId}/generations`, {
      body: { instruction, slot_ids: slotIds },
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),

  generateDetailPage: (sessionId, instruction, idempotencyKey) =>
    request('POST', `/sessions/${sessionId}/detail-pages/generations`, {
      body: { instruction },
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),

  getResults: (sessionId, version) => request('GET', `/sessions/${sessionId}/results${buildQuery({ version })}`),

  getDetailResults: (sessionId, version) =>
    request('GET', `/sessions/${sessionId}/detail-pages/results${buildQuery({ version })}`),

  globalEdit: (sessionId, instruction, scope, assetIds, idempotencyKey) =>
    request('POST', `/sessions/${sessionId}/results/global-edit`, {
      body: { instruction, scope, asset_ids: assetIds },
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),

  regenerateGallery: (sessionId, reason, instruction, idempotencyKey) =>
    request('POST', `/sessions/${sessionId}/results/regenerate`, {
      body: { reason, instruction },
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),

  regenerateAsset: (assetId, instruction, keepStyleConsistency, idempotencyKey) =>
    request('POST', `/assets/${assetId}/regenerate`, {
      body: { instruction, keep_style_consistency: keepStyleConsistency },
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),

  downloadResults: (sessionId, version) =>
    downloadFile(`/sessions/${sessionId}/download${buildQuery({ version })}`, `session_${sessionId}_results.zip`),

  downloadDetailResults: (sessionId, version) =>
    downloadFile(`/sessions/${sessionId}/detail-pages/download${buildQuery({ version })}`, `session_${sessionId}_detail_results.zip`),

  // ===== Jobs =====
  getJob: (jobId) => request('GET', `/jobs/${jobId}`),

  // ===== Prompt Presets =====
  getPromptPresets: (params = {}) => request('GET', `/prompt-presets${buildQuery(params)}`),

  createPromptPreset: (payload) => request('POST', '/prompt-presets', { body: payload }),

  updatePromptPreset: (presetId, payload) =>
    request('PUT', `/prompt-presets/${presetId}`, { body: payload }),

  archivePromptPreset: (presetId) =>
    request('POST', `/prompt-presets/${presetId}/archive`),

  clonePromptPreset: (presetId) =>
    request('POST', `/prompt-presets/${presetId}/clone`),

  streamJobEvents: async (jobId, onEvent, onError, onComplete) =>
    openSseStream(`/jobs/${jobId}/events`, onEvent, onError, onComplete),
}

// 错误码映射
export const ERROR_CODES = {
  40001: 'invalid_request',
  40002: 'invalid_session_status',
  40003: 'invalid_platform',
  40004: 'invalid_copy_field',
  40005: 'too_many_images',
  40006: 'unsupported_file_type',
  40007: 'file_too_large',
  40008: 'missing_required_images',
  40201: 'insufficient_credits',
  40401: 'session_not_found',
  40402: 'job_not_found',
  40403: 'asset_not_found',
  40901: 'job_already_running',
  40902: 'duplicate_idempotency_key',
  50201: 'upstream_llm_error',
  50202: 'upstream_image_error',
}

// Session 状态映射
export const SESSION_STATUS = {
  created: { label: '已创建', color: '#a0a0a0' },
  images_uploaded: { label: '已上传', color: '#3b82f6' },
  analyzing: { label: '分析中', color: '#f59e0b' },
  analyzed: { label: '已分析', color: '#10b981' },
  platform_selected: { label: '已选平台', color: '#8b5cf6' },
  copy_ready: { label: 'Copy就绪', color: '#8b5cf6' },
  strategy_ready: { label: '策略就绪', color: '#8b5cf6' },
  generating: { label: '生成中', color: '#f59e0b' },
  completed: { label: '已完成', color: '#10b981' },
  failed: { label: '失败', color: '#ef4444' },
}

// Job 状态映射
export const JOB_STATUS = {
  queued: { label: '排队中', color: '#a0a0a0' },
  running: { label: '执行中', color: '#f59e0b' },
  succeeded: { label: '成功', color: '#10b981' },
  failed: { label: '失败', color: '#ef4444' },
  partial_succeeded: { label: '部分成功', color: '#f59e0b' },
  canceled: { label: '已取消', color: '#a0a0a0' },
}

// Slot 类型
export const SLOT_TYPES = [
  { value: 'front', label: '正面图' },
  { value: 'angle45', label: '45度角' },
  { value: 'side', label: '侧面图' },
  { value: 'extra', label: '额外图' },
]

// Copy 字段
export const COPY_FIELDS = [
  { key: 'product_name', label: '产品名称', required: true },
  { key: 'category', label: '品类', required: true },
  { key: 'hero_scene', label: '首图场景', required: false },
  { key: 'core_selling_points', label: '核心卖点', required: false },
  { key: 'key_parameters', label: '核心参数', required: false },
  { key: 'product_advantages', label: '产品优势', required: false },
  { key: 'style_preset_id', label: '风格预设', required: false },
  { key: 'style_custom', label: '自定义风格', required: false },
]

// Copy 重生成目标字段
export const COPY_REGENERATE_TARGETS = [
  { value: 'headline', label: '主标题' },
  { value: 'selling_points', label: '卖点' },
  { value: 'usage_scenes', label: '使用场景' },
  { value: 'specs', label: '规格参数' },
]
