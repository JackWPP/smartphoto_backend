export function formatDate(value) {
  if (!value) {
    return '-'
  }
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return value
  }
}

export function prettyJson(value) {
  return JSON.stringify(value ?? {}, null, 2)
}

export function parseJsonInput(text, fallback = {}) {
  const trimmed = (text || '').trim()
  if (!trimmed) {
    return fallback
  }
  return JSON.parse(trimmed)
}

export function csvToList(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function listToMultiline(value) {
  return Array.isArray(value) ? value.join('\n') : ''
}

export function multilineToList(value) {
  return String(value || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}
