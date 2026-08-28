# 开发交接记录

## 固定约定

- 前端独立运行于 `127.0.0.1:5173`，后端独立运行于 `127.0.0.1:5000`。
- 公共字段以 `docs/api-contract.md` 和 `frontend/src/types/api.ts` 为准。
- 数据库以 `docs/database-design.md` 和 `backend/app/models.py` 为准。
- 后续任务不得删减 F01–F18，不得扩展到真实员工档案、考勤审批或薪资管理。
- 任何公共契约修改必须同时更新文档、后端、前端类型及测试。

## 任务 1：工程骨架与契约冻结

### 已完成

- Flask 应用工厂、环境配置、CORS、CSRF、请求 ID、统一错误响应和健康检查。
- SQLAlchemy 完整领域实体及 Flask-Migrate 接入。
- Vue 3/Vite/TypeScript strict、Pinia、Vue Router、Axios 和 Element Plus 基础工程。
- 员工三栏沙盘与 HR 控制台页面骨架。
- API 契约、数据库设计和 F01–F18 追踪矩阵。

### 后续入口

- 任务 2 从 `Policy`、`PolicyVersion`、`Clause` 和 `IndexSnapshot` 开始实现知识库。
- 制度启用和索引发布必须采用事务及原子切换。
- 新接口只能在 `/api/v1` 下实现，并返回统一 envelope。

### 验证结果

- 后端依赖：`pip check` 通过，无损坏依赖。
- 数据库：初始 Alembic 修订 `a6996e6553d9` 已生成并升级；`flask db check` 无待生成操作。
- 后端测试：`pytest -q`，4 项全部通过。
- 前端检查：TypeScript strict 检查通过；Vitest 1 项通过。
- 生产构建：Vite 构建通过；路由懒加载后主包约 186 KB、gzip 约 72 KB，无大包警告。
- 运行检查：Waitress/Flask 端口 5000、Vite 端口 5173 可独立启动；健康接口返回 200。
- 浏览器检查：员工端、HR 管理端路由正常；桌面三栏和 390 px 单栏布局无水平溢出，控制台无错误。
- 文档检查：正式 Markdown 与 16 页 PDF 已同步为 Vue 3、Flask、SQLAlchemy、SQLite 和 DeepSeek，F18 调整为 P1 全覆盖。

### 任务 1 结束时状态（已由任务 2 接续）

- 本机已配置 DeepSeek 环境变量，但任务 1未发送真实模型请求；在线冒烟测试留给可信问答任务。
- 嵌入模型尚未下载，健康接口显示 `embedding_index: not_built`，由任务 2 负责构建。

## 任务 2：制度知识库与混合检索

### 已完成

- 管理员登录、退出、会话检查和管理接口鉴权；写请求沿用任务 1 的 CSRF 防护。
- Markdown、TXT、PDF、DOCX 解析和文件本体 10 MB 限制；空白或扫描版 PDF 给出明确错误。
- 制度编号与版本唯一、单制度仅一个启用版本、启用版本禁止删除、历史证据引用版本禁止物理删除。
- 按 Markdown 标题、章/节/条和编号标题切分条款，保存来源页码/段落号、文本哈希和稳定锚点。
- 真实 `BAAI/bge-small-zh-v1.5` 向量、jieba + BM25、RRF(k=60) 融合检索；调试接口返回 Top 5 三路分数与名次。
- 知识指纹覆盖启用版本、文件哈希、条款哈希、嵌入模型及切分器版本；制度启停后索引自动判定为 `stale`。
- 所有嵌入先在内存完成，向量和快照在同一事务发布；失败保留原 `is_current` 快照。
- 五类虚构示例制度共 30 条，以及 25 条精确到制度和条款号的检索评测集。
- 公共制度阅读器按稳定锚点返回完整条款；健康接口报告真实索引状态。

### 数据库与命令

- 新迁移：`f1098ad60503`，增加 `policy_versions.parse_error` 与 `index_snapshots.is_current`。
- 初始化顺序：`flask db upgrade` → `flask create-admin` → `flask seed-policies` → `flask build-index`。
- 检索验收：`flask evaluate-retrieval`。

### 验证结果

- 后端测试：`pytest -q`，13 项全部通过（任务 2 逻辑使用隔离内存库和确定性测试向量）。
- 真实模型：BGE 小型中文模型已下载并成功生成 30 条 `float32` 向量。
- 检索评测：Recall@3 为 `100.00% (25/25)`，高于 85% 门槛。
- 索引状态：`ready`，30 个已发布条款与 30 个启用条款一致，指纹无过期。

