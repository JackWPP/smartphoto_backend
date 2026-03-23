<template>
  <div class="console-shell">
    <aside class="console-sidebar">
      <div class="brand-block">
        <span class="eyebrow">SmartPhoto</span>
        <h1>Admin Console</h1>
        <p>运营、配置、排障三位一体控制台</p>
      </div>
      <nav class="nav-grid">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-link">
          <span class="nav-kicker">{{ item.kicker }}</span>
          <strong>{{ item.label }}</strong>
          <small>{{ item.description }}</small>
        </RouterLink>
      </nav>
      <div class="sidebar-footer">
        <div>
          <strong>{{ auth.user?.display_name || auth.user?.username }}</strong>
          <small>{{ auth.user?.username }}</small>
        </div>
        <button class="ghost-button" @click="logout">退出</button>
      </div>
    </aside>
    <div class="console-main">
      <header class="console-topbar">
        <div>
          <span class="eyebrow">Super Console</span>
          <h2>{{ route.meta.title || 'Admin' }}</h2>
        </div>
        <div class="topbar-badges">
          <span class="status-chip">单一超管</span>
          <span class="status-chip status-chip--warning">直接改生产</span>
        </div>
      </header>
      <main class="console-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const navItems = [
  { to: '/overview', label: 'Overview', kicker: '01', description: '经营概览、趋势与待处理事项' },
  { to: '/users', label: 'Users', kicker: '02', description: '用户、额度、订单与通知' },
  { to: '/sessions', label: 'Sessions', kicker: '03', description: 'Session 干预与结果追踪' },
  { to: '/jobs', label: 'Jobs', kicker: '04', description: '任务、事件时间线与重试' },
  { to: '/assets', label: 'Assets', kicker: '05', description: '资产预览、归档与重生成' },
  { to: '/prompts', label: 'Prompts', kicker: '06', description: 'Prompt Preset 管理' },
  { to: '/rule-packs', label: 'Rule Packs', kicker: '07', description: '规则包草稿、版本与发布' },
  { to: '/audit', label: 'Audit', kicker: '08', description: '高风险操作审计追踪' },
  { to: '/system', label: 'System', kicker: '09', description: '运行时与定价观测' },
]

async function logout() {
  await auth.logout()
  router.replace({ name: 'login' })
}
</script>
