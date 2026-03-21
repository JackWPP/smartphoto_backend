<template>
  <div class="image-upload">
    <div 
      class="upload-dropzone" 
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="handleDrop"
      :class="{ 'is-dragging': isDragging }"
    >
      <input 
        type="file" 
        ref="fileInput" 
        @change="handleFileChange" 
        style="display: none" 
        accept="image/*" 
      />
      <div class="upload-controls">
        <button class="btn btn-primary" @click="triggerFileInput" :disabled="isUploading">
          Select Image
        </button>
        <span class="drag-text">or drag and drop here</span>
      </div>

      <div class="upload-options" v-if="selectedFile">
        <p class="file-name">{{ selectedFile.name }}</p>
        <div class="form-group">
          <label>Slot Type:</label>
          <select v-model="slotType" class="form-control">
            <option value="front">Front</option>
            <option value="angle45">Angle 45</option>
            <option value="side">Side</option>
            <option value="extra">Extra</option>
          </select>
        </div>
        <div class="form-group">
          <label>Display Order:</label>
          <input type="number" v-model="displayOrder" class="form-control" min="1" />
        </div>
        <button class="btn btn-success" @click="uploadImage" :disabled="isUploading">
          {{ isUploading ? 'Uploading...' : 'Confirm Upload' }}
        </button>
        <button class="btn btn-text" @click="cancelUpload" :disabled="isUploading">Cancel</button>
      </div>
    </div>

    <div class="image-grid" v-if="images && images.length > 0">
      <div v-for="img in sortedImages" :key="img.id" class="image-card">
        <img :src="img.url || img.asset_id" :alt="img.slot_type" />
        <div class="image-info">
          <span class="badge">{{ img.slot_type }} ({{ img.display_order }})</span>
          <button class="btn-icon delete-btn" @click="$emit('delete', img.id)" title="Delete">×</button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>No images uploaded yet.</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  sessionId: {
    type: String,
    required: true
  },
  images: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['upload', 'delete', 'refresh'])

const fileInput = ref(null)
const selectedFile = ref(null)
const isDragging = ref(false)
const isUploading = ref(false)

const slotType = ref('front')
const displayOrder = ref(1)

const sortedImages = computed(() => {
  return [...props.images].sort((a, b) => a.display_order - b.display_order)
})

const triggerFileInput = () => {
  fileInput.value.click()
}

const handleFileChange = (e) => {
  const file = e.target.files[0]
  if (file) {
    selectedFile.value = file
  }
}

const handleDrop = (e) => {
  isDragging.value = false
  const file = e.dataTransfer.files[0]
  if (file && file.type.startsWith('image/')) {
    selectedFile.value = file
  }
}

const cancelUpload = () => {
  selectedFile.value = null
  fileInput.value.value = ''
}

const uploadImage = async () => {
  if (!selectedFile.value) return
  
  isUploading.value = true
  try {
    emit('upload', {
      file: selectedFile.value,
      slot_type: slotType.value,
      display_order: Math.max(1, Number(displayOrder.value) || 1)
    })
    // Reset after emit, actual upload happens in parent
    selectedFile.value = null
    slotType.value = 'front'
    displayOrder.value = 1
  } finally {
    isUploading.value = false
  }
}
</script>

<style scoped>
.image-upload {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.upload-dropzone {
  border: 2px dashed var(--border-color, #444);
  border-radius: 8px;
  padding: 2rem;
  text-align: center;
  background-color: var(--bg-tertiary, #2a2a2a);
  transition: all 0.2s ease;
}

.upload-dropzone.is-dragging {
  border-color: var(--accent-blue, #3b82f6);
  background-color: rgba(59, 130, 246, 0.1);
}

.upload-controls {
  margin-bottom: 1rem;
}

.drag-text {
  margin-left: 1rem;
  color: var(--text-secondary, #a0a0a0);
}

.upload-options {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border-color, #444);
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: center;
}

.file-name {
  font-weight: bold;
  color: var(--text-primary, #fff);
}

.form-group {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.form-control {
  background-color: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #444);
  color: var(--text-primary, #fff);
  padding: 0.5rem;
  border-radius: 4px;
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

.btn-success {
  background-color: var(--success-color, #10b981);
  color: white;
}

.btn-text {
  background: none;
  color: var(--text-secondary, #a0a0a0);
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 1rem;
}

.image-card {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-color, #444);
  background-color: var(--bg-tertiary, #2a2a2a);
}

.image-card img {
  width: 100%;
  height: 150px;
  object-fit: cover;
  display: block;
}

.image-info {
  padding: 0.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: rgba(0, 0, 0, 0.7);
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
}

.badge {
  background-color: var(--accent-blue, #3b82f6);
  color: white;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
}

.btn-icon {
  background: rgba(239, 68, 68, 0.8);
  color: white;
  border: none;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
}

.btn-icon:hover {
  background: rgba(239, 68, 68, 1);
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary, #a0a0a0);
  background-color: var(--bg-tertiary, #2a2a2a);
  border-radius: 8px;
  border: 1px dashed var(--border-color, #444);
}
</style>
