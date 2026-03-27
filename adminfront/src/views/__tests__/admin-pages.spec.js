import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import JobsView from '../JobsView.vue'
import CategoryCatalogView from '../CategoryCatalogView.vue'
import OverviewView from '../OverviewView.vue'
import PromptsView from '../PromptsView.vue'
import RulePacksView from '../RulePacksView.vue'
import SessionsView from '../SessionsView.vue'
import SystemView from '../SystemView.vue'
import AuditView from '../AuditView.vue'

const adminApiMock = vi.hoisted(() => ({
  dashboardOverview: vi.fn(),
  dashboardTrends: vi.fn(),
  listSessions: vi.fn(),
  getSession: vi.fn(),
  getSessionResults: vi.fn(),
  getSessionDetailResults: vi.fn(),
  previewSessionPrompts: vi.fn(),
  previewDetailPrompts: vi.fn(),
  listJobs: vi.fn(),
  getJob: vi.fn(),
  getJobEvents: vi.fn(),
  listPromptPresets: vi.fn(),
  getPromptPreset: vi.fn(),
  listCategoryCatalog: vi.fn(),
  getCategoryCatalog: vi.fn(),
  createCategoryCatalog: vi.fn(),
  updateCategoryCatalog: vi.fn(),
  archiveCategoryCatalog: vi.fn(),
  restoreCategoryCatalog: vi.fn(),
  listRulePacks: vi.fn(),
  getRulePack: vi.fn(),
  listAuditLogs: vi.fn(),
  getSystemRuntime: vi.fn(),
}))

vi.mock('../../api', () => ({
  adminApi: adminApiMock,
}))

const globalConfig = {
  global: {
    stubs: {
      ConfirmDialog: { template: '<div class="confirm-dialog-stub" />' },
      JsonEditor: { template: '<div class="json-editor-stub" />' },
      TrendChart: { template: '<div class="trend-chart-stub" />' },
    },
  },
}