### 任务 3 入口

- 直接复用 `services.retrieval.hybrid_search(question, limit)`，不要另建检索实现。
- 正式答案必须保存当前 `knowledge_fingerprint`，并将命中条款映射为 `ClaimEvidence` 快照。
- 索引为 `not_built/stale` 时不得生成正式结论；DeepSeek 不可用时只允许返回本地证据降级结果。
- 任务 4 再实现 F06–F10 管理页面；不得改变本任务冻结的接口字段，除非同步更新契约、类型和测试。

## 任务 3：可信问答与会话

### 已完成

- `POST /chat/query`、会话新建/列表/详情/删除及回答详情接口；`X-Client-Session-ID` 隔离匿名浏览器数据。
- 最近 6 轮消息进入 DeepSeek 上下文；短追问和指代追问与上一个用户问题组合为独立检索问题，同时保留原始问题。
- Top 1 BGE 相关度门槛在模型调用前执行低证据拒答，避免把无关条款交给模型组织答案。
- DeepSeek Responses API + JSON Schema 结构化输出；系统提示明确把问题和证据视为不可信数据，制度正文中的指令不能覆盖系统规则。
- 声明验证依次检查本次 Top 5 证据 ID、当前启用版本、数字一致性、向量语义相关度；未通过的声明不会展示或入库。
- 正式答案保存 `Claim`、`ClaimEvidence`、制度版本快照、完整检索分数、覆盖率和知识指纹；摘要直接取首条已验证声明。
- DeepSeek 未配置、超时、错误或无效结构时返回 `degraded`，只展示并持久化 Top 3 本地制度原文，不生成结论。
- 会话仅接受四类非敏感情景槽位，未知字段拒绝保存；每次查询写入 `QueryLog` 供 F18 使用。
- 前端 HTTP 客户端自动生成并携带匿名会话 UUID；公共 TypeScript 类型已同步会话、回答、证据和降级字段。

### 数据库与配置

- 新迁移：`8523228205a4`，增加 `answers.evidence_snapshot`、`evidence_coverage`、`degraded_reason`。
- 新配置：`DEEPSEEK_MAX_OUTPUT_TOKENS`、`RETRIEVAL_MIN_VECTOR_SCORE`、`CLAIM_EVIDENCE_MIN_SCORE`。
- BGE 加载优先使用本地缓存，缓存缺失时才联网下载；实测预热后检索约 `0.024 s`。

### 验证结果

- 离线后端测试：`pytest -q`，22 项全部通过；自动测试不访问 DeepSeek，使用可替换生成器。
- 覆盖场景：API 失败降级、低分拒答、有效引用、伪造证据 ID、数字幻觉、多轮追问、会话隔离、持久化历史和敏感槽位拦截。
- DeepSeek 在线冒烟：HTTP 200、`answer`、2 条声明、2 条证据、覆盖率 `1.0`，全部声明通过服务端校验。
- 无答案实测：“公司是否提供宠物补贴？”返回 `refusal`，0 声明、0 证据且未降级。
- 真实 BGE 性能：冷启动约 `6.471 s`，同进程预热后单次检索约 `0.024 s`，满足预热后小于 2 秒要求。
- 传统运行冒烟：Waitress 启动后 `/health` 为 `ok`、索引为 `ready`，在线回答可从隔离会话历史完整读取。

### 后续入口

- 任务 4 实现员工问答、证据高亮、会话历史，以及 F06–F10 管理页面；直接复用本任务 API 和类型。
- F12–F15 的主动澄清、情景重放、一问一办和答案刷新仍按后续创新任务实施；任务 3 已保留 `scenario`、`action_card`、`stale` 数据契约。
- 不得在前端拼接结论或自行判断引用有效性；只展示后端 `claims/evidence/evidence_coverage` 的已验证结果。

## 任务 4：前端整合与端到端联调

### 已完成

- 员工端三栏工作台：会话新建、列表、切换、删除、示例问题、中文问答和最近会话消息展示。
- 答案状态完整展示：`answer`、`refusal`、`degraded`、`clarification`、证据覆盖率、知识过期和接口异常均有独立文本提示。
- 逐声明展示服务端已验证证据；点击引用后按制度版本加载阅读器，并以 `stable_anchor` 定位、滚动和高亮原文。
- HR 管理端：登录退出、未登录隔离、制度版本上传/预览/启停/受约束删除、索引状态与原子重建、Top 5 混合检索诊断。
- Top 5 诊断同时展示向量、BM25、RRF 分数及各路名次；制度卡展示版本、生效日期、状态、条款数和文件大小。
- Axios 客户端持久生成 `X-Client-Session-ID`，并在登录成功后同步服务端轮换的 CSRF Token，保证首个管理写请求可用。
- 桌面三栏、平板和手机单栏响应式布局已完成；任务 4 未在前端伪造 F12–F15 创新功能。

