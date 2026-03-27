<template>
  <section class="page-stack">
    <div class="page-toolbar">
      <div>
        <span class="eyebrow">Category Catalog</span>
        <h3>全局品类库</h3>
      </div>
      <div class="toolbar-actions">
        <input v-model="filters.q" class="compact-input" placeholder="搜索品类 / slug / notes" />
        <label class="status-chip">
          <input v-model="filters.includeInactive" type="checkbox" @change="loadCategories" />
          <span style="margin-left: 8px;">包含停用项</span>
        </label>
        <button type="button" class="ghost-button" @click="loadCategories">刷新</button>
        <button type="button" class="primary-button" @click="startCreate">新建品类</button>
      </div>
    </div>

    <div class="metric-grid metric-grid--compact">
      <article class="metric-card">
        <span class="metric-card__label">启用品类</span>
        <strong class="metric-card__value">{{ summary.active }}</strong>
        <small>active</small>
      </article>
      <article class="metric-card">
        <span class="metric-card__label">重点推荐</span>
        <strong class="metric-card__value">{{ summary.featured }}</strong>
        <small>featured</small>
      </article>
      <article class="metric-card">
        <span class="metric-card__label">系统种子</span>
        <strong class="metric-card__value">{{ summary.system }}</strong>
        <small>system</small>
      </article>
    </div>

    <div class="workspace-grid">
      <article class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">Catalog List</span>
            <h4>品类列表</h4>
          </div>
          <span>{{ categories.total || categories.items?.length || 0 }}</span>
        </div>
        <div class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>品类</th>
                <th>排序</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in categories.items || []"
                :key="item.category_id"
                :class="{ active: selectedCategoryId === item.category_id }"
                @click="openCategory(item.category_id)"
              >
                <td>
                  <strong>{{ item.name }}</strong>
                  <small>{{ item.slug }}</small>
                </td>
                <td>{{ item.sort_order }}</td>
                <td>
                  <div class="stack-list__item--dense">
                    <span class="status-chip" :class="item.is_active ? 'status-chip--success' : 'status-chip--danger'">
                      {{ item.is_active ? 'active' : 'inactive' }}
                    </span>
                    <small>{{ item.is_featured ? 'featured' : 'normal' }} / {{ item.is_system ? 'system' : 'custom' }}</small>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="surface-card">
        <div class="surface-card__header">
          <div>
            <span class="eyebrow">Catalog Editor</span>
            <h4>{{ editor.name || '新建品类' }}</h4>
          </div>
          <span>{{ selectedCategoryId || 'draft' }}</span>
        </div>

        <div class="panel-grid panel-grid--wide">
          <form class="form-grid">
            <label class="field"><span>name</span><input v-model="editor.name" /></label>
            <label class="field"><span>slug</span><input v-model="editor.slug" :disabled="Boolean(selectedCategoryId && editor.is_system)" /></label>
            <label class="field"><span>sort_order</span><input v-model.number="editor.sort_order" type="number" min="1" max="9999" /></label>
            <label class="field"><span>aliases</span><textarea v-model="editor.aliases_text" rows="4" placeholder="每行一个别名" /></label>
            <label class="field"><span>sample_keywords</span><textarea v-model="editor.sample_keywords_text" rows="4" placeholder="每行一个关键词" /></label>
            <label class="field"><span>notes</span><textarea v-model="editor.notes" rows="4" placeholder="品类说明" /></label>
            <label class="field"><span>operator_note</span><textarea v-model="editor.operator_note" rows="3" placeholder="说明这次品类库变更目的" /></label>
          </form>

          <div class="surface-pane">
            <div class="surface-card__header">
              <h4>状态与动作</h4>
            </div>
            <div class="stack-list">
              <div class="stack-list__item stack-list__item--dense">
                <div>
                  <strong>可见状态</strong>
                  <small>{{ editor.is_active ? 'active' : 'inactive' }}</small>
                </div>
                <label class="status-chip">
                  <input v-model="editor.is_active" type="checkbox" :disabled="Boolean(selectedCategoryId && editor.is_system && editor.is_active)" />
                  <span style="margin-left: 8px;">启用</span>
                </label>
              </div>
              <div class="stack-list__item stack-list__item--dense">
                <div>
                  <strong>重点推荐</strong>
                  <small>{{ editor.is_featured ? 'featured' : 'normal' }}</small>
                </div>
                <label class="status-chip">
                  <input v-model="editor.is_featured" type="checkbox" />
                  <span style="margin-left: 8px;">featured</span>
                </label>
              </div>
              <div class="stack-list__item stack-list__item--dense">
                <div>
                  <strong>系统种子</strong>
                  <small>{{ editor.is_system ? 'system' : 'custom' }}</small>
                </div>
                <span class="status-chip">{{ editor.is_system ? 'system' : 'custom' }}</span>
              </div>
            </div>

            <div class="toolbar-actions" style="margin-top: 16px;">
              <button type="button" class="primary-button" data-test="category-save" @click="saveCategory">{{ selectedCategoryId ? '保存品类' : '创建品类' }}</button>
              <button type="button" class="ghost-button" data-test="category-archive" :disabled="!selectedCategoryId || !editor.is_active" @click="archiveCategory">归档</button>
              <button type="button" class="ghost-button" data-test="category-restore" :disabled="!selectedCategoryId || editor.is_active" @click="restoreCategory">恢复</button>
              <button type="button" class="ghost-button" data-test="category-new" @click="startCreate">新建</button>
            </div>

            <div class="surface-pane" style="margin-top: 18px;">
              <div class="surface-card__header">
                <h4>当前编辑摘要</h4>
              </div>
              <pre>{{ editorSummary }}</pre>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { adminApi } from '../api'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { multilineToList, prettyJson } from '../lib/format'
