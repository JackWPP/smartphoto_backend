<template>
  <div class="detail-strategy-preview">
    <DetailStyleUpload :images="styleImages" @upload="$emit('uploadStyleImage', $event)" @delete="$emit('deleteStyleImage', $event)" />

    <div class="planner-panel card-lite">
      <div class="field">
        <label>Detail Planner Instruction</label>
        <textarea v-model="plannerInstruction" rows="3" placeholder="例如：标题更短、版式更像亚马逊详情页、字体更有科技感"></textarea>
      </div>
      <div class="field">
        <label>Panel Preferences JSON</label>
        <textarea v-model="panelPreferencesText" rows="5" placeholder='例如：[{"slot_id":"detail_slot_02","panel_type":"parameter_explainer","display_order":2,"locked":true}]'></textarea>
        <small class="subtle">可选。用于调试 panel slot 的 `panel_type` 覆盖和排序。</small>
        <small v-if="preferenceError" class="error-text">{{ preferenceError }}</small>
      </div>
      <div class="header-actions">
        <button class="btn btn-primary" @click="handleBuild" :disabled="!sessionId">Build Detail Strategy</button>
      </div>
      <p v-if="overrideMessage" class="subtle">{{ overrideMessage }}</p>
    </div>

    <div v-if="strategy" class="strategy-content">
      <div class="meta-section">
        <div class="field"><label>Use Case</label><div class="value">{{ strategy.use_case || '-' }}</div></div>
        <div class="field"><label>Aspect Ratio</label><div class="value">{{ strategy.aspect_ratio || '-' }}</div></div>
        <div class="field"><label>Panel Count</label><div class="value">{{ strategy.panel_count || 0 }}</div></div>
        <div class="field"><label>Style Source</label><div class="value">{{ strategy.style_source || '-' }}</div></div>
        <div class="field"><label>Style Summary</label><div class="value">{{ strategy.style_summary || '-' }}</div></div>
        <div class="field"><label>Planner Instruction</label><div class="value">{{ strategy.planner_instruction || 'None' }}</div></div>
        <div class="field"><label>Detail Rule Pack</label><div class="value">{{ strategy.detail_rule_pack || '-' }}</div></div>
      </div>

      <div class="reference-dual-grid">
        <div class="reference-section">
          <div class="section-header"><h3>Product References</h3><span class="subtle">{{ strategy.product_reference_manifest?.length || 0 }} images</span></div>
          <div v-if="strategy.product_reference_manifest?.length" class="reference-grid">
            <div v-for="item in strategy.product_reference_manifest" :key="item.image_id" class="reference-card">
              <img :src="item.source_url" :alt="item.slot_type" class="reference-thumb" />
              <div class="reference-meta">
                <div class="badge-row"><span class="badge">{{ item.slot_type }}</span><span class="order">#{{ item.display_order }}</span></div>
                <div class="meta-line mono">{{ item.image_id }}</div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state compact">No product references.</div>
        </div>

        <div class="reference-section">
          <div class="section-header"><h3>Style References</h3><span class="subtle">{{ strategy.style_reference_manifest?.length || 0 }} images</span></div>
          <div v-if="strategy.style_reference_manifest?.length" class="reference-grid">
            <div v-for="item in strategy.style_reference_manifest" :key="item.image_id" class="reference-card">
              <img :src="item.source_url" :alt="item.image_id" class="reference-thumb" />
              <div class="reference-meta">
                <div class="badge-row"><span class="badge">Style</span><span class="order">#{{ item.display_order }}</span></div>
                <div class="meta-line mono">{{ item.image_id }}</div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state compact">No style references. Planner will fallback to Step 4 style fields.</div>
        </div>
      </div>

      <div class="plan-section">
        <div class="section-header"><h3>Detail Panel Plan</h3><span class="subtle">{{ strategy.panel_plan?.length || 0 }} panels</span></div>
        <div v-if="strategy.panel_plan?.length" class="plan-grid">
          <div v-for="item in strategy.panel_plan" :key="item.slot_id || item.panel_id" class="plan-card">
            <div class="plan-header">
              <span class="badge">{{ item.panel_label || item.panel_id }}</span>
              <span class="order">Order: {{ item.display_order }}</span>
            </div>
            <div class="plan-body">
              <div class="meta-chip-row">
                <span class="chip">{{ item.slot_id || item.panel_id }}</span>
                <span class="chip">{{ item.planner_source || 'rule_based' }}</span>
                <span class="chip" v-if="item.panel_type">{{ item.panel_type }}</span>
                <span class="chip" v-if="item.layout_template">{{ item.layout_template }}</span>
              </div>

              <div class="field-block">
                <label>Editable Copy Blocks</label>
                <input class="form-control" :value="overrideFor(item).copy_blocks_override.headline || ''" @input="updateCopyBlock(item, 'headline', $event.target.value)" placeholder="主标题" />
                <input class="form-control" :value="overrideFor(item).copy_blocks_override.supporting || ''" @input="updateCopyBlock(item, 'supporting', $event.target.value)" placeholder="副标题" />
                <textarea class="form-control" rows="3" :value="linesText(overrideFor(item).copy_blocks_override.bullet_points)" @input="updateLineBlock(item, 'bullet_points', $event.target.value)" placeholder="bullet_points，一行一个"></textarea>
                <textarea class="form-control" rows="3" :value="linesText(overrideFor(item).copy_blocks_override.proof_lines)" @input="updateLineBlock(item, 'proof_lines', $event.target.value)" placeholder="proof_lines，一行一个"></textarea>
                <input class="form-control" :value="overrideFor(item).copy_blocks_override.cta_line || ''" @input="updateCopyBlock(item, 'cta_line', $event.target.value)" placeholder="CTA" />
              </div>

              <div class="field-block">
                <label>Raw Prompt Override</label>
                <textarea class="form-control" rows="4" :value="overrideFor(item).raw_prompt_override || ''" @input="updateRawPrompt(item, $event.target.value)" placeholder="留空则走结构化 prompt"></textarea>
              </div>

              <div class="field-block">
                <label>Template</label>
                <select class="form-control" :value="overrideFor(item).applied_preset_id || ''" @change="updatePreset(item, $event.target.value)">
                  <option value="">不套用模板</option>
                  <option v-for="preset in applicablePresets(item)" :key="preset.preset_id" :value="preset.preset_id">
                    {{ preset.name }}
                  </option>
                </select>
              </div>

              <div class="header-actions compact-actions">
                <button class="btn btn-secondary btn-sm" @click="saveOverrides">保存 panel 文案/Prompt</button>
                <button class="btn btn-secondary btn-sm" @click="savePromptAsTemplate(item)">保存为模板</button>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state compact">No detail panel plan generated.</div>
      </div>

      <div class="raw-section">
        <h3>Raw JSON</h3>
        <pre class="json-preview">{{ JSON.stringify(strategy, null, 2) }}</pre>
      </div>
    </div>

    <div v-else class="empty-state">
      <p>Build detail strategy to preview 8-panel slot planning.</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { api } from '../api/index.js'
