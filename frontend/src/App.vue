<template>
  <div class="app-container">
    <!-- 顶部标题栏 -->
    <header class="app-header">
      <div class="header-left">
        <h1>📸 SmartPhoto Debug Console</h1>
        <span class="version">v2.0</span>
      </div>
      <div class="header-right">
        <template v-if="authenticated && currentUser">
          <div class="user-chip">
            <strong>{{ currentUser.display_name || currentUser.email }}</strong>
            <span>{{ currentUser.email }}</span>
          </div>
          <div v-if="accountOverview" class="metric-chip">
            余额 {{ accountOverview.wallet_balance }}
          </div>
          <div v-if="notificationSummary.unread_count > 0" class="metric-chip metric-chip-accent">
            未读 {{ notificationSummary.unread_count }}
          </div>
          <button @click="refreshAccountData" class="btn-ghost">刷新账户</button>
          <button @click="logout" class="btn-ghost">退出</button>
        </template>
        <button @click="showApiLog = !showApiLog" class="btn-ghost">
          {{ showApiLog ? '隐藏' : '显示' }}日志
        </button>
        <button @click="clearStorage" class="btn-ghost text-error">
          清空缓存
        </button>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="app-main">
      <section v-if="!authReady" class="auth-shell">
        <div class="auth-card auth-loading">
          <h2>恢复登录中</h2>
          <p>正在检查 refresh cookie 和本地 access token...</p>
        </div>
      </section>

      <section v-else-if="!authenticated" class="auth-shell">
        <div class="auth-card">
          <div class="auth-header">
            <h2>登录调试前端</h2>
            <p>当前 `/api/v2` 已要求真实用户身份，先登录再进入 6 步调试台。</p>
          </div>
          <div class="auth-tabs">
            <button class="auth-tab" :class="{ active: authMode === 'login' }" @click="setAuthMode('login')">
              登录
            </button>
            <button class="auth-tab" :class="{ active: authMode === 'register' }" @click="setAuthMode('register')">
              注册
            </button>
          </div>
          <div class="auth-form">
            <input v-model="authForm.email" type="email" placeholder="邮箱，例如 jack@example.com" />
            <input v-model="authForm.password" type="password" placeholder="密码，至少 8 位" @keyup.enter="submitAuth" />
            <input
              v-if="authMode === 'register'"
              v-model="authForm.display_name"
              placeholder="显示名称，可选"
              @keyup.enter="submitAuth"
            />
            <button class="btn-primary auth-submit" :disabled="authSubmitting" @click="submitAuth">
              <span v-if="authSubmitting" class="spinner"></span>
              {{ authMode === 'login' ? '登录并进入控制台' : '注册并进入控制台' }}
            </button>
            <p v-if="authErrorMessage" class="auth-error">{{ authErrorMessage }}</p>
          </div>
        </div>
      </section>

      <template v-else>
      <section v-if="currentUser" class="section overview-grid">
        <div class="overview-card overview-hero">
          <div>
            <p class="overview-eyebrow">当前用户</p>
            <h2>{{ currentUser.display_name || currentUser.email }}</h2>
            <p class="overview-subtitle">{{ currentUser.email }}</p>
          </div>
          <div class="overview-quick-actions">
            <button class="btn-secondary" @click="refreshAccountData">刷新</button>
            <button
              class="btn-secondary"
              :disabled="notificationSummary.unread_count === 0"
              @click="markAllNotificationsRead"
            >
              全部已读
            </button>
          </div>
        </div>
        <div class="overview-card stat-card">
          <span class="stat-label">累计资产</span>
          <strong>{{ accountOverview?.total_generated_assets ?? 0 }}</strong>
        </div>
        <div class="overview-card stat-card">
          <span class="stat-label">本月生成</span>
          <strong>{{ accountOverview?.generated_assets_this_month ?? 0 }}</strong>
        </div>
        <div class="overview-card stat-card">
          <span class="stat-label">Session 数</span>
          <strong>{{ accountOverview?.session_count ?? 0 }}</strong>
        </div>
        <div class="overview-card stat-card">
          <span class="stat-label">钱包余额</span>
          <strong>{{ accountOverview?.wallet_balance ?? 0 }}</strong>
        </div>
        <div class="overview-card panel-card">
          <div class="panel-header">
            <h3>最近资产</h3>
            <span>{{ accountAssets.length }} 条</span>
          </div>
          <div v-if="accountAssets.length" class="mini-list">
            <button
              v-for="item in accountAssets"
              :key="item.session_id"
              class="mini-list-item"
              @click="openAccountAsset(item.session_id)"
            >
              <strong>{{ item.product_name || item.session_id }}</strong>
              <span>{{ item.platform_id || '未选平台' }} · 主图 {{ item.counts.main }} · 详情 {{ item.counts.detail }}</span>
            </button>
          </div>
          <div v-else class="mini-empty">还没有可展示的历史资产</div>
        </div>
        <div class="overview-card panel-card">
          <div class="panel-header">
            <h3>站内通知</h3>
            <span>{{ notificationSummary.unread_count }} 未读</span>
          </div>
          <div v-if="accountNotifications.length" class="mini-list">
            <button
              v-for="item in accountNotifications"
              :key="item.notification_id"
              class="mini-list-item"
              :class="{ unread: !item.is_read }"
              @click="markNotificationRead(item.notification_id)"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.content }}</span>
            </button>
          </div>
          <div v-else class="mini-empty">暂无通知</div>
        </div>
      </section>

      <!-- Session 管理栏 -->
      <section class="section session-bar">
        <div class="session-controls">
          <button @click="createSession" class="btn-primary" :disabled="loading">
            <span v-if="loading" class="spinner"></span>
            创建新 Session
          </button>
          <div class="session-input">
            <input
              v-model="sessionInput"
              placeholder="输入 Session ID 恢复调试..."
              @keyup.enter="loadSession"
            />
            <button @click="loadSession" class="btn-secondary">加载</button>
          </div>
        </div>
        
        <div v-if="session" class="session-info">
          <div class="session-id">
            <span class="label">Session ID:</span>
            <code>{{ session.session_id }}</code>
            <button @click="copyToClipboard(session.session_id)" class="btn-icon" title="复制">
              📋
            </button>
          </div>
          <div class="session-status">
            <span class="label">状态:</span>
            <span
              class="status-badge"
              :style="{ backgroundColor: statusConfig.color }"
            >
              {{ statusConfig.label }}
            </span>
            <span class="step-indicator">Step {{ session.current_step }}/6</span>
          </div>
        </div>

        <div v-if="session" class="generation-mode-bar">
          <div class="generation-mode-copy">
            <span class="label">生成出口:</span>
            <span class="mode-hint">切到详情页时，不会触发主图 5 张生成。</span>
          </div>
          <div class="mode-toggle-group">
            <button
              v-for="mode in GENERATION_MODES"
              :key="mode.value"
              class="mode-toggle"
              :class="{ active: generationMode === mode.value }"
              @click="setGenerationMode(mode.value)"
            >
              {{ mode.label }}
            </button>
          </div>
        </div>
      </section>

      <!-- 6步流程面板 -->
      <template v-if="session">
        <!-- Step 1: 图片上传 -->
        <StepPanel
          title="Step 1: 上传图片"
          :step="1"
          :currentStep="session.current_step"
          :open="activeStep === 1"
          @toggle="activeStep = activeStep === 1 ? null : 1"
        >
          <ImageUpload
            :session-id="session.session_id"
            :images="images"
            @upload="handleUpload"
            @delete="handleDeleteImage"
            @refresh="fetchSessionImages"
          />
        </StepPanel>

        <!-- Step 2: 分析 -->
        <StepPanel
          title="Step 2: 分析图片"
          :step="2"
          :currentStep="session.current_step"
          :open="activeStep === 2"
          @toggle="activeStep = activeStep === 2 ? null : 2"
        >
          <AnalysisPanel
            :session-id="session.session_id"
            :analysis="analysis"
            @trigger="handleAnalysis"
          />
        </StepPanel>

        <!-- Step 3: 平台选择 -->
        <StepPanel
          title="Step 3: 选择平台"
          :step="3"
          :currentStep="session.current_step"
          :open="activeStep === 3"
          @toggle="activeStep = activeStep === 3 ? null : 3"
        >
          <PlatformSelector
            :session-id="session.session_id"
            :platforms="platforms"
            :selected="session.selected_platform_ids"
            :active="session.active_platform_id"
            @save="handlePlatformSelection"
          />
        </StepPanel>

        <!-- Step 4: Copy 编辑 -->
        <StepPanel
          title="Step 4: 编辑 Copy"
          :step="4"
          :currentStep="session.current_step"
          :open="activeStep === 4"
          @toggle="activeStep = activeStep === 4 ? null : 4"
        >
          <CopyEditor
            :session-id="session.session_id"
            :copy="copy"
            @save="handleSaveCopy"
            @regenerate="handleRegenerateCopy"
          />
        </StepPanel>

        <!-- Step 5: 策略预览 -->
        <div ref="step5Container">
          <StepPanel
            :title="generationMode === 'main_gallery' ? 'Step 5: 策略预览（主图组）' : 'Step 5: 策略预览（详情页）'"
            :step="5"
            :currentStep="session.current_step"
            :open="activeStep === 5"
            @toggle="activeStep = activeStep === 5 ? null : 5"
          >
            <StrategyPreview
              v-if="generationMode === 'main_gallery'"
              :session-id="session.session_id"
              :strategy="strategy"
              @build="handleBuildStrategy"
            />
            <DetailStrategyPreview
              v-else
              :session-id="session.session_id"
              :strategy="detailStrategy"
              :style-images="detailStyleImages"
              @build="handleBuildDetailStrategy"
              @upload-style-image="handleUploadDetailStyleImage"
              @delete-style-image="handleDeleteDetailStyleImage"
            />
          </StepPanel>
        </div>

        <!-- Step 6: 生成 & 结果 -->
        <StepPanel
          :title="generationMode === 'main_gallery' ? 'Step 6: 生成 & 结果（主图组）' : 'Step 6: 生成 & 结果（详情页）'"
          :step="6"
          :currentStep="session.current_step"
          :open="activeStep === 6"
          @toggle="activeStep = activeStep === 6 ? null : 6"
        >
          <GenerationPanel
            v-if="generationMode === 'main_gallery'"
            :session-id="session.session_id"
            :results="results"
            :latest-version="session.latest_result_version"
            :is-generating="isGenerationRunning"
            @generate="handleGenerate"
            @generate-single="handleGenerateSingleSlot"
            @global-edit="handleGlobalEdit"
            @regenerate-gallery="handleRegenerateGallery"
            @regenerate-asset="handleRegenerateAsset"
            @edit-slot="handleEditSlot"
            @download="handleDownload"
            @refresh="fetchResults"
            @refresh-version="fetchResults"
          />
          <DetailGenerationPanel
            v-else
            :session-id="session.session_id"
            :results="detailResults"
            :latest-version="session.detail_latest_result_version"
            :is-generating="isGenerationRunning"
            @generate="handleGenerateDetailPage"
            @edit-panel="handleEditDetailPanel"
            @regenerate-asset="handleRegenerateAsset"
            @download="handleDownloadDetailPage"
            @refresh="fetchDetailResults"
            @refresh-version="fetchDetailResults"
          />
        </StepPanel>
      </template>

      <!-- 空状态 -->
      <div v-else class="empty-state">
        <div class="empty-icon">🚀</div>
        <h2>欢迎使用 SmartPhoto Debug Console</h2>
        <p>创建新 Session 或输入已有 Session ID 开始调试</p>
      </div>
      </template>
    </main>

    <!-- Job 监控面板 -->
    <JobMonitor
      v-if="activeJob"
      :job="activeJob"
      :events="jobEvents"
      @close="closeJobMonitor"
    />

    <!-- API 日志侧边栏 -->
    <div v-if="showApiLog" class="api-log-sidebar">
      <div class="log-header">
        <h3>API 日志</h3>
        <button @click="clearLogs" class="btn-ghost">清空</button>
      </div>
      <div class="log-list">
        <div
          v-for="(log, index) in apiLogs"
          :key="index"
          class="log-item"
          :class="{ 'log-error': log.error }"
        >
          <div class="log-meta">
            <span class="log-method" :class="log.method.toLowerCase()">{{ log.method }}</span>
            <span class="log-path">{{ log.path }}</span>
            <span class="log-status" :class="log.status < 400 ? 'success' : 'error'">
              {{ log.status }}
            </span>
            <span class="log-duration">{{ log.duration }}ms</span>
          </div>
          <details v-if="log.request || log.response" class="log-details">
            <summary>详情</summary>
            <pre v-if="log.request">{{ JSON.stringify(log.request, null, 2) }}</pre>
            <pre v-if="log.response">{{ JSON.stringify(log.response, null, 2) }}</pre>
            <pre v-if="log.error" class="error">{{ JSON.stringify(log.error, null, 2) }}</pre>
          </details>
        </div>
        <div v-if="apiLogs.length === 0" class="log-empty">
          暂无日志
        </div>
      </div>
    </div>

    <!-- 全局错误提示 -->
    <div v-if="globalError" class="global-error" @click="globalError = null">
      <div class="error-content">
        <span class="error-icon">⚠️</span>
        <div class="error-message">
          <strong>错误 {{ globalError.code }}</strong>
          <p>{{ globalError.message }}</p>
        </div>
        <button class="btn-close">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { api, GENERATION_MODES, SESSION_STATUS } from './api/index.js'

