# Guest First 前端联调说明

本文档给前端同学使用，目标是把当前后端已经落地的 `guest-first` 逻辑讲清楚，避免继续按旧的“guest 首轮受限 / 登录自动认领 / 结果后必须登录才能继续编辑”的假设接入。

真相源仍然是代码与现有接口：
- `app/api/v2/sessions.py`
- `app/api/v2/assets.py`
- `app/api/v2/auth.py`
- `app/api/v2/guest.py`

## 1. 当前业务结论

### 1.1 一句话版本
- 未登录用户可以作为 guest 在**当前 session 内持续创作**
- guest 可以真实完成上传、分析、参数、文案、主图生成、详情页生成、全局修改、整组重生成、单图重生成
- guest **不能下载**
- guest **不能查看 History / 账户资产列表**
- 登录或注册成功后，**不会自动认领**
- 如果前端希望把当前 session 纳入账号，必须显式调用：
  - `POST /api/v2/guest/sessions/{session_id}/claim`

### 1.2 和旧逻辑相比，最关键的变化
- 不再有“guest 只能首轮生成一次”的产品门禁
- 不再有“guest 3 次额度”的前端判断逻辑
- 不再有“登录成功后后端自动把当前浏览器全部 guest session 迁走”的逻辑
- 不再有“guest 出结果后必须登录才能继续编辑”的逻辑
- 只剩两个需要登录的方向：
  - 下载
  - 进入账号侧 History / `/api/v2/account/assets`

## 2. 前端必须遵守的总原则

### 2.1 已登录用户始终走 user 链路
- 如果前端当前已经拿到有效 Bearer token，就应该始终带 Authorization 调用 `/api/v2/sessions*`
- 这时创建出来的 session 属于 user
- 这类 session 会自然进入 History / 资产列表
- 不要为了“体验统一”故意让已登录用户先走 guest

### 2.2 未登录用户走 guest 链路
- 不带 Authorization
- 但必须带 `credentials: "include"`
- 后端会通过 HttpOnly guest cookie 识别当前浏览器 guest 身份
- 前端自己**拿不到 guest token**，也不需要拿

### 2.3 guest 的“继续当前 session”依赖两个东西
- 前端自己保存 `session_id`
- 浏览器保留后端下发的 guest cookie

缺任何一个都不能继续：
- 只剩 cookie，没有 `session_id`，前端没法知道该打开哪个 session
- 只剩 `session_id`，guest cookie 过期或丢失，请求会被视为别的 actor，直接 404

### 2.4 guest cookie 有效期是 24 小时
- 后端按 `first_seen_at + 24h` 做软失效
- 超时后：
  - guest 不能继续访问自己的 session
  - guest 也不能再 claim

## 3. 前端状态模型建议

前端至少维护这些状态：
- `currentSessionId`
- `isAuthenticated`
- `accessToken`
- `currentAuthMode`
  - `guest | user`
- `sessionSnapshot`
- `currentStep`
- `selectedPlatformIds`
- `activePlatformId`
- `latestResultVersion`
- `detailLatestResultVersion`

建议再额外维护这些派生状态：
- `canDownload`
- `canContinueEditing`
- `loginRequiredActions`
- `isSessionBoundToAccount`

其中：
- `isSessionBoundToAccount` 不要靠本地猜
- 最好用 `GET /api/v2/sessions/{session_id}` 返回的：
  - `auth_mode`
  - `can_download`
  - `login_required_actions`
来推导当前页面该怎么表现

## 4. 调用规则

### 4.1 guest 请求的统一要求
guest 模式下，以下请求都要带：

```ts
fetch(url, {
  method,
  credentials: "include",
})
```

注意：
- 不能漏 `credentials: "include"`
- 否则浏览器不会带 guest cookie
- 跨域场景下也一样

### 4.2 user 请求的统一要求
user 模式下带：

```ts
fetch(url, {
  method,
  headers: {
    Authorization: `Bearer ${accessToken}`,
  },
  credentials: "include",
})
```

这里仍建议保留 `credentials: "include"`，因为：
- 登录/刷新本身依赖 HttpOnly refresh cookie
- claim 也需要当前浏览器 guest cookie

### 4.3 最重要的坑：登录成功后不要立刻把当前 guest session 请求切成 Bearer
这是本轮最容易踩的坑。

