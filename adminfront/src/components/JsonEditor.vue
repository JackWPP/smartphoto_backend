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
      :readonly="readonly"
      :rows="rows"
      spellcheck="false"
      @input="$emit('update:modelValue', $event.target.value)"
    />
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: String, default: '{}' },
  title: { type: String, default: 'JSON' },
  rows: { type: Number, default: 12 },
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

function format() {
  try {
    const formatted = JSON.stringify(JSON.parse(props.modelValue || '{}'), null, 2)
    emit('update:modelValue', formatted)
  } catch {
    // Keep invalid JSON untouched so the operator can fix it manually.
  }
}

async function copyToClipboard() {
  await navigator.clipboard.writeText(props.modelValue || '')
}
</script>