import StepPanel from './components/StepPanel.vue'
import ImageUpload from './components/ImageUpload.vue'
import AnalysisPanel from './components/AnalysisPanel.vue'
import PlatformSelector from './components/PlatformSelector.vue'
import CopyEditor from './components/CopyEditor.vue'
import StrategyPreview from './components/StrategyPreview.vue'
import DetailStrategyPreview from './components/DetailStrategyPreview.vue'
import GenerationPanel from './components/GenerationPanel.vue'
import DetailGenerationPanel from './components/DetailGenerationPanel.vue'
import JobMonitor from './components/JobMonitor.vue'

const GENERATION_JOB_TYPES = [
  'generate_gallery',
  'global_edit',
  'regenerate_gallery',
  'regenerate_asset',
  'generate_detail_page',
  'regenerate_detail_panel',
]

function normalizeGenerationMode(mode) {
  return GENERATION_MODES.some((item) => item.value === mode) ? mode : 'main_gallery'
}

// ===== 状态管理 =====
const session = ref(null)
const sessionInput = ref('')
const loading = ref(false)
const activeStep = ref(1)
const showApiLog = ref(false)
const globalError = ref(null)
const generationMode = ref(normalizeGenerationMode(localStorage.getItem('smartphoto_generation_mode')))
const authReady = ref(false)
const authenticated = ref(false)
const authMode = ref('login')
const authSubmitting = ref(false)
const authErrorMessage = ref('')
const authForm = ref({ email: '', password: '', display_name: '' })
const currentUser = ref(null)
const accountOverview = ref(null)
const accountNotifications = ref([])
const accountAssets = ref([])

