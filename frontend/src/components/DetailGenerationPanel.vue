<template>
  <div class="generation-panel">
    <div class="generate-section card">
      <div class="header">
        <div>
          <h3>Generate Detail Page</h3>
          <p class="subtle">固定生成 8 张 21:9 panel 图和 1 张竖向拼接长图。</p>
        </div>
        <button class="btn btn-primary generate-btn" @click="handleGenerate" :disabled="!sessionId || isGenerating">
          <span v-if="isGenerating" class="spinner"></span>
          {{ isGenerating ? 'Generating...' : 'Generate Detail Page' }}
        </button>
      </div>

      <div class="form-group">
        <label>Instruction (Optional)</label>
        <textarea v-model="instruction" placeholder="Any specific instructions for this detail page generation?" rows="2"></textarea>
      </div>
    </div>

    <div class="prompt-debug card">
      <div class="header prompt-debug-header">
        <div>
          <h3>Detail Prompt Debug</h3>
          <p v-if="promptPreview" class="prompt-debug-meta">
            Use Case: {{ promptPreview.use_case }} | Ratio: {{ promptPreview.aspect_ratio }} | Size: {{ promptPreview.image_size }}
          </p>
        </div>
        <div class="actions">
          <button class="btn btn-secondary btn-sm" @click="refreshPromptPreview" :disabled="!sessionId || promptPreviewLoading">
            {{ promptPreviewLoading ? 'Refreshing...' : 'Refresh Detail Prompt Preview' }}
          </button>
          <button class="btn btn-secondary btn-sm" @click="showPromptDebug = !showPromptDebug">
            {{ showPromptDebug ? 'Collapse' : 'Expand' }}
          </button>
        </div>
      </div>

      <div v-if="showPromptDebug" class="prompt-debug-content">
        <div v-if="promptPreviewError" class="empty-state"><p>{{ promptPreviewError }}</p></div>
        <div v-else-if="promptPreviewLoading && !promptPreview" class="empty-state"><p>Loading detail prompt preview...</p></div>

        <div v-if="promptPreview?.product_reference_manifest?.length" class="prompt-manifest">
          <label>Product Reference Manifest</label>
          <div class="field-tags">
            <span v-for="image in promptPreview.product_reference_manifest" :key="image.image_id" class="field-tag">
              {{ image.slot_type }} · {{ image.image_id.slice(0, 8) }}
            </span>
          </div>
        </div>

        <div v-if="promptPreview?.style_reference_manifest?.length" class="prompt-manifest">
          <label>Style Reference Manifest</label>
          <div class="field-tags">
            <span v-for="image in promptPreview.style_reference_manifest" :key="image.image_id" class="field-tag">
              style · {{ image.image_id.slice(0, 8) }}
            </span>
          </div>
        </div>

        <div v-if="promptCards.length" class="prompt-grid">
          <div v-for="prompt in promptCards" :key="`${prompt.slot_id || prompt.panel_id}-${prompt.display_order}`" class="prompt-card">
            <div class="plan-header">
              <span class="badge">{{ prompt.panel_label || prompt.panel_id }}</span>
              <span class="order">Order: {{ prompt.display_order }}</span>
            </div>

            <div class="prompt-chips">
              <span class="chip">{{ prompt.aspect_ratio }}</span>
              <span class="chip">{{ prompt.use_case }}</span>
              <span class="chip">{{ prompt.planner_source || 'rule_based' }}</span>
              <span class="chip" v-if="prompt.slot_id">{{ prompt.slot_id }}</span>
              <span class="chip" v-if="prompt.panel_type">{{ prompt.panel_type }}</span>
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
                <button class="btn btn-secondary btn-sm" @click="copyPrompt(prompt.final_prompt)">Copy Prompt</button>
              </div>
              <pre class="json-preview prompt-text">{{ prompt.final_prompt }}</pre>
            </div>

            <div class="prompt-section" v-if="prompt.strategy_fields_used?.length">
              <label>Strategy Fields Used</label>
              <div class="field-tags">
                <span v-for="field in prompt.strategy_fields_used" :key="field" class="field-tag">{{ field }}</span>
              </div>
            </div>

            <div class="prompt-section" v-if="prompt.product_reference_images_used?.length">
              <label>Product References Used</label>
              <div class="field-tags">
                <span v-for="image in prompt.product_reference_images_used" :key="image.image_id" class="field-tag">
                  {{ image.slot_type }} · {{ image.image_id.slice(0, 8) }}
                </span>
              </div>
            </div>

            <div class="prompt-section" v-if="prompt.style_reference_images_used?.length">
              <label>Style References Used</label>
              <div class="field-tags">
                <span v-for="image in prompt.style_reference_images_used" :key="image.image_id" class="field-tag">
                  style · {{ image.image_id.slice(0, 8) }}
                </span>
              </div>
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
                Version {{ latestAssetFor(prompt).version_no }} · {{ latestAssetFor(prompt).slot_id || latestAssetFor(prompt).panel_id }} · order {{ latestAssetFor(prompt).display_order }}
              </div>
              <pre class="json-preview prompt-text">{{ latestAssetFor(prompt).prompt_snapshot }}</pre>
              <div v-if="latestAssetFor(prompt).generation_snapshot" class="snapshot-meta">
                Upstream: {{ latestAssetFor(prompt).generation_snapshot.upstream_endpoint || '-' }}
              </div>
              <div v-if="latestAssetFor(prompt).generation_snapshot?.timing?.render_total_ms" class="snapshot-meta">
                Render: {{ latestAssetFor(prompt).generation_snapshot.timing.render_total_ms }}ms
              </div>
              <div v-if="latestAssetFor(prompt).panel_type" class="snapshot-meta">
                Panel Type: {{ latestAssetFor(prompt).panel_type }}
              </div>
              <pre v-if="latestAssetFor(prompt).generation_snapshot" class="json-preview prompt-text">{{ JSON.stringify(latestAssetFor(prompt).generation_snapshot, null, 2) }}</pre>
            </div>
          </div>
        </div>
        <div v-else class="empty-state"><p>No detail prompt preview available yet.</p></div>
      </div>
    </div>

    <div class="results-section card" v-if="results">
      <div class="header results-header">
        <h3>🧾 Detail Page Results ({{ displayAssets.length }} assets)</h3>
        <div class="version-selector">
          <label>Version:</label>
          <select v-model="selectedVersion">
            <option v-for="version in availableVersions" :key="version" :value="version">
              Version {{ version }} {{ version === latestVersion ? '(Latest)' : '' }}
            </option>
          </select>
        </div>
        <div class="actions">
          <button class="btn btn-secondary" @click="$emit('refresh')" :disabled="isGenerating">🔄 Refresh</button>
          <button class="btn btn-primary" @click="$emit('download', selectedVersion)" :disabled="!displayAssets.length || isGenerating">⬇️ Download ZIP</button>
        </div>
      </div>

      <div class="results-stats" v-if="results.summary">
        <div class="stat-item"><span class="stat-label">Total:</span><span class="stat-value">{{ results.summary.total_count }}</span></div>
        <div class="stat-item"><span class="stat-label">Ready:</span><span class="stat-value text-success">{{ results.summary.ready_count }}</span></div>
        <div class="stat-item"><span class="stat-label">Panels:</span><span class="stat-value">{{ results.summary.panel_count }}</span></div>
        <div class="stat-item"><span class="stat-label">Round:</span><span class="stat-value">{{ results.detail_generation_round }}</span></div>
      </div>

      <div v-if="selectedStitchedAsset" class="stitched-highlight">
        <div class="stitched-copy">
          <h4>Stitched Long Image</h4>
          <p>这是 8 张 panel 自动竖向拼接后的长图。</p>
        </div>
        <img :src="selectedStitchedAsset.image_url" alt="stitched detail page" class="stitched-preview" />
      </div>

      <div class="image-grid" v-if="displayAssets.length">
        <div v-for="asset in displayAssets" :key="asset.asset_id" class="image-card" :class="asset.status || 'ready'">
          <div class="img-wrapper">
            <img v-if="asset.image_url" :src="asset.image_url" :alt="asset.panel_id || asset.asset_kind || 'generated'" />
            <div v-else class="status-indicator">No Image</div>
          </div>
            <div class="img-info">
              <div class="meta">
              <span class="badge role">{{ asset.panel_label || asset.panel_id || asset.asset_kind }}</span>
              <span class="badge status" :class="asset.status || 'ready'">{{ asset.status || 'ready' }}</span>
            </div>
            <div class="asset-meta">
              <small>Order: {{ asset.display_order }}</small>
              <small v-if="asset.width && asset.height">{{ asset.width }}x{{ asset.height }}</small>
              <small v-if="asset.slot_id">Slot: {{ asset.slot_id }}</small>
              <small v-if="asset.panel_type">Type: {{ asset.panel_type }}</small>
              <small v-if="asset.render_total_ms != null">Render: {{ asset.render_total_ms }}ms</small>
            </div>
            <div class="actions mt-2">
              <button class="btn btn-secondary btn-sm full-width" @click="$emit('editPanel', asset.slot_id || asset.panel_id)" :disabled="isGenerating">
                Edit Text
              </button>
              <button class="btn btn-secondary btn-sm full-width" @click="$emit('regenerateAsset', asset.asset_id)" :disabled="isGenerating">
                Regenerate Single
              </button>
            </div>
            <div class="debug-info mt-1">
              <small>ID: {{ (asset.asset_id || 'unknown').substring(0, 8) }}...</small>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="!isGenerating" class="results-section card empty-results">
      <div class="empty-state large">
        <div class="empty-icon">🧾</div>
        <h3>No Detail Page Generated Yet</h3>
        <p>Click “Generate Detail Page” above to produce 8 panels and 1 stitched long image.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api/index.js'

