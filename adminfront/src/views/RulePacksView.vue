<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">规则包管理</span>
        <h3>规则包草稿、版本与发布控制台</h3>
      </div>
      <div class="toolbar-actions">
        <input v-model="filters.q" class="compact-input" placeholder="搜索规则包" />
        <button class="ghost-button" @click="loadRulePacks">刷新</button>
        <button class="primary-button" @click="startCreate">新建规则包</button>
      </div>
    </div>
    <div class="workspace-grid">
      <article class="surface-card">
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>规则包</th>
                <th>资产族</th>
                <th>当前版本</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in rulePacks.items || []" :key="item.rule_pack_id" :class="{ active: selectedRulePackId === item.rule_pack_id }" @click="openRulePack(item.rule_pack_id)">
                <td>
                  <strong>{{ item.name }}</strong>
                  <small>{{ item.rule_pack_key }}</small>
                </td>
                <td>{{ item.asset_family }}</td>
                <td>{{ item.current_version_no }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
      <article class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">规则包编辑器</span>
            <h4>{{ editor.name || '新规则包' }}</h4>
          </div>
          <span class="status-chip">{{ selectedRulePackId || '草稿中 (draft)' }}</span>
        </div>
        <form class="form-grid">
          <label class="field"><span>名称 (name)</span><input v-model="editor.name" /></label>
          <label class="field"><span>覆盖资产族 (asset_family)</span><input v-model="editor.asset_family" /></label>
          <label class="field"><span>挂载平台 (platform_id)</span><input v-model="editor.platform_id" placeholder="选填，如为空则适用全局" /></label>
          <label class="field"><span>标识键 (rule_pack_key)</span><input v-model="editor.rule_pack_key" :disabled="Boolean(selectedRulePackId)" /></label>
          <label class="field"><span>修改备注 (operator_note)</span><textarea v-model="editor.operator_note" rows="3" placeholder="说明规则包变更原因" /></label>
        </form>
        <JsonEditor v-model="editor.config_snapshot_json" title="完整配置快照 (config_snapshot)" :rows="14" />
        <div class="toolbar-actions" style="margin-top: 12px;">
          <button class="primary-button" @click="saveRulePack">{{ selectedRulePackId ? '保存草稿' : '创建规则包' }}</button>
          <button class="ghost-button" :disabled="!selectedRulePackId" @click="publishRulePack">发布当前版本</button>
          <button class="ghost-button" :disabled="!selectedRulePackId" @click="cloneRulePack">克隆该规则包</button>
          <button class="ghost-button" :disabled="!selectedRulePackId" @click="archiveRulePack">归档/禁用</button>
        </div>

        <div class="panel-grid" style="margin-top: 24px;">
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>版本历史</h4>
            </div>
            <div class="stack-list">
              <div v-for="item in versions" :key="item.version_id" :class="['stack-list__item', { active: compareVersionId === item.version_id }]" @click="compareVersionId = item.version_id">
                <div>
                  <strong>v{{ item.version_no }}</strong>
                  <small>{{ item.created_at }}</small>
                </div>
                <span class="status-chip">{{ item.is_published ? '已发布 (published)' : '草稿 (draft)' }}</span>
              </div>
            </div>
          </div>
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>版本对照代码</h4>
            </div>
            <pre>{{ prettyJson(compareVersion?.config_snapshot) }}</pre>
          </div>
        </div>

        <div class="surface-pane" style="margin-top: 24px;">
          <div class="surface-card__header">
            <h4>策略结构预览测试</h4>
          </div>
          <div class="toolbar-actions" style="margin-bottom: 12px;">
            <input v-model="previewSessionId" class="compact-input" placeholder="输入测试用的 Session ID" />
            <button class="ghost-button" @click="loadSampleStrategyPreview">重建该 Session 策略预览</button>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { adminApi } from '../api'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import JsonEditor from '../components/JsonEditor.vue'
import { parseJsonInput, prettyJson } from '../lib/format'
import { useConfirmAction } from '../lib/useConfirmAction'

const filters = reactive({ q: '' })
const rulePacks = ref({ items: [] })
const selectedRulePackId = ref('')
const versions = ref([])
const compareVersionId = ref('')
const previewSessionId = ref('')
const samplePreview = ref({})
const editor = reactive({
  name: '',
  asset_family: 'main_gallery',
  platform_id: '',
  rule_pack_key: '',
  config_snapshot_json: '{}',
  operator_note: '',
})
const { dialog, requestConfirm, cancelConfirm, confirmAction } = useConfirmAction()

const compareVersion = computed(() => versions.value.find((item) => item.version_id === compareVersionId.value) || versions.value[0] || null)

function resetEditor() {
  editor.name = ''
  editor.asset_family = 'main_gallery'
  editor.platform_id = ''
  editor.rule_pack_key = ''
  editor.config_snapshot_json = '{}'
  editor.operator_note = ''
}

async function loadRulePacks() {
  rulePacks.value = await adminApi.listRulePacks({ q: filters.q, page_size: 50 })
  if (!selectedRulePackId.value && rulePacks.value.items?.length) {
    openRulePack(rulePacks.value.items[0].rule_pack_id)
  }
}

async function openRulePack(rulePackId) {
  selectedRulePackId.value = rulePackId
  const data = await adminApi.getRulePack(rulePackId)
  versions.value = data.versions || []
  compareVersionId.value = versions.value[0]?.version_id || ''
  editor.name = data.rule_pack.name
  editor.asset_family = data.rule_pack.asset_family
  editor.platform_id = data.rule_pack.platform_id || ''
  editor.rule_pack_key = data.rule_pack.rule_pack_key
  editor.config_snapshot_json = prettyJson(data.rule_pack.version?.config_snapshot || {})
  editor.operator_note = ''
}

function payload() {
  return {
    name: editor.name,
    asset_family: editor.asset_family,
    platform_id: editor.platform_id || null,
    rule_pack_key: editor.rule_pack_key,
    config_snapshot: parseJsonInput(editor.config_snapshot_json, {}),
    operator_note: editor.operator_note,
  }
}

async function saveRulePack() {
  const currentPayload = payload()
  if (!currentPayload.operator_note?.trim()) {
    return
  }
  requestConfirm({
    title: selectedRulePackId.value ? '确认保存规则包草稿' : '确认创建规则包',
    message: selectedRulePackId.value
      ? `即将更新规则包 ${selectedRulePackId.value} 的草稿配置。`
      : '即将创建新的规则包并写入后台审计。',
    confirmText: selectedRulePackId.value ? '确认保存' : '确认创建',
    onConfirm: async () => {
      if (selectedRulePackId.value) {
        await adminApi.updateRulePack(selectedRulePackId.value, currentPayload)
      } else {
        const created = await adminApi.createRulePack(currentPayload)
        selectedRulePackId.value = created.rule_pack.rule_pack_id
      }
      await loadRulePacks()
      if (selectedRulePackId.value) {
        await openRulePack(selectedRulePackId.value)
      }
    },
  })
}

async function publishRulePack() {
  requestConfirm({
    title: '确认发布规则包',
    message: `即将发布规则包 ${selectedRulePackId.value}，会影响后续策略构建。`,
    confirmText: '确认发布',
    onConfirm: async () => {
      await adminApi.publishRulePack(selectedRulePackId.value, { operator_note: editor.operator_note || 'publish rule pack' })
      await openRulePack(selectedRulePackId.value)
    },
  })
}

async function cloneRulePack() {
  requestConfirm({
    title: '确认克隆规则包',
    message: `即将克隆规则包 ${selectedRulePackId.value}。`,
    confirmText: '确认克隆',
    onConfirm: async () => {
      await adminApi.cloneRulePack(selectedRulePackId.value, { operator_note: editor.operator_note || 'clone rule pack' })
      await loadRulePacks()
    },
  })
}

async function archiveRulePack() {
  requestConfirm({
    title: '确认归档规则包',
    message: `即将归档规则包 ${selectedRulePackId.value}。`,
    confirmText: '确认归档',
    onConfirm: async () => {
      await adminApi.archiveRulePack(selectedRulePackId.value, { operator_note: editor.operator_note || 'archive rule pack' })
      await loadRulePacks()
    },
  })
}

function startCreate() {
  selectedRulePackId.value = ''
  versions.value = []
  compareVersionId.value = ''
  resetEditor()
}

async function loadSampleStrategyPreview() {
  if (!previewSessionId.value.trim()) {
    return
  }
  samplePreview.value = await adminApi.buildSessionStrategyPreview(previewSessionId.value.trim(), {})
}

onMounted(loadRulePacks)
</script>
