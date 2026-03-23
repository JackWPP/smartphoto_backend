<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">Audit</span>
        <h3>高风险操作审计</h3>
      </div>
      <div class="toolbar-actions">
        <select v-model="filters.module" class="compact-input">
          <option value="">全部模块</option>
          <option value="users">users</option>
          <option value="sessions">sessions</option>
          <option value="assets">assets</option>
          <option value="jobs">jobs</option>
          <option value="prompts">prompts</option>
          <option value="rule_packs">rule_packs</option>
        </select>
        <button class="ghost-button" @click="loadAudit">刷新</button>
      </div>
    </div>
    <div class="workspace-grid">
      <article class="surface-card">
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>动作</th>
                <th>模块</th>
                <th>风险</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in logs.items || []" :key="item.audit_log_id" :class="{ active: selectedId === item.audit_log_id }" @click="selectAudit(item)">
                <td>
                  <strong>{{ item.action }}</strong>
                  <small>{{ item.target_type }} / {{ item.target_id }}</small>
                </td>
                <td>{{ item.module }}</td>
                <td><span class="status-chip">{{ item.risk_level }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
      <article v-if="selectedAudit" class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">Audit Detail</span>
            <h4>{{ selectedAudit.action }}</h4>
          </div>
          <span>{{ selectedAudit.created_at }}</span>
        </div>
        <div class="metric-grid metric-grid--compact">
          <article class="metric-card">
            <span class="metric-card__label">模块</span>
            <strong class="metric-card__value">{{ selectedAudit.module }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">风险</span>
            <strong class="metric-card__value">{{ selectedAudit.risk_level }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">备注</span>
            <strong class="metric-card__value">{{ selectedAudit.operator_note || '-' }}</strong>
          </article>
        </div>
        <div class="panel-grid">
          <div class="surface-pane">
            <h4>Before Snapshot</h4>
            <pre>{{ prettyJson(selectedAudit.before_snapshot) }}</pre>
          </div>
          <div class="surface-pane">
            <h4>After Snapshot</h4>
            <pre>{{ prettyJson(selectedAudit.after_snapshot) }}</pre>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '../api'
import { prettyJson } from '../lib/format'

const filters = reactive({ module: '' })
const logs = ref({ items: [] })
const selectedAudit = ref(null)
const selectedId = ref('')

async function loadAudit() {
  logs.value = await adminApi.listAuditLogs({ ...filters, page_size: 100 })
  if (!selectedId.value && logs.value.items?.length) {
    selectAudit(logs.value.items[0])
  }
}

function selectAudit(item) {
  selectedAudit.value = item
  selectedId.value = item.audit_log_id
}

onMounted(loadAudit)
</script>
