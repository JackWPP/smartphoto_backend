import { reactive } from 'vue'

export function useConfirmAction() {
  const dialog = reactive({
    open: false,
    eyebrow: '高风险操作',
    title: '确认执行',
    message: '',
    confirmText: '确认',
    danger: true,
  })

  let pendingAction = null

  function requestConfirm(options) {
    dialog.open = true
    dialog.eyebrow = options.eyebrow || '高风险操作'
    dialog.title = options.title || '确认执行'
    dialog.message = options.message || ''
    dialog.confirmText = options.confirmText || '确认'
    dialog.danger = options.danger !== false
    pendingAction = options.onConfirm || null
  }

  function cancelConfirm() {
    dialog.open = false
    pendingAction = null
  }

  async function confirmAction() {
    const action = pendingAction
    cancelConfirm()
    if (typeof action === 'function') {
      await action()
    }
  }

  return {
    dialog,
    requestConfirm,
    cancelConfirm,
    confirmAction,
  }
}
