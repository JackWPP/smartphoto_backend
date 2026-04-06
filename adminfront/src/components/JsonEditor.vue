<template>
  <div class="editor-shell">
    <div class="editor-toolbar">
      <span class="editor-title">{{ title }}</span>
      <div class="toolbar-actions">
        <button class="ghost-button" @click="format">格式化</button>
        <button v-if="readonly" class="ghost-button" @click="copyToClipboard">复制</button>
      </div>
    </div>
    <textarea
      :value="modelValue"
      class="code-editor"
      :class="{ 'code-editor--invalid': !isValid }"
      :readonly="readonly"
      :rows="rows"
      spellcheck="false"
      @input="onInput"
    />
    <div v-if="!isValid" class="json-error-hint">JSON 格式有误，请检查语法</div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '{}' },
  title: { type: String, default: 'JSON' },
  rows: { type: Number, default: 12 },
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'valid'])

const isValid = ref(true)

function checkValidity(val) {
  try {
    JSON.parse(val || '{}')
    isValid.value = true
  } catch {
    isValid.value = false
  }
  emit('valid', isValid.value)
}

function onInput(event) {
  const val = event.target.value
  emit('update:modelValue', val)
  checkValidity(val)
}

// Validate on external (non-input) changes, e.g. parent resetting the value
watch(() => props.modelValue, (val, oldVal) => { if (val !== oldVal) checkValidity(val) }, { immediate: true })

function format() {
  try {
    const formatted = JSON.stringify(JSON.parse(props.modelValue || '{}'), null, 2)
    emit('update:modelValue', formatted)
    isValid.value = true
    emit('valid', true)
  } catch {
    // Keep invalid JSON untouched so the operator can fix it manually.
  }
}

async function copyToClipboard() {
  await navigator.clipboard.writeText(props.modelValue || '')
}
</script>

<style scoped>
.code-editor--invalid {
  border-color: var(--danger, #ef4444) !important;
  box-shadow: 0 0 0 1px rgba(239, 68, 68, 0.3);
}
.json-error-hint {
  font-size: 11px;
  color: var(--danger, #ef4444);
  padding: 4px 8px;
}
</style>
