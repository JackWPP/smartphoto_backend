<template>
  <div class="strategy-preview">
    <div class="planner-panel card-lite">
      <div class="field">
        <label>Planner Instruction</label>
        <textarea
          v-model="plannerInstruction"
          rows="3"
          placeholder="例如：白底图必须更标准、主图更像参考图、场景图更偏客厅使用感"
        ></textarea>
      </div>
      <div class="field">
        <label>Slot Preferences JSON</label>
        <textarea
          v-model="slotPreferencesText"
          rows="5"
          placeholder='例如：[{"slot_id":"proof_authority","expression_mode":"certificate_proof","locked":true}]'
        ></textarea>
        <small class="subtle">可选。用于调试槽位级 `expression_mode` 覆盖。</small>
        <small v-if="preferenceError" class="error-text">{{ preferenceError }}</small>
      </div>
      <div class="actions-row">
        <button class="btn btn-secondary" @click="triggerReferenceUpload">上传策略参考图</button>
        <input ref="strategyReferenceInput" type="file" accept=".jpg,.jpeg,.png,.webp" class="hidden-input" @change="handleStrategyReferenceUpload" />
        <button class="btn btn-primary" @click="handleBuild" :disabled="!sessionId">Build Strategy + Prompt Plan</button>
      </div>
      <div v-if="strategyReferenceImages.length" class="tag-list">
        <span v-for="image in strategyReferenceImages" :key="image.image_id" class="tag">
          {{ image.image_id.slice(0, 8) }}
          <button class="link-btn" @click="deleteStrategyReference(image.image_id)">×</button>
        </span>
      </div>
      <p v-if="overrideMessage" class="subtle">{{ overrideMessage }}</p>
    </div>

    <div v-if="strategy" class="strategy-content">
      <div class="meta-section">
        <div class="field"><label>Product Name</label><div class="value">{{ strategy.product_name || '-' }}</div></div>
        <div class="field"><label>Platform Strategy</label><div class="value">{{ strategy.platform_strategy || '-' }}</div></div>
        <div class="field"><label>Core Selling Point</label><div class="value">{{ strategy.core_selling_point || '-' }}</div></div>
        <div class="field"><label>Planner Instruction</label><div class="value">{{ strategy.planner_instruction || 'None' }}</div></div>
        <div class="field"><label>Rule Pack</label><div class="value">{{ strategy.platform_rule_pack || '-' }}</div></div>
        <div class="field"><label>Platform Overlay</label><div class="value">{{ strategy.platform_overlay?.overlay_id || strategy.platform_overlay?.id || '-' }}</div></div>
      </div>

      <div class="reference-section">
        <div class="section-header">
          <h3>Reference Manifest</h3>
          <span class="subtle">{{ strategy.reference_manifest?.length || 0 }} images</span>
        </div>
        <div v-if="strategy.reference_manifest?.length" class="reference-grid">
          <div v-for="item in strategy.reference_manifest" :key="item.image_id" class="reference-card">
            <img :src="item.source_url" :alt="item.slot_type" class="reference-thumb" />
            <div class="reference-meta">
              <div class="badge-row">
                <span class="badge">{{ item.slot_type }}</span>
                <span class="order">#{{ item.display_order }}</span>
              </div>
              <div class="meta-line">{{ item.width }}x{{ item.height }}</div>
              <div class="meta-line mono">{{ item.image_id }}</div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">No reference images available.</div>
      </div>

      <div class="plan-section">
        <div class="section-header">
          <h3>Prompt Plan</h3>
          <span class="subtle">{{ strategy.prompt_plan?.length || 0 }} slots</span>
        </div>
        <div v-if="strategy.prompt_plan?.length" class="plan-grid">
          <div v-for="item in strategy.prompt_plan" :key="item.slot_id || item.role" class="plan-card">
            <div class="plan-header">
              <span class="badge">{{ item.slot_label || item.role_label || item.slot_id || item.role }}</span>
              <span class="order">Order: {{ item.display_order }}</span>
            </div>
            <div class="plan-body">
              <div class="meta-chip-row">
                <span class="chip">{{ item.planner_source || 'rule_based' }}</span>
                <span class="chip" v-if="item.white_bg_mode">white-bg branch</span>
                <span class="chip">{{ assetPlanMap[item.slot_id || item.role]?.aspect_ratio || '1:1' }}</span>
                <span class="chip" v-if="item.expression_label || item.expression_mode">{{ item.expression_label || item.expression_mode }}</span>
                <span class="chip" v-if="assetPlanMap[item.slot_id || item.role]?.emphasis_style">{{ assetPlanMap[item.slot_id || item.role]?.emphasis_style }}</span>
              </div>

              <div class="field-block" v-if="assetPlanMap[item.slot_id || item.role]?.visual_structure">
                <label>Visual Structure</label>
                <p>{{ assetPlanMap[item.slot_id || item.role]?.visual_structure }}</p>
              </div>

              <div class="field-block" v-if="assetPlanMap[item.slot_id || item.role]?.copy_density || assetPlanMap[item.slot_id || item.role]?.proof_mode || assetPlanMap[item.slot_id || item.role]?.scene_mode">
                <label>Slot Meta</label>
                <div class="tag-list">
                  <span v-if="assetPlanMap[item.slot_id || item.role]?.copy_density" class="tag">copy {{ assetPlanMap[item.slot_id || item.role]?.copy_density }}</span>
                  <span v-if="assetPlanMap[item.slot_id || item.role]?.proof_mode" class="tag">proof {{ assetPlanMap[item.slot_id || item.role]?.proof_mode }}</span>
                  <span v-if="assetPlanMap[item.slot_id || item.role]?.scene_mode" class="tag">scene {{ assetPlanMap[item.slot_id || item.role]?.scene_mode }}</span>
                </div>
              </div>

              <div class="field-block" v-if="item.slot_guardrails?.length">
                <label>Slot Guardrails</label>
                <div class="tag-list">
                  <span v-for="value in item.slot_guardrails" :key="value" class="tag">{{ value }}</span>
                </div>
              </div>

              <div class="field-block">
                <label>Reference Images Used</label>
                <div class="tag-list">
                  <span v-for="imageId in item.reference_image_ids || []" :key="imageId" class="tag mono">{{ imageId }}</span>
                </div>
              </div>

              <div class="field-block">
                <label>Editable Copy Blocks</label>
                <input class="form-control" :value="overrideFor(item).copy_blocks_override.headline || ''" @input="updateCopyBlock(item, 'headline', $event.target.value)" placeholder="主标题" />
                <input class="form-control" :value="overrideFor(item).copy_blocks_override.supporting || ''" @input="updateCopyBlock(item, 'supporting', $event.target.value)" placeholder="副标题" />
                <textarea class="form-control" rows="3" :value="linesText(overrideFor(item).copy_blocks_override.proof_lines)" @input="updateLineBlock(item, 'proof_lines', $event.target.value)" placeholder="proof_lines，一行一个"></textarea>
                <textarea class="form-control" rows="3" :value="linesText(overrideFor(item).copy_blocks_override.matrix_lines)" @input="updateLineBlock(item, 'matrix_lines', $event.target.value)" placeholder="matrix_lines，一行一个"></textarea>
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

              <div class="actions-row compact-actions">
                <button class="btn btn-secondary btn-sm" @click="saveOverrides">保存文字/Prompt</button>
                <button class="btn btn-secondary btn-sm" @click="savePromptAsTemplate(item)">保存为模板</button>
              </div>

              <div class="field-block" v-if="item.final_prompt_base"><label>Final Prompt Base</label><p>{{ item.final_prompt_base }}</p></div>
              <div class="field-block" v-if="item.must_keep?.length"><label>Must Keep</label><div class="tag-list"><span v-for="value in item.must_keep" :key="value" class="tag">{{ value }}</span></div></div>
              <div class="field-block" v-if="item.rule_modules_used?.length"><label>Rule Modules</label><div class="tag-list"><span v-for="value in item.rule_modules_used" :key="value" class="tag mono">{{ value }}</span></div></div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">No prompt plan generated.</div>
      </div>

      <div class="raw-section">
        <h3>Raw JSON</h3>
        <pre class="json-preview">{{ JSON.stringify(strategy, null, 2) }}</pre>
      </div>
    </div>

    <div v-else class="empty-state">
      <p>Build Step 5 to preview reference manifest and slot-level prompt plan.</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api/index.js'

