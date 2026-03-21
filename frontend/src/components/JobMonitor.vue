<template>
  <div class="modal-overlay" v-if="job">
    <div class="modal-content">
      <div class="modal-header">
        <div class="job-info">
          <h3>Job Monitor</h3>
          <span class="badge job-type">{{ job.job_type }}</span>
          <span class="badge status" :class="job.status">{{ job.status }}</span>
        </div>
        <button class="btn-close" @click="$emit('close')">&times;</button>
      </div>
      
      <div class="modal-body">
        <div class="progress-section">
          <div class="progress-info">
            <span class="stage">{{ job.stage || 'Initializing...' }}</span>
            <span class="percentage">{{ job.progress || 0 }}%</span>
          </div>
          <div class="progress-bar">
            <div 
              class="progress-fill" 
              :class="{ 'failed': job.status === 'failed', 'completed': job.status === 'completed' || job.status === 'succeeded' }"
              :style="{ width: `${job.progress || 0}%` }"
            ></div>
          </div>
        </div>

        <div class="timing-section" v-if="job.queue_wait_ms != null || job.total_duration_ms != null || job.current_stage_elapsed_ms != null">
          <div class="timing-grid">
            <div class="timing-item"><span class="timing-label">Queue Wait</span><span>{{ formatDuration(job.queue_wait_ms) }}</span></div>
            <div class="timing-item"><span class="timing-label">Current Stage</span><span>{{ formatDuration(job.current_stage_elapsed_ms) }}</span></div>
            <div class="timing-item"><span class="timing-label">Total</span><span>{{ formatDuration(job.total_duration_ms) }}</span></div>
          </div>
          <div v-if="job.stage_timings?.length" class="stage-timings">
            <div v-for="stage in job.stage_timings" :key="`${stage.stage}-${stage.started_at}`" class="stage-timing-item">
              <span>{{ stage.stage }}</span>
              <span>{{ formatDuration(stage.duration_ms) }}</span>
            </div>
          </div>
        </div>

        <div class="events-section">
          <h4>Event Log</h4>
          <div class="events-list" ref="eventsList">
            <div v-for="(event, index) in events" :key="index" class="event-item">
              <div class="event-time">{{ formatTime(event.timestamp || new Date()) }}</div>
              <div class="event-content">
                <span class="event-type badge" :class="getEventClass(event.event_type || event.event)">
                  {{ event.event_type || event.event || 'event' }}
                </span>
                <pre class="event-payload" v-if="event.payload">{{ formatPayload(event.payload) }}</pre>
              </div>
            </div>
            <div v-if="!events.length" class="no-events">
              Waiting for events...
            </div>
          </div>
        </div>
      </div>
      
      <div class="modal-footer">
        <div class="job-id">ID: {{ job.job_id || job.id }}</div>
        <button class="btn btn-secondary" @click="$emit('close')">
          {{ isFinished ? 'Close' : 'Hide (Run in Background)' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps({
  job: {
    type: Object,
    default: null
  },
  events: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close'])
const eventsList = ref(null)

const isFinished = computed(() => {
  if (!props.job) return true
  return ['completed', 'succeeded', 'failed'].includes(props.job.status)
})

// Auto-scroll events to bottom
watch(() => props.events.length, async () => {
  await nextTick()
  if (eventsList.value) {
    eventsList.value.scrollTop = eventsList.value.scrollHeight
  }
})

const formatTime = (timestamp) => {
  const d = new Date(timestamp)
  return d.toLocaleTimeString() + '.' + d.getMilliseconds().toString().padStart(3, '0')
}

const formatPayload = (payload) => {
  try {
    return JSON.stringify(payload, null, 2)
  } catch (e) {
    return String(payload)
  }
}

const formatDuration = (value) => {
  if (value == null) return '-'
  if (value < 1000) return `${value}ms`
  return `${(value / 1000).toFixed(2)}s`
}

const getEventClass = (type) => {
  if (!type) return ''
  if (type.includes('started') || type.includes('queued')) return 'blue'
  if (type.includes('ready') || type.includes('succeeded') || type.includes('completed')) return 'green'
  if (type.includes('failed') || type.includes('error')) return 'red'
  if (type.includes('progress')) return 'yellow'
  return 'default'
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.modal-content {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
}

.modal-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-secondary);
  border-radius: 8px 8px 0 0;
}

.job-info {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.job-info h3 {
  margin: 0;
  color: var(--text-primary);
}

.btn-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
}

.btn-close:hover {
  color: var(--danger-red);
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.progress-section {
  background: var(--bg-tertiary);
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-primary);
}

.progress-bar {
  height: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-blue);
  transition: width 0.3s ease;
}

.progress-fill.completed { background: var(--success-green); }
.progress-fill.failed { background: var(--danger-red); }

.timing-section {
  background: var(--bg-tertiary);
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.timing-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
}

.timing-item,
.stage-timing-item {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  color: var(--text-primary);
}

.timing-label {
  color: var(--text-muted);
}

.stage-timings {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.events-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 300px;
}

.events-section h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-secondary);
}

.events-list {
  flex: 1;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 0.5rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  font-family: monospace;
}

.event-item {
  display: flex;
  gap: 1rem;
  padding: 0.5rem;
  border-bottom: 1px solid var(--border-color);
}

.event-item:last-child {
  border-bottom: none;
}

.event-time {
  color: var(--text-muted);
  font-size: 0.85rem;
  white-space: nowrap;
}

.event-content {
  flex: 1;
}

.event-payload {
  margin: 0.5rem 0 0 0;
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 0.5rem;
  border-radius: 4px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.job-type {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.badge.status.processing, .badge.status.in_progress, .badge.blue { background: rgba(41, 128, 185, 0.2); color: var(--accent-blue); }
.badge.status.completed, .badge.status.succeeded, .badge.green { background: rgba(39, 174, 96, 0.2); color: var(--success-green); }
.badge.status.failed, .badge.red { background: rgba(231, 76, 60, 0.2); color: var(--danger-red); }
.badge.status.pending, .badge.yellow { background: rgba(243, 156, 18, 0.2); color: var(--warning-yellow); }
.badge.default { background: var(--bg-primary); color: var(--text-secondary); border: 1px solid var(--border-color); }

.no-events {
  padding: 2rem;
  text-align: center;
  color: var(--text-muted);
  font-style: italic;
}

.modal-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-secondary);
  border-radius: 0 0 8px 8px;
}

.job-id {
  color: var(--text-muted);
  font-family: monospace;
  font-size: 0.85rem;
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
}
</style>