### 主要文件

- 产品需求：`docs/prds/task4-frontend-integration-v1.0-prd.md`
- 员工页面：`frontend/src/views/EmployeeWorkbenchView.vue`
- 管理页面：`frontend/src/views/AdminDashboardView.vue`
- API 服务：`frontend/src/services/chat.ts`、`frontend/src/services/admin.ts`、`frontend/src/services/http.ts`
- 组件测试：`frontend/tests/employee-workbench.spec.ts`、`frontend/tests/admin-dashboard.spec.ts`

### 验证结果

- 后端回归：`pytest -q`，22 项全部通过；`pip check` 无损坏依赖。
- 数据库：当前修订为 `8523228205a4 (head)`；`flask db check` 无待生成操作。
- 前端回归：TypeScript strict 检查通过；Vitest 2 个测试文件、2 项测试全部通过；Vite 生产构建通过。
- 真实浏览器桌面验收：连续完成“年假如何计算？”和“那试用期员工呢？”多轮问答，覆盖率 100%，证据可定位到 `LEAVE-001` 对应条款并高亮。
- 真实浏览器管理验收：登录、制度预览、30 条款索引重建和 Top 5 检索正常；重建后索引状态为 `ready`。
- 390 px 移动端验收：员工三张工作卡降为单列，员工端和管理登录页均无横向溢出。

### 任务 5 入口

- 开始实现创新需求 F12–F15：主动澄清、情景条件重放与差异、一问一办行动卡、知识指纹过期提醒与答案刷新。
- 沿用任务 3 已冻结的 `scenario`、`clarification`、`action_card`、`stale` 字段；如需扩展公共契约，必须同步 API 文档、前端类型、迁移和测试。
- 任务 5 必须覆盖创新链路的后端规则、前端交互、持久化和端到端测试，不得只做静态卡片或演示数据。

## 任务 5：创新工作流 F12–F15

### 已完成

- F12 主动澄清：服务端识别年假工龄、年假审批天数和离职员工状态等关键条件；缺失时持久化 `clarification` 回答，不提前调用模型或输出结论。
- 普通多轮追问继承会话情景；问题中明确出现的事项、员工状态和工龄会补入非敏感情景槽位，未知字段继续拒绝。
- F13 情景推演：`POST /chat/replay` 校验回答归属、合并情景、拒绝无变化请求，并返回逐字段的前值、后值和展示标签。
- 推演将已确认情景写入模型问题，要求只输出当前分支结论；实测工龄 3 年与 12 年分别得到 5 天和 10 天年假结论。
- F14 一问一办：仅从已验证证据抽取适用条件、时间线、材料与注意事项；每一步携带证据 ID，可复用稳定锚点阅读器定位原文。
- F15 答案保鲜：知识指纹或引用版本变化时标记旧回答过期；`POST /answers/{id}/refresh` 生成新回答并保留原回答和证据快照。
- Answer 新增 `clarification`、`source_answer_id`、`generation_kind`；迁移修订为 `b1d0d81b0b64`。
- 员工端新增回答版本历史、澄清选项、四槽位情景沙盘、变化摘要、行动卡和过期刷新入口。

### 验证结果

- 后端：`pytest -q` 共 28 项通过，覆盖澄清持久化、离职状态澄清、推演差异、行动卡证据约束、无变化、跨会话越权、刷新及当前答案冲突。
- 前端：TypeScript strict 通过；Vitest 2 个测试文件、4 项测试通过；生产构建通过。
- 数据库：`b1d0d81b0b64 (head)`，`flask db check` 无待生成操作，旧回答通过服务器默认值兼容迁移。
- 真实浏览器：完成“年假如何计算？”→工龄澄清→3 年推演→12 年再次推演；差异摘要和行动卡证据高亮正确，控制台无警告或错误。
- 保鲜验收：旧回答被标记过期后出现刷新入口，刷新生成独立的“保鲜刷新”历史版本，旧回答仍可选择和读取。
- 390 px 验收：三栏工作台和四字段情景沙盘均降为单列，无横向溢出。

