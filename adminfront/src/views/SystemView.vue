<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">System</span>
        <h3>运行时与队列观测</h3>
      </div>
      <button class="ghost-button" @click="loadSystem">刷新</button>
    </div>

    <div class="metric-grid">
      <article v-for="item in runtime.queue_stats || []" :key="item.queue_name" class="metric-card">
        <span class="metric-card__label">{{ item.queue_name }}</span>
        <strong class="metric-card__value">{{ item.depth }}</strong>
        <small>queue depth</small>
      </article>
    </div>

    <div class="panel-grid">
      <article class="surface-card">
        <div class="surface-card__header">
          <h4>运行时配置</h4>
        </div>
        <div class="stats-list">
          <div class="stats-row"><span>APP_ENV</span><strong>{{ runtime.app_env }}</strong></div>
          <div class="stats-row"><span>PUBLIC_BASE_URL</span><strong>{{ runtime.public_base_url }}</strong></div>
          <div class="stats-row"><span>Storage</span><strong>{{ runtime.storage_backend }}</strong></div>
          <div class="stats-row"><span>S3 Bucket</span><strong>{{ runtime.s3_bucket || '-' }}</strong></div>
          <div class="stats-row"><span>Redis</span><strong>{{ runtime.redis_url }}</strong></div>
        </div>
        <pre>{{ prettyJson(runtime) }}</pre>
      </article>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from '../api'
import { prettyJson } from '../lib/format'

const runtime = ref({})
async function loadSystem() {
  runtime.value = await adminApi.getSystemRuntime()
}

onMounted(loadSystem)
</script>
