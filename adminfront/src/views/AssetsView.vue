<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">素材资产库</span>
        <h3>资产治理工作台</h3>
      </div>
      <div class="toolbar-actions">
        <input v-model="filters.session_id" class="compact-input" placeholder="session_id" />
        <select v-model="filters.asset_family" class="compact-input">
          <option value="">全部资产族</option>
          <option value="main_gallery">main_gallery</option>
          <option value="detail_page">detail_page</option>
        </select>
        <button class="ghost-button" @click="loadAssets">刷新</button>
      </div>
    </div>

    <div class="workspace-grid">
      <article class="surface-card">
        <div class="surface-card__header">
          <h4>资产列表</h4>
        </div>
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>资产</th>
                <th>版本</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in assets.items || []" :key="item.asset_id" :class="{ active: selectedAssetId === item.asset_id }" @click="openAsset(item.asset_id)">
                <td>
                  <strong>{{ item.role || item.asset_kind }}</strong>
                  <small>{{ item.asset_id }}</small>
                </td>
                <td>{{ item.version_no }}</td>
                <td><span class="status-chip">{{ item.visibility_status }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="surface-card" v-if="detail.asset">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">素材大图详情</span>
            <h4>{{ detail.asset.role || detail.asset.asset_kind }}</h4>
          </div>
        </div>
        <img v-if="detail.asset.image_url" :src="detail.asset.image_url" class="asset-preview" />
        <div class="metric-grid metric-grid--compact">
          <article class="metric-card">
            <span class="metric-card__label">状态</span>
            <strong class="metric-card__value">{{ detail.asset.visibility_status }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">版本</span>
            <strong class="metric-card__value">{{ detail.asset.version_no }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">Session</span>
            <strong class="metric-card__value">{{ detail.asset.session_id }}</strong>
          </article>
        </div>
        <label class="field">
          <span>操作备注</span>
          <textarea v-model="operatorNote" rows="3" placeholder="归档/恢复/重生成前必须填写" />
        </label>
        <div class="toolbar-actions">
          <button class="ghost-button" @click="archiveSelected">归档</button>
          <button class="ghost-button" @click="restoreSelected">恢复</button>
          <button class="primary-button" @click="regenerateSelected">重生成</button>
        </div>
        <div class="surface-pane">
          <h4>生成参数快照</h4>
          <pre>{{ prettyJson(detail.asset.generation_snapshot) }}</pre>
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

const filters = reactive({ session_id: '', asset_family: '' })
const assets = ref({ items: [] })
const detail = ref({})
const selectedAssetId = ref('')
const operatorNote = ref('')
const { dialog, requestConfirm, cancelConfirm, confirmAction } = useConfirmAction()

async function loadAssets() {
  assets.value = await adminApi.listAssets({ ...filters, page_size: 50 })
  if (!selectedAssetId.value && assets.value.items?.length) {
    openAsset(assets.value.items[0].asset_id)
  }
}

async function openAsset(assetId) {
  selectedAssetId.value = assetId
  detail.value = await adminApi.getAsset(assetId)
}

async function archiveSelected() {
  if (!selectedAssetId.value || !operatorNote.value.trim()) {
    return
  }
  requestConfirm({
    title: '确认归档资产',
    message: `归档后用户侧结果与下载会默认隐藏资产 ${selectedAssetId.value}。`,
    confirmText: '确认归档',
    onConfirm: async () => {
      await adminApi.archiveAsset(selectedAssetId.value, { operator_note: operatorNote.value, reason: operatorNote.value })
      await openAsset(selectedAssetId.value)
      await loadAssets()
    },
  })
}

async function restoreSelected() {
  if (!selectedAssetId.value || !operatorNote.value.trim()) {
    return
  }
  requestConfirm({
    title: '确认恢复资产',
    message: `即将恢复资产 ${selectedAssetId.value} 的用户可见性。`,
    confirmText: '确认恢复',
    onConfirm: async () => {
      await adminApi.restoreAsset(selectedAssetId.value, { operator_note: operatorNote.value, reason: operatorNote.value })
      await openAsset(selectedAssetId.value)
      await loadAssets()
    },
  })
}

async function regenerateSelected() {
  if (!selectedAssetId.value || !operatorNote.value.trim()) {
    return
  }
  requestConfirm({
    title: '确认重生成资产',
    message: `即将基于当前资产 ${selectedAssetId.value} 发起新的重生成任务。`,
    confirmText: '确认重生成',
    onConfirm: async () => {
      await adminApi.regenerateAsset(selectedAssetId.value, { operator_note: operatorNote.value, instruction: operatorNote.value })
      operatorNote.value = ''
    },
  })
}

onMounted(loadAssets)
</script>