// 数据状态
const images = ref([])
const analysis = ref(null)
const platforms = ref([])
const copy = ref({})
const copyRegenerateResult = ref(null)
const strategy = ref(null)
const detailStrategy = ref(null)
const detailStyleImages = ref([])
const results = ref(null)
const detailResults = ref(null)
const step5Container = ref(null)

// Job 监控
const activeJob = ref(null)
const jobEvents = ref([])

// API 日志
const apiLogs = ref([])

const notificationSummary = computed(() => ({
  unread_count: accountNotifications.value.filter((item) => !item.is_read).length,
}))

// ===== 计算属性 =====
const statusConfig = computed(() => {
  if (!session.value) return { label: '-', color: '#666' }
  return SESSION_STATUS[session.value.status] || { label: session.value.status, color: '#666' }
})

const isGenerationRunning = computed(() => {
  const jobType = activeJob.value?.job_type || activeJob.value?.type
  return Boolean(activeJob.value && GENERATION_JOB_TYPES.includes(jobType))
})

// ===== 生命周期 =====
onMounted(() => {
  window.addEventListener('api-log', handleApiLog)
  void bootstrapApp()
})

onUnmounted(() => {
  window.removeEventListener('api-log', handleApiLog)
})

// ===== API 日志处理 =====
function handleApiLog(event) {
  apiLogs.value.unshift(event.detail)
  if (apiLogs.value.length > 50) {
    apiLogs.value = apiLogs.value.slice(0, 50)
  }
}