const props = defineProps({
  sessionId: { type: String, required: true },
  strategy: { type: Object, default: null }
})

const emit = defineEmits(['build'])

const plannerInstruction = ref('')
const slotPreferencesText = ref('[]')
const preferenceError = ref('')
const overrideState = ref({})
const promptPresets = ref([])
const strategyReferenceImages = ref([])
const overrideMessage = ref('')
const strategyReferenceInput = ref(null)

watch(() => props.strategy?.planner_instruction, (value) => {
  plannerInstruction.value = value || ''
}, { immediate: true })

watch(() => props.strategy?.slot_preferences, (value) => {
  slotPreferencesText.value = JSON.stringify(value || [], null, 2)
  preferenceError.value = ''
}, { immediate: true })

watch(
  () => [props.sessionId, props.strategy?.prompt_plan],
  async () => {
    seedOverridesFromStrategy()
    await Promise.all([loadOverrides(), loadPromptPresets(), loadStrategyReferenceImages()])
  },
  { immediate: true, deep: true }
)

const assetPlanMap = computed(() => {
  const map = {}
  for (const item of props.strategy?.asset_plan || []) {
    map[item.slot_id || item.role] = item
  }
  return map
})

function seedOverridesFromStrategy() {
  const next = {}
  for (const item of props.strategy?.prompt_plan || []) {
    const slotId = item.slot_id || item.role
    next[slotId] = {
      slot_id: slotId,
      copy_blocks_override: { ...(item.copy_blocks || {}) },
      raw_prompt_override: item.raw_prompt_override || '',
      expression_mode_override: item.expression_mode || '',
      applied_preset_id: item.applied_preset_id || '',
      locked: false,
    }
  }
  overrideState.value = next
}

