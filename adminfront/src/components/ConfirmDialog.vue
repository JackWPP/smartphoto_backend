<template>
  <Teleport to="body">
    <div v-if="open" class="dialog-backdrop">
      <div class="dialog-card">
        <div class="dialog-header">
          <div>
            <span class="eyebrow">{{ eyebrow }}</span>
            <h3>{{ title }}</h3>
          </div>
          <button class="icon-button" @click="$emit('cancel')">×</button>
        </div>
        <p class="dialog-copy">{{ message }}</p>
        <slot />
        <div class="dialog-actions">
          <button class="ghost-button" @click="$emit('cancel')">取消</button>
          <button :class="danger ? 'danger-button' : 'primary-button'" @click="$emit('confirm')">
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  eyebrow: { type: String, default: '高风险操作' },
  title: { type: String, default: '确认执行' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确认' },
  danger: { type: Boolean, default: false },
})

defineEmits(['cancel', 'confirm'])
</script>
