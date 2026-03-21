<template>
  <div class="generation-panel">
    <!-- Generate Section -->
    <div class="generate-section card">
      <div class="header">
        <h3>Generate Images</h3>
        <button 
          class="btn btn-primary generate-btn" 
          @click="handleGenerate"
          :disabled="!sessionId || isGenerating"
        >
          <span v-if="isGenerating" class="spinner"></span>
          {{ isGenerating ? 'Generating...' : 'Generate Gallery' }}
        </button>
      </div>
      
      <div class="form-group">
        <label>Instruction (Optional)</label>
        <textarea 
          v-model="instruction" 
          placeholder="Any specific instructions for this generation?"
          rows="2"
        ></textarea>
      </div>
    </div>

    <div class="prompt-debug card">
      <div class="header prompt-debug-header">
        <div>
          <h3>Prompt Debug</h3>
          <p v-if="promptPreview" class="prompt-debug-meta">
            Model: {{ promptPreview.model }} | Size: {{ promptPreview.image_size }}
          </p>
        </div>
        <div class="actions">
          <button class="btn btn-secondary btn-sm" @click="refreshPromptPreview" :disabled="!sessionId || promptPreviewLoading">
            {{ promptPreviewLoading ? 'Refreshing...' : 'Refresh Prompt Preview' }}
          </button>
          <button class="btn btn-secondary btn-sm" @click="showPromptDebug = !showPromptDebug">
            {{ showPromptDebug ? 'Collapse' : 'Expand' }}
          </button>
        </div>
      </div>

      <div v-if="showPromptDebug" class="prompt-debug-content">
        <div v-if="promptPreviewError" class="empty-state">
          <p>{{ promptPreviewError }}</p>
        </div>
        <div v-else-if="promptPreviewLoading && !promptPreview" class="empty-state">
          <p>Loading prompt preview...</p>
        </div>
        <div v-if="promptPreview?.reference_manifest?.length" class="prompt-manifest">
          <label>Current Reference Manifest</label>
          <div class="field-tags">
            <span
              v-for="image in promptPreview.reference_manifest"
              :key="image.image_id"
              class="field-tag"
            >
              {{ image.slot_type }} · {{ image.image_id.slice(0, 8) }}
            </span>
          </div>
        </div>
        <div v-if="promptCards.length" class="prompt-grid">
          <div v-for="prompt in promptCards" :key="`${prompt.slot_id || prompt.role}-${prompt.display_order}`" class="prompt-card">
            <div class="plan-header">
              <span class="badge">{{ prompt.slot_label || prompt.role_label || prompt.slot_id || prompt.role }}</span>
              <span class="order">Order: {{ prompt.display_order }}</span>
            </div>

            <div class="prompt-chips">
              <span class="chip">{{ prompt.aspect_ratio }}</span>
              <span class="chip">{{ prompt.background_mode }}</span>
              <span class="chip">{{ prompt.text_policy }}</span>
              <span class="chip" v-if="prompt.expression_label || prompt.expression_mode">{{ prompt.expression_label || prompt.expression_mode }}</span>
              <span class="chip" v-if="prompt.emphasis_style">{{ prompt.emphasis_style }}</span>
            </div>

            <div class="prompt-section" v-if="prompt.visual_structure || prompt.copy_density || prompt.proof_mode || prompt.scene_mode">
              <label>Slot Structure</label>
              <div class="snapshot-meta" v-if="prompt.visual_structure">Visual Structure: {{ prompt.visual_structure }}</div>
              <div class="field-tags">
                <span v-if="prompt.copy_density" class="field-tag">copy {{ prompt.copy_density }}</span>
                <span v-if="prompt.proof_mode" class="field-tag">proof {{ prompt.proof_mode }}</span>
                <span v-if="prompt.scene_mode" class="field-tag">scene {{ prompt.scene_mode }}</span>
              </div>
            </div>

            <div class="prompt-section" v-if="prompt.slot_guardrails?.length">
              <label>Slot Guardrails</label>
              <div class="field-tags">
                <span v-for="item in prompt.slot_guardrails" :key="item" class="field-tag">{{ item }}</span>
              </div>
            </div>

            <div class="prompt-section" v-if="prompt.copy_policy_applied && Object.keys(prompt.copy_policy_applied).length">
              <label>Copy Policy</label>
              <div class="snapshot-meta" v-if="prompt.copy_policy_applied.summary">{{ prompt.copy_policy_applied.summary }}</div>
              <div class="field-tags">
                <span class="field-tag">headline ≤ {{ prompt.copy_policy_applied.headline_max_chars || 0 }}</span>
                <span class="field-tag">supporting lines {{ prompt.copy_policy_applied.supporting_max_lines || 0 }}</span>
                <span class="field-tag">benefits {{ prompt.copy_policy_applied.benefit_point_max || 0 }}</span>
                <span class="field-tag">proof tags {{ prompt.copy_policy_applied.proof_tag_max || 0 }}</span>
                <span class="field-tag" v-if="prompt.copy_policy_applied.selected_visible_copy_count !== undefined">
                  visible copy {{ prompt.copy_policy_applied.selected_visible_copy_count }}
                </span>
                <span class="field-tag" v-if="prompt.copy_policy_applied.degraded_to_minimal_copy">
                  degraded to minimal copy
                </span>
              </div>
            </div>

            <div class="prompt-blocks">
              <div v-for="blockKey in promptBlockOrder" :key="blockKey" class="prompt-block" v-if="prompt.blocks?.[blockKey]">
                <label>{{ promptBlockLabels[blockKey] }}</label>
                <p>{{ prompt.blocks[blockKey] }}</p>
              </div>
            </div>

            <div class="prompt-section">
              <div class="prompt-section-header">
                <label>Final Prompt</label>
                <div class="actions">
                  <button class="btn btn-secondary btn-sm" @click="copyPrompt(prompt.final_prompt)">Copy Prompt</button>
                  <button class="btn btn-primary btn-sm" @click="triggerSingleSlotGenerate(prompt)" :disabled="isGenerating">
                    Generate This Slot
                  </button>
                </div>
              </div>
              <pre class="json-preview prompt-text">{{ prompt.final_prompt }}</pre>
            </div>

            <div class="prompt-section" v-if="prompt.strategy_fields_used?.length">
              <label>Strategy Fields Used</label>
              <div class="field-tags">
                <span v-for="field in prompt.strategy_fields_used" :key="field" class="field-tag">{{ field }}</span>
              </div>
            </div>

            <div class="prompt-section" v-if="prompt.prompt_sections_used?.length">
              <label>Prompt Sections Used</label>
              <div class="field-tags">
                <span v-for="field in prompt.prompt_sections_used" :key="field" class="field-tag">{{ field }}</span>
              </div>
            </div>

            <div class="prompt-section" v-if="prompt.reference_images_used?.length">
              <label>Reference Images Used</label>
              <div class="field-tags">
                <span
                  v-for="image in prompt.reference_images_used"
                  :key="image.image_id"
                  class="field-tag"
                >
                  {{ image.slot_type }} · {{ image.image_id.slice(0, 8) }}
                </span>
              </div>
              <div class="snapshot-meta">Planner Source: {{ prompt.planner_source }}</div>
            </div>

            <div class="prompt-section" v-if="prompt.copy_blocks && Object.keys(prompt.copy_blocks).length">
              <label>Copy Blocks</label>
              <pre class="json-preview prompt-text">{{ JSON.stringify(prompt.copy_blocks, null, 2) }}</pre>
            </div>

            <div class="prompt-section" v-if="prompt.rule_modules_used?.length">
              <label>Rule Modules</label>
              <div class="field-tags">
                <span v-for="moduleId in prompt.rule_modules_used" :key="moduleId" class="field-tag">{{ moduleId }}</span>
              </div>
            </div>

            <div class="prompt-section" v-if="latestAssetFor(prompt)">
              <label>Latest prompt_snapshot</label>
              <div class="snapshot-meta">
                Version {{ latestAssetFor(prompt).version_no }} · {{ latestAssetFor(prompt).slot_id || latestAssetFor(prompt).role }} · order {{ latestAssetFor(prompt).display_order }}
              </div>
              <pre class="json-preview prompt-text">{{ latestAssetFor(prompt).prompt_snapshot }}</pre>
              <div v-if="latestAssetFor(prompt).edit_instruction" class="snapshot-meta">
                Edit Instruction: {{ latestAssetFor(prompt).edit_instruction }}
              </div>
              <div v-if="latestAssetFor(prompt).generation_snapshot" class="snapshot-meta">
                Upstream: {{ latestAssetFor(prompt).generation_snapshot.upstream_endpoint || '-' }}
              </div>
              <div v-if="latestAssetFor(prompt).generation_snapshot?.timing?.render_total_ms" class="snapshot-meta">
                Render: {{ latestAssetFor(prompt).generation_snapshot.timing.render_total_ms }}ms
              </div>
              <div v-if="latestAssetFor(prompt).expression_mode" class="snapshot-meta">
                Expression: {{ latestAssetFor(prompt).expression_mode }}
              </div>
              <div v-if="latestAssetFor(prompt).rule_pack_id" class="snapshot-meta">
                Rule Pack: {{ latestAssetFor(prompt).rule_pack_id }}
              </div>
              <div v-if="latestAssetFor(prompt).generation_snapshot?.reference_image_ids?.length" class="field-tags">
                <span
                  v-for="imageId in latestAssetFor(prompt).generation_snapshot.reference_image_ids"
                  :key="imageId"
                  class="field-tag"
                >
                  used {{ imageId.slice(0, 8) }}
                </span>
              </div>
              <div v-if="latestAssetFor(prompt).generation_snapshot?.planner_instruction" class="snapshot-meta">
                Planner Instruction: {{ latestAssetFor(prompt).generation_snapshot.planner_instruction }}
              </div>
              <pre
                v-if="latestAssetFor(prompt).generation_snapshot"
                class="json-preview prompt-text"
              >{{ JSON.stringify(latestAssetFor(prompt).generation_snapshot, null, 2) }}</pre>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>No prompt preview available yet.</p>
        </div>
      </div>
    </div>

    <!-- Results Section -->
    <div class="results-section card" v-if="results">
      <div class="header results-header">
        <h3>📸 Results Gallery ({{ filteredResults.length }} images)</h3>
        <div class="version-selector">
          <label>Version:</label>
          <select v-model="selectedVersion">
            <option v-for="v in availableVersions" :key="v" :value="v">
              Version {{ v }} {{ v === latestVersion ? '(Latest)' : '' }}
            </option>
          </select>
        </div>
        <div class="actions">
          <button class="btn btn-secondary" @click="$emit('refresh')" :disabled="isGenerating">🔄 Refresh</button>
          <button class="btn btn-primary" @click="$emit('download', selectedVersion)" :disabled="!filteredResults.length || isGenerating">
            ⬇️ Download ZIP
          </button>
        </div>
      </div>

      <!-- Summary Stats -->
      <div class="results-stats" v-if="results.summary">
        <div class="stat-item">
          <span class="stat-label">Total:</span>
          <span class="stat-value">{{ results.summary.total_count }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Ready:</span>
          <span class="stat-value text-success">{{ results.summary.ready_count }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Round:</span>
          <span class="stat-value">{{ results.generation_round }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Latest Version:</span>
          <span class="stat-value">{{ results.latest_result_version }}</span>
        </div>
      </div>

      <!-- Global Actions for this version -->
      <div class="global-actions" v-if="filteredResults.length">
        <div class="global-edit-form">
          <input type="text" v-model="globalInstruction" placeholder="Global instruction (e.g., 'Make background lighter')" />
          <select v-model="globalScope">
            <option value="all">All generated images</option>
            <option value="failed">Failed only</option>
          </select>
          <button class="btn btn-secondary btn-sm" @click="handleGlobalEdit" :disabled="!globalInstruction || isGenerating">
            ✏️ Global Edit
          </button>
        </div>
        <button class="btn btn-warning btn-sm" @click="$emit('regenerateGallery')" :disabled="isGenerating">
          🔄 Regenerate All (New Version)
        </button>
      </div>

      <!-- Image Grid -->
      <div class="image-grid" v-if="filteredResults.length">
        <div v-for="asset in filteredResults" :key="asset.asset_id" class="image-card" :class="asset.status || 'ready'">
          <div class="img-wrapper">
            <img v-if="asset.image_url || asset.url" :src="asset.image_url || asset.url" :alt="asset.role || 'generated'" />
            <div v-else-if="asset.status === 'processing' || asset.status === 'pending'" class="status-indicator processing">
              <span class="spinner"></span> Processing...
            </div>
            <div v-else-if="asset.status === 'failed'" class="status-indicator failed">
              Failed
            </div>
            <div v-else class="status-indicator">
              No Image
            </div>
          </div>
          
            <div class="img-info">
              <div class="meta">
              <span class="badge role">{{ asset.slot_id || asset.role || 'generated' }}</span>
              <span class="badge status" :class="asset.status || 'ready'">{{ asset.status || 'ready' }}</span>
            </div>
            <div class="asset-meta">
              <small>Order: {{ asset.display_order }}</small>
              <small v-if="asset.width && asset.height">{{ asset.width }}x{{ asset.height }}</small>
              <small v-if="asset.expression_mode">Expression: {{ asset.expression_mode }}</small>
              <small v-if="asset.rule_pack_id">Pack: {{ asset.rule_pack_id }}</small>
              <small v-if="asset.render_total_ms != null">Render: {{ asset.render_total_ms }}ms</small>
            </div>
            <div class="actions mt-2">
              <button class="btn btn-secondary btn-sm full-width" @click="$emit('editSlot', asset.slot_id || asset.role)" :disabled="isGenerating">
                Edit Text
              </button>
              <button class="btn btn-secondary btn-sm full-width" @click="$emit('regenerateAsset', asset.asset_id || asset.id)" :disabled="isGenerating">
                Regenerate Single
              </button>
            </div>
            <div class="debug-info mt-1">
              <small>ID: {{ (asset.asset_id || asset.id || 'unknown').substring(0, 8) }}...</small>
            </div>
          </div>
        </div>
      </div>
      
      <div v-else class="empty-state">
        <div class="empty-icon">📭</div>
        <p>No images found for version {{ selectedVersion }}.</p>
        <p class="hint">Try selecting a different version or generate new images.</p>
      </div>
    </div>
    
    <!-- Initial Empty State - No results yet -->
    <div v-else-if="!isGenerating" class="results-section card empty-results">
      <div class="empty-state large">
        <div class="empty-icon">🎨</div>
        <h3>No Generated Images Yet</h3>
        <p>Click "Generate Gallery" above to create your first set of images.</p>
        <div class="generation-info">
          <div class="info-item">
            <span class="info-label">Latest Version:</span>
            <span class="info-value">{{ latestVersion }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Session Status:</span>
            <span class="info-value">{{ results?.status || 'Ready' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { api } from '../api/index.js'

const props = defineProps({
  sessionId: String,
  results: {
    type: Object,
    default: null
  },
  latestVersion: {
    type: Number,
    default: 1
  },
  isGenerating: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'generate', 
  'generateSingle',
  'globalEdit', 
  'regenerateGallery', 
  'regenerateAsset', 
  'editSlot',
  'download',
  'refresh',
  'refreshVersion'
])

const instruction = ref('')
const selectedVersion = ref(props.latestVersion || 1)
const globalInstruction = ref('')
const globalScope = ref('all')
const showPromptDebug = ref(true)
const promptPreview = ref(null)
const promptPreviewLoading = ref(false)
const promptPreviewError = ref('')

const promptBlockOrder = ['goal', 'subject', 'composition', 'background', 'style', 'selling_points', 'constraints', 'instruction']
const promptBlockLabels = {
  goal: 'Goal',
  subject: 'Subject',
  composition: 'Composition',
  background: 'Background',
  style: 'Style',
  selling_points: 'Selling Points',
  constraints: 'Constraints',
  instruction: 'Instruction'
}

// Update selected version when latest version changes
watch(() => props.latestVersion, (newVal) => {
  if (newVal && newVal > selectedVersion.value) {
    selectedVersion.value = newVal
  }
}, { immediate: true })

watch(
  () => props.results,
  (value) => {
    const maxVersion = value?.latest_result_version || props.latestVersion || 1
    if (maxVersion && maxVersion !== selectedVersion.value) {
      selectedVersion.value = maxVersion
    }
  },
  { immediate: true, deep: true }
)

const availableVersions = computed(() => {
  if (props.results?.available_versions?.length) return props.results.available_versions
  if (!props.results || !props.results.assets || props.results.assets.length === 0) return [props.latestVersion || 1]
  const versions = new Set(props.results.assets.map(r => r.version_no).filter(v => v != null))
  if (versions.size === 0) return [props.latestVersion || 1]
  return Array.from(versions).sort((a, b) => b - a)
})

const filteredResults = computed(() => {
  const assets = props.results?.assets || []
  const requestedVersion = props.results?.requested_version ?? selectedVersion.value
  return assets.filter(r => r.version_no === requestedVersion)
})

const promptCards = computed(() => promptPreview.value?.prompts || [])

const latestAssetMap = computed(() => {
  const map = {}
  for (const asset of promptPreview.value?.latest_assets || []) {
    map[`${asset.slot_id || asset.role}:${asset.display_order}`] = asset
  }
  return map
})

watch(
  () => [props.sessionId, props.latestVersion],
  ([sessionId]) => {
    if (!sessionId) {
      promptPreview.value = null
      promptPreviewError.value = ''
      return
    }
    refreshPromptPreview()
  },
  { immediate: true }
)

watch(
  () => selectedVersion.value,
  (value) => {
    if (!props.sessionId) return
    if ((props.results?.requested_version || props.latestVersion || 1) === value) return
    emit('refreshVersion', value)
  }
)

const handleGenerate = () => {
  emit('generate', { instruction: instruction.value, slotIds: [] })
  instruction.value = ''
}

const triggerSingleSlotGenerate = (prompt) => {
  const slotId = prompt?.slot_id || prompt?.role
  if (!slotId) return
  emit('generateSingle', {
    instruction: instruction.value || null,
    slotIds: [slotId],
  })
}

const handleGlobalEdit = () => {
  emit('globalEdit', {
    instruction: globalInstruction.value,
    scope: globalScope.value
  })
  globalInstruction.value = ''
}

async function refreshPromptPreview() {
  if (!props.sessionId) return

  promptPreviewLoading.value = true
  promptPreviewError.value = ''
  try {
    promptPreview.value = await api.previewPrompts(props.sessionId, instruction.value || null, true)
  } catch (error) {
    promptPreview.value = null
    if ([40002, 40003].includes(error.code)) {
      promptPreviewError.value = 'Prompt preview 需要先完成 copy 和 active platform 配置。'
      return
    }
    promptPreviewError.value = error.message || 'Failed to load prompt preview.'
  } finally {
    promptPreviewLoading.value = false
  }
}

function latestAssetFor(prompt) {
  return latestAssetMap.value[`${prompt.slot_id || prompt.role}:${prompt.display_order}`] || null
}

async function copyPrompt(text) {
  if (!text) return
  await navigator.clipboard.writeText(text)
}
</script>

<style scoped>
.generation-panel {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1.5rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.header h3 {
  margin: 0;
  font-size: 1.2rem;
  color: var(--text-primary);
}

.results-header {
  flex-wrap: wrap;
  gap: 1rem;
}

.prompt-debug-header {
  align-items: flex-start;
}

.prompt-debug-meta {
  margin: 0.35rem 0 0;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.prompt-debug-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.prompt-manifest {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.prompt-manifest label {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.prompt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 1rem;
}

.prompt-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.prompt-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.75rem 1rem 0;
}

.chip {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-family: monospace;
}

.prompt-blocks {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  padding: 1rem;
}

.prompt-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.prompt-block label,
.prompt-section label {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.prompt-block p {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.5;
}

.prompt-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0 1rem 1rem;
}

.prompt-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
}

.prompt-text {
  margin: 0;
  max-height: 220px;
  overflow: auto;
}

.field-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.field-tag {
  background: rgba(41, 128, 185, 0.12);
  color: var(--accent-blue);
  border: 1px solid rgba(41, 128, 185, 0.2);
  border-radius: 999px;
  padding: 0.2rem 0.55rem;
  font-size: 0.75rem;
  font-family: monospace;
}

.snapshot-meta {
  color: var(--text-muted);
  font-size: 0.82rem;
}

.version-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.version-selector label {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.actions {
  display: flex;
  gap: 0.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-size: 0.9rem;
  color: var(--text-secondary);
}

textarea, select, input {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 0.75rem;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.95rem;
}

textarea:focus, select:focus, input:focus {
  outline: none;
  border-color: var(--accent-blue);
}

.global-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-tertiary);
  padding: 1rem;
  border-radius: 6px;
  margin-bottom: 1.5rem;
  border: 1px solid var(--border-color);
  flex-wrap: wrap;
  gap: 1rem;
}

.global-edit-form {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex: 1;
}

.global-edit-form input {
  flex: 1;
  min-width: 200px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1.5rem;
}

.image-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.image-card.processing { border-color: var(--accent-blue); }
.image-card.failed { border-color: var(--danger-red); }
.image-card.completed { border-color: var(--success-green); }

.img-wrapper {
  height: 220px;
  background: var(--bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
  border-bottom: 1px solid var(--border-color);
}

.img-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.status-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-muted);
}

.status-indicator.processing { color: var(--accent-blue); }
.status-indicator.failed { color: var(--danger-red); }

.img-info {
  padding: 1rem;
  display: flex;
  flex-direction: column;
}

.meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.role {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.badge.status.completed { background: rgba(39, 174, 96, 0.2); color: var(--success-green); }
.badge.status.processing { background: rgba(41, 128, 185, 0.2); color: var(--accent-blue); }
.badge.status.pending { background: rgba(243, 156, 18, 0.2); color: var(--warning-yellow); }
.badge.status.failed { background: rgba(231, 76, 60, 0.2); color: var(--danger-red); }

.badge.status.ready { background: rgba(39, 174, 96, 0.2); color: var(--success-green); }

.asset-meta {
  display: flex;
  justify-content: space-between;
  color: var(--text-muted);
  font-size: 0.8rem;
  margin-top: 0.5rem;
}

.results-stats {
  display: flex;
  gap: 2rem;
  padding: 1rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
  margin-bottom: 1.5rem;
  border: 1px solid var(--border-color);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.stat-label {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.stat-value {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 1.1rem;
}

.text-success {
  color: var(--success-green);
}

.empty-results {
  margin-top: 1rem;
}

.empty-state.large {
  padding: 4rem 2rem;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.empty-state h3 {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary);
}

.empty-state p {
  margin: 0.5rem 0;
  color: var(--text-secondary);
}

.empty-state .hint {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-top: 1rem;
}

.generation-info {
  display: flex;
  justify-content: center;
  gap: 2rem;
  margin-top: 2rem;
  padding-top: 2rem;
  border-top: 1px solid var(--border-color);
}

.info-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.info-label {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.info-value {
  font-weight: 600;
  color: var(--accent-blue);
  font-size: 1.2rem;
}

.debug-info {
  color: var(--text-muted);
  font-family: monospace;
}

.mt-1 { margin-top: 0.25rem; }
.mt-2 { margin-top: 0.5rem; }

.full-width {
  width: 100%;
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.btn-sm {
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
}

.btn-primary { background: var(--accent-blue); color: white; }
.btn-primary:hover:not(:disabled) { background: #3a8ee6; }

.btn-secondary { background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-color); }
.btn-secondary:hover:not(:disabled) { background: var(--bg-tertiary); }

.btn-warning { background: var(--warning-yellow); color: #000; }
.btn-warning:hover:not(:disabled) { filter: brightness(1.1); }

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 1s ease-in-out infinite;
}

.status-indicator .spinner {
  border-top-color: var(--accent-blue);
  width: 24px;
  height: 24px;
  border-width: 3px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  text-align: center;
  padding: 3rem;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px dashed var(--border-color);
}

.json-preview {
  background: var(--bg-primary);
  padding: 0.9rem;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
