<template>
  <div class="page-stack">
    <div class="page-toolbar">
      <div>
        <h3>平台策略体系</h3>
        <p class="page-desc">管理各电商平台的生图约束与文案策略，配置会直接影响所有该平台下的图片生成结果。</p>
      </div>
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
              <small>文字限制: {{ HERO_TEXT_LABELS[c.hero_text_overlay] || c.hero_text_overlay }}</small><br />
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
            <td colspan="8" class="align-center"><small>暂无平台配置，系统将在首次加载时自动初始化预设配置</small></td>
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

          <!-- Basic info section -->
          <div class="form-section-title">基本信息</div>
          <div class="field">
            <span>平台 ID (系统标识) *</span>
            <small class="field-hint">系统内部标识，创建后不可修改。如 amazon、1688</small>
            <input v-model="form.platform_id" type="text" :disabled="isEdit" placeholder="如 amazon, 1688" />
          </div>
          <div class="field">
            <span>显示名称 *</span>
            <small class="field-hint">管理面板中的显示名称</small>
            <input v-model="form.name" type="text" placeholder="如 亚马逊美国站, 阿里1688" />
          </div>
          <div class="panel-grid">
            <div class="field">
              <span>Locale (语区)</span>
              <small class="field-hint">语区标识，影响文案规则适配</small>
              <input v-model="form.locale" type="text" placeholder="zh-CN 或 en-US" />
            </div>
            <div class="field">
              <span>文案语言</span>
              <small class="field-hint">图片上文案使用的语言，zh=中文 en=英文</small>
              <input v-model="form.copy_language" type="text" placeholder="zh 或 en" />
            </div>
            <div class="field">
              <span>默认生成张数</span>
              <small class="field-hint">每次生成的主图数量</small>
              <input v-model.number="form.default_image_count" type="number" />
            </div>
            <div class="field">
              <span>默认宽高比</span>
              <small class="field-hint">生成图片的宽高比</small>
              <input v-model="form.default_aspect_ratio" type="text" placeholder="1:1" />
            </div>
          </div>

          <!-- Hero & subject constraints -->
          <div class="surface-card" style="padding: 16px; margin: 8px 0;">
            <div class="form-section-title" style="margin-top: 0;">首图及主体约束</div>
            <small class="field-hint" style="display: block; margin-bottom: 12px;">控制生成图片的文字策略、白底要求和元素许可</small>
            <div class="panel-grid">
              <div class="field">
                <span>首图文字策略</span>
                <small class="field-hint">控制首图上是否允许出现文字</small>
                <select v-model="form.hero_text_overlay">
                  <option value="forbidden">禁止出现 — 如 Amazon 要求纯产品图</option>
                  <option value="minimal">极少点缀 — 仅允许少量短文案</option>
                  <option value="allowed">常规允许 — 可正常添加标题文案</option>
                  <option value="dense">密集展示 — 适合1688等信息密集平台</option>
                </select>
              </div>
              <div class="field">
                <span style="display:flex; align-items:center; gap:8px;">
                  <input v-model="form.white_bg_mandatory" type="checkbox" style="width: auto;" /> 强制首图白底
                </span>
                <small class="field-hint">开启后首图必须通过白底验证（Amazon、TEMU 等平台要求）</small>
              </div>
              <div class="field">
                <span style="display:flex; align-items:center; gap:8px;">
                  <input v-model="form.allow_dense_copy" type="checkbox" style="width: auto;" /> 允许密集文案
                </span>
                <small class="field-hint">适用于 1688、淘宝等需要较多文案信息的国内平台</small>
              </div>
              <div class="field">
                <span style="display:flex; align-items:center; gap:8px;">
                  <input v-model="form.allow_certificate_elements" type="checkbox" style="width: auto;" /> 允许证书/背书元素
                </span>
                <small class="field-hint">允许在图中展示认证、资质等佐证信息</small>
              </div>
              <div class="field">
                <span style="display:flex; align-items:center; gap:8px;">
                  <input v-model="form.allow_compare_overlay" type="checkbox" style="width: auto;" /> 允许对比覆层
                </span>
                <small class="field-hint">允许生成对比图（如 before/after 或竞品对比）</small>
              </div>
            </div>
          </div>

          <!-- Generation constraints -->
          <div class="form-section-title">生成约束规则</div>
          <div class="field">
            <span>禁止生成的元素</span>
            <small class="field-hint">生成时绝对不允许出现的元素，每行填写一项</small>
            <textarea v-model="formExt.prohibited" rows="3" placeholder="如 price_tags&#10;watermarks&#10;promotional_stickers"></textarea>
          </div>
          <div class="field">
            <span>追加的 Negative Prompt</span>
            <small class="field-hint">附加到每个槽位的负面约束指令，每行填写一项</small>
            <textarea v-model="formExt.negatives" rows="3" placeholder="如 Do not add any text on the main image&#10;不要生成牛皮癣式密集促销贴纸"></textarea>
          </div>
          <div class="field">
            <span>平台强制约束规则</span>
            <small class="field-hint">所有槽位共享的平台级生成规则，每行填写一项</small>
            <textarea v-model="formExt.constraints" rows="3" placeholder="如 文案应保持短句，避免信息卡海报化&#10;优先保证商品保真"></textarea>
          </div>

          <!-- Status & notes -->
          <div class="form-section-title">状态与备注</div>
          <div class="field">
            <span style="display:flex; align-items:center; gap:8px;">
              <input v-model="form.is_active" type="checkbox" style="width: auto;" /> 启用该配置
            </span>
            <small class="field-hint">停用后该平台将回退使用系统默认规则</small>
          </div>
          <div class="field">
            <span>修改备注 *</span>
            <small class="field-hint">记录本次修改原因，便于审计追踪</small>
            <input v-model="form.operator_note" type="text" placeholder="如：根据平台新规调整文字策略" />
          </div>
        </div>
        <div v-if="error" class="error-banner">{{ error }}</div>
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

const HERO_TEXT_LABELS = {
  forbidden: '禁止文字',
  minimal: '极少点缀',
  allowed: '常规允许',
  dense: '密集展示',
}

const ERROR_ZH = {
  duplicate_platform_config: '该平台 ID 已存在配置，请使用编辑功能修改',
  platform_config_not_found: '未找到该平台配置，可能已被删除',
  invalid_request: '请求参数有误，请检查表单内容',
}

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
    alert('加载平台配置失败，请刷新重试')
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
  error.value = ''

  // Frontend validation
  if (!isEdit.value && !form.value.platform_id.trim()) {
    error.value = '请填写平台 ID'
    return
  }
  if (!form.value.name.trim()) {
    error.value = '请填写显示名称'
    return
  }
  if (!form.value.operator_note?.trim()) {
    error.value = '请填写修改备注，用于审计追踪'
    return
  }

  saving.value = true

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
    const key = err?.payload?.key || err?.data?.key || ''
    error.value = ERROR_ZH[key] || err.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchConfigs()
})
</script>

<style scoped>
.page-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-muted, #888);
  font-weight: normal;
}
.field-hint {
  display: block;
  font-size: 11px;
  color: var(--text-muted, #888);
  margin: 2px 0 4px;
  line-height: 1.4;
}
.form-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent, #a78bfa);
  margin: 16px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
}
.error-banner {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.12);
  color: var(--danger, #ef4444);
  font-size: 13px;
  border: 1px solid rgba(239, 68, 68, 0.25);
}
</style>
