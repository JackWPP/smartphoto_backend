<template>
  <div class="app-shell">
    <div v-if="!authenticated" class="login-card">
      <h1>SmartPhoto Admin</h1>
      <input v-model="loginForm.username" placeholder="用户名" />
      <input v-model="loginForm.password" placeholder="密码" type="password" />
      <button @click="login">登录</button>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </div>
    <div v-else class="layout">
      <aside class="sidebar">
        <h2>Admin</h2>
        <button v-for="item in tabs" :key="item" :class="{ active: activeTab === item }" @click="activeTab = item">
          {{ item }}
        </button>
        <button class="logout" @click="logout">退出</button>
      </aside>
      <main class="content">
        <section v-if="activeTab === 'Dashboard'">
          <h3>Dashboard</h3>
          <pre>{{ dashboardData }}</pre>
        </section>
        <section v-if="activeTab === 'Sessions'" class="grid">
          <div>
            <h3>Sessions</h3>
            <button @click="loadSessions">刷新</button>
            <ul class="list">
              <li v-for="item in sessions" :key="item.session_id" @click="openSession(item.session_id)">
                {{ item.session_id }} · {{ item.status }} · {{ item.active_platform_id || '-' }}
              </li>
            </ul>
          </div>
          <div v-if="selectedSession">
            <h3>Session Detail</h3>
            <button @click="saveCopy">保存 Step4</button>
            <textarea v-model="selectedCopyText" rows="24"></textarea>
          </div>
        </section>
        <section v-if="activeTab === 'Jobs'">
          <h3>Jobs</h3>
          <button @click="loadJobs">刷新</button>
          <pre>{{ jobs }}</pre>
        </section>
        <section v-if="activeTab === 'Assets'">
          <h3>Assets</h3>
          <button @click="loadAssets">刷新</button>
          <pre>{{ assets }}</pre>
        </section>
        <section v-if="activeTab === 'Prompt Presets'">
          <h3>Prompt Presets</h3>
          <button @click="loadPromptPresets">刷新</button>
          <pre>{{ promptPresets }}</pre>
        </section>
        <section v-if="activeTab === 'Rule Packs'">
          <h3>Rule Packs</h3>
          <button @click="loadRulePacks">刷新</button>
          <pre>{{ rulePacks }}</pre>
        </section>
        <section v-if="activeTab === 'Audit Logs'">
          <h3>Audit Logs</h3>
          <button @click="loadAuditLogs">刷新</button>
          <pre>{{ auditLogs }}</pre>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from './api'

const tabs = ['Dashboard', 'Sessions', 'Jobs', 'Assets', 'Prompt Presets', 'Rule Packs', 'Audit Logs']
const activeTab = ref('Dashboard')
const authenticated = ref(false)
const errorMessage = ref('')
const loginForm = ref({ username: '', password: '' })
const dashboardData = ref({})
const sessions = ref([])
const selectedSession = ref(null)
const selectedCopyText = ref('{}')
const jobs = ref([])
const assets = ref([])
const promptPresets = ref([])
const rulePacks = ref([])
const auditLogs = ref([])

async function login() {
  try {
    const data = await adminApi.login(loginForm.value)
    adminApi.setAccessToken(data.access_token)
    authenticated.value = true
    errorMessage.value = ''
    await bootstrap()
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function logout() {
  await adminApi.logout()
  adminApi.setAccessToken('')
  authenticated.value = false
}

async function bootstrap() {
  await Promise.all([loadDashboard(), loadSessions(), loadJobs(), loadAssets(), loadPromptPresets(), loadRulePacks(), loadAuditLogs()])
}

async function loadDashboard() {
  dashboardData.value = await adminApi.dashboard()
}

async function loadSessions() {
  const data = await adminApi.listSessions()
  sessions.value = data.items || []
}

async function openSession(sessionId) {
  const data = await adminApi.getSession(sessionId)
  selectedSession.value = data.session
  selectedCopyText.value = JSON.stringify(data.session.confirmed_copy || {}, null, 2)
}

async function saveCopy() {
  if (!selectedSession.value) return
  await adminApi.updateCopy(selectedSession.value.session_id, JSON.parse(selectedCopyText.value))
  await openSession(selectedSession.value.session_id)
}

async function loadJobs() {
  jobs.value = (await adminApi.listJobs()).items || []
}

async function loadAssets() {
  assets.value = (await adminApi.listAssets()).items || []
}

async function loadPromptPresets() {
  promptPresets.value = (await adminApi.listPromptPresets()).presets || []
}

async function loadRulePacks() {
  rulePacks.value = (await adminApi.listRulePacks()).items || []
}

async function loadAuditLogs() {
  auditLogs.value = (await adminApi.listAuditLogs()).items || []
}

onMounted(async () => {
  try {
    const data = await adminApi.me()
    if (data?.admin_user_id) {
      authenticated.value = true
      await bootstrap()
    }
  } catch {
    authenticated.value = false
  }
})
</script>