async function loadOverrides() {
  if (!props.sessionId) return
  try {
    const data = await api.getStrategyOverrides(props.sessionId)
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
    console.error('Failed to load overrides', error)
  }
}

async function loadPromptPresets() {
  try {
    const data = await api.getPromptPresets({ asset_family: 'main_gallery' })
    promptPresets.value = data.presets || []
  } catch (error) {
    console.error('Failed to load prompt presets', error)
  }
}

async function loadStrategyReferenceImages() {
  if (!props.sessionId) return
  try {
    const data = await api.getStrategyReferenceImages(props.sessionId)
    strategyReferenceImages.value = data.images || []
  } catch (error) {
    console.error('Failed to load strategy reference images', error)
  }
}

function applicablePresets(item) {
  const overlayId = props.strategy?.platform_overlay?.overlay_id || props.strategy?.platform_overlay?.id || null
  return promptPresets.value.filter((preset) => {
    if (!['slot_recipe', 'raw_prompt'].includes(preset.preset_type)) return false
    const platformOk = !preset.platform_id || preset.platform_id === overlayId
    const slotOk = !preset.slot_family || preset.slot_family === item.slot_family
    return platformOk && slotOk
  })
}

function overrideFor(item) {
  const slotId = item.slot_id || item.role
  if (!overrideState.value[slotId]) {
    overrideState.value[slotId] = {
      slot_id: slotId,
      copy_blocks_override: { ...(item.copy_blocks || {}) },
      raw_prompt_override: '',
      expression_mode_override: item.expression_mode || '',
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
    await api.saveStrategyOverrides(props.sessionId, overrides)
    overrideMessage.value = '主图 override 已保存'
    handleBuild()
  } catch (error) {
    overrideMessage.value = error.message || '主图 override 保存失败'
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
      asset_family: 'main_gallery',
      platform_id: props.strategy?.platform_overlay?.overlay_id || props.strategy?.platform_overlay?.id || null,
      slot_family: item.slot_family || null,
      category: null,
      locale: props.strategy?.platform_overlay?.locale || null,
      style_summary: null,
      default_expression_mode: current.expression_mode_override || item.expression_mode || null,
      copy_blocks_template: current.copy_blocks_override || {},
      raw_prompt_template: current.raw_prompt_override || null,
      tags: [item.slot_id || item.role],
    })
    overrideMessage.value = '模板已保存到 Prompt 仓库'
    await loadPromptPresets()
  } catch (error) {
    overrideMessage.value = error.message || '保存模板失败'
  }
}

