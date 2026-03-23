<template>
  <div v-if="!auth.ready" class="boot-screen">
    <div class="boot-card">
      <span class="eyebrow">SmartPhoto</span>
      <h1>Admin Command Console</h1>
      <p>正在恢复管理员会话与控制台上下文。</p>
    </div>
  </div>
  <RouterView v-else />
</template>

<script setup>
import { onMounted, watchEffect } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

onMounted(() => {
  auth.bootstrap()
})

watchEffect(() => {
  if (!auth.ready) {
    return
  }
  if (!auth.authenticated && route.name !== 'login') {
    router.replace({ name: 'login' })
    return
  }
  if (auth.authenticated && route.name === 'login') {
    router.replace({ name: 'overview' })
  }
})
</script>