function clearLogs() {
  apiLogs.value = []
}

async function bootstrapApp() {
  await fetchPlatforms()
  await restoreAuthentication()
  authReady.value = true
  if (authenticated.value) {
    await bootstrapAuthenticatedConsole()
  }
}

async function restoreAuthentication() {
  try {
    if (api.hasAccessToken()) {
      currentUser.value = await api.me()
      authenticated.value = true
      return
    }
    const refreshed = await api.refresh()
    api.setAccessToken(refreshed.access_token)
    currentUser.value = refreshed.user
    authenticated.value = true
  } catch {
    api.setAccessToken('')
    authenticated.value = false
    currentUser.value = null
  }
}

async function bootstrapAuthenticatedConsole() {
  authErrorMessage.value = ''
  await fetchPlatforms()
  await refreshAccountData()
  const savedSessionId = localStorage.getItem('smartphoto_session_id')
  if (savedSessionId) {
    sessionInput.value = savedSessionId
    await loadSession()
  }
}

function setAuthMode(mode) {
  authMode.value = mode
  authErrorMessage.value = ''
}

async function submitAuth() {
  authSubmitting.value = true
  try {
    const payload = {
      email: authForm.value.email.trim(),
      password: authForm.value.password,
      display_name: authForm.value.display_name?.trim() || undefined,
    }
    const data = authMode.value === 'login'
      ? await api.login({ email: payload.email, password: payload.password })
      : await api.register(payload)
    api.setAccessToken(data.access_token)
    currentUser.value = data.user
    authenticated.value = true
    authErrorMessage.value = ''
    await bootstrapAuthenticatedConsole()
  } catch (error) {
    authErrorMessage.value = error.message || '认证失败'
  } finally {
    authSubmitting.value = false
  }
}

async function logout() {
  try {
    await api.logout()
  } catch (error) {
    console.warn('Logout failed:', error)
  }
  handleAuthExpired('')
}

function resetConsoleState() {
  if (activeJob.value?.cleanup) {
    activeJob.value.cleanup()
  }
  session.value = null
  sessionInput.value = ''
  images.value = []
  analysis.value = null
  copy.value = {}
  copyRegenerateResult.value = null
  strategy.value = null
  detailStrategy.value = null
  detailStyleImages.value = []
  results.value = null
  detailResults.value = null
  activeJob.value = null
  jobEvents.value = []
}

function handleAuthExpired(message = '登录已失效，请重新登录') {
  api.setAccessToken('')
  localStorage.removeItem('smartphoto_session_id')
  authenticated.value = false
  currentUser.value = null
  accountOverview.value = null
  accountNotifications.value = []
  accountAssets.value = []
  authErrorMessage.value = message
  resetConsoleState()
}

async function refreshAccountData() {
  if (!authenticated.value) return
  try {
    const [profile, overview, notifications, assets] = await Promise.all([
      api.me(),
      api.getAccountOverview(),
      api.getAccountNotifications(6),
      api.getAccountAssets({ page: 1, page_size: 6 }),
    ])
    currentUser.value = profile
    accountOverview.value = overview
    accountNotifications.value = notifications.items || []
    accountAssets.value = assets.items || []
  } catch (error) {
    showError(error)
  }
}

async function markNotificationRead(notificationId) {
  try {
    await api.markNotificationRead(notificationId)
    await refreshAccountData()
  } catch (error) {
    showError(error)
  }
}

async function markAllNotificationsRead() {
  try {
    await api.markAllNotificationsRead()
    await refreshAccountData()
  } catch (error) {
    showError(error)
  }
}

async function openAccountAsset(sessionId) {
  sessionInput.value = sessionId
  await loadSession()
}

