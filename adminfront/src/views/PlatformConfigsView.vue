<template>
  <div class="page-stack">
    <div class="page-toolbar">
      <h3>平台策略体系</h3>
      <div class="toolbar-actions">
        <button class="ghost-button" @click="fetchConfigs">刷新</button>
        <button class="primary-button" @click="openCreate">创建配置</button>
      </div>
    </div>

    <div class="surface-pane table-shell">
      <table class="data-table">
        <thead>
          <tr>
            <th>状态</th>
            <th>平台 ID</th>
            <th>平台名称</th>
            <th>本地化</th>
            <th>主图规则</th>
            <th>默认张数</th>
            <th>最后更新</th>
            <th class="align-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in configs" :key="c.platform_id">
            <td>
              <span v-if="c.is_active" class="status-chip status-chip--success">已启用</span>
              <span v-else class="status-chip status-chip--danger">已停用</span>
            </td>
            <td><strong>{{ c.platform_id }}</strong></td>
            <td>{{ c.name }}</td>
            <td>
              <small>语区: {{ c.locale }}</small><br />
              <small>文案: {{ c.copy_language }}</small>
            </td>
            <td>
              <small>文字限制: {{ c.hero_text_overlay }}</small><br />
              <small>强制白底: {{ c.white_bg_mandatory ? '是' : '否' }}</small>
            </td>
            <td>{{ c.default_image_count }} (比例 {{ c.default_aspect_ratio }})</td>
            <td><small>{{ new Date(c.updated_at || c.created_at || Date.now()).toLocaleString() }}</small></td>
            <td class="align-right">
              <button class="ghost-button" @click="openEdit(c)">编辑</button>
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="8" class="align-center"><small>加载中...</small></td>
          </tr>
          <tr v-else-if="!configs.length">
            <td colspan="8" class="align-center"><small>暂无平台配置</small></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Edit/Create Dialog -->
    <div v-if="showModal" class="dialog-backdrop">
      <div class="dialog-card" style="max-height: 90vh; overflow-y: auto;">
        <div class="dialog-header">
          <h4>{{ isEdit ? '编辑平台配置' : '创建平台配置' }}</h4>
          <button class="icon-button" @click="closeModal">×</button>
        </div>
        <div class="form-grid" style="margin-top: 20px;">
          <div class="field">
            <span>平台 ID (系统标识)*</span>
            <input v-model="form.platform_id" type="text" :disabled="isEdit" placeholder="如 amazon, 1688" />
          </div>
          <div class="field">
            <span>显示名称*</span>
            <input v-model="form.name" type="text" placeholder="如 亚马逊美国站, 阿里1688" />
          </div>
          <div class="panel-grid">
            <div class="field">
              <span>Locale</span>
              <input v-model="form.locale" type="text" placeholder="en-US" />
            </div>
            <div class="field">
              <span>文案语言</span>
              <input v-model="form.copy_language" type="text" placeholder="en" />
            </div>
            <div class="field">
              <span>默认生成张数</span>
              <input v-model.number="form.default_image_count" type="number" />
            </div>
            <div class="field">
              <span>默认宽高比</span>
              <input v-model="form.default_aspect_ratio" type="text" placeholder="1:1" />
            </div>
          </div>
          
          <div class="surface-card" style="padding: 16px; margin: 8px 0;">
            <h5 style="margin: 0 0 12px; color: var(--accent);">首图及主体约束</h5>
            <div class="panel-grid">
              <div class="field">
                <span>首图文字策略 (hero_text_overlay)</span>
                <select v-model="form.hero_text_overlay">
                  <option value="forbidden">禁止出现 (forbidden)</option>
                  <option value="minimal">极少点缀 (minimal)</option>
                  <option value="allowed">常规允许 (allowed)</option>
                  <option value="dense">密集展示 (dense)</option>
                </select>
              </div>
              <div class="field">
                <span style="display:flex; align-items:center; gap:8px;">
                  <input v-model="form.white_bg_mandatory" type="checkbox" style="width: auto;" /> 强制首图白底
                </span>
              </div>
              <div class="field">
                <span style="display:flex; align-items:center; gap:8px;">
                  <input v-model="form.allow_dense_copy" type="checkbox" style="width: auto;" /> 允许密集文案
                </span>
              </div>
              <div class="field">
                <span style="display:flex; align-items:center; gap:8px;">
                  <input v-model="form.allow_certificate_elements" type="checkbox" style="width: auto;" /> 允许证书/背书元素
                </span>
              </div>
            </div>
          </div>

          <div class="field">
            <span>禁止生成的元素 (每行一项)</span>
            <textarea v-model="formExt.prohibited" rows="3" placeholder="如 price_tags, watermarks"></textarea>
          </div>
          <div class="field">
            <span>追加的 Negative Prompt (每行一项)</span>
            <textarea v-model="formExt.negatives" rows="3" placeholder="如 Do not add any text..."></textarea>
          </div>
          <div class="field">
            <span>平台强制约束条件规则 (每行一项)</span>
            <textarea v-model="formExt.constraints" rows="3"></textarea>
          </div>
          
          <div class="field">
            <span style="display:flex; align-items:center; gap:8px;">
              <input v-model="form.is_active" type="checkbox" style="width: auto;" /> 启用该配置
            </span>
          </div>
          <div class="field">
            <span>修改备注</span>
            <input v-model="form.operator_note" type="text" placeholder="记录本次修改的原因" />
          </div>
        </div>
        <div v-if="error" class="error-message" style="margin-top: 12px; color: var(--danger);">{{ error }}</div>
        <div class="dialog-actions">
          <button class="ghost-button" @click="closeModal" :disabled="saving">取消</button>
          <button class="primary-button" @click="saveConfig" :disabled="saving">
            {{ saving ? '保存中...' : '保存配置' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '../api'

const configs = ref([])
const loading = ref(false)
const showModal = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const error = ref('')

const defaultForm = () => ({
  platform_id: '', name: '', locale: 'zh-CN', copy_language: 'zh',
  hero_text_overlay: 'minimal', white_bg_mandatory: false,
  allow_dense_copy: false, allow_certificate_elements: false, allow_compare_overlay: false,
  default_image_count: 5, default_aspect_ratio: '1:1',
  is_active: true, operator_note: '', main_rule_pack_id: 'default_main_gallery_v2', detail_rule_pack_id: 'ecommerce_detail_v2'
})

const form = ref(defaultForm())
const formExt = ref({ prohibited: '', negatives: '', constraints: '' })

async function fetchConfigs() {
  loading.value = true
  try {
    const res = await adminApi.listPlatformConfigs({ include_inactive: true })
    configs.value = res.configs || []
  } catch (err) {
    alert('Failed to load platform configs')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  form.value = defaultForm()
  formExt.value = { prohibited: '', negatives: '', constraints: '' }
  error.value = ''
  showModal.value = true
}

function openEdit(cfg) {
  isEdit.value = true
  form.value = { ...cfg, operator_note: '' }
  formExt.value = {
    prohibited: (cfg.prohibited_elements || []).join('\n'),
    negatives: (cfg.negative_prompt_additions || []).join('\n'),
    constraints: (cfg.constraints || []).join('\n')
  }
  error.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
}

async function saveConfig() {
  saving.value = true
  error.value = ''
  
  const payload = {
    ...form.value,
    prohibited_elements: formExt.value.prohibited.split('\n').map(s => s.trim()).filter(Boolean),
    negative_prompt_additions: formExt.value.negatives.split('\n').map(s => s.trim()).filter(Boolean),
    constraints: formExt.value.constraints.split('\n').map(s => s.trim()).filter(Boolean)
  }

  try {
    if (isEdit.value) {
      await adminApi.updatePlatformConfig(form.value.platform_id, payload)
    } else {
      await adminApi.createPlatformConfig(payload)
    }
    closeModal()
    fetchConfigs()
  } catch (err) {
    error.value = err.message || 'Saving failed'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchConfigs()
})
</script>
