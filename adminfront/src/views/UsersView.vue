<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">Users</span>
        <h3>用户、额度与订单运营</h3>
      </div>
      <div class="toolbar-actions">
        <input v-model="filters.q" class="compact-input" placeholder="搜索邮箱 / 名称 / user_id" @keyup.enter="loadUsers" />
        <button class="ghost-button" @click="loadUsers">搜索</button>
      </div>
    </div>

    <div class="workspace-grid">
      <article class="surface-card">
        <div class="surface-card__header">
          <h4>用户列表</h4>
          <span>{{ users.total || 0 }} users</span>
        </div>
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>额度</th>
                <th>会话</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in users.items || []" :key="item.user_id" :class="{ active: selectedUserId === item.user_id }" @click="openUser(item.user_id)">
                <td>
                  <strong>{{ item.display_name || item.email }}</strong>
                  <small>{{ item.email }}</small>
                </td>
                <td>{{ item.wallet_balance }}</td>
                <td>{{ item.session_count }}</td>
                <td><span class="status-chip">{{ item.status }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="surface-card" v-if="detail.user">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">User Detail</span>
            <h4>{{ detail.user.display_name || detail.user.email }}</h4>
          </div>
          <span>{{ detail.user.user_id }}</span>
        </div>

        <div class="metric-grid metric-grid--compact">
          <article class="metric-card">
            <span class="metric-card__label">钱包余额</span>
            <strong class="metric-card__value">{{ detail.wallet?.balance ?? 0 }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">Session 数</span>
            <strong class="metric-card__value">{{ detail.stats?.session_count ?? 0 }}</strong>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">Asset 数</span>
            <strong class="metric-card__value">{{ detail.stats?.asset_count ?? 0 }}</strong>
          </article>
        </div>

        <div class="panel-grid">
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>额度调整</h4>
            </div>
            <form class="form-grid" @submit.prevent="submitWalletAdjust">
              <label class="field">
                <span>变更额度</span>
                <input v-model.number="walletForm.credits_delta" type="number" />
              </label>
              <label class="field">
                <span>业务备注</span>
                <input v-model="walletForm.note" placeholder="例如：人工补偿" />
              </label>
              <label class="field">
                <span>操作备注</span>
                <textarea v-model="walletForm.operator_note" rows="3" placeholder="说明为什么要改生产额度" />
              </label>
              <button class="primary-button">提交额度调整</button>
            </form>
          </div>

          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>手工补单</h4>
            </div>
            <form class="form-grid" @submit.prevent="submitOrder">
              <label class="field">
                <span>方案名称</span>
                <input v-model="orderForm.plan_name" />
              </label>
              <label class="field">
                <span>入账额度</span>
                <input v-model.number="orderForm.credits_delta" type="number" />
              </label>
              <label class="field">
                <span>金额</span>
                <input v-model.number="orderForm.amount" type="number" />
              </label>
              <label class="field">
                <span>操作备注</span>
                <textarea v-model="orderForm.operator_note" rows="3" placeholder="说明补单原因" />
              </label>
              <button class="primary-button">创建补单</button>
            </form>
          </div>
        </div>

        <div class="panel-grid">
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>最近订单</h4>
            </div>
            <div class="stack-list">
              <div v-for="item in detail.recent_orders || []" :key="item.order_id" class="stack-list__item">
                <div>
                  <strong>{{ item.plan_name }}</strong>
                  <small>{{ item.order_no }}</small>
                </div>
                <div class="align-right">
                  <span class="status-chip">{{ item.status }}</span>
                  <small>+{{ item.credits_delta }}</small>
                </div>
              </div>
            </div>
          </div>
          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>额度流水</h4>
            </div>
            <div class="stack-list">
              <div v-for="item in detail.recent_transactions || []" :key="item.transaction_id" class="stack-list__item">
                <div>
                  <strong>{{ item.source || item.transaction_type }}</strong>
                  <small>{{ item.note || '-' }}</small>
                </div>
                <div class="align-right">
                  <span :class="item.credits_delta >= 0 ? 'status-chip status-chip--success' : 'status-chip status-chip--danger'">
                    {{ item.credits_delta >= 0 ? '+' : '' }}{{ item.credits_delta }}
                  </span>
                  <small>余额 {{ item.balance_after }}</small>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="surface-pane">
          <div class="surface-card__header">
            <h4>用户通知</h4>
            <span>未读 {{ notifications.unread_count || 0 }}</span>
          </div>
          <div class="stack-list">
            <div v-for="item in notifications.items || []" :key="item.notification_id" class="stack-list__item">
              <div>
                <strong>{{ item.title }}</strong>
                <small>{{ item.category }}</small>
              </div>
              <div class="align-right">
                <span class="status-chip">{{ item.is_read ? '已读' : '未读' }}</span>
                <small>{{ item.created_at }}</small>
              </div>
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
import { useConfirmAction } from '../lib/useConfirmAction'

const filters = reactive({ q: '' })
const users = ref({ items: [], total: 0 })
const selectedUserId = ref('')
const detail = ref({})
const notifications = ref({ items: [], unread_count: 0 })
const walletForm = reactive({ credits_delta: 0, note: '', operator_note: '' })
const orderForm = reactive({ plan_name: 'Manual Grant', credits_delta: 10, amount: 0, operator_note: '' })
const { dialog, requestConfirm, cancelConfirm, confirmAction } = useConfirmAction()

async function loadUsers() {
  users.value = await adminApi.listUsers({ q: filters.q, page_size: 50 })
  if (!selectedUserId.value && users.value.items?.length) {
    openUser(users.value.items[0].user_id)
  }
}

async function openUser(userId) {
  selectedUserId.value = userId
  detail.value = await adminApi.getUser(userId)
  notifications.value = await adminApi.listUserNotifications(userId, { page_size: 20 })
}

async function submitWalletAdjust() {
  if (!selectedUserId.value || !walletForm.operator_note.trim()) {
    return
  }
  requestConfirm({
    title: '确认调整用户额度',
    message: `即将对用户 ${selectedUserId.value} 调整 ${walletForm.credits_delta} 点额度，并写入审计日志。`,
    confirmText: '确认调整',
    onConfirm: async () => {
      await adminApi.adjustUserWallet(selectedUserId.value, { ...walletForm })
      await openUser(selectedUserId.value)
      walletForm.credits_delta = 0
      walletForm.note = ''
      walletForm.operator_note = ''
    },
  })
}

async function submitOrder() {
  if (!selectedUserId.value || !orderForm.operator_note.trim()) {
    return
  }
  requestConfirm({
    title: '确认创建手工补单',
    message: `即将为用户 ${selectedUserId.value} 创建补单并入账 ${orderForm.credits_delta} 点额度。`,
    confirmText: '确认补单',
    onConfirm: async () => {
      await adminApi.createUserOrder(selectedUserId.value, { ...orderForm, currency: 'CNY', source: 'manual_grant', status: 'paid' })
      await openUser(selectedUserId.value)
      orderForm.plan_name = 'Manual Grant'
      orderForm.credits_delta = 10
      orderForm.amount = 0
      orderForm.operator_note = ''
    },
  })
}

onMounted(loadUsers)
</script>