// ===== Session 管理 =====
async function createSession() {
  loading.value = true
  try {
    await fetchPlatforms()
    const data = await api.createSession()
    session.value = data
    strategy.value = data.strategy_preview || null
    detailStrategy.value = data.detail_strategy_preview || null
    sessionInput.value = data.session_id
    localStorage.setItem('smartphoto_session_id', data.session_id)
    activeStep.value = 1

    images.value = []
    analysis.value = null
    copy.value = {}
    copyRegenerateResult.value = null
    strategy.value = null
    detailStrategy.value = null
    detailStyleImages.value = []
    results.value = null
    detailResults.value = null
  } catch (error) {
    showError(error)
  } finally {
    loading.value = false
  }
}

async function loadSession() {
  if (!sessionInput.value.trim()) return

  loading.value = true
  try {
    await fetchPlatforms()
    const data = await api.getSession(sessionInput.value)
    session.value = data
    strategy.value = data.strategy_preview || null
    detailStrategy.value = data.detail_strategy_preview || null
    localStorage.setItem('smartphoto_session_id', data.session_id)

    await Promise.all([
      fetchSessionImages(),
      fetchAnalysis(),
      fetchCopy(),
      fetchStrategy(),
      fetchDetailStrategy(),
      fetchDetailStyleImages(),
      fetchResults(),
      fetchDetailResults(),
    ])

    const savedImages = localStorage.getItem(`smartphoto_images_${data.session_id}`)
    if (savedImages) {
      try {
        images.value = JSON.parse(savedImages)
      } catch (e) {
        console.error('Failed to parse saved images:', e)
      }
    }

    activeStep.value = data.current_step
  } catch (error) {
    showError(error)
  } finally {
    loading.value = false
  }
}

function clearStorage() {
  if (session.value?.session_id) {
    localStorage.removeItem(`smartphoto_images_${session.value.session_id}`)
  }
  localStorage.removeItem('smartphoto_session_id')
  resetConsoleState()
}

function setGenerationMode(mode) {
  generationMode.value = normalizeGenerationMode(mode)
  localStorage.setItem('smartphoto_generation_mode', generationMode.value)
}

// ===== Step 1: 图片上传 =====
async function fetchSessionImages() {
  if (!session.value) return

  try {
    const data = await api.getSessionImages(session.value.session_id)
    if (data.images) {
      images.value = data.images.map((img) => ({
        id: img.image_id,
        slot_type: img.slot_type,
        display_order: img.display_order,
        url: img.url,
        width: img.width,
        height: img.height,
      }))
      localStorage.setItem(`smartphoto_images_${session.value.session_id}`, JSON.stringify(images.value))
    }
  } catch (error) {
    console.error('Failed to fetch images:', error)
  }
}

async function handleUpload(data) {
  try {
    const result = await api.uploadImage(session.value.session_id, data.file, data.slot_type, data.display_order)
    showSuccess('图片上传成功')
    if (result.uploaded_images) {
      images.value = result.uploaded_images.map((img) => ({
        id: img.image_id,
        slot_type: img.slot_type,
        display_order: img.display_order,
        url: img.url,
      }))
      localStorage.setItem(`smartphoto_images_${session.value.session_id}`, JSON.stringify(images.value))
    }
    await fetchSession()
  } catch (error) {
    showError(error)
  }
}

async function handleDeleteImage(imageId) {
  try {
    await api.deleteImage(session.value.session_id, imageId)
    showSuccess('图片已删除')
    images.value = images.value.filter((img) => img.id !== imageId)
    localStorage.setItem(`smartphoto_images_${session.value.session_id}`, JSON.stringify(images.value))
    await fetchSession()
  } catch (error) {
    showError(error)
  }
}

async function fetchDetailStyleImages() {
  if (!session.value) return

  try {
    const data = await api.getDetailStyleImages(session.value.session_id)
    detailStyleImages.value = (data.images || []).map((img) => ({
      id: img.image_id,
      image_id: img.image_id,
      display_order: img.display_order,
      url: img.url,
      width: img.width,
      height: img.height,
      mime_type: img.mime_type,
      file_size: img.file_size,
    }))
  } catch (error) {
    console.error('Failed to fetch detail style images:', error)
    detailStyleImages.value = []
  }
}

async function handleUploadDetailStyleImage(data) {
  try {
    const result = await api.uploadDetailStyleImage(session.value.session_id, data.file, data.display_order)
    if (result.uploaded_images?.length) {
      detailStyleImages.value = result.uploaded_images.map((img) => ({
        id: img.image_id,
        image_id: img.image_id,
        display_order: img.display_order,
        url: img.url,
      }))
      await fetchDetailStyleImages()
    } else {
      await fetchDetailStyleImages()
    }
    showSuccess('详情页风格图已上传，重新 Build Detail Strategy 后会生效')
  } catch (error) {
    showError(error)
  }
}

async function handleDeleteDetailStyleImage(imageId) {
  try {
    await api.deleteDetailStyleImage(session.value.session_id, imageId)
    detailStyleImages.value = detailStyleImages.value.filter((img) => (img.image_id || img.id) !== imageId)
    showSuccess('详情页风格图已删除，重新 Build Detail Strategy 后会生效')
  } catch (error) {
    showError(error)
  }
}

// ===== Step 2: 分析 =====
async function fetchAnalysis() {
  if (!session.value) return

  try {
    const data = await api.getAnalysis(session.value.session_id)
    analysis.value = data.analysis_snapshot
  } catch (error) {
    console.error('Failed to fetch analysis:', error)
  }
}