function mockDefaultResponses() {
  adminApiMock.dashboardOverview.mockResolvedValue({
    runtime_cards: [{ key: 'jobs_24h', label: '24h 任务量', value: 12 }],
    ops_cards: [{ key: 'queue_backlog', label: '队列积压', value: 1 }],
    config_cards: [{ key: 'total_sessions', label: '总 Session', value: 3 }],
    recent_failed_jobs: [],
    recent_high_risk_actions: [],
  })
  adminApiMock.dashboardTrends.mockResolvedValue({
    points: [{ bucket: '2026-03-27', jobs_total: 12, jobs_failed: 1, assets_ready: 20 }],
  })

  adminApiMock.listSessions.mockResolvedValue({
    items: [{ session_id: 'sess_1', service_id: 'default', active_platform_id: 'taobao', status: 'ready' }],
    total: 1,
  })
  adminApiMock.getSession.mockResolvedValue({
    session: {
      session_id: 'sess_1',
      status: 'ready',
      current_step: 6,
      latest_result_version: 1,
      detail_latest_result_version: 1,
      active_platform_id: 'taobao',
      confirmed_copy: {
        product_name: 'Demo Product',
        category: 'generic',
        hero_scene: 'desk',
        style_preset_id: '',
        style_custom: '',
        core_selling_points: ['point a'],
        product_advantages: ['advantage a'],
        key_parameters: [],
      },
      parameter_snapshot: {},
      strategy_preview: { overrides: [] },
      detail_strategy_preview: { overrides: [] },
    },
    recent_jobs: [],
    recent_assets: [],
  })
  adminApiMock.getSessionResults.mockResolvedValue({ assets: [] })
  adminApiMock.getSessionDetailResults.mockResolvedValue({ panels: [] })
  adminApiMock.previewSessionPrompts.mockResolvedValue({ prompts: [] })
  adminApiMock.previewDetailPrompts.mockResolvedValue({ prompts: [] })

  adminApiMock.listJobs.mockResolvedValue({
    items: [{ job_id: 'job_1', job_type: 'analysis', status: 'failed', progress: 100 }],
    total: 1,
  })
  adminApiMock.getJob.mockResolvedValue({
    job_id: 'job_1',
    job_type: 'analysis',
    status: 'failed',
    progress: 100,
    error_code: 'upstream_error',
    input_payload: { hello: 'world' },
    result_payload: {},
  })
  adminApiMock.getJobEvents.mockResolvedValue({ items: [], total: 0 })

  adminApiMock.listPromptPresets.mockResolvedValue({
    items: [{ preset_id: 'preset_1', name: 'Prompt A', preset_type: 'style', asset_family: 'main_gallery', version_no: 1 }],
    total: 1,
  })
  adminApiMock.getPromptPreset.mockResolvedValue({
    preset_id: 'preset_1',
    name: 'Prompt A',
    preset_type: 'style',
    asset_family: 'main_gallery',
    platform_id: '',
    slot_family: '',
    category: 'generic',
    locale: 'zh-CN',
    style_summary: 'clean',
    default_expression_mode: '',
    tags: [],
    copy_blocks_template: {},
    raw_prompt_template: 'prompt',
  })

  adminApiMock.listCategoryCatalog.mockResolvedValue({
    items: [
      {
        category_id: 'cat_1',
        name: '空气净化器',
        slug: 'air_purifier',
        sort_order: 10,
        aliases: ['净化器', '空气清新机'],
        sample_keywords: ['HEPA', 'CADR'],
        notes: '空气治理类核心品类',
        is_featured: true,
        is_system: true,
        is_active: true,
        created_by: null,
      },
      {
        category_id: 'cat_2',
        name: '宠物粮',
        slug: 'pet_food',
        sort_order: 600,
        aliases: ['猫粮', '狗粮'],
        sample_keywords: ['冻干', '成犬粮'],
        notes: '宠物食品',
        is_featured: true,
        is_system: false,
        is_active: false,
        created_by: 'admin',
      },
    ],
    total: 2,
  })
  adminApiMock.getCategoryCatalog.mockImplementation(async (id) => {
    if (id === 'cat_2') {
      return {
        category_id: 'cat_2',
        name: '宠物粮',
        slug: 'pet_food',
        sort_order: 600,
        aliases: ['猫粮', '狗粮'],
        sample_keywords: ['冻干', '成犬粮'],
        notes: '宠物食品',
        is_featured: true,
        is_system: false,
        is_active: false,
        created_by: 'admin',
      }
    }
    if (id === 'cat_3') {
      return {
        category_id: 'cat_3',
        name: '加湿器',
        slug: 'humidifier',
        sort_order: 20,
        aliases: ['空气加湿器'],
        sample_keywords: ['雾化', '恒湿'],
        notes: '新增测试品类',
        is_featured: true,
        is_system: false,
        is_active: true,
        created_by: 'admin',
      }
    }
    return {
      category_id: 'cat_1',
      name: '空气净化器',
      slug: 'air_purifier',
      sort_order: 10,
      aliases: ['净化器', '空气清新机'],
      sample_keywords: ['HEPA', 'CADR'],
      notes: '空气治理类核心品类',
      is_featured: true,
      is_system: true,
      is_active: true,
      created_by: null,
    }
  })
  adminApiMock.createCategoryCatalog.mockResolvedValue({
    category: {
      category_id: 'cat_3',
      name: '加湿器',
      slug: 'humidifier',
      sort_order: 20,
      aliases: ['空气加湿器'],
      sample_keywords: ['雾化', '恒湿'],
      notes: '新增测试品类',
      is_featured: true,
      is_system: false,
      is_active: true,
      created_by: 'admin',
    },
  })
  adminApiMock.updateCategoryCatalog.mockResolvedValue({
    category: {
      category_id: 'cat_1',
      name: '空气净化器',
      slug: 'air_purifier',
      sort_order: 10,
      aliases: ['净化器', '空气清新机'],
      sample_keywords: ['HEPA', 'CADR', '除甲醛'],
      notes: '空气治理类核心品类',
      is_featured: true,
      is_system: true,
      is_active: true,
      created_by: null,
    },
  })
  adminApiMock.archiveCategoryCatalog.mockResolvedValue({
    category: {
      category_id: 'cat_2',
      name: '宠物粮',
      slug: 'pet_food',
      sort_order: 600,
      aliases: ['猫粮', '狗粮'],
      sample_keywords: ['冻干', '成犬粮'],
      notes: '宠物食品',
      is_featured: true,
      is_system: false,
      is_active: false,
      created_by: 'admin',
    },
  })
  adminApiMock.restoreCategoryCatalog.mockResolvedValue({
    category: {
      category_id: 'cat_2',
      name: '宠物粮',
      slug: 'pet_food',
      sort_order: 600,
      aliases: ['猫粮', '狗粮'],
      sample_keywords: ['冻干', '成犬粮'],
      notes: '宠物食品',
      is_featured: true,
      is_system: false,
      is_active: true,
      created_by: 'admin',
    },
  })

  adminApiMock.listRulePacks.mockResolvedValue({
    items: [{ rule_pack_id: 'rule_1', name: 'Alibaba', rule_pack_key: 'alibaba_core_5_slot', asset_family: 'main_gallery', current_version_no: 1 }],
    total: 1,
  })
  adminApiMock.getRulePack.mockResolvedValue({
    rule_pack: {
      rule_pack_id: 'rule_1',
      name: 'Alibaba',
      asset_family: 'main_gallery',
      platform_id: 'taobao',
      rule_pack_key: 'alibaba_core_5_slot',
      version: { config_snapshot: { slots: [] } },
    },
    versions: [{ version_id: 'v1', version_no: 1, is_published: true, created_at: '2026-03-23T00:00:00Z', config_snapshot: { slots: [] } }],
  })

  adminApiMock.listAuditLogs.mockResolvedValue({
    items: [
      {
        audit_log_id: 'audit_1',
        action: 'retry_job',
        module: 'jobs',
        risk_level: 'high',
        target_type: 'job',
        target_id: 'job_1',
        operator_note: 'manual replay',
        created_at: '2026-03-27T00:00:00Z',
        before_snapshot: {},
        after_snapshot: {},
      },
    ],
    total: 1,
  })
  adminApiMock.getSystemRuntime.mockResolvedValue({
    app_env: 'dev',
    public_base_url: 'http://127.0.0.1:8000',
    storage_backend: 'local',
    s3_bucket: '',
    redis_url: 'redis://localhost:6379/0',
    queue_stats: [{ queue_name: 'q.analysis', depth: 0 }],
  })
}