import { useConfirmAction } from '../lib/useConfirmAction'

const filters = reactive({
  q: '',
  includeInactive: false,
})

const categories = ref({ items: [], total: 0 })
const selectedCategoryId = ref('')
const editor = reactive({
  name: '',
  slug: '',
  sort_order: 100,
  aliases_text: '',
  sample_keywords_text: '',
  notes: '',
  is_featured: false,
  is_system: false,
  is_active: true,
  operator_note: '',
})
const { dialog, requestConfirm, cancelConfirm, confirmAction } = useConfirmAction()

const summary = computed(() => {
  const items = categories.value.items || []
  return {
    active: items.filter((item) => item.is_active).length,
    featured: items.filter((item) => item.is_featured).length,
    system: items.filter((item) => item.is_system).length,
  }
})

const editorSummary = computed(() =>
  prettyJson({
    category_id: selectedCategoryId.value || 'draft',
    name: editor.name,
    slug: editor.slug,
    sort_order: editor.sort_order,
    aliases: multilineToList(editor.aliases_text),
    sample_keywords: multilineToList(editor.sample_keywords_text),
    notes: editor.notes,
    is_featured: editor.is_featured,
    is_system: editor.is_system,
    is_active: editor.is_active,
  }),
)

function resetEditor() {
  editor.name = ''
  editor.slug = ''
  editor.sort_order = 100
  editor.aliases_text = ''
  editor.sample_keywords_text = ''
  editor.notes = ''
  editor.is_featured = false
  editor.is_system = false
  editor.is_active = true
  editor.operator_note = ''
}

function applyCategory(item) {
  selectedCategoryId.value = item.category_id
  editor.name = item.name || ''
  editor.slug = item.slug || ''
  editor.sort_order = Number(item.sort_order || 100)
  editor.aliases_text = (item.aliases || []).join('\n')
  editor.sample_keywords_text = (item.sample_keywords || []).join('\n')
  editor.notes = item.notes || ''
  editor.is_featured = Boolean(item.is_featured)
  editor.is_system = Boolean(item.is_system)
  editor.is_active = Boolean(item.is_active)
  editor.operator_note = ''
}

async function loadCategories() {
  categories.value = await adminApi.listCategoryCatalog({
    q: filters.q,
    include_inactive: filters.includeInactive,
    page_size: 100,
  })
  if (!selectedCategoryId.value && categories.value.items?.length) {
    applyCategory(categories.value.items[0])
  }
}

async function openCategory(categoryId) {
  selectedCategoryId.value = categoryId
  const data = await adminApi.getCategoryCatalog(categoryId)
  applyCategory(data)
}

function payload() {
  return {
    name: editor.name,
    slug: editor.slug,
    sort_order: Number(editor.sort_order || 100),
    aliases: multilineToList(editor.aliases_text),
    sample_keywords: multilineToList(editor.sample_keywords_text),
    notes: editor.notes || null,
    is_featured: Boolean(editor.is_featured),
    operator_note: editor.operator_note || null,
  }
}

function withDefaultOperatorNote(value) {
  return value || (selectedCategoryId.value ? 'update category catalog' : 'create category catalog')
}

async function saveCategory() {
  const currentPayload = payload()
  requestConfirm({
    title: selectedCategoryId.value ? '确认保存品类' : '确认创建品类',
    message: selectedCategoryId.value
      ? `即将保存品类 ${editor.name || selectedCategoryId.value}，并写入后台审计。`
      : '即将创建新的品类条目，并写入后台审计。',
    confirmText: selectedCategoryId.value ? '确认保存' : '确认创建',
    onConfirm: async () => {
      const submitPayload = { ...currentPayload, operator_note: withDefaultOperatorNote(currentPayload.operator_note) }
      if (selectedCategoryId.value) {
        await adminApi.updateCategoryCatalog(selectedCategoryId.value, submitPayload)
      } else {
        const created = await adminApi.createCategoryCatalog(submitPayload)
        selectedCategoryId.value = created.category.category_id
      }
      await loadCategories()
      if (selectedCategoryId.value) {
        await openCategory(selectedCategoryId.value)
      }
    },
  })
}

async function archiveCategory() {
  requestConfirm({
    title: '确认归档品类',
    message: `即将停用品类 ${editor.name || selectedCategoryId.value}。`,
    confirmText: '确认归档',
    onConfirm: async () => {
      await adminApi.archiveCategoryCatalog(selectedCategoryId.value, {
        operator_note: withDefaultOperatorNote(editor.operator_note || 'archive category'),
      })
      await loadCategories()
      await openCategory(selectedCategoryId.value)
    },
  })
}

async function restoreCategory() {
  requestConfirm({
    title: '确认恢复品类',
    message: `即将恢复品类 ${editor.name || selectedCategoryId.value}。`,
    confirmText: '确认恢复',
    onConfirm: async () => {
      await adminApi.restoreCategoryCatalog(selectedCategoryId.value, {
        operator_note: withDefaultOperatorNote(editor.operator_note || 'restore category'),
      })
      await loadCategories()
      await openCategory(selectedCategoryId.value)
    },
  })
}

function startCreate() {
  selectedCategoryId.value = ''
  resetEditor()
}

onMounted(loadCategories)
</script>
