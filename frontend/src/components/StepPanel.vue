<template>
  <div class="step-panel" :class="{ 'is-active': currentStep === step, 'is-completed': step < currentStep }">
    <div class="panel-header" @click="$emit('toggle')">
      <div class="step-badge">
        <span v-if="step < currentStep">✓</span>
        <span v-else>{{ step }}</span>
      </div>
      <h3 class="step-title">{{ title }}</h3>
      <div class="spacer"></div>
      <div class="toggle-icon">{{ open ? '▼' : '▶' }}</div>
    </div>
    
    <div class="panel-content" v-show="open">
      <slot></slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    required: true
  },
  step: {
    type: Number,
    required: true
  },
  currentStep: {
    type: Number,
    required: true
  },
  open: {
    type: Boolean,
    default: false
  }
})

defineEmits(['toggle'])
</script>

<style scoped>
.step-panel {
  background-color: var(--bg-secondary, #1e1e1e);
  border-radius: 8px;
  margin-bottom: 1rem;
  overflow: hidden;
  border: 1px solid var(--border-color, #333);
  transition: all 0.3s ease;
}

.step-panel.is-active {
  border-color: var(--accent-blue, #3b82f6);
  box-shadow: 0 0 0 1px var(--accent-blue, #3b82f6);
}

.step-panel.is-completed .step-badge {
  background-color: var(--success-color, #10b981);
  color: #fff;
}

.panel-header {
  display: flex;
  align-items: center;
  padding: 1rem;
  cursor: pointer;
  background-color: var(--bg-tertiary, #2a2a2a);
  user-select: none;
}

.panel-header:hover {
  background-color: var(--hover-color, #3a3a3a);
}

.step-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background-color: var(--bg-primary, #121212);
  color: var(--text-secondary, #a0a0a0);
  font-weight: bold;
  margin-right: 1rem;
  border: 1px solid var(--border-color, #333);
}

.is-active .step-badge {
  background-color: var(--accent-blue, #3b82f6);
  color: #fff;
  border-color: var(--accent-blue, #3b82f6);
}

.step-title {
  margin: 0;
  font-size: 1.1rem;
  color: var(--text-primary, #ffffff);
}

.spacer {
  flex-grow: 1;
}

.toggle-icon {
  color: var(--text-secondary, #a0a0a0);
  font-size: 0.8rem;
}

.panel-content {
  padding: 1.5rem;
  border-top: 1px solid var(--border-color, #333);
  background-color: var(--bg-secondary, #1e1e1e);
}
</style>