function parseSlotPreferences() {
  const parsed = JSON.parse(slotPreferencesText.value || '[]')
  if (!Array.isArray(parsed)) {
    throw new Error('Slot Preferences JSON must be an array.')
  }
  return parsed
}

function handleBuild() {
  try {
    const parsed = parseSlotPreferences()
    preferenceError.value = ''
    emit('build', {
      plannerInstruction: plannerInstruction.value || null,
      slotPreferences: parsed,
    })
  } catch (error) {
    preferenceError.value = error.message || 'Invalid JSON'
  }
}

function triggerReferenceUpload() {
  strategyReferenceInput.value?.click()
}

async function handleStrategyReferenceUpload(event) {
  const file = event.target.files?.[0]
  if (!file || !props.sessionId) return
  try {
    await api.uploadStrategyReferenceImage(props.sessionId, file, strategyReferenceImages.value.length + 1)
    overrideMessage.value = '策略参考图已上传'
    await loadStrategyReferenceImages()
    handleBuild()
  } catch (error) {
    overrideMessage.value = error.message || '策略参考图上传失败'
  } finally {
    if (strategyReferenceInput.value) {
      strategyReferenceInput.value.value = ''
    }
  }
}

async function deleteStrategyReference(imageId) {
  if (!props.sessionId) return
  try {
    await api.deleteStrategyReferenceImage(props.sessionId, imageId)
    overrideMessage.value = '策略参考图已删除'
    await loadStrategyReferenceImages()
    handleBuild()
  } catch (error) {
    overrideMessage.value = error.message || '策略参考图删除失败'
  }
}
</script>

<style scoped>
.strategy-preview {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.card-lite,
.meta-section,
.json-preview,
.empty-state {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.planner-panel {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.actions-row {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.strategy-content {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.meta-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  padding: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field label,
.field-block label {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.field .value {
  color: var(--text-primary);
  font-weight: 500;
  line-height: 1.5;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header h3,
.raw-section h3 {
  margin: 0;
  color: var(--text-primary);
}

.subtle {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.error-text {
  color: #f87171;
  font-size: 0.82rem;
}

.hidden-input {
  display: none;
}

.reference-grid,
.plan-grid {
  display: grid;
  gap: 1rem;
}

.reference-grid {
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
}

.reference-card,
.plan-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.reference-thumb {
  width: 100%;
  height: 180px;
  object-fit: contain;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border-color);
}

.reference-meta,
.plan-body {
  padding: 0.9rem 1rem;
}

.badge-row,
.plan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.plan-header {
  padding: 0.75rem 1rem;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.badge,
.chip,
.tag {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  font-size: 0.76rem;
}

.badge {
  background: var(--accent-blue);
  color: white;
  text-transform: capitalize;
}

.chip {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.tag {
  background: rgba(41, 128, 185, 0.12);
  color: var(--accent-blue);
  border: 1px solid rgba(41, 128, 185, 0.2);
}

.tag.danger {
  background: rgba(192, 57, 43, 0.12);
  color: #c0392b;
  border-color: rgba(192, 57, 43, 0.2);
}

.mono {
  font-family: monospace;
}

.meta-line {
  color: var(--text-secondary);
  font-size: 0.86rem;
  line-height: 1.5;
}

.plan-grid {
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}

.meta-chip-row,
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.plan-body {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.compact-json {
  margin: 0;
  padding: 0.75rem;
  font-size: 0.82rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.form-control {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 0.7rem;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.link-btn {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
}

.compact-actions {
  justify-content: flex-start;
}

.field-block p {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.5;
}

.json-preview {
  padding: 1rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.empty-state {
  padding: 1.25rem;
  color: var(--text-muted);
  text-align: center;
}

.btn {
  padding: 0.55rem 1rem;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  border: none;
}

.btn-primary {
  background: var(--accent-blue);
  color: white;
}

textarea {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 0.75rem;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.95rem;
}

textarea:focus {
  outline: none;
  border-color: var(--accent-blue);
}
</style>
