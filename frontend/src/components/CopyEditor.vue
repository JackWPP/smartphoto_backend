<template>
  <div class="copy-editor">
    <div class="editor-section">
      <h4>Step 4 正式字段</h4>
      <p class="section-desc">Step 3 参数提取和后续策略统一基于这 4 个正式字段与风格配置。</p>

      <div class="form-grid two-col">
        <div class="form-group">
          <label for="product_name">产品名称</label>
          <input id="product_name" v-model="localCopy.product_name" class="form-control" type="text" />
        </div>
        <div class="form-group">
          <label for="category">品类</label>
          <input id="category" v-model="localCopy.category" class="form-control" type="text" />
        </div>
      </div>

      <div class="form-group">
        <label for="hero_scene">首图场景</label>
        <input id="hero_scene" v-model="localCopy.hero_scene" class="form-control" type="text" placeholder="如：宠物家庭、客厅净化、母婴卧室" />
      </div>

      <div class="array-section">
        <div class="section-header">
          <h5>核心卖点</h5>
          <button class="btn btn-secondary" @click="addSellingPoint">新增卖点</button>
        </div>
        <div v-for="(item, index) in localCopy.core_selling_points" :key="`sp-${index}`" class="array-row">
          <input v-model="localCopy.core_selling_points[index]" class="form-control" type="text" placeholder="输入卖点" />
          <button class="btn btn-danger" @click="removeSellingPoint(index)">删除</button>
        </div>
      </div>

      <div class="parameter-card">
        <div class="section-header">
          <h5>核心参数</h5>
          <button class="btn btn-secondary" @click="addKeyParameter">新增参数</button>
        </div>
        <div v-for="(item, index) in localCopy.key_parameters" :key="`kp-${index}`" class="parameter-row">
          <input v-model="item.label" class="form-control" type="text" placeholder="参数名" />
          <input v-model="item.value" class="form-control" type="text" placeholder="参数值" />
          <input v-model="item.unit" class="form-control" type="text" placeholder="单位" />
          <button class="btn btn-danger" @click="removeKeyParameter(index)">删除</button>
        </div>
      </div>

      <div class="array-section">
        <div class="section-header">
          <h5>产品优势</h5>
          <button class="btn btn-secondary" @click="addAdvantage">新增优势</button>
        </div>
        <div v-for="(item, index) in localCopy.product_advantages" :key="`adv-${index}`" class="array-row">
          <input v-model="localCopy.product_advantages[index]" class="form-control" type="text" placeholder="输入产品优势" />
          <button class="btn btn-danger" @click="removeAdvantage(index)">删除</button>
        </div>
      </div>

      <div class="preset-row">
        <div class="form-group">
          <label>风格预设</label>
          <select v-model="localCopy.style_preset_id" class="form-control">
            <option value="">不使用预设</option>
            <option v-for="preset in stylePresets" :key="preset.preset_id" :value="preset.preset_id">
              {{ preset.name }}
            </option>
          </select>
        </div>
        <button class="btn btn-secondary" @click="applySelectedStylePreset" :disabled="!localCopy.style_preset_id">
          套用风格预设
        </button>
      </div>

      <div class="form-group">
        <label for="style_custom">自定义风格补充</label>
        <textarea
          id="style_custom"
          v-model="localCopy.style_custom"
          class="form-control"
          rows="3"
          placeholder="补充色调、材质感、光影、字体或品牌风格偏好"
        ></textarea>
      </div>

      <div class="actions">
        <button class="btn btn-primary" @click="saveCopy">保存正式字段</button>
      </div>
    </div>

    <div class="parameter-section">
      <h4>Step 3 参数附件与提取</h4>
      <p class="section-desc">上传说明书、参数图或 PDF，触发参数提取。提取完成后会直接覆盖上面的 4 个正式字段。</p>

      <div class="actions inline-actions">
        <input ref="parameterInput" type="file" accept=".jpg,.jpeg,.png,.webp,.pdf" @change="handleParameterUpload" />
        <button class="btn btn-secondary" @click="extractParameters" :disabled="isExtracting || !parameterAttachments.length">
          {{ isExtracting ? '提取中...' : '提取参数' }}
        </button>
      </div>

      <div v-if="parameterAttachments.length" class="tag-list">
        <span v-for="attachment in parameterAttachments" :key="attachment.attachment_id" class="tag">
          {{ attachment.original_name }}
          <button class="link-btn" @click="deleteParameterAttachment(attachment.attachment_id)">×</button>
        </span>
      </div>

      <details class="json-debug">
        <summary>查看原始参数结果 JSON</summary>
        <div class="form-group">
          <textarea
            v-model="parameterSnapshotText"
            class="form-control"
            rows="10"
            placeholder='{"hero_scene":"客厅净化","core_selling_points":["低噪","高效净化"]}'
          ></textarea>
        </div>
        <div class="actions">
          <button class="btn btn-secondary" @click="saveParameters">保存原始参数结果</button>
        </div>
      </details>
      <p v-if="parameterMessage" class="section-desc">{{ parameterMessage }}</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../api/index.js'

