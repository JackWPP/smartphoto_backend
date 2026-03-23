import { createRouter, createWebHashHistory } from 'vue-router'
import AdminLayout from '../views/AdminLayout.vue'
import AssetsView from '../views/AssetsView.vue'
import AuditView from '../views/AuditView.vue'
import JobsView from '../views/JobsView.vue'
import LoginView from '../views/LoginView.vue'
import OverviewView from '../views/OverviewView.vue'
import PromptsView from '../views/PromptsView.vue'
import RulePacksView from '../views/RulePacksView.vue'
import SessionsView from '../views/SessionsView.vue'
import SystemView from '../views/SystemView.vue'
import UsersView from '../views/UsersView.vue'

export const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { title: '登录' } },
    {
      path: '/',
      component: AdminLayout,
      children: [
        { path: '', redirect: { name: 'overview' } },
        { path: 'overview', name: 'overview', component: OverviewView, meta: { title: 'Overview' } },
        { path: 'users', name: 'users', component: UsersView, meta: { title: 'Users' } },
        { path: 'sessions', name: 'sessions', component: SessionsView, meta: { title: 'Sessions' } },
        { path: 'jobs', name: 'jobs', component: JobsView, meta: { title: 'Jobs' } },
        { path: 'assets', name: 'assets', component: AssetsView, meta: { title: 'Assets' } },
        { path: 'prompts', name: 'prompts', component: PromptsView, meta: { title: 'Prompts' } },
        { path: 'rule-packs', name: 'rule-packs', component: RulePacksView, meta: { title: 'Rule Packs' } },
        { path: 'audit', name: 'audit', component: AuditView, meta: { title: 'Audit' } },
        { path: 'system', name: 'system', component: SystemView, meta: { title: 'System' } },
      ],
    },
  ],
})