原因：
- 后端 `get_request_actor` 的优先级是：
  1. Bearer token
  2. guest cookie
- 也就是说，一旦你带了 Authorization，请求 actor 就会被认成 `user`
- 但如果当前 session 还没 claim，它的 owner 仍然是 `guest_id`
- 这时你直接带 Bearer 去打：
  - `GET /api/v2/sessions/{session_id}`
  - `POST /api/v2/sessions/{session_id}/results/regenerate`
  - 任何当前 guest session 的接口
- 都可能直接 `404 session_not_found`

正确顺序必须是：
1. 登录 / 注册成功，拿到 `accessToken`
2. 立刻调用 `POST /api/v2/guest/sessions/{session_id}/claim`
   - 这个请求要同时带：
     - `Authorization: Bearer ...`
     - `credentials: "include"`
3. claim 成功后，再把当前 session 的后续请求切到 user 模式

## 5. 页面级行为说明

### 5.1 Upload / Analyze / Parameters / Copy / Strategy
guest 和 user 都能正常调用：
- `POST /api/v2/sessions`
- `GET|POST|DELETE /api/v2/sessions/{session_id}/images*`
- `POST|GET /api/v2/sessions/{session_id}/analysis*`
- `PUT /api/v2/sessions/{session_id}/platform-selection`
- `POST|GET|PUT /api/v2/sessions/{session_id}/parameters*`
- `GET|PUT /api/v2/sessions/{session_id}/copy`
- `POST /api/v2/sessions/{session_id}/copy/regenerate`
- `POST /api/v2/sessions/{session_id}/strategy/preview`
- `GET|PUT /api/v2/sessions/{session_id}/strategy/overrides`
- `POST /api/v2/sessions/{session_id}/prompts/preview`

前端在这些步骤上不需要强制登录。

### 5.2 主图生成页
guest 可调用：
- `POST /api/v2/sessions/{session_id}/generations`

而且：
- 可以整组生成
- 也可以带 `slot_ids` 做局部调试
- 可以多次调用
- 不再有“只允许首轮”的限制

前端不要再写这些旧判断：
- “guest 只能第一次生成”
- “guest 不能带 `slot_ids`”
- “第 4 次要提示试用结束”

### 5.3 主图结果页
guest 可调用：
- `GET /api/v2/sessions/{session_id}/results`
- `POST /api/v2/sessions/{session_id}/results/global-edit`
- `POST /api/v2/sessions/{session_id}/results/regenerate`
- `POST /api/v2/assets/{asset_id}/regenerate`

guest 不可调用：
- `GET /api/v2/sessions/{session_id}/download`

因此页面上建议拆成两类按钮：

可直接用：
- 再生成一版
- 全局修改
- 单图重生成
- 继续去详情页

需登录后再执行：
- 下载主图
- 进入账户历史

### 5.4 详情页链路
guest 可调用：
- `GET|POST|DELETE /api/v2/sessions/{session_id}/detail-pages/style-images`
- `POST /api/v2/sessions/{session_id}/detail-pages/strategy/preview`
- `GET|PUT /api/v2/sessions/{session_id}/detail-pages/strategy/overrides`
- `POST /api/v2/sessions/{session_id}/detail-pages/prompts/preview`
- `POST /api/v2/sessions/{session_id}/detail-pages/generations`
- `GET /api/v2/sessions/{session_id}/detail-pages/results`

guest 不可调用：
- `GET /api/v2/sessions/{session_id}/detail-pages/download`

所以详情页结果页也应和主图结果页一样：
- 生成、调整、重做都允许
- 下载仍要求登录

### 5.5 History / Account
这些都是 user-only：
- `/api/v2/account/overview`
- `/api/v2/account/assets`
- 以及整个 `/api/v2/account/*`

前端结论：
- guest 不应该看到“我的历史”可用态
- 可以展示登录 CTA
- 但不要把当前创作流程强制中断

## 6. Session 快照字段怎么用

`GET /api/v2/sessions/{session_id}` 现在前端最该关心这些字段：

### 6.1 `auth_mode`
含义：
- 当前这次请求是按什么身份访问的

可能值：
- `guest`
- `user`

注意：
- 它反映的是“当前请求 actor”
- 所以它和“session 最终是不是已经绑定账号”高度相关，但本质上是请求上下文语义