### 任务 6 入口

- 实现 F16–F18：员工共创意见箱、HR 反馈闭环与回归用例、数据洞察仪表盘。
- 反馈必须复制回答、声明、证据和版本快照；匿名意见不得保存姓名，处理事件只追加不覆盖。
- 任务 6 完成后执行 F01–F18 最终全覆盖回归与演示验收。

## 任务 6：反馈闭环、数据洞察与最终回归

### 已完成

- F16 共创意见箱：员工可针对本人回答提交五类实名或匿名意见；服务端校验匿名会话归属，并保存原问题、规范化问题、情景、声明、证据、制度版本和知识指纹快照。匿名记录不保存姓名，原会话删除后反馈快照仍可审计。
- F17 反馈闭环：HR 可按状态、类型、制度和日期筛选，按 `open → processing → resolved`、`processing → open` 或 `open/processing → rejected` 状态机处理；每次提交、状态变化、复测和固化均追加不可覆盖事件，员工端可查看处理时间线。
- 复测复用现有 Top 5 混合检索，以快照中的规范化问题恢复短追问上下文，不调用 DeepSeek、不新增会话消息；原证据稳定锚点全部召回才通过。
- 只有已解决且最近复测通过的意见可固化为回归用例；数据库唯一约束与服务层共同防止重复固化，前端已固化后不再显示重复操作入口。
- F18 数据洞察：展示查询量、命中/拒答/澄清/降级率、平均耗时、反馈待办、回归用例、每日趋势、制度命中、热门/未命中问题和反馈分类/状态，并支持日期、制度和反馈状态过滤。
- 员工工作台新增制度共创卡、提交表单和最近处理时间线；HR 控制台新增洞察仪表盘、筛选、处理、复测、固化和完整事件时间线。
- F01–F18 需求追踪矩阵已全部标记完成，API 契约、数据库设计、README、PRD 和前后端类型同步冻结。

### 数据库与主要文件

- 新迁移：`0316b1a7de8e`，增加 `feedback.client_session_id`、`primary_policy_id`、`answer_snapshot`，以及 `regression_cases.feedback_id` 唯一约束。
- 后端入口：`backend/app/services/feedback.py`、`backend/app/services/analytics.py`、`backend/app/api/feedback.py`。
- 前端入口：`frontend/src/services/feedback.ts`、`frontend/src/services/admin.ts`、`frontend/src/views/EmployeeWorkbenchView.vue`、`frontend/src/views/AdminDashboardView.vue`。
- 任务需求：`docs/prds/task6-feedback-analytics-v1.0-prd.md`。

### 最终验证结果

- 后端全量回归：`pytest -q`，33 项全部通过；`pip check` 无损坏依赖。
- 数据库：`0316b1a7de8e (head)`；`flask db check` 无待生成操作。
- 前端全量回归：TypeScript strict 通过；Vitest 2 个测试文件、6 项测试全部通过；Vite 生产构建通过。
- 真实浏览器闭环：员工匿名提交 → HR 开始处理 → 原问题复测通过 → 解决 → 固化回归用例 → 员工查看已解决状态与完整事件，均通过；控制台无错误或警告。
- 390 px 移动端：洞察、筛选与反馈卡片降为单列，员工端和管理端均无横向溢出。
- 浏览器验收产生的两条反馈、一个回归用例和临时管理员已精确清理；未修改原有业务会话与制度数据，验收服务已关闭。

### 维护入口

- 继续沿用传统前后端分开运行：先在 `backend` 执行迁移并启动 `run.py`，再在 `frontend` 执行 `npm run dev`。
- 修改反馈快照、状态流、洞察字段或回归条件时，必须同步 API 契约、SQLAlchemy 模型、迁移、TypeScript 类型和两端测试。
- 回归用例当前用于持续治理沉淀和最近结果记录；若后续增加批量定时执行，应复用相同稳定锚点判定，不改变历史反馈事件。

## 任务 7：统一集成、测试与交付

### 已完成