import DetailStyleUpload from './DetailStyleUpload.vue'

const props = defineProps({
  sessionId: { type: String, required: true },
  strategy: { type: Object, default: null },
  styleImages: { type: Array, default: () => [] },
})

const emit = defineEmits(['build', 'uploadStyleImage', 'deleteStyleImage'])
const plannerInstruction = ref('')
const panelPreferencesText = ref('[]')
const preferenceError = ref('')
const overrideState = ref({})
const promptPresets = ref([])
const overrideMessage = ref('')

watch(
  () => props.strategy?.planner_instruction,
  (value) => {
    plannerInstruction.value = value || ''
  },
  { immediate: true }
)

watch(
  () => props.strategy?.panel_preferences,
  (value) => {
    panelPreferencesText.value = JSON.stringify(value || [], null, 2)
    preferenceError.value = ''
  },
  { immediate: true }
)

watch(
  () => [props.sessionId, props.strategy?.panel_plan],
  async () => {
    seedOverridesFromStrategy()
    await Promise.all([loadOverrides(), loadPromptPresets()])
  },
  { immediate: true, deep: true }
)

function seedOverridesFromStrategy() {
  const next = {}
  for (const item of props.strategy?.panel_plan || []) {
    const slotId = item.slot_id || item.panel_id
    next[slotId] = {
      slot_id: slotId,
      copy_blocks_override: { ...(item.copy_blocks || {}) },
      raw_prompt_override: item.raw_prompt_override || '',
      expression_mode_override: '',
      applied_preset_id: item.applied_preset_id || '',
      locked: false,
    }
  }
  overrideState.value = next
}

async function loadOverrides() {
  if (!props.sessionId) return
  try {
    const data = await api.getDetailStrategyOverrides(props.sessionId)
    for (const item of data.overrides || []) {
      overrideState.value[item.slot_id] = {
        slot_id: item.slot_id,
        copy_blocks_override: { ...(item.copy_blocks_override || {}) },
        raw_prompt_override: item.raw_prompt_override || '',
        expression_mode_override: item.expression_mode_override || '',
        applied_preset_id: item.applied_preset_id || '',
        locked: !!item.locked,
      }
    }
  } catch (error) {
    console.error('Failed to load detail overrides', error)
  }
}

async function loadPromptPresets() {
  try {
    const data = await api.getPromptPresets({ asset_family: 'detail_page' })
    promptPresets.value = data.presets || []
  } catch (error) {
    console.error('Failed to load detail prompt presets', error)
  }
}

function applicablePresets(item) {
  return promptPresets.value.filter((preset) => {
    if (!['slot_recipe', 'raw_prompt'].includes(preset.preset_type)) return false
    return !preset.slot_family || preset.slot_family === item.slot_id
  })
}

