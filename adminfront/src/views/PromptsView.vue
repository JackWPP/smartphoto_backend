<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">提示词模板管理</span>
        <h3>Prompt Preset 控制台</h3>
      </div>
      <div class="toolbar-actions">
        <input v-model="filters.q" class="compact-input" placeholder="搜索模板名/风格摘要" />
        <button class="ghost-button" @click="loadPresets">刷新</button>
        <button class="primary-button" @click="startCreate">新建模板</button>
      </div>
    </div>
    <div class="workspace-grid">
      <article class="surface-card">
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>模板</th>
                <th>资产族</th>
                <th>版本</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in presets.items || []" :key="item.preset_id" :class="{ active: selectedPresetId === item.preset_id }" @click="openPreset(item.preset_id)">
                <td>
                  <strong>{{ item.name }}</strong>
                  <small>{{ item.preset_type }}</small>
                </td>
                <td>{{ item.asset_family }}</td>
                <td>{{ item.version_no }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
      <article class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">提示词编辑器</span>
            <h4>{{ editor.name || '新模板' }}</h4>
          </div>
          <span>{{ selectedPresetId || 'draft' }}</span>
        </div>
        <form class="form-grid">
          <label class="field"><span>name</span><input v-model="editor.name" /></label>
          <label class="field"><span>preset_type</span><input v-model="editor.preset_type" /></label>
          <label class="field"><span>asset_family</span><input v-model="editor.asset_family" /></label>
          <label class="field"><span>platform_id</span><input v-model="editor.platform_id" /></label>
          <label class="field"><span>slot_family</span><input v-model="editor.slot_family" /></label>
          <label class="field"><span>category</span><input v-model="editor.category" /></label>
          <label class="field"><span>locale</span><input v-model="editor.locale" /></label>
          <label class="field"><span>style_summary</span><textarea v-model="editor.style_summary" rows="3" /></label>
          <label class="field"><span>default_expression_mode</span><input v-model="editor.default_expression_mode" /></label>
          <label class="field"><span>tags</span><input v-model="editor.tags_text" placeholder="tag1,tag2" /></label>
          <label class="field"><span>operator_note</span><textarea v-model="editor.operator_note" rows="3" placeholder="说明这次模板变更目的" /></label>
        </form>
        <JsonEditor v-model="editor.copy_blocks_template_json" title="copy_blocks_template" :rows="10" />
        <label class="field">
          <span>raw_prompt_template</span>
          <textarea v-model="editor.raw_prompt_template" rows="8" spellcheck="false" />
        </label>
        <div class="toolbar-actions">
          <button class="primary-button" @click="savePreset">{{ selectedPresetId ? '保存模板' : '创建模板' }}</button>
          <button class="ghost-button" :disabled="!selectedPresetId" @click="clonePreset">克隆</button>
          <button class="ghost-button" :disabled="!selectedPresetId" @click="archivePreset">归档</button>
        </div>

        <div class="surface-pane">
          <div class="surface-card__header">
            <h4>会话 Prompt 生成预览</h4>
          </div>
          <div class="toolbar-actions">
            <input v-model="previewSessionId" class="compact-input" placeholder="sample session_id" />
            <button class="ghost-button" @click="loadSamplePreview">预览当前 Session Prompt</button>
          </div>
          <pre>{{ prettyJson(samplePreview) }}</pre>
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
import { csvToList, parseJsonInput, prettyJson } from '../lib/format'
import { useConfirmAction } from '../lib/useConfirmAction'

const filters = reactive({ q: '' })
const presets = ref({ items: [] })
const selectedPresetId = ref('')
const previewSessionId = ref('')
const samplePreview = ref({})
const editor = reactive({
  name: '',
  preset_type: 'style',
  asset_family: 'main_gallery',
  platform_id: '',
  slot_family: '',
  category: 'generic',
  locale: 'zh-CN',
  style_summary: '',
  default_expression_mode: '',
  tags_text: '',
  copy_blocks_template_json: '{}',
  raw_prompt_template: '',
  operator_note: '',
})
const { dialog, requestConfirm, cancelConfirm, confirmAction } = useConfirmAction()

function resetEditor() {
  editor.name = ''
  editor.preset_type = 'style'
  editor.asset_family = 'main_gallery'
  editor.platform_id = ''
  editor.slot_family = ''
  editor.category = 'generic'
  editor.locale = 'zh-CN'
  editor.style_summary = ''
  editor.default_expression_mode = ''
  editor.tags_text = ''
  editor.copy_blocks_template_json = '{}'
  editor.raw_prompt_template = ''
  editor.operator_note = ''
}

async function loadPresets() {
  presets.value = await adminApi.listPromptPresets({ q: filters.q, page_size: 50 })
  if (!selectedPresetId.value && presets.value.items?.length) {
    openPreset(presets.value.items[0].preset_id)
  }
}

async function openPreset(id) {
  selectedPresetId.value = id
  const data = await adminApi.getPromptPreset(id)
  editor.name = data.name
  editor.preset_type = data.preset_type
  editor.asset_family = data.asset_family
  editor.platform_id = data.platform_id || ''
  editor.slot_family = data.slot_family || ''
  editor.category = data.category || ''
  editor.locale = data.locale || 'zh-CN'
  editor.style_summary = data.style_summary || ''
  editor.default_expression_mode = data.default_expression_mode || ''
  editor.tags_text = (data.tags || []).join(', ')
  editor.copy_blocks_template_json = prettyJson(data.copy_blocks_template || {})
  editor.raw_prompt_template = data.raw_prompt_template || ''
  editor.operator_note = ''
}

function payload() {
  return {
    name: editor.name,
    preset_type: editor.preset_type,
    asset_family: editor.asset_family,
    platform_id: editor.platform_id || null,
    slot_family: editor.slot_family || null,
    category: editor.category || null,
    locale: editor.locale || null,
    style_summary: editor.style_summary || null,
    default_expression_mode: editor.default_expression_mode || null,
    copy_blocks_template: parseJsonInput(editor.copy_blocks_template_json, {}),
    raw_prompt_template: editor.raw_prompt_template || null,
    tags: csvToList(editor.tags_text),
    operator_note: editor.operator_note,
  }
}

async function savePreset() {
  const currentPayload = payload()
  if (!currentPayload.operator_note?.trim()) {
    return
  }
  requestConfirm({
    title: selectedPresetId.value ? '确认更新 Prompt Preset' : '确认创建 Prompt Preset',
    message: selectedPresetId.value
      ? `即将更新模板 ${selectedPresetId.value}，该变更会写入后台审计。`
      : '即将创建新的 Prompt Preset 并写入后台审计。',
    confirmText: selectedPresetId.value ? '确认更新' : '确认创建',
    onConfirm: async () => {
      if (selectedPresetId.value) {
        await adminApi.updatePromptPreset(selectedPresetId.value, currentPayload)
      } else {
        const created = await adminApi.createPromptPreset(currentPayload)
        selectedPresetId.value = created.preset.preset_id
      }
      await loadPresets()
      if (selectedPresetId.value) {
        await openPreset(selectedPresetId.value)
      }
    },
  })
}

async function clonePreset() {
  requestConfirm({
    title: '确认克隆 Prompt Preset',
    message: `即将克隆模板 ${selectedPresetId.value}。`,
    confirmText: '确认克隆',
    onConfirm: async () => {
      await adminApi.clonePromptPreset(selectedPresetId.value, { operator_note: editor.operator_note || 'clone preset' })
      await loadPresets()
    },
  })
}

async function archivePreset() {
  requestConfirm({
    title: '确认归档 Prompt Preset',
    message: `即将归档模板 ${selectedPresetId.value}。`,
    confirmText: '确认归档',
    onConfirm: async () => {
      await adminApi.archivePromptPreset(selectedPresetId.value, { operator_note: editor.operator_note || 'archive preset' })
      await loadPresets()
    },
  })
}

function startCreate() {
  selectedPresetId.value = ''
  resetEditor()
}

async function loadSamplePreview() {
  if (!previewSessionId.value.trim()) {
    return
  }
  samplePreview.value = await adminApi.previewSessionPrompts(previewSessionId.value.trim(), { include_latest_assets: true })
}

onMounted(loadPresets)
</script>