async function handleAnalysis() {
  try {
    const data = await api.triggerAnalysis(session.value.session_id, generateIdempotencyKey())
    openJobMonitor(data.job_id, 'analysis')
  } catch (error) {
    showError(error)
  }
}

// ===== Step 3: 平台选择 =====
async function fetchPlatforms() {
  try {
    const data = await api.getPlatforms()
    platforms.value = data.items || []
  } catch (error) {
    console.error('Failed to fetch platforms:', error)
    platforms.value = []
    showError(error)
  }
}

async function handlePlatformSelection(data) {
  try {
    await api.setPlatformSelection(session.value.session_id, data.selected_platform_ids, data.active_platform_id)
    showSuccess('平台选择已保存')
    await fetchSession()
  } catch (error) {
    showError(error)
  }
}

// ===== Step 4: Copy 编辑 =====
async function fetchCopy() {
  if (!session.value) return

  try {
    const data = await api.getCopy(session.value.session_id)
    copy.value = data
  } catch (error) {
    console.error('Failed to fetch copy:', error)
  }
}

async function fetchCopyRegenerateResult(jobId) {
  if (!session.value || !jobId) return

  try {
    const data = await api.getCopyRegenerateResult(session.value.session_id, jobId)
    copyRegenerateResult.value = data
    if (data.generated_fields) {
      copy.value = { ...copy.value, ...data.generated_fields }
      showSuccess('Copy 字段已重生成')
    }
  } catch (error) {
    console.error('Failed to fetch copy regenerate result:', error)
  }
}

async function handleSaveCopy(copyData) {
  try {
    await api.saveCopy(session.value.session_id, copyData)
    showSuccess('Copy 已保存')
    await fetchSession()
  } catch (error) {
    showError(error)
  }
}

async function handleRegenerateCopy(data) {
  try {
    const result = await api.regenerateCopy(
      session.value.session_id,
      data.targets,
      data.instruction,
      generateIdempotencyKey(),
    )
    openJobMonitor(result.job_id, 'regenerate_copy')
  } catch (error) {
    showError(error)
  }
}

// ===== Step 5: 策略预览 =====
async function fetchStrategy() {
  if (!session.value) return
  strategy.value = session.value.strategy_preview || null
}

async function fetchDetailStrategy() {
  if (!session.value) return
  detailStrategy.value = session.value.detail_strategy_preview || null
}

async function handleBuildStrategy(payload = {}) {
  try {
    const data = await api.buildStrategy(
      session.value.session_id,
      payload.plannerInstruction || null,
      payload.slotPreferences || [],
    )
    strategy.value = data.strategy_preview
    showSuccess('策略预览已生成')
    await fetchSession()
  } catch (error) {
    showError(error)
  }
}

async function handleBuildDetailStrategy(payload = {}) {
  try {
    const data = await api.buildDetailStrategy(
      session.value.session_id,
      payload.plannerInstruction || null,
      payload.panelPreferences || [],
    )
    detailStrategy.value = data.detail_strategy_preview
    showSuccess('详情页策略预览已生成')
    await fetchSession()
  } catch (error) {
    showError(error)
  }
}

// ===== Step 6: 生成 & 结果 =====
async function fetchResults(version = null) {
  if (!session.value) return

  try {
    const data = await api.getResults(session.value.session_id, version)
    results.value = data
  } catch (error) {
    console.error('Failed to fetch results:', error)
    showError(error)
  }
}

async function fetchDetailResults(version = null) {
  if (!session.value) return

  try {
    const data = await api.getDetailResults(session.value.session_id, version)
    detailResults.value = data
  } catch (error) {
    console.error('Failed to fetch detail results:', error)
    showError(error)
  }
}

async function handleGenerate(data) {
  try {
    const result = await api.generateGallery(
      session.value.session_id,
      data.instruction,
      generateIdempotencyKey(),
      data.slotIds || [],
    )
    openJobMonitor(result.job_id, 'generate_gallery')
  } catch (error) {
    showError(error)
  }
}

async function handleGenerateSingleSlot(data) {
  try {
    const result = await api.generateGallery(
      session.value.session_id,
      data.instruction || null,
      generateIdempotencyKey(),
      data.slotIds || [],
    )
    openJobMonitor(result.job_id, 'generate_gallery')
    showSuccess(`已触发单槽位生成：${(data.slotIds || []).join(', ')}`)
  } catch (error) {
    showError(error)
  }
}

async function handleGenerateDetailPage(data) {
  try {
    const result = await api.generateDetailPage(
      session.value.session_id,
      data.instruction,
      generateIdempotencyKey(),
    )
    openJobMonitor(result.job_id, 'generate_detail_page')
  } catch (error) {
    showError(error)
  }
}

async function handleGlobalEdit(data) {
  try {
    const result = await api.globalEdit(
      session.value.session_id,
      data.instruction,
      data.scope,
      data.assetIds || [],
      generateIdempotencyKey(),
    )
    openJobMonitor(result.job_id, 'global_edit')
  } catch (error) {
    showError(error)
  }
}

async function handleRegenerateGallery() {
  try {
    const result = await api.regenerateGallery(
      session.value.session_id,
      null,
      null,
      generateIdempotencyKey(),
    )
    openJobMonitor(result.job_id, 'regenerate_gallery')
  } catch (error) {
    showError(error)
  }
}