const props = defineProps({
  sessionId: {
    type: String,
    required: true,
  },
  copy: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['save', 'regenerate'])

const stylePresets = ref([])
const parameterAttachments = ref([])
const parameterSnapshotText = ref('{}')
const isExtracting = ref(false)
const parameterMessage = ref('')
const parameterInput = ref(null)
const localCopy = ref(createDefaultCopy())

function createDefaultCopy() {
  return {
    product_name: '',
    category: '',
    hero_scene: '',
    core_selling_points: [],
    key_parameters: [],
    product_advantages: [],
    style_preset_id: '',
    style_custom: '',
    style_choice: '',
  }
}

function normalizeCopy(copy) {
  const source = copy && typeof copy === 'object' ? copy : {}
  return {
    product_name: source.product_name || '',
    category: source.category || '',
    hero_scene: source.hero_scene || '',
    core_selling_points: Array.isArray(source.core_selling_points) ? [...source.core_selling_points] : [],
    key_parameters: Array.isArray(source.key_parameters)
      ? source.key_parameters.map((item, index) => ({
          key: item?.key || `param_${index + 1}`,
          label: item?.label || '',
          value: item?.value || '',
          unit: item?.unit || '',
          confidence: item?.confidence ?? null,
          editable: item?.editable ?? true,
        }))
      : [],
    product_advantages: Array.isArray(source.product_advantages) ? [...source.product_advantages] : [],
    style_preset_id: source.style_preset_id || '',
    style_custom: source.style_custom || '',
    style_choice: source.style_choice || '',
  }
}

function syncLocalCopy() {
  localCopy.value = normalizeCopy(props.copy)
}

onMounted(() => {
  syncLocalCopy()
  void loadStylePresets()
  void loadParameterAttachments()
  void loadParameters()
})

watch(
  () => props.copy,
  () => {
    syncLocalCopy()
  },
  { deep: true, immediate: true },
)

watch(
  () => props.sessionId,
  () => {
    syncLocalCopy()
    void loadStylePresets()
    void loadParameterAttachments()
    void loadParameters()
  },
)

function saveCopy() {
  emit('save', { ...localCopy.value })
}

function addSellingPoint() {
  localCopy.value.core_selling_points.push('')
}

function removeSellingPoint(index) {
  localCopy.value.core_selling_points.splice(index, 1)
}

function addAdvantage() {
  localCopy.value.product_advantages.push('')
}

function removeAdvantage(index) {
  localCopy.value.product_advantages.splice(index, 1)
}

function addKeyParameter() {
  localCopy.value.key_parameters.push({
    key: `param_${localCopy.value.key_parameters.length + 1}`,
    label: '',
    value: '',
    unit: '',
    confidence: null,
    editable: true,
  })
}

function removeKeyParameter(index) {
  localCopy.value.key_parameters.splice(index, 1)
}

async function loadStylePresets() {
  if (!props.sessionId) return
  try {
    const data = await api.getPromptPresets({ preset_type: 'style', asset_family: 'main_gallery' })
    stylePresets.value = data.presets || []
  } catch (error) {
    console.error('Failed to load style presets', error)
  }
}

function applySelectedStylePreset() {
  const preset = stylePresets.value.find((item) => item.preset_id === localCopy.value.style_preset_id)
  if (!preset) return
  if (!localCopy.value.style_custom) {
    localCopy.value.style_custom = preset.style_summary || ''
  }
}

async function loadParameterAttachments() {
  if (!props.sessionId) return
  try {
    const data = await api.getParameterAttachments(props.sessionId)
    parameterAttachments.value = data.attachments || []
  } catch (error) {
    console.error('Failed to load parameter attachments', error)
  }
}

async function refreshCopy() {
  if (!props.sessionId) return
  try {
    const data = await api.getCopy(props.sessionId)
    localCopy.value = normalizeCopy(data)
  } catch (error) {
    console.error('Failed to refresh copy', error)
  }
}

async function handleParameterUpload(event) {
  const file = event.target.files?.[0]
  if (!file || !props.sessionId) return
  try {
    await api.uploadParameterAttachment(props.sessionId, file, parameterAttachments.value.length + 1)
    parameterMessage.value = '参数附件已上传'
    await loadParameterAttachments()
  } catch (error) {
    parameterMessage.value = error.message || '参数附件上传失败'
  } finally {
    if (parameterInput.value) {
      parameterInput.value.value = ''
    }
  }
}

async function deleteParameterAttachment(attachmentId) {
  if (!props.sessionId) return
  try {
    await api.deleteParameterAttachment(props.sessionId, attachmentId)
    parameterMessage.value = '参数附件已删除'
    await loadParameterAttachments()
  } catch (error) {
    parameterMessage.value = error.message || '参数附件删除失败'
  }
}

async function loadParameters() {
  if (!props.sessionId) return
  try {
    const data = await api.getParameters(props.sessionId)
    parameterSnapshotText.value = JSON.stringify(data.parameter_snapshot || {}, null, 2)
  } catch (error) {
    console.error('Failed to load parameters', error)
  }
}

async function extractParameters() {
  if (!props.sessionId) return
  isExtracting.value = true
  try {
    const job = await api.extractParameters(props.sessionId)
    await waitForJob(job.job_id)
    await Promise.all([loadParameters(), refreshCopy()])
    parameterMessage.value = '参数提取已完成，正式字段已覆盖更新'
  } catch (error) {
    parameterMessage.value = error.message || '参数提取失败'
  } finally {
    isExtracting.value = false
  }
}

async function saveParameters() {
  if (!props.sessionId) return
  try {
    const parsed = JSON.parse(parameterSnapshotText.value || '{}')
    await api.saveParameters(props.sessionId, parsed)
    await Promise.all([loadParameters(), refreshCopy()])
    parameterMessage.value = '参数结果已保存并覆盖正式字段'
  } catch (error) {
    parameterMessage.value = error.message || '参数结果 JSON 非法'
  }
}

async function waitForJob(jobId) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const job = await api.getJob(jobId)
    if (job.status === 'succeeded') return
    if (job.status === 'failed') {
      throw new Error(job.error_message || 'job failed')
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error('job timeout')
}
</script>

<style scoped>
.copy-editor {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.editor-section,
.parameter-section {
  background-color: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  padding: 1.5rem;
}

.form-grid {
  display: grid;
  gap: 1rem;
}

.two-col {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.preset-row,
.array-row,
.parameter-row,
.section-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.section-header {
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.array-section,
.parameter-card {
  margin-top: 1.5rem;
}

.array-row,
.parameter-row {
  margin-bottom: 0.75rem;
}

.array-row .form-control,
.parameter-row .form-control,
.preset-row .form-group {
  flex: 1;
}

.form-control {
  background-color: var(--bg-tertiary, #2a2a2a);
  border: 1px solid var(--border-color, #444);
  color: var(--text-primary, #fff);
  padding: 0.75rem;
  border-radius: 4px;
  font-family: inherit;
  resize: vertical;
}

.form-control:focus {
  outline: none;
  border-color: var(--accent-blue, #3b82f6);
  box-shadow: 0 0 0 1px var(--accent-blue, #3b82f6);
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color, #333);
}

.inline-actions {
  align-items: center;
  justify-content: flex-start;
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  border: none;
  transition: opacity 0.2s;
}

.btn:hover {
  opacity: 0.9;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background-color: var(--accent-blue, #3b82f6);
  color: white;
}

.btn-secondary {
  background-color: transparent;
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-color, #555);
}

.btn-danger {
  background-color: rgba(239, 68, 68, 0.18);
  color: #fecaca;
  border: 1px solid rgba(239, 68, 68, 0.4);
}

.section-desc {
  color: var(--text-secondary, #a0a0a0);
  font-size: 0.9rem;
  margin-top: 0;
}

.tag-list {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary, #fff);
}

.link-btn {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
}

.json-debug {
  margin-top: 1rem;
}

.json-debug summary {
  cursor: pointer;
  color: var(--text-primary, #fff);
  margin-bottom: 0.75rem;
}

label,
h4,
h5 {
  color: var(--text-primary, #fff);
}

@media (max-width: 900px) {
  .two-col {
    grid-template-columns: 1fr;
  }

  .preset-row,
  .array-row,
  .parameter-row,
  .section-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
