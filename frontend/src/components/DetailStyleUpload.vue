<template>
  <div class="detail-style-upload">
    <div class="upload-panel card-lite">
      <div class="upload-header">
        <div>
          <h3>Style / Font References</h3>
          <p>可选上传 1-4 张风格、排版或字体参考图，不会混入商品图槽位。</p>
        </div>
      </div>

      <div class="upload-controls">
        <input ref="fileInput" type="file" accept="image/*" hidden @change="handleFileChange" />
        <button class="btn btn-primary" @click="triggerFileInput" :disabled="isUploading">Select Style Image</button>
        <input v-model.number="displayOrder" class="form-control order-input" type="number" min="1" />
        <button class="btn btn-secondary" @click="uploadImage" :disabled="!selectedFile || isUploading">
          {{ isUploading ? 'Uploading...' : 'Upload' }}
        </button>
      </div>

      <div v-if="selectedFile" class="selected-file">
        <span>{{ selectedFile.name }}</span>
        <button class="btn btn-ghost btn-sm" @click="clearSelection">Clear</button>
      </div>
    </div>

    <div v-if="images?.length" class="reference-grid">
      <div v-for="image in sortedImages" :key="image.image_id || image.id" class="reference-card">
        <img :src="image.url" :alt="`style-${image.display_order}`" class="reference-thumb" />
        <div class="reference-meta">
          <div class="badge-row">
            <span class="badge">Style Ref</span>
            <span class="order">#{{ image.display_order }}</span>
          </div>
          <div class="meta-line" v-if="image.width && image.height">{{ image.width }}x{{ image.height }}</div>
          <div class="meta-line mono">{{ shortId(image.image_id || image.id) }}</div>
        </div>
        <button class="btn-icon delete-btn" @click="$emit('delete', image.image_id || image.id)" title="Delete">×</button>
      </div>
    </div>
    <div v-else class="empty-state compact">
      <p>未上传风格图时，详情页会回退使用 Step 4 的风格字段。</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  images: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['upload', 'delete'])

const fileInput = ref(null)
const selectedFile = ref(null)
const displayOrder = ref(1)
const isUploading = ref(false)

const sortedImages = computed(() => [...props.images].sort((a, b) => a.display_order - b.display_order))

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileChange(event) {
  const [file] = event.target.files || []
  if (file) {
    selectedFile.value = file
  }
}

function clearSelection() {
  selectedFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function uploadImage() {
  if (!selectedFile.value) return

  isUploading.value = true
  try {
    emit('upload', {
      file: selectedFile.value,
      display_order: Math.max(1, Number(displayOrder.value) || 1),
    })
    clearSelection()
  } finally {
    isUploading.value = false
  }
}

function shortId(value) {
  if (!value) return '-'
  return `${value.slice(0, 8)}...`
}
</script>

<style scoped>
.detail-style-upload {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.card-lite {
  background: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  padding: 1rem;
}

.upload-header h3 {
  margin: 0 0 0.35rem;
  color: var(--text-primary, #fff);
}

.upload-header p {
  margin: 0;
  color: var(--text-secondary, #a0a0a0);
}

.upload-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  margin-top: 1rem;
}

.order-input {
  width: 96px;
}

.selected-file {
  margin-top: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--text-primary, #fff);
}

.reference-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 1rem;
}

.reference-card {
  position: relative;
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-primary, #121212);
}

.reference-thumb {
  width: 100%;
  height: 160px;
  object-fit: cover;
  display: block;
}

.reference-meta {
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.badge-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.badge {
  background: var(--accent-blue, #3b82f6);
  color: #fff;
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
}

.order,
.meta-line {
  color: var(--text-secondary, #a0a0a0);
  font-size: 0.78rem;
}

.mono {
  font-family: monospace;
}

.delete-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  border: none;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
  cursor: pointer;
}

.compact {
  min-height: auto;
  padding: 1rem;
}

.btn,
.form-control {
  border-radius: 6px;
}

.btn-primary {
  background: var(--accent-blue, #3b82f6);
  color: #fff;
  border: none;
}

.btn-secondary,
.btn-ghost {
  background: transparent;
  color: var(--text-secondary, #a0a0a0);
  border: 1px solid var(--border-color, #444);
}

.btn-sm {
  padding: 0.35rem 0.6rem;
}

.form-control {
  background: var(--bg-secondary, #1e1e1e);
  border: 1px solid var(--border-color, #444);
  color: var(--text-primary, #fff);
  padding: 0.55rem 0.7rem;
}
</style>