function overrideFor(item) {
  const slotId = item.slot_id || item.panel_id
  if (!overrideState.value[slotId]) {
    overrideState.value[slotId] = {
      slot_id: slotId,
      copy_blocks_override: { ...(item.copy_blocks || {}) },
      raw_prompt_override: '',
      expression_mode_override: '',
      applied_preset_id: '',
      locked: false,
    }
  }
  return overrideState.value[slotId]
}

function updateCopyBlock(item, key, value) {
  overrideFor(item).copy_blocks_override = {
    ...(overrideFor(item).copy_blocks_override || {}),
    [key]: value,
  }
}

function updateLineBlock(item, key, value) {
  updateCopyBlock(
    item,
    key,
    value.split('\n').map((line) => line.trim()).filter(Boolean),
  )
}

function updateRawPrompt(item, value) {
  overrideFor(item).raw_prompt_override = value
}

function updatePreset(item, value) {
  overrideFor(item).applied_preset_id = value
}

function linesText(value) {
  return Array.isArray(value) ? value.join('\n') : ''
}

async function saveOverrides() {
  if (!props.sessionId) return
  try {
    const overrides = Object.values(overrideState.value).map((item) => ({
      slot_id: item.slot_id,
      copy_blocks_override: item.copy_blocks_override || {},
      raw_prompt_override: item.raw_prompt_override || null,
      expression_mode_override: item.expression_mode_override || null,
      applied_preset_id: item.applied_preset_id || null,
      locked: !!item.locked,
    }))
    await api.saveDetailStrategyOverrides(props.sessionId, overrides)
    overrideMessage.value = '详情页 override 已保存'
    handleBuild()
  } catch (error) {
    overrideMessage.value = error.message || '详情页 override 保存失败'
  }
}

async function savePromptAsTemplate(item) {
  const name = window.prompt('模板名称')
  if (!name) return
  const current = overrideFor(item)
  try {
    await api.createPromptPreset({
      name,
      preset_type: current.raw_prompt_override ? 'raw_prompt' : 'slot_recipe',
      asset_family: 'detail_page',
      platform_id: null,
      slot_family: item.slot_id || null,
      category: null,
      locale: 'zh-CN',
      style_summary: null,
      default_expression_mode: null,
      copy_blocks_template: current.copy_blocks_override || {},
      raw_prompt_template: current.raw_prompt_override || null,
      tags: [item.slot_id || item.panel_id],
    })
    overrideMessage.value = '详情页模板已保存'
    await loadPromptPresets()
  } catch (error) {
    overrideMessage.value = error.message || '详情页模板保存失败'
  }
}

function handleBuild() {
  try {
    const parsed = JSON.parse(panelPreferencesText.value || '[]')
    if (!Array.isArray(parsed)) {
      throw new Error('Panel Preferences JSON must be an array.')
    }
    preferenceError.value = ''
    emit('build', {
      plannerInstruction: plannerInstruction.value || null,
      panelPreferences: parsed,
    })
  } catch (error) {
    preferenceError.value = error.message || 'Invalid JSON'
  }
}
</script>

<style scoped>
.detail-strategy-preview {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.card-lite {
  background-color: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  padding: 1rem;
}

.header-actions {
  display: flex;
  justify-content: flex-end;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field label {
  color: var(--text-secondary, #a0a0a0);
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.field textarea,
.value {
  background: var(--bg-secondary, #1e1e1e);
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  color: var(--text-primary, #fff);
  padding: 0.8rem;
}

.strategy-content,
.plan-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.meta-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
}

.reference-dual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem;
}

.reference-section,
.plan-section,
.raw-section {
  background: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  padding: 1rem;
}

.section-header,
.plan-header,
.badge-row,
.meta-chip-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
}

.section-header h3,
.raw-section h3 {
  margin: 0;
  color: var(--text-primary, #fff);
}

.subtle,
.order,
.meta-line {
  color: var(--text-secondary, #a0a0a0);
  font-size: 0.82rem;
}

.error-text {
  color: #f87171;
  font-size: 0.82rem;
}

.reference-grid,
.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.reference-card,
.plan-card {
  background: var(--bg-secondary, #1e1e1e);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  overflow: hidden;
}

.reference-thumb {
  width: 100%;
  height: 160px;
  object-fit: cover;
}

.reference-meta,
.plan-body {
  padding: 0.9rem;
}

.badge,
.chip,
.tag {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
}

.badge {
  background: var(--accent-blue, #3b82f6);
  color: #fff;
}

.chip,
.tag {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border-color, #333);
  color: var(--text-secondary, #a0a0a0);
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field-block p {
  margin: 0;
  line-height: 1.55;
  color: var(--text-primary, #fff);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.json-preview {
  margin: 0;
  max-height: 420px;
  overflow: auto;
  background: #0f1218;
  color: #d8e0f0;
  padding: 1rem;
  border-radius: 8px;
  font-size: 0.82rem;
}

.compact {
  min-height: auto;
}

.mono {
  font-family: monospace;
}

.btn-primary {
  background: var(--accent-blue, #3b82f6);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 0.7rem 1rem;
}
</style>
