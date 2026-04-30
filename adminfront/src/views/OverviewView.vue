<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">全局概览</span>
        <h3>运行与产出总览</h3>
      </div>
      <button class="ghost-button" @click="loadAll">刷新看板</button>
    </div>

    <div class="metric-grid">
      <article v-for="card in allCards" :key="card.key" class="metric-card">
        <span class="metric-card__label">{{ card.label }}</span>
        <strong class="metric-card__value">{{ card.value }}</strong>
        <small>{{ card.unit || card.trend_hint || 'current' }}</small>
      </article>
    </div>

    <div class="panel-grid panel-grid--wide">
      <article class="surface-card">
        <TrendChart
          title="近 7 日运行趋势"
          :categories="trendBuckets"
          :series="trendSeries"
        />
      </article>
      <article class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">操作关注点</span>
            <h4>当前关注点</h4>
          </div>
        </div>
        <p>只保留图片系统的运行指标、失败任务和高风险操作。用户、订单、额度类经营视角已从当前后台移除。</p>
      </article>
    </div>

    <div class="panel-grid">
      <article class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">失败队列</span>
            <h4>最近失败任务</h4>
          </div>
        </div>
        <div class="stack-list">
          <div v-for="job in overview.recent_failed_jobs || []" :key="job.job_id" class="stack-list__item">
            <div>
              <strong>{{ job.job_type }}</strong>
              <small>{{ job.job_id }}</small>
            </div>
            <div class="align-right">
              <span class="status-chip status-chip--danger">{{ job.status }}</span>
              <small>{{ job.error_message || '-' }}</small>
            </div>
          </div>
        </div>
      </article>
      <article class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">审计记录</span>
            <h4>最近高风险操作</h4>
          </div>
        </div>
        <div class="stack-list">
          <div v-for="item in overview.recent_high_risk_actions || []" :key="item.audit_log_id" class="stack-list__item">
            <div>
              <strong>{{ item.action }}</strong>
              <small>{{ item.module }} / {{ item.target_type }} / {{ item.target_id }}</small>
            </div>
            <div class="align-right">
              <span class="status-chip status-chip--warning">{{ item.risk_level }}</span>
              <small>{{ item.operator_note || '-' }}</small>
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { adminApi } from '../api'
import TrendChart from '../components/TrendChart.vue'

const overview = ref({ summary: {}, runtime_cards: [], ops_cards: [], config_cards: [] })
const trends = ref({ points: [] })

const allCards = computed(() => [
  ...(overview.value.runtime_cards || []),
  ...(overview.value.ops_cards || []),
  ...(overview.value.config_cards || []),
])

const trendBuckets = computed(() => (trends.value.points || []).map((item) => item.bucket))
const trendSeries = computed(() => [
  {
    name: '任务总量',
    type: 'line',
    smooth: true,
    itemStyle: { color: '#d97706' },
    areaStyle: { color: 'rgba(217,119,6,0.14)' },
    data: (trends.value.points || []).map((item) => item.jobs_total),
  },
  {
    name: '失败任务',
    type: 'bar',
    itemStyle: { color: '#b91c1c' },
    data: (trends.value.points || []).map((item) => item.jobs_failed),
  },
  {
    name: '成功资产',
    type: 'line',
    smooth: true,
    itemStyle: { color: '#0f766e' },
    areaStyle: { color: 'rgba(15,118,110,0.14)' },
    data: (trends.value.points || []).map((item) => item.assets_ready),
  },
])

async function loadAll() {
  const [overviewData, trendData] = await Promise.all([
    adminApi.dashboardOverview(),
    adminApi.dashboardTrends({ days: 7 }),
  ])
  overview.value = overviewData
  trends.value = trendData
}

onMounted(loadAll)
</script>