describe('adminfront key routes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockDefaultResponses()
  })

  it('renders Overview view with image-ops cards', async () => {
    const wrapper = mount(OverviewView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('运行与产出总览')
    expect(wrapper.text()).toContain('当前关注点')
    expect(adminApiMock.dashboardOverview).toHaveBeenCalled()
  })

  it('renders Sessions view with preview and action workspace', async () => {
    const wrapper = mount(SessionsView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('Session 干预与结果追踪')
    expect(wrapper.text()).toContain('动作工作台')
    expect(adminApiMock.getSession).toHaveBeenCalled()
  })

  it('renders Jobs view with history panel', async () => {
    const wrapper = mount(JobsView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('任务排障与事件时间线')
    expect(wrapper.text()).toContain('事件时间线')
    expect(adminApiMock.getJobEvents).toHaveBeenCalled()
  })

  it('renders Prompts view with editor and sample preview', async () => {
    const wrapper = mount(PromptsView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('Prompt Preset 控制台')
    expect(wrapper.text()).toContain('Sample Session Prompt Preview')
    expect(adminApiMock.getPromptPreset).toHaveBeenCalled()
  })

  it('renders Category Catalog view and supports create/update workflow', async () => {
    const wrapper = mount(CategoryCatalogView, {
      global: {
        stubs: {
          ConfirmDialog: {
            props: ['open', 'confirmText'],
            template: '<div v-if="open" class="confirm-dialog-stub"><button class="confirm-button" @click="$emit(\'confirm\')">{{ confirmText }}</button></div>',
          },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('全局品类库')
    expect(wrapper.text()).toContain('空气净化器')
    expect(adminApiMock.listCategoryCatalog).toHaveBeenCalled()

    await wrapper.find('[data-test="category-new"]').trigger('click')
    await wrapper.find('.field input').setValue('加湿器')
    const inputs = wrapper.findAll('.field input')
    await inputs[1].setValue('humidifier')
    await inputs[2].setValue('20')
    const textareas = wrapper.findAll('.field textarea')
    await textareas[0].setValue('空气加湿器')
    await textareas[1].setValue('雾化\n恒湿')
    await textareas[2].setValue('新增测试品类')
    await textareas[3].setValue('add category')
    await wrapper.find('[data-test="category-save"]').trigger('click')
    await wrapper.find('.confirm-button').trigger('click')
    await flushPromises()

    expect(adminApiMock.createCategoryCatalog).toHaveBeenCalled()
    expect(adminApiMock.getCategoryCatalog).toHaveBeenCalledWith('cat_3')
  })

  it('renders Category Catalog view and supports archive/restore workflow', async () => {
    const catalogState = [
      {
        category_id: 'cat_1',
        name: '空气净化器',
        slug: 'air_purifier',
        sort_order: 10,
        aliases: ['净化器', '空气清新机'],
        sample_keywords: ['HEPA', 'CADR'],
        notes: '空气治理类核心品类',
        is_featured: true,
        is_system: true,
        is_active: true,
        created_by: null,
      },
      {
        category_id: 'cat_2',
        name: '宠物粮',
        slug: 'pet_food',
        sort_order: 600,
        aliases: ['猫粮', '狗粮'],
        sample_keywords: ['冻干', '成犬粮'],
        notes: '宠物食品',
        is_featured: true,
        is_system: false,
        is_active: true,
        created_by: 'admin',
      },
    ]
    adminApiMock.listCategoryCatalog.mockImplementation(async () => ({
      items: catalogState.map((item) => ({ ...item })),
      total: catalogState.length,
    }))
    adminApiMock.getCategoryCatalog.mockImplementation(async (id) => {
      const item = catalogState.find((entry) => entry.category_id === id)
      return item ? { ...item } : null
    })
    adminApiMock.archiveCategoryCatalog.mockImplementation(async (id) => {
      const item = catalogState.find((entry) => entry.category_id === id)
      if (item) {
        item.is_active = false
      }
      return { category: item ? { ...item } : null }
    })
    adminApiMock.restoreCategoryCatalog.mockImplementation(async (id) => {
      const item = catalogState.find((entry) => entry.category_id === id)
      if (item) {
        item.is_active = true
      }
      return { category: item ? { ...item } : null }
    })

    const wrapper = mount(CategoryCatalogView, {
      global: {
        stubs: {
          ConfirmDialog: {
            props: ['open', 'confirmText'],
            template: '<div v-if="open" class="confirm-dialog-stub"><button class="confirm-button" @click="$emit(\'confirm\')">{{ confirmText }}</button></div>',
          },
        },
      },
    })
    await flushPromises()

    await wrapper.findAll('tbody tr')[0].trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="category-archive"]').trigger('click')
    await wrapper.find('.confirm-button').trigger('click')
    await flushPromises()
    expect(adminApiMock.archiveCategoryCatalog).toHaveBeenCalled()

    await wrapper.find('[data-test="category-restore"]').trigger('click')
    await wrapper.find('.confirm-button').trigger('click')
    await flushPromises()
    expect(adminApiMock.restoreCategoryCatalog).toHaveBeenCalled()
  })

  it('renders Rule Packs view with version compare and sample strategy preview', async () => {
    const wrapper = mount(RulePacksView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('规则包草稿、版本与发布控制台')
    expect(wrapper.text()).toContain('版本对照')
    expect(adminApiMock.getRulePack).toHaveBeenCalled()
  })

  it('renders Audit view without user module filters', async () => {
    const wrapper = mount(AuditView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('高风险操作审计')
    expect(wrapper.text()).not.toContain('users')
    expect(adminApiMock.listAuditLogs).toHaveBeenCalled()
  })

  it('renders System view with runtime-only telemetry', async () => {
    const wrapper = mount(SystemView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('运行时与队列观测')
    expect(wrapper.text()).toContain('运行时配置')
    expect(adminApiMock.getSystemRuntime).toHaveBeenCalled()
  })
})
