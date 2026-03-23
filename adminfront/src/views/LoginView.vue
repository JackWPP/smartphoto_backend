<template>
  <div class="login-screen">
    <div class="login-panel">
      <div class="login-panel__header">
        <span class="eyebrow">Internal Control Plane</span>
        <h1>SmartPhoto 超级控制台</h1>
        <p>统一管理用户额度、Prompt、规则包、任务与资产治理。</p>
      </div>
      <form class="form-grid" @submit.prevent="submit">
        <label class="field">
          <span>管理员账号</span>
          <input v-model="form.username" autocomplete="username" placeholder="admin" />
        </label>
        <label class="field">
          <span>密码</span>
          <input v-model="form.password" autocomplete="current-password" type="password" placeholder="请输入密码" />
        </label>
        <button class="primary-button" :disabled="auth.loading">{{ auth.loading ? '登录中...' : '进入控制台' }}</button>
        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      </form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({ username: '', password: '' })
const errorMessage = ref('')

async function submit() {
  errorMessage.value = ''
  try {
    await auth.login(form)
    router.replace({ name: 'overview' })
  } catch (error) {
    errorMessage.value = error.message || '登录失败'
  }
}
</script>