const props = defineProps({
  sessionId: String,
  results: {
    type: Object,
    default: null,
  },
  latestVersion: {
    type: Number,
    default: 0,
  },
  isGenerating: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['generate', 'download', 'refresh', 'refreshVersion', 'editPanel', 'regenerateAsset'])

const instruction = ref('')
const selectedVersion = ref(props.latestVersion || 1)
const showPromptDebug = ref(true)
const promptPreview = ref(null)
const promptPreviewLoading = ref(false)
const promptPreviewError = ref('')

const promptBlockOrder = ['goal', 'subject', 'layout', 'text', 'style', 'constraints', 'instruction']
const promptBlockLabels = {
  goal: 'Goal',
  subject: 'Subject',
  layout: 'Layout',
  text: 'On-image Copy',
  style: 'Style',
  constraints: 'Constraints',
  instruction: 'Instruction',
}

watch(
  () => props.latestVersion,
  (newVal) => {
    if (newVal && newVal > selectedVersion.value) {
      selectedVersion.value = newVal
    }
  },
  { immediate: true }
)

watch(
  () => props.results,
  (value) => {
    const maxVersion = value?.detail_latest_result_version || props.latestVersion || 1
    if (maxVersion && maxVersion !== selectedVersion.value) {
      selectedVersion.value = maxVersion
    }
  },
  { immediate: true, deep: true }
)

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

const displayAssets = computed(() => {
  const panels = props.results?.panels || []
  return [...panels]
    .filter((asset) => asset.version_no === (props.results?.requested_version ?? selectedVersion.value))
    .sort((a, b) => a.display_order - b.display_order)
})
const availableVersions = computed(() => {
  if (props.results?.available_versions?.length) {
    return props.results.available_versions
  }
  const versions = new Set((props.results?.panels || []).map((asset) => asset.version_no).filter((item) => item != null))
  if (props.results?.stitched_asset?.version_no != null) {
    versions.add(props.results.stitched_asset.version_no)
  }
  if (versions.size === 0) {
    return [props.latestVersion || 1]
  }
  return Array.from(versions).sort((a, b) => b - a)
})
const selectedStitchedAsset = computed(() => {
  const stitched = props.results?.stitched_asset
  if (!stitched) {
    return null
  }
  return stitched.version_no === (props.results?.requested_version ?? selectedVersion.value) ? stitched : null
})

watch(
  () => selectedVersion.value,
  (value) => {
    if (!props.sessionId) return
    if ((props.results?.requested_version || props.latestVersion || 1) === value) return
    emit('refreshVersion', value)
  }
)
const promptCards = computed(() => promptPreview.value?.prompts || [])
const latestAssetMap = computed(() => {
  const map = {}
  for (const asset of promptPreview.value?.latest_assets || []) {
    if (asset.asset_kind === 'panel') {
      map[`${asset.slot_id || asset.panel_id}:${asset.display_order}`] = asset
    }
  }
  return map
})

function handleGenerate() {
  emit('generate', { instruction: instruction.value || null })
  instruction.value = ''
}

async function refreshPromptPreview() {
  if (!props.sessionId) return
  promptPreviewLoading.value = true
  promptPreviewError.value = ''
  try {
    promptPreview.value = await api.previewDetailPrompts(props.sessionId, instruction.value || null, true)
  } catch (error) {
    promptPreview.value = null
    if ([40002, 40003].includes(error.code)) {
      promptPreviewError.value = '详情页 Prompt Preview 需要先完成 copy 和 active platform 配置。'
      return
    }
    promptPreviewError.value = error.message || 'Failed to load detail prompt preview.'
  } finally {
    promptPreviewLoading.value = false
  }
}

function latestAssetFor(prompt) {
  return latestAssetMap.value[`${prompt.slot_id || prompt.panel_id}:${prompt.display_order}`] || null
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

.header,
.results-header,
.prompt-debug-header,
.prompt-section-header,
.results-stats,
.stitched-highlight {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.header {
  align-items: flex-start;
  margin-bottom: 1rem;
}

.header h3,
.stitched-copy h4 {
  margin: 0;
}

.subtle,
.prompt-debug-meta,
.snapshot-meta,
.stat-label,
.asset-meta small,
.debug-info small {
  color: var(--text-muted);
}

.prompt-debug-content,
.prompt-blocks,
.prompt-section,
.prompt-block,
.results-section,
.stitched-copy,
.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.prompt-grid,
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1rem;
}

.prompt-card,
.image-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.plan-header,
.prompt-chips,
.prompt-blocks,
.prompt-section,
.img-info,
.field-tags,
.actions,
.meta {
  padding: 0 1rem;
}

.plan-header,
.meta,
.field-tags,
.prompt-chips,
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.plan-header,
.img-info {
  padding-top: 1rem;
}

.prompt-section,
.prompt-blocks,
.img-info {
  padding-bottom: 1rem;
}

.badge,
.chip,
.field-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
}

.badge,
.btn-primary {
  background: var(--accent-blue, #3b82f6);
  color: #fff;
}

.chip,
.field-tag,
.btn-secondary {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.prompt-block label,
.prompt-section label,
.prompt-manifest label,
.form-group label {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.prompt-block p,
.stitched-copy p {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.5;
}

.prompt-text,
.json-preview {
  margin: 0;
  background: #0f1218;
  color: #d8e0f0;
  border-radius: 8px;
  padding: 0.9rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.img-wrapper img,
.stitched-preview {
  width: 100%;
  display: block;
}

.img-wrapper img {
  aspect-ratio: 21 / 9;
  object-fit: cover;
}

.stitched-highlight {
  align-items: flex-start;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1rem;
}

.stitched-copy {
  flex: 1;
}

.stitched-preview {
  max-width: 280px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.btn {
  border-radius: 6px;
  border: none;
  padding: 0.6rem 0.9rem;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

textarea,
select {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  padding: 0.75rem;
}

@media (max-width: 900px) {
  .results-header,
  .stitched-highlight,
  .header {
    flex-direction: column;
  }

  .stitched-preview {
    max-width: none;
  }
}
</style>