### 6.2 `can_download`
当前语义：
- guest: `false`
- user: `true`

前端建议：
- 直接用它控制下载按钮是否可执行
- 若为 `false`，点下载时走登录/注册

### 6.3 `can_continue_editing`
当前语义：
- 对合法可访问的 session，目前都是 `true`

前端建议：
- 可以继续保留这个字段的消费
- 但不要再把它理解成“guest 出结果后就不能继续”
- 当前这套实现里，guest 是可以继续创作的

### 6.4 `login_required_actions`
guest 当前固定是：

```json
["download", "save_history"]
```

前端可以据此做动作级控制：
- `download`
  - 点击时要求登录
- `save_history`
  - 理解为“纳入账号历史 / 进入账户体系”
  - 点击时要求登录并 claim

user 当前一般是：

```json
[]
```

### 6.5 `guest_quota_remaining`
当前是兼容字段，固定返回：

```json
null
```

前端要求：
- 可以兼容解析
- 但不要再用它做任何业务判断

## 7. 生成响应字段怎么处理

主图和详情页生成接口响应里还会带：
- `guest_trial`
- `guest_quota_remaining`
- `login_required_after_result`

这三个字段目前只是兼容字段，当前固定语义是：

```json
{
  "guest_trial": false,
  "guest_quota_remaining": null,
  "login_required_after_result": false
}
```

前端结论：
- 不要再用这三个字段弹登录
- 不要再用这三个字段展示试用剩余次数
- 真正的 UI 控制请改用：
  - `auth_mode`
  - `can_download`
  - `login_required_actions`

## 8. 登录 / 注册 / claim 的标准前端时序

### 8.1 场景 A：用户一直不登录，继续 guest 创作
1. 未登录进入页面
2. `POST /api/v2/sessions`
3. 本地保存 `session_id`
4. 后续所有 session 请求都不带 Authorization，但带 `credentials: "include"`
5. 用户持续创作
6. 如用户不点下载，也可以一直留在 guest 模式

### 8.2 场景 B：guest 点“下载”，触发登录后绑定当前 session
1. guest 在结果页点击下载
2. 前端发现：
   - `can_download = false`
   - 或 `login_required_actions` 包含 `download`
3. 弹登录 / 注册
4. 登录成功，前端拿到 `accessToken`
5. 立刻调用：

```http
POST /api/v2/guest/sessions/{session_id}/claim
Authorization: Bearer <access_token>
Cookie: <guest cookie by browser>
```

6. claim 成功后：
   - 当前 session 已属于该 user
   - 后续 session 请求切换到 user 模式
7. 重新调用下载接口

### 8.3 场景 C：guest 点“保存到我的历史”
推荐和下载一样处理：
1. 弹登录 / 注册
2. 登录成功后立即 claim 当前 session
3. claim 成功后跳转到 `/account/assets` 或前端 History 页面

### 8.4 场景 D：用户在中途登录，但暂时不想绑定当前 session
这是允许的。

前端可以这样做：
- 登录只是建立账号态
- 当前创作若还想继续按 guest session 跑，就不要立刻对这个 session 切 user 接口
- 只有在用户明确要“纳入历史 / 下载 / 转正式账号链路”时，再 claim 当前 session

但实现上更简单的建议是：
- 一旦用户在当前创作页登录成功，就直接 claim 当前 session
- 这样后续整页都切成 user 模式，最不容易乱

## 9. 前端不要再做的旧逻辑

下面这些旧逻辑要删掉：

### 9.1 不要再依赖自动认领
错误假设：
- 登录成功后，后端会自动把当前 guest session 挂到账号

当前真实情况：
- 不会自动认领
- 必须前端显式调 claim

### 9.2 不要再依赖 guest 配额
错误假设：
- guest 有固定试用次数
- 到第 4 次会被后端拒绝

当前真实情况：
- 没有产品级生成次数限制
- 前端不要做剩余次数 UI

### 9.3 不要再把“结果出来后必须登录”当成规则
错误假设：
- guest 有结果后不能再编辑

当前真实情况：
- guest 可以继续主图和详情页创作
- 只有下载 / 历史归属要求登录

### 9.4 不要在登录成功后立即对未 claim 的当前 session 走 Bearer 请求
这会导致 `404 session_not_found`

## 10. 推荐的前端实现方式