- 按原模块化计划串联员工问答、HR 知识维护、主动澄清、情景推演、一问一办、答案保鲜、意见修复、回归用例与 F18 数据洞察；不新增业务范围。
- 增加任务 7 公共 JSON 契约测试，并完成人工三方审计：`docs/api-contract.md`、Flask 序列化结果和 `frontend/src/types/api.ts` 无已知冲突。
- Alembic 保留 5 个有业务意义的线性修订；验证只有 `0316b1a7de8e` 一个 head，现有库无模型漂移，空白 SQLite 可从初始修订完整升级。未发现应删除的重复或临时迁移。
- 后端新增任务 7 集成测试，覆盖正式回答 JSON 字段、非法模型结构、模拟超时、非法请求 JSON 和并发索引重建。
- 前端接入 `@playwright/test`，将 Vitest 与 E2E 目录隔离；Playwright 使用本机 Edge 跑桌面和移动端员工/HR 流程，并把页面异常和控制台错误纳入失败条件。
- 新增 `setup-demo.ps1`、`start-demo.ps1`、`stop-demo.ps1`：初始化、迁移、构建、Waitress/Vite Preview 启动、双端健康检查和安全停止形成可重复流程。
- 新增配置说明、用户手册和最终测试报告；F01–F18 追踪矩阵补齐每项接口、页面与测试证据。

### 集成阶段修复

- 明确 Vitest 只扫描 `frontend/tests`，避免把 Playwright 用例加载进组件测试运行器。
- 修复停止脚本读取 JSON UTC 时间时丢失时区导致的 PID 复用误判；保留 PID + 启动时间双重保护。
- 增加内嵌 favicon，消除桌面和移动端页面的 404 控制台错误。
- 测试模型替身抛出的非结构错误统一转换为 `ModelGenerationError`，与真实 DeepSeek 超时/网络异常保持相同降级语义。

### 最终验证

- `scripts/check-foundation.ps1`：Pytest 36 项通过；`pip check` 通过；迁移为 `0316b1a7de8e (head)` 且无漂移；TypeScript strict 通过；Vitest 2 个文件、6 项通过；Vite 生产构建通过。
- Playwright：Edge 桌面/移动端共 4 项通过，员工查询、HR 登录、制度数据、F18 和反馈治理均可访问；无横向溢出、页面异常或控制台错误。
- 真实检索：Recall@3 `100.00% (25/25)`。
- 正式报告 12 个场景、F18 及伪造证据、非法 JSON、模型超时、索引过期、重复版本、恶意文件和并发重建均有测试结论，详见 `docs/test-report.md`。
- 一键启动和停止已重复实测；5000/5173 最终均关闭。临时管理员、E2E 会话、查询日志和迁移测试库已清理。

### 最终交付入口

- 首次安装与演示：`docs/configuration-guide.md`。
- 员工与 HR 操作：`docs/user-manual.md`。
- 完整质量证据：`docs/test-report.md` 与 `docs/requirements-traceability.md`。
- 后续修改必须继续保持前后端分离运行、F01–F18 契约兼容和同等级全量回归。

## 2026-08-28：全站 UI/UX 优化

### 设计与实现

- 安装并采用 `ui-ux-pro-max` 规范，以“企业知识工作台”为视觉方向；保留 Vue 3 + Element Plus 技术体系和全部业务流程。
- 建立深墨绿、暖白与橙色强调的统一设计令牌，覆盖 Element Plus 主色、状态色、圆角、阴影、表单焦点和按钮反馈，消除默认蓝色与品牌色冲突。
- 员工端强化可信能力说明、首要咨询入口、三段工作流层级、证据卡片、情景沙盘和空状态；桌面保持三栏，移动端降为单列。
- HR 端优化登录故事、治理三步流程、指标卡、制度版本、索引、数据洞察和反馈闭环的视觉层级；移动端将登录表单置于治理介绍之前，保证首屏主任务可执行。
- 增加跳到主要内容链接、统一键盘焦点、可读表单边界、`prefers-reduced-motion` 降低动效规则及 150–300 ms 微交互。

### 安全边界

- 仅修改 `frontend/src/App.vue`、`frontend/src/styles/main.css` 和三个视图模板。
- 未修改 `backend/`、数据库、迁移、前端 `services/`、API 类型和前后端接口；验证过程未登录、未提问、未提交表单，不产生业务数据。

### 验证结果

- `npm run build` 通过，TypeScript strict 与 Vite 生产构建无错误。
- `npm run test:run`：2 个测试文件、6 项组件测试全部通过。
- 后端隔离回归：使用 `backend/.venv` 执行 `pytest -q`，36 项全部通过；只读 `/api/v1/health` 返回 API、数据库与嵌入索引正常。
- 真实 `http://127.0.0.1:5000/` 浏览器验收：员工端、HR 登录端在默认窄屏和 1440×900 桌面宽屏均无横向溢出，控制台无错误或警告。
- 本地 5000 端口服务保持运行，最终交付时未关闭。
