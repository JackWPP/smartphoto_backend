import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import JobsView from '../JobsView.vue'
import PromptsView from '../PromptsView.vue'
import RulePacksView from '../RulePacksView.vue'
import SessionsView from '../SessionsView.vue'
import UsersView from '../UsersView.vue'

const adminApiMock = vi.hoisted(() => ({
  listUsers: vi.fn(),
  getUser: vi.fn(),
  listUserNotifications: vi.fn(),
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
  listRulePacks: vi.fn(),
  getRulePack: vi.fn(),
}))

vi.mock('../../api', () => ({
  adminApi: adminApiMock,
}))

const globalConfig = {
  global: {
    stubs: {
      ConfirmDialog: { template: '<div class="confirm-dialog-stub" />' },
      JsonEditor: { template: '<div class="json-editor-stub" />' },
    },
  },
}

function mockDefaultResponses() {
  adminApiMock.listUsers.mockResolvedValue({
    items: [{ user_id: 'user_1', email: 'user@example.com', display_name: 'User One', wallet_balance: 100, session_count: 2, status: 'active' }],
    total: 1,
  })
  adminApiMock.getUser.mockResolvedValue({
    user: { user_id: 'user_1', email: 'user@example.com', display_name: 'User One' },
    wallet: { balance: 100 },
    stats: { session_count: 2, asset_count: 5 },
    recent_orders: [],
    recent_transactions: [],
  })
  adminApiMock.listUserNotifications.mockResolvedValue({ items: [], unread_count: 0 })

  adminApiMock.listSessions.mockResolvedValue({
    items: [{ session_id: 'sess_1', user_id: 'user_1', active_platform_id: 'taobao', status: 'ready' }],
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
}

describe('adminfront key routes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockDefaultResponses()
  })

  it('renders Users view with operator controls', async () => {
    const wrapper = mount(UsersView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('用户、额度与订单运营')
    expect(wrapper.text()).toContain('额度调整')
    expect(adminApiMock.listUsers).toHaveBeenCalled()
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

  it('renders Rule Packs view with version compare and sample strategy preview', async () => {
    const wrapper = mount(RulePacksView, globalConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('规则包草稿、版本与发布控制台')
    expect(wrapper.text()).toContain('版本对照')
    expect(adminApiMock.getRulePack).toHaveBeenCalled()
  })
})