### 10.1 接口层分两套 request helper
建议封两种：

```ts
requestAsGuest()
requestAsUser()
```

区别：
- `requestAsGuest`
  - 不带 Authorization
  - 一律 `credentials: "include"`
- `requestAsUser`
  - 带 Authorization
  - 也带 `credentials: "include"`

### 10.2 当前 session 页面增加一个 owner mode
比如：

```ts
type SessionOwnerMode = "guest" | "user"
```

推荐来源：
- 初次进入页面时，用 session snapshot 的 `auth_mode`
- claim 成功后，把本页 owner mode 切成 `user`

### 10.3 下载按钮逻辑
```ts
if (!snapshot.can_download) {
  openLoginModal()
  return
}
download()
```

### 10.4 登录成功回调逻辑
```ts
async function onLoginSuccess(accessToken: string) {
  if (!currentSessionId) return

  await claimCurrentSession(currentSessionId, accessToken)
  switchCurrentPageToUserMode(accessToken)
  await refetchSessionSnapshotAsUser()
}
```

## 11. claim 接口说明

### 11.1 请求
```http
POST /api/v2/guest/sessions/{session_id}/claim
Authorization: Bearer <access_token>
```

并且浏览器必须自动带上当前 guest cookie，所以前端 fetch 仍要：

```ts
credentials: "include"
```

### 11.2 成功语义
- 返回原 `session_id`
- 不会新建 session
- claim 成功后，该 session 进入 user 体系

前端效果：
- `GET /api/v2/sessions/{session_id}` 带 Bearer 后可正常读到
- `/api/v2/account/assets` 可以出现该 session 相关记录
- 下载可以继续

### 11.3 幂等语义
如果当前 session 已经属于当前用户，再调 claim 也会成功。

前端结论：
- claim 可以放心做成“登录成功后的固定一步”
- 不需要自己复杂判断“是不是已经 claim 过”

## 12. 错误处理建议

### 12.1 guest 打下载接口返回 401
这是预期行为。

前端动作：
- 不要 toast 成“系统异常”
- 应该转成登录引导

### 12.2 登录后直接打当前 session 接口返回 404
高概率是因为：
- 你已经带 Bearer
- 但还没 claim 当前 guest session

前端动作：
- 先调 claim
- claim 成功后重试当前接口

### 12.3 guest session 过期导致 404
可能原因：
- guest cookie 24h 过期
- 用户清了 cookie
- 前端本地还保留旧 `session_id`

前端动作建议：
- 提示“当前临时创作会话已失效，请重新开始”
- 不要尝试本地伪恢复

## 13. 联调 checklist

前端联调时至少验证这些场景：

### 13.1 纯 guest 创作
- 未登录创建 session
- 完成上传、分析、参数、文案、主图生成
- 进入详情页生成
- 执行全局修改
- 执行整组重生成
- 执行单图重生成
- 整个过程中都不被要求登录

### 13.2 下载门禁
- guest 点主图下载时被要求登录
- guest 点详情页下载时被要求登录

### 13.3 登录后 claim 当前 session
- guest 先创作并出结果
- 登录成功后立即 claim 当前 session
- claim 成功后同一个 `session_id` 在 user 模式下可继续访问
- 该 session 能进入 `/api/v2/account/assets`

### 13.4 不自动认领
- guest 有两个 session
- 登录后只 claim 当前这个
- 另一个 guest session 不应自动进入账号历史

### 13.5 登录成功但不先 claim 的错误场景
- 登录后直接带 Bearer 去读当前 guest session
- 预期会失败
- 然后 claim 后恢复正常

## 14. 给前端的最终落地建议

如果要最稳，推荐这么做：

### 方案
- 未登录时，全页按 guest 跑
- 登录弹窗只在这些动作触发：
  - 下载
  - 保存到我的历史
- 一旦用户在当前创作页登录成功：
  - 立刻 claim 当前 session
  - 当前页切成 user 模式
  - 后续所有该 session 请求都带 Bearer

### 原因
- 这是最不容易出 owner mismatch 的方案
- 不需要同时维护“当前页一半 guest 一半 user”的混合状态
- 用户体验也最连贯

---

如果前端还需要，我建议下一步再补一份“接口调用时序图 + 伪代码版 SDK 封装建议”，这样他们可以直接照着实现。
