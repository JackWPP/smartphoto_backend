import { createRouter, createWebHashHistory } from 'vue-router'
import AdminLayout from '../views/AdminLayout.vue'
import AssetsView from '../views/AssetsView.vue'
import AuditView from '../views/AuditView.vue'
import JobsView from '../views/JobsView.vue'
import LoginView from '../views/LoginView.vue'
import OverviewView from '../views/OverviewView.vue'
import CategoryCatalogView from '../views/CategoryCatalogView.vue'
import PromptsView from '../views/PromptsView.vue'
import RulePacksView from '../views/RulePacksView.vue'
import SessionsView from '../views/SessionsView.vue'
import SystemView from '../views/SystemView.vue'

export const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { title: '登录' } },
    {
      path: '/',
      component: AdminLayout,
      children: [
        { path: '', redirect: { name: 'overview' } },
        { path: 'overview', name: 'overview', component: OverviewView, meta: { title: '系统概览' } },
        { path: 'sessions', name: 'sessions', component: SessionsView, meta: { title: '会话跟踪' } },
        { path: 'jobs', name: 'jobs', component: JobsView, meta: { title: '任务队列' } },
        { path: 'assets', name: 'assets', component: AssetsView, meta: { title: '素材管理' } },
        { path: 'platform-configs', name: 'platform-configs', component: () => import('../views/PlatformConfigsView.vue'), meta: { title: '平台策略体系' } },
        { path: 'prompts', name: 'prompts', component: PromptsView, meta: { title: 'Prompt模板' } },
        { path: 'category-catalog', name: 'category-catalog', component: CategoryCatalogView, meta: { title: '品类库配置' } },
        { path: 'rule-packs', name: 'rule-packs', component: RulePacksView, meta: { title: '生成规则包' } },
        { path: 'audit', name: 'audit', component: AuditView, meta: { title: '权限与审计' } },
        { path: 'system', name: 'system', component: SystemView, meta: { title: '系统观测' } },
      ],
    },
  ],
})
