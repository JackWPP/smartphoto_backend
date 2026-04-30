<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">任务队列管理</span>
        <h3>任务排障与事件时间线</h3>
      </div>
      <div class="toolbar-actions">
        <input v-model="filters.session_id" class="compact-input" placeholder="session_id" />
        <select v-model="filters.status" class="compact-input">
          <option value="">全部状态</option>
          <option value="queued">queued</option>
          <option value="running">running</option>
          <option value="succeeded">succeeded</option>
          <option value="failed">failed</option>
        </select>
        <button class="ghost-button" @click="loadJobs">刷新</button>
      </div>
    </div>

    <div class="workspace-grid">
      <article class="surface-card">
        <div class="surface-card__header">
          <h4>任务列表</h4>
        </div>
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>进度</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in jobs.items || []" :key="item.job_id" :class="{ active: selectedJobId === item.job_id }" @click="openJob(item.job_id)">
                <td>
                  <strong>{{ item.job_type }}</strong>
                  <small>{{ item.job_id }}</small>
                </td>
                <td><span class="status-chip">{{ item.status }}</span></td>
                <td>{{ item.progress }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="surface-card" v-if="detail.job_id">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">任务执行详情</span>
            <h4>{{ detail.job_type }}</h4>
          </div>
          <button class="ghost-button" @click="retrySelectedJob">重试任务</button>
        </div>

        <div class="metric-grid metric-grid--compact">
          <article class="metric-card">
            <span class="metric-card__label">状态</span>
            <strong class="metric-card__value">{{ detail.status }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">进度</span>
            <strong class="metric-card__value">{{ detail.progress }}%</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">错误码</span>
            <strong class="metric-card__value">{{ detail.error_code || '-' }}</strong>
          </article>
        </div>

        <label class="field">
          <span>重试备注</span>
          <textarea v-model="retryNote" rows="3" placeholder="说明为什么重试这个任务" />
        </label>

        <div class="panel-grid">
          <div class="surface-pane">
            <h4>输入载荷</h4>
            <pre>{{ prettyJson(detail.input_payload) }}</pre>
          </div>
          <div class="surface-pane">
            <h4>结果载荷</h4>
            <pre>{{ prettyJson(detail.result_payload) }}</pre>
          </div>
        </div>

        <div class="surface-pane">
          <div class="surface-card__header">
            <h4>事件流时间轴</h4>
            <span>{{ events.total || 0 }} events</span>
          </div>
          <div class="stack-list">
            <div v-for="item in events.items || []" :key="item.event_id" class="stack-list__item stack-list__item--dense">
              <div>
                <strong>#{{ item.seq_no }} · {{ item.event_type }}</strong>
                <small>{{ item.created_at }}</small>
              </div>
              <pre>{{ prettyJson(item.payload) }}</pre>
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
  <ConfirmDialog
    :open="dialog.open"
    :eyebrow="dialog.eyebrow"
    :title="dialog.title"
    :message="dialog.message"
    :confirm-text="dialog.confirmText"
    :danger="dialog.danger"
    @cancel="cancelConfirm"
    @confirm="confirmAction"
  />
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '../api'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { prettyJson } from '../lib/format'
import { useConfirmAction } from '../lib/useConfirmAction'

const filters = reactive({ session_id: '', status: '' })
const jobs = ref({ items: [] })
const detail = ref({})
const events = ref({ items: [] })
const selectedJobId = ref('')
const retryNote = ref('')
const { dialog, requestConfirm, cancelConfirm, confirmAction } = useConfirmAction()

async function loadJobs() {
  jobs.value = await adminApi.listJobs({ ...filters, page_size: 50 })
  if (!selectedJobId.value && jobs.value.items?.length) {
    openJob(jobs.value.items[0].job_id)
  }
}

async function openJob(jobId) {
  selectedJobId.value = jobId
  detail.value = await adminApi.getJob(jobId)
  events.value = await adminApi.getJobEvents(jobId, { page_size: 200 })
}

async function retrySelectedJob() {
  if (!selectedJobId.value || !retryNote.value.trim()) {
    return
  }
  requestConfirm({
    title: '确认重试任务',
    message: `即将重试任务 ${selectedJobId.value}，该动作会重新进入 worker 队列。`,
    confirmText: '确认重试',
    onConfirm: async () => {
      await adminApi.retryJob(selectedJobId.value, { operator_note: retryNote.value })
      retryNote.value = ''
      await loadJobs()
    },
  })
}

onMounted(loadJobs)
</script>
