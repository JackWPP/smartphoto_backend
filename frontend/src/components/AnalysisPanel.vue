<template>
  <div class="analysis-panel">
    <div class="actions">
      <button class="btn btn-primary" @click="handleTrigger" :disabled="isAnalyzing">
        <span v-if="isAnalyzing">Analyzing...</span>
        <span v-else>Start Analysis</span>
      </button>
      <div v-if="isAnalyzing" class="spinner"></div>
    </div>

    <div v-if="hasAnalysisData" class="analysis-results">
      <div class="results-header">
        <h4>Analysis Snapshot</h4>
      </div>
      <div class="results-content">
        <pre class="json-display">{{ formattedAnalysis }}</pre>
      </div>
    </div>
    
    <div v-else class="empty-state">
      <p>Click "Start Analysis" to analyze the uploaded images.</p>
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
  analysis: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['trigger'])

const isAnalyzing = ref(false)

const hasAnalysisData = computed(() => {
  if (!props.analysis) return false
  if (typeof props.analysis !== 'object') return false
  return Object.keys(props.analysis).length > 0
})

const formattedAnalysis = computed(() => {
  if (!props.analysis) return ''
  return JSON.stringify(props.analysis, null, 2)
})

const handleTrigger = async () => {
  isAnalyzing.value = true
  try {
    emit('trigger')
    // Resetting loading state should ideally be done when parent signals completion,
    // but without explicit parent feedback prop, we simulate or assume it resets shortly
    // For a real component, parent would pass an `isLoading` prop or we just let it emit.
    setTimeout(() => {
      isAnalyzing.value = false
    }, 1500) // simulated loading feedback
  } catch (e) {
    isAnalyzing.value = false
  }
}
</script>

<style scoped>
.analysis-panel {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.actions {
  display: flex;
  align-items: center;
  gap: 1rem;
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

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-color, #444);
  border-top-color: var(--accent-blue, #3b82f6);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.analysis-results {
  background-color: var(--bg-primary, #121212);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  overflow: hidden;
}

.results-header {
  background-color: var(--bg-tertiary, #2a2a2a);
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--border-color, #333);
}

.results-header h4 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 0.95rem;
}

.results-content {
  padding: 1rem;
  max-height: 400px;
  overflow-y: auto;
}

.json-display {
  margin: 0;
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--text-secondary, #a0a0a0);
  white-space: pre-wrap;
  word-break: break-all;
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