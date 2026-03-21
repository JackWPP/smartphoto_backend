<template>
  <div class="platform-selector">
    <div v-if="platforms && platforms.length > 0" class="platform-list">
      <div 
        v-for="platform in platforms" 
        :key="platform.id" 
        class="platform-card"
        :class="{ 'is-active': localActive === platform.id, 'is-selected': localSelected.includes(platform.id) }"
      >
        <div class="card-header">
          <label class="checkbox-container">
            <input 
              type="checkbox" 
              :value="platform.id" 
              v-model="localSelected" 
              @change="handleSelectionChange"
            />
            <span class="checkmark"></span>
            <span class="platform-name">{{ platform.name }}</span>
          </label>
        </div>
        
        <div class="card-body">
          <div class="platform-meta">
            <span class="meta-label">ID:</span>
            <span class="meta-value">{{ platform.id }}</span>
          </div>
          <div class="platform-meta">
            <span class="meta-label">Default Image Count:</span>
            <span class="meta-value badge">{{ platform.default_image_count }}</span>
          </div>
          
          <div class="active-toggle" v-if="localSelected.includes(platform.id)">
            <label class="radio-container">
              <input 
                type="radio" 
                name="activePlatform" 
                :value="platform.id" 
                v-model="localActive"
              />
              <span class="radio-mark"></span>
              <span class="radio-label">Set as Active</span>
            </label>
          </div>
        </div>
      </div>
    </div>
    
    <div v-else class="empty-state">
      <p>No platforms available.</p>
    </div>

    <div class="actions">
      <button 
        class="btn btn-primary" 
        @click="saveSelection" 
        :disabled="localSelected.length === 0"
      >
        Save Platforms
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  sessionId: {
    type: String,
    required: true
  },
  platforms: {
    type: Array,
    default: () => []
  },
  selected: {
    type: Array,
    default: () => []
  },
  active: {
    type: String,
    default: null
  }
})

const emit = defineEmits(['save'])

const localSelected = ref([...props.selected])
const localActive = ref(props.active)

// Keep local state in sync with props
watch(() => props.selected, (newVal) => {
  localSelected.value = [...newVal]
}, { deep: true })

watch(() => props.active, (newVal) => {
  localActive.value = newVal
})

const handleSelectionChange = () => {
  // If active platform is deselected, reset it
  if (localActive.value && !localSelected.value.includes(localActive.value)) {
    localActive.value = localSelected.value.length > 0 ? localSelected.value[0] : null
  }
  // If no active platform but we have selected ones, pick first
  if (!localActive.value && localSelected.value.length > 0) {
    localActive.value = localSelected.value[0]
  }
}

const saveSelection = () => {
  emit('save', {
    selected_platform_ids: localSelected.value,
    active_platform_id: localActive.value
  })
}
</script>

<style scoped>
.platform-selector {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.platform-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.platform-card {
  background-color: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s ease;
}

.platform-card.is-selected {
  border-color: rgba(59, 130, 246, 0.5);
  background-color: rgba(59, 130, 246, 0.05);
}

.platform-card.is-active {
  border-color: var(--accent-blue, #3b82f6);
  box-shadow: 0 0 0 1px var(--accent-blue, #3b82f6);
}

.card-header {
  padding: 1rem;
  background-color: var(--bg-tertiary, #2a2a2a);
  border-bottom: 1px solid var(--border-color, #333);
}

.card-body {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.platform-name {
  font-weight: 600;
  color: var(--text-primary, #fff);
  font-size: 1.1rem;
}

.platform-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
}

.meta-label {
  color: var(--text-secondary, #a0a0a0);
}

.meta-value {
  color: var(--text-primary, #fff);
  font-family: monospace;
}

.badge {
  background-color: var(--accent-blue, #3b82f6);
  color: white;
  padding: 0.1rem 0.5rem;
  border-radius: 12px;
  font-size: 0.8rem;
  font-family: inherit;
}

.active-toggle {
  margin-top: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px dashed var(--border-color, #444);
}

/* Custom Checkbox */
.checkbox-container, .radio-container {
  display: flex;
  align-items: center;
  position: relative;
  cursor: pointer;
  user-select: none;
}

.checkbox-container input, .radio-container input {
  position: absolute;
  opacity: 0;
  cursor: pointer;
  height: 0;
  width: 0;
}

.checkmark, .radio-mark {
  height: 20px;
  width: 20px;
  background-color: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #555);
  margin-right: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.checkmark {
  border-radius: 4px;
}

.radio-mark {
  border-radius: 50%;
}

.checkbox-container:hover input ~ .checkmark,
.radio-container:hover input ~ .radio-mark {
  border-color: var(--accent-blue, #3b82f6);
}

.checkbox-container input:checked ~ .checkmark,
.radio-container input:checked ~ .radio-mark {
  background-color: var(--accent-blue, #3b82f6);
  border-color: var(--accent-blue, #3b82f6);
}

.checkmark:after, .radio-mark:after {
  content: "";
  display: none;
}

.checkbox-container input:checked ~ .checkmark:after,
.radio-container input:checked ~ .radio-mark:after {
  display: block;
}

.checkbox-container .checkmark:after {
  width: 5px;
  height: 10px;
  border: solid white;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
  margin-bottom: 2px;
}

.radio-container .radio-mark:after {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: white;
}

.radio-label {
  font-size: 0.9rem;
  color: var(--text-primary, #fff);
}

.actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color, #333);
}

.btn {
  padding: 0.5rem 1.5rem;
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

.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary, #a0a0a0);
  background-color: var(--bg-tertiary, #2a2a2a);
  border-radius: 8px;
  border: 1px dashed var(--border-color, #444);
}
</style>