async function handleRegenerateAsset(assetId) {
  try {
    const result = await api.regenerateAsset(
      assetId,
      '重新生成',
      true,
      generateIdempotencyKey(),
    )
    openJobMonitor(result.job_id, result.job_type || 'regenerate_asset')
  } catch (error) {
    showError(error)
  }
}

async function focusStep5() {
  await nextTick()
  step5Container.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function handleEditSlot() {
  generationMode.value = 'main_gallery'
  activeStep.value = 5
  void focusStep5()
}

function handleEditDetailPanel() {
  generationMode.value = 'detail_page'
  activeStep.value = 5
  void focusStep5()
}

async function handleDownload(version) {
  try {
    await api.downloadResults(session.value.session_id, version)
  } catch (error) {
    showError(error)
  }
}

async function handleDownloadDetailPage(version) {
  try {
    await api.downloadDetailResults(session.value.session_id, version)
  } catch (error) {
    showError(error)
  }
}

// ===== Job 监控 =====
async function refreshAfterJob(jobType, jobId) {
  await fetchSession()
  await Promise.all([fetchResults(), fetchDetailResults(), refreshAccountData()])

  if (jobType === 'analysis') {
    await Promise.all([fetchAnalysis(), fetchCopy()])
    return
  }

  if (jobType === 'regenerate_copy') {
    await fetchCopyRegenerateResult(jobId)
  }
}

function openJobMonitor(jobId, jobType) {
  activeJob.value = { id: jobId, job_id: jobId, type: jobType, job_type: jobType, status: 'queued', progress: 0 }
  jobEvents.value = []

  const pushMonitorEvent = (event) => {
    const normalized = event?.payload
      ? event
      : {
          ...event,
          payload: event,
          timestamp: event?.timestamp || new Date().toISOString(),
        }
    jobEvents.value.push(normalized)
  }

  const refreshJobStatus = async () => {
    try {
      const status = await api.getJob(jobId)
      activeJob.value = { ...activeJob.value, ...status, id: status.job_id || jobId, type: jobType, job_type: status.job_type || jobType }
    } catch (error) {
      console.error('Failed to refresh job status', error)
    }
  }

  void refreshJobStatus()
  const timer = window.setInterval(() => {
    void refreshJobStatus()
  }, 1000)

  let cleanup = () => {}
  void api
    .streamJobEvents(
      jobId,
      (event) => {
        pushMonitorEvent(event)

        if (event.event === 'asset_ready') {
          fetchResults()
          fetchDetailResults()
        }
      },
      (error) => {
        console.error('SSE error:', error)
        pushMonitorEvent({
          event: 'stream_error',
          message: error?.message || 'SSE stream error',
        })
      },
      () => {
        window.clearInterval(timer)
        void refreshAfterJob(jobType, jobId)
      },
    )
    .then((streamCleanup) => {
      cleanup = streamCleanup || (() => {})
    })
    .catch((error) => {
      console.error('Failed to start SSE stream:', error)
      pushMonitorEvent({
        event: 'stream_error',
        message: error?.message || 'Failed to start SSE stream',
      })
    })

  activeJob.value.cleanup = () => {
    cleanup()
    window.clearInterval(timer)
  }
}

function closeJobMonitor() {
  if (activeJob.value?.cleanup) {
    activeJob.value.cleanup()
  }
  activeJob.value = null
  jobEvents.value = []
}

// ===== 工具函数 =====
async function fetchSession() {
  if (!session.value) return

  try {
    const data = await api.getSession(session.value.session_id)
    session.value = data
    strategy.value = data.strategy_preview || null
    detailStrategy.value = data.detail_strategy_preview || null
  } catch (error) {
    console.error('Failed to fetch session:', error)
  }
}

function generateIdempotencyKey() {
  return `debug-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text)
  showSuccess('已复制到剪贴板')
}

function showError(error) {
  if (error?.status === 401) {
    handleAuthExpired(error.message || '登录已失效，请重新登录')
    return
  }
  globalError.value = error
  setTimeout(() => {
    globalError.value = null
  }, 5000)
}

function showSuccess(message) {
  console.log('✅', message)
}
</script>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: var(--bg-primary);
}

/* Header */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h1 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.version {
  font-size: 12px;
  color: var(--text-muted);
  background-color: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 12px;
}

.header-right {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.user-chip,
.metric-chip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background-color: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 12px;
}

.user-chip strong,
.metric-chip {
  color: var(--text-primary);
}

.metric-chip {
  justify-content: center;
  min-height: 38px;
}

.metric-chip-accent {
  background-color: rgba(59, 130, 246, 0.12);
  color: var(--accent-blue);
}

.auth-shell {
  min-height: calc(100vh - 140px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
}

.auth-card {
  width: min(100%, 460px);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 24px;
  box-shadow: var(--shadow-md);
}

.auth-loading {
  text-align: center;
}

.auth-header h2 {
  font-size: 24px;
  margin-bottom: 8px;
}

.auth-header p {
  color: var(--text-secondary);
  margin-bottom: 20px;
}

.auth-tabs {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}

.auth-tab {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  background-color: var(--bg-tertiary);
}

.auth-tab.active {
  color: white;
  background-color: var(--accent-blue);
  border-color: var(--accent-blue);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.auth-submit {
  width: 100%;
}

.auth-error {
  color: var(--accent-red);
  font-size: 13px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.overview-card {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
}

.overview-hero {
  grid-column: span 2;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.overview-eyebrow {
  font-size: 12px;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  margin-bottom: 6px;
}

.overview-subtitle {
  color: var(--text-secondary);
}

.overview-quick-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: center;
}

.stat-card strong {
  font-size: 28px;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-muted);
}

.panel-card {
  grid-column: span 2;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-header h3 {
  font-size: 16px;
}

.mini-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mini-list-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  text-align: left;
  padding: 12px;
  border-radius: var(--radius-sm);
  background-color: var(--bg-tertiary);
  border: 1px solid transparent;
  transition: border-color 0.2s, transform 0.2s;
}

.mini-list-item:hover {
  border-color: var(--accent-blue);
  transform: translateY(-1px);
}

.mini-list-item.unread {
  border-color: rgba(59, 130, 246, 0.35);
}

.mini-list-item strong {
  color: var(--text-primary);
}

.mini-list-item span,
.mini-empty {
  color: var(--text-secondary);
  font-size: 13px;
}

/* Session Bar */
.session-bar {
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  padding: 16px 24px;
}

.session-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.session-input {
  display: flex;
  gap: 8px;
  flex: 1;
  max-width: 500px;
}

.session-input input {
  flex: 1;
}

.session-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background-color: var(--bg-tertiary);
  border-radius: var(--radius-md);
}

.generation-mode-bar {
  margin-top: 12px;
  padding: 12px;
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.generation-mode-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mode-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.mode-toggle-group {
  display: inline-flex;
  gap: 8px;
  background-color: var(--bg-tertiary);
  padding: 4px;
  border-radius: 999px;
}

.mode-toggle {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  padding: 8px 14px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.mode-toggle.active {
  background-color: var(--accent-blue);
  color: white;
}

.session-id {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-id code {
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--accent-blue);
  background-color: var(--bg-primary);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}

.session-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-badge {
  font-size: 12px;
  font-weight: 500;
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
}

.step-indicator {
  font-size: 12px;
  color: var(--text-muted);
}

/* Main Content */
.app-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  text-align: center;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 24px;
}

.empty-state h2 {
  font-size: 24px;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.empty-state p {
  color: var(--text-secondary);
}

/* API Log Sidebar */
.api-log-sidebar {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  background-color: var(--bg-secondary);
  border-left: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}

.log-header h3 {
  font-size: 16px;
  font-weight: 600;
}

.log-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.log-item {
  background-color: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  padding: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}

.log-item.log-error {
  border-left: 3px solid var(--accent-red);
}

.log-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.log-method {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
}

.log-method.get { background-color: var(--accent-green); color: white; }
.log-method.post { background-color: var(--accent-blue); color: white; }
.log-method.put { background-color: var(--accent-yellow); color: black; }
.log-method.delete { background-color: var(--accent-red); color: white; }

.log-path {
  flex: 1;
  color: var(--text-primary);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-status {
  font-weight: 600;
}

.log-status.success { color: var(--accent-green); }
.log-status.error { color: var(--accent-red); }

.log-duration {
  color: var(--text-muted);
}

.log-details {
  margin-top: 8px;
}

.log-details pre {
  background-color: var(--bg-primary);
  padding: 8px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-size: 11px;
}

.log-details pre.error {
  color: var(--accent-red);
}

.log-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 24px;
}

/* Global Error */
.global-error {
  position: fixed;
  top: 80px;
  right: 24px;
  background-color: var(--bg-tertiary);
  border: 1px solid var(--accent-red);
  border-radius: var(--radius-md);
  padding: 16px;
  box-shadow: var(--shadow-lg);
  cursor: pointer;
  z-index: 200;
  animation: fadeIn 0.3s ease-out;
}

.error-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.error-icon {
  font-size: 24px;
}

.error-message {
  flex: 1;
}

.error-message strong {
  color: var(--accent-red);
  display: block;
  margin-bottom: 4px;
}

.error-message p {
  font-size: 14px;
  color: var(--text-secondary);
}

.btn-close {
  color: var(--text-muted);
  font-size: 18px;
}

/* Buttons */
.btn-primary {
  background-color: var(--accent-blue);
  color: white;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  transition: background-color 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  transition: background-color 0.2s;
}

.btn-secondary:hover {
  background-color: var(--bg-hover);
}

.btn-ghost {
  color: var(--text-secondary);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  transition: background-color 0.2s;
}

.btn-ghost:hover {
  background-color: var(--bg-tertiary);
}

.btn-icon {
  color: var(--text-muted);
  padding: 4px;
  font-size: 16px;
}

.btn-icon:hover {
  color: var(--text-primary);
}

/* Spinner */
.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 8px;
}

/* Label */
.label {
  font-size: 12px;
  color: var(--text-muted);
  margin-right: 8px;
}

@media (max-width: 960px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  .overview-hero,
  .panel-card {
    grid-column: span 1;
  }
}
</style>
