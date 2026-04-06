<template>
  <div class="console-shell">
    <aside class="console-sidebar">
      <div class="brand-block">
        <span class="eyebrow">SmartPhoto</span>
        <h1>Admin Console</h1>
        <p>图片生成运维与配置控制台</p>
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
  { to: '/overview', label: '系统概览', kicker: '01', description: '运行概览、趋势与待处理事项' },
  { to: '/sessions', label: '会话跟踪', kicker: '02', description: 'Session 干预与结果追踪' },
  { to: '/jobs', label: '任务队列', kicker: '03', description: '任务、事件时间线与重试' },
  { to: '/assets', label: '素材管理', kicker: '04', description: '资产预览、归档与重生成' },
  { to: '/platform-configs', label: '平台策略体系', kicker: '05', description: '各重点电商平台全局配置和约束' },
  { to: '/prompts', label: 'Prompt模板', kicker: '06', description: 'Prompt Preset 管理' },
  { to: '/category-catalog', label: '品类库配置', kicker: '07', description: '全局品类库配置与启停' },
  { to: '/rule-packs', label: '生成规则包', kicker: '08', description: '规则包草稿、版本与发布' },
  { to: '/audit', label: '权限与审计', kicker: '09', description: '高风险操作审计追踪' },
  { to: '/system', label: '系统观测', kicker: '10', description: '运行时与模型/队列观测' },
]

async function logout() {
  await auth.logout()
  router.replace({ name: 'login' })
}
</script>
