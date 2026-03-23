<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">Sessions</span>
        <h3>Session 干预与结果追踪</h3>
      </div>
      <div class="toolbar-actions">
        <input v-model="filters.session_id" class="compact-input" placeholder="session_id" />
        <input v-model="filters.user_id" class="compact-input" placeholder="user_id" />
        <button class="ghost-button" @click="loadSessions">刷新</button>
      </div>
    </div>

    <div class="workspace-grid workspace-grid--narrow">
      <article class="surface-card">
        <div class="surface-card__header">
          <h4>Session 列表</h4>
        </div>
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>Session</th>
                <th>平台</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in sessions.items || []" :key="item.session_id" :class="{ active: selectedSessionId === item.session_id }" @click="openSession(item.session_id)">
                <td>
                  <strong>{{ item.session_id }}</strong>
                  <small>{{ item.user_id }}</small>
                </td>
                <td>{{ item.active_platform_id || '-' }}</td>
                <td><span class="status-chip">{{ item.status }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="surface-card" v-if="detail.session">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">Session Detail</span>
            <h4>{{ detail.session.session_id }}</h4>
          </div>
          <span>{{ detail.session.status }} / step {{ detail.session.current_step }}</span>
        </div>

        <div class="metric-grid metric-grid--compact">
          <article class="metric-card">
            <span class="metric-card__label">主图版本</span>
            <strong class="metric-card__value">{{ detail.session.latest_result_version }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">详情页版本</span>
            <strong class="metric-card__value">{{ detail.session.detail_latest_result_version }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">平台</span>
            <strong class="metric-card__value">{{ detail.session.active_platform_id || '-' }}</strong>
          </article>
        </div>

        <div class="panel-grid">
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>Step4 Copy</h4>
              <button class="ghost-button" @click="saveCopy">保存 Copy</button>
            </div>
            <form class="form-grid">
              <label class="field"><span>product_name</span><input v-model="copyForm.product_name" /></label>
              <label class="field"><span>category</span><input v-model="copyForm.category" /></label>
              <label class="field"><span>hero_scene</span><input v-model="copyForm.hero_scene" /></label>
              <label class="field"><span>style_preset_id</span><input v-model="copyForm.style_preset_id" /></label>
              <label class="field"><span>style_custom</span><textarea v-model="copyForm.style_custom" rows="3" /></label>
              <label class="field"><span>core_selling_points</span><textarea v-model="copyForm.core_selling_points_text" rows="4" placeholder="每行一个卖点" /></label>
              <label class="field"><span>product_advantages</span><textarea v-model="copyForm.product_advantages_text" rows="4" placeholder="每行一个优势" /></label>
              <label class="field"><span>key_parameters JSON</span><textarea v-model="copyForm.key_parameters_json" rows="8" spellcheck="false" /></label>
              <label class="field">
                <span>操作备注</span>
                <textarea v-model="copyForm.operator_note" rows="3" placeholder="说明这次 copy 干预原因" />
              </label>
            </form>
          </div>

          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>参数 / Override</h4>
            </div>
            <JsonEditor v-model="parameterJson" title="parameter_snapshot" :rows="10" />
            <label class="field">
              <span>参数操作备注</span>
              <textarea v-model="parameterOperatorNote" rows="2" />
            </label>
            <button class="ghost-button" @click="saveParameters">保存参数</button>
            <JsonEditor v-model="mainOverrideJson" title="main strategy overrides" :rows="10" />
            <button class="ghost-button" @click="saveMainOverrides">保存主图 Override</button>
            <JsonEditor v-model="detailOverrideJson" title="detail strategy overrides" :rows="10" />
            <button class="ghost-button" @click="saveDetailOverrides">保存详情页 Override</button>
          </div>
        </div>

        <div class="surface-pane">
          <div class="surface-card__header">
            <h4>动作工作台</h4>
          </div>
          <div class="form-grid">
            <label class="field">
              <span>instruction</span>
              <textarea v-model="actionForm.instruction" rows="3" />
            </label>
            <label class="field">
              <span>slot_ids</span>
              <input v-model="actionForm.slot_ids_text" placeholder="slot_id,slot_id" />
            </label>
            <label class="field">
              <span>操作备注</span>
              <textarea v-model="actionForm.operator_note" rows="3" placeholder="所有高风险操作必须留痕" />
            </label>
          </div>
          <div class="toolbar-actions">
            <button class="ghost-button" @click="runAction('reanalyze')">重跑分析</button>
            <button class="ghost-button" @click="runAction('extract')">参数提取</button>
            <button class="primary-button" @click="runAction('main')">重跑主图</button>
            <button class="primary-button" @click="runAction('detail')">重跑详情页</button>
            <button class="ghost-button" @click="loadPreviews">刷新预览</button>
          </div>
        </div>

        <div class="panel-grid">
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>主图结果</h4>
              <div class="toolbar-actions">
                <input v-model.number="mainVersion" class="compact-input" type="number" min="1" />
                <button class="ghost-button" @click="loadResults">加载</button>
              </div>
            </div>
            <div class="asset-grid">
              <div v-for="item in mainResults.assets || []" :key="item.asset_id" class="asset-card">
                <img :src="item.thumbnail_url || item.image_url" />
                <strong>{{ item.slot_id || item.role }}</strong>
                <small>v{{ item.version_no }}</small>
              </div>
            </div>
          </div>
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>详情页结果</h4>
              <div class="toolbar-actions">
                <input v-model.number="detailVersion" class="compact-input" type="number" min="1" />
                <button class="ghost-button" @click="loadDetailResults">加载</button>
              </div>
            </div>
            <div class="asset-grid">
              <div v-for="item in detailResults.panels || []" :key="item.asset_id" class="asset-card">
                <img :src="item.thumbnail_url || item.image_url" />
                <strong>{{ item.slot_id || item.panel_id }}</strong>
                <small>v{{ item.version_no }}</small>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-grid">
          <div class="surface-pane">
            <h4>主图 Prompt 预览</h4>
            <pre>{{ prettyJson(promptPreview) }}</pre>
          </div>
          <div class="surface-pane">
            <h4>详情页 Prompt 预览</h4>
            <pre>{{ prettyJson(detailPromptPreview) }}</pre>
          </div>
        </div>

        <div class="panel-grid">
          <div class="surface-pane">
            <h4>最近任务</h4>
            <div class="stack-list">
              <div v-for="item in detail.recent_jobs || []" :key="item.job_id" class="stack-list__item">
                <div>
                  <strong>{{ item.job_type }}</strong>
                  <small>{{ item.job_id }}</small>
                </div>
                <span class="status-chip">{{ item.status }}</span>
              </div>
            </div>
          </div>
          <div class="surface-pane">
            <h4>最近资产</h4>
            <div class="stack-list">
              <div v-for="item in detail.recent_assets || []" :key="item.asset_id" class="stack-list__item">
                <div>
                  <strong>{{ item.role || item.asset_kind }}</strong>
                  <small>{{ item.asset_id }}</small>
                </div>
                <span class="status-chip">{{ item.visibility_status }}</span>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
  <ConfirmDialog
    :open="dialog.open"
    :eyebrow="dialog.eyebrow"
    :title="dialog.title"
    :message="dialog.message"
    :confirm-text="dialog.confirmText"
    :danger="dialog.danger"
    @cancel="cancelConfirm"
    @confirm="confirmAction"
  />
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '../api'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import JsonEditor from '../components/JsonEditor.vue'
import { csvToList, listToMultiline, multilineToList, parseJsonInput, prettyJson } from '../lib/format'
import { useConfirmAction } from '../lib/useConfirmAction'

const filters = reactive({ session_id: '', user_id: '' })
const sessions = ref({ items: [] })
const detail = ref({})
const selectedSessionId = ref('')
const mainResults = ref({ assets: [] })
const detailResults = ref({ panels: [] })
const promptPreview = ref({})
const detailPromptPreview = ref({})
const mainVersion = ref(null)
const detailVersion = ref(null)
const parameterJson = ref('{}')
const parameterOperatorNote = ref('')
const mainOverrideJson = ref('{"operator_note":"","overrides":[]}')
const detailOverrideJson = ref('{"operator_note":"","overrides":[]}')
const copyForm = reactive({
  product_name: '',
  category: '',
  hero_scene: '',
  style_preset_id: '',
  style_custom: '',
  core_selling_points_text: '',
  product_advantages_text: '',
  key_parameters_json: '[]',
  operator_note: '',
})
const actionForm = reactive({ instruction: '', slot_ids_text: '', operator_note: '' })
const { dialog, requestConfirm, cancelConfirm, confirmAction } = useConfirmAction()

async function loadSessions() {
  sessions.value = await adminApi.listSessions({ ...filters, page_size: 50 })
  if (!selectedSessionId.value && sessions.value.items?.length) {
    openSession(sessions.value.items[0].session_id)
  }
}

function hydrateEditors(session) {
  const copy = session.confirmed_copy || {}
  copyForm.product_name = copy.product_name || ''
  copyForm.category = copy.category || ''
  copyForm.hero_scene = copy.hero_scene || ''
  copyForm.style_preset_id = copy.style_preset_id || ''
  copyForm.style_custom = copy.style_custom || ''
  copyForm.core_selling_points_text = listToMultiline(copy.core_selling_points)
  copyForm.product_advantages_text = listToMultiline(copy.product_advantages)
  copyForm.key_parameters_json = prettyJson(copy.key_parameters || [])
  parameterJson.value = prettyJson(session.parameter_snapshot || {})
  mainOverrideJson.value = prettyJson({ operator_note: '', overrides: (session.strategy_preview || {}).overrides || [] })
  detailOverrideJson.value = prettyJson({ operator_note: '', overrides: (session.detail_strategy_preview || {}).overrides || [] })
  mainVersion.value = session.latest_result_version || null
  detailVersion.value = session.detail_latest_result_version || null
}

async function openSession(sessionId) {
  selectedSessionId.value = sessionId
  detail.value = await adminApi.getSession(sessionId)
  hydrateEditors(detail.value.session)
  await Promise.all([loadResults(), loadDetailResults(), loadPreviews()])
}

function buildCopyPayload() {
  return {
    product_name: copyForm.product_name,
    category: copyForm.category,
    hero_scene: copyForm.hero_scene,
    core_selling_points: multilineToList(copyForm.core_selling_points_text),
    product_advantages: multilineToList(copyForm.product_advantages_text),
    style_preset_id: copyForm.style_preset_id || null,
    style_custom: copyForm.style_custom,
    style_choice: '',
    key_parameters: parseJsonInput(copyForm.key_parameters_json, []),
    headline: '',
    selling_points: '',
    usage_scenes: '',
    specs: '',
    operator_note: copyForm.operator_note,
  }
}

async function saveCopy() {
  if (!selectedSessionId.value || !copyForm.operator_note.trim()) {
    return
  }
  requestConfirm({
    title: '确认保存 Session Copy',
    message: `即将直接修改 Session ${selectedSessionId.value} 的 Step4 copy。`,
    confirmText: '确认保存',
    onConfirm: async () => {
      await adminApi.updateCopy(selectedSessionId.value, buildCopyPayload())
      await openSession(selectedSessionId.value)
    },
  })
}

async function saveParameters() {
  if (!selectedSessionId.value || !parameterOperatorNote.value.trim()) {
    return
  }
  const payload = parseJsonInput(parameterJson.value, {})
  requestConfirm({
    title: '确认保存参数快照',
    message: `即将覆盖 Session ${selectedSessionId.value} 的参数快照。`,
    confirmText: '确认保存',
    onConfirm: async () => {
      await adminApi.updateParameters(selectedSessionId.value, { ...payload, operator_note: parameterOperatorNote.value })
      await openSession(selectedSessionId.value)
    },
  })
}

async function saveMainOverrides() {
  if (!selectedSessionId.value) {
    return
  }
  const payload = parseJsonInput(mainOverrideJson.value, { overrides: [] })
  if (!payload.operator_note?.trim()) {
    return
  }
  requestConfirm({
    title: '确认保存主图策略 Override',
    message: `即将改写 Session ${selectedSessionId.value} 的主图策略 override。`,
    confirmText: '确认保存',
    onConfirm: async () => {
      await adminApi.updateStrategyOverrides(selectedSessionId.value, payload)
      await openSession(selectedSessionId.value)
    },
  })
}

async function saveDetailOverrides() {
  if (!selectedSessionId.value) {
    return
  }
  const payload = parseJsonInput(detailOverrideJson.value, { overrides: [] })
  if (!payload.operator_note?.trim()) {
    return
  }
  requestConfirm({
    title: '确认保存详情页策略 Override',
    message: `即将改写 Session ${selectedSessionId.value} 的详情页策略 override。`,
    confirmText: '确认保存',
    onConfirm: async () => {
      await adminApi.updateDetailStrategyOverrides(selectedSessionId.value, payload)
      await openSession(selectedSessionId.value)
    },
  })
}

async function loadPreviews() {
  if (!selectedSessionId.value) {
    return
  }
  const [mainPrompt, detailPrompt] = await Promise.all([
    adminApi.previewSessionPrompts(selectedSessionId.value, { instruction: actionForm.instruction, include_latest_assets: true }),
    adminApi.previewDetailPrompts(selectedSessionId.value, { instruction: actionForm.instruction, include_latest_assets: true }),
  ])
  promptPreview.value = mainPrompt
  detailPromptPreview.value = detailPrompt
}

async function loadResults() {
  if (!selectedSessionId.value) {
    return
  }
  mainResults.value = await adminApi.getSessionResults(selectedSessionId.value, { version: mainVersion.value || undefined })
}

async function loadDetailResults() {
  if (!selectedSessionId.value) {
    return
  }
  detailResults.value = await adminApi.getSessionDetailResults(selectedSessionId.value, { version: detailVersion.value || undefined })
}

async function runAction(mode) {
  if (!selectedSessionId.value || !actionForm.operator_note.trim()) {
    return
  }
  const payload = {
    instruction: actionForm.instruction,
    slot_ids: csvToList(actionForm.slot_ids_text),
    operator_note: actionForm.operator_note,
  }
  const actionMap = {
    reanalyze: {
      title: '确认重跑分析',
      message: `即将重新分析 Session ${selectedSessionId.value} 的输入素材。`,
      confirmText: '确认重跑分析',
      run: () => adminApi.reanalyzeSession(selectedSessionId.value, payload),
    },
    extract: {
      title: '确认重跑参数提取',
      message: `即将重新提取 Session ${selectedSessionId.value} 的结构化参数。`,
      confirmText: '确认提取',
      run: () => adminApi.extractSessionParameters(selectedSessionId.value, payload),
    },
    main: {
      title: '确认重跑主图',
      message: `即将重新生成 Session ${selectedSessionId.value} 的主图库。`,
      confirmText: '确认重跑主图',
      run: () => adminApi.regenerateMainGallery(selectedSessionId.value, payload),
    },
    detail: {
      title: '确认重跑详情页',
      message: `即将重新生成 Session ${selectedSessionId.value} 的详情页。`,
      confirmText: '确认重跑详情页',
      run: () => adminApi.regenerateDetailPage(selectedSessionId.value, payload),
    },
  }
  const action = actionMap[mode]
  if (!action) {
    return
  }
  requestConfirm({
    title: action.title,
    message: action.message,
    confirmText: action.confirmText,
    onConfirm: action.run,
  })
}

onMounted(loadSessions)
</script>
