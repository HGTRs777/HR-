# 公司 HR 制度智能问答 API 契约

**版本：** `v1`  
**状态：** 任务 7 统一集成验收完成，F01–F18 公共接口已实现并最终冻结  
**后端基址：** `http://127.0.0.1:5000/api/v1`

后续任务不得在未同步修改本文件、后端校验模型和前端 TypeScript 类型的情况下改变公共字段。

## 1. 通用规则

### 1.1 成功响应

```json
{
  "ok": true,
  "data": {},
  "meta": {}
}
```

`meta` 只用于分页、统计口径或性能信息，没有内容时省略。

### 1.2 失败响应

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "问题长度必须在 1 到 1000 字之间",
    "request_id": "uuid",
    "details": {"field": "question"}
  }
}
```

固定错误码：

| 错误码 | HTTP 状态 | 含义 |
| --- | ---: | --- |
| `VALIDATION_ERROR` | 400 | 字段、文件或状态不符合规则 |
| `AUTH_REQUIRED` | 401 | 管理员未登录 |
| `FORBIDDEN` | 403 | 当前会话没有操作权限 |
| `CSRF_INVALID` | 403 | 管理端写请求 CSRF 校验失败 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `CONFLICT` | 409 | 版本重复、状态冲突或并发重建 |
| `FILE_TOO_LARGE` | 413 | 上传文件超过 10 MB |
| `UNSUPPORTED_FILE` | 415 | 文件格式不支持或内容无法解析 |
| `INDEX_NOT_READY` | 503 | 索引缺失、过期或构建失败 |
| `MODEL_UNAVAILABLE` | 503 | DeepSeek 不可用且请求无法降级 |
| `INTERNAL_ERROR` | 500 | 未预期的服务器错误 |

所有响应包含 `X-Request-ID`。前端可提交不超过 64 字符的 `X-Request-ID`，否则后端生成 UUID。

### 1.3 会话、CORS 与 CSRF

- 员工使用实名账号登录；服务端按已认证员工隔离会话、条件、清单和意见记录。`X-Client-Session-ID` 仅作为兼容性客户端标识，不替代员工认证。
- HR 使用 Flask 服务器会话；前端 Axios 必须开启 `withCredentials`。
- 前端来源由 `FRONTEND_ORIGINS` 白名单控制，不允许 `*` 与凭据同时使用。
- 管理端写操作前调用 `GET /admin/auth/csrf`，随后在请求头携带 `X-CSRF-Token`。
- 日期使用 `YYYY-MM-DD`，时间使用 UTC ISO 8601，比例使用 `0` 到 `1` 的小数。

## 2. 问答与情景推演

### `POST /chat/query`

请求：

```json
{
  "conversation_id": "可选 UUID",
  "question": "试用期可以休年假吗？",
  "scenario": {
    "employee_status": "probation",
    "tenure_years": 0.5,
    "matter_type": "annual_leave",
    "duration_days": 2
  }
}
```

约束：`question` 去除首尾空白后为 1–1000 字；`scenario` 只能保存非敏感条件。

服务端对短追问或含指代的追问拼接最近一个用户问题用于检索，并向模型提供最近 6 轮消息；原始问题仍单独保存。当前登录员工档案会以服务端可信数据注入情景，已配置字段优先于客户端情景值；系统不从聊天文字推断员工状态、工龄等档案属性。允许的情景字段还包括部门、岗位、入职日期、直属负责人、HRBP、年假额度/余额及各事项办理条件，未知字段直接拒绝。

回答的 `status` 只能为：

- `answer`：已通过声明—证据校验的正式答案。
- `clarification`：制度相关但缺少关键条件；返回明确的条件不足结论、全部缺失条件，以及当前可补充的槽位和选项。
- `refusal`：知识库没有足够依据。
- `degraded`：DeepSeek 不可用，只展示本地检索证据，不生成制度结论。

响应：

```json
{
  "ok": true,
  "data": {
    "answer_id": "uuid",
    "conversation_id": "uuid",
    "status": "answer",
    "question_type": "eligibility",
    "answer_focus": "试用期员工是否具备年假资格",
    "decision": "denied",
    "conclusion": "不可以",
    "primary_answer": "不可以申请年假。试用期员工当前不具备申请资格。",
    "reason_title": "为什么不可以？",
    "reason_items": ["你当前处于试用期，制度将试用期员工列为排除对象。"],
    "chat_answer": "【明确结论】\n不可以申请年假。试用期员工当前不具备申请资格。\n\n【为什么不可以？】\n你当前处于试用期，制度将试用期员工列为排除对象。",
    "summary": "不可以",
    "claims": [
      {
        "id": "claim-1",
        "position": 1,
        "text": "试用期员工暂不享受年假。",
        "evidence_ids": ["evidence-1"],
        "evidence_validated": true
      }
    ],
    "next_steps": [],
    "missing_conditions": [],
    "scenario": {"employee_status": "probation"},
    "employee_context": {
      "known": [
        {"field": "employee_status", "label": "员工状态", "value": "probation", "value_label": "试用期", "source": "employee_profile"}
      ],
      "missing": []
    },
    "decision_statement": "你当前不符合年假申请条件。",
    "clarification": null,
    "action_card": {
      "conclusion": "不可以",
      "applicable_conditions": ["员工状态为试用期"],
      "timeline": [],
      "materials": [],
      "cautions": []
    },
    "source_answer_id": null,
    "generation_kind": "query",
    "evidence": [
      {
        "id": "evidence-1",
        "clause_id": 31,
        "stable_anchor": "leave-v1-article-6",
        "policy_id": 2,
        "policy_code": "LEAVE-001",
        "policy_title": "休假管理制度",
        "policy_version_id": 4,
        "policy_version": "1.0",
        "effective_date": "2026-08-01",
        "section_path": "第三章 年假",
        "clause_number": "第六条",
        "page_number": 3,
        "quote": "……",
        "rank": 1,
        "vector_score": 0.83,
        "bm25_score": 4.27,
        "rrf_score": 0.0325
      }
    ],
    "evidence_coverage": 1.0,
    "knowledge_fingerprint": "sha256",
    "stale": false,
    "policy_updates": [],
    "degraded": false
  }
}
```

`question_type` 只能为 `eligibility`、`deadline`、`duration`、`quota`、`procedure`、`materials`、`approver`、`destination`、`condition`、`status`、`definition`、`reason`、`policy_lookup`、`general`。`answer_focus` 是不含业务答案的主答案槽位描述。

`primary_answer` 必须直接回答 `answer_focus`，并与第一条已验证 `claim.text` 完全一致，因此不能绕过引用和声明—证据校验。`chat_answer` 是供聊天记录持久化和展示的短回答，只完整包含一次 `primary_answer`；`reason_title/reason_items` 是经过语义去重的可选解释。`decision/conclusion` 继续保存资格或规则判断，但非资格问题只作为内部辅助判断，不在页面机械替代主答案。

`decision` 只能为 `allowed`、`denied`、`conditional`、`informational`。可判断问题的 `conclusion` 使用“可以、不可以、需要、不需要、符合、不符合、条件不足，暂时无法判断”之一。`conditional` 必须列出非空的 `missing_conditions`；其他决策不得继续要求补充条件。回答仅返回可验证原因、下一步和制度引用，不返回模型隐藏推理过程。

`decision_statement` 兼容表示首条已验证结论。`employee_context.known` 只返回与当前问题类型直接相关且已从登录员工档案取得的少量条件；完整画像仍参与后台判断，但不随每次回答平铺。`employee_context.missing` 只返回会影响当前结论、但档案值为空的字段；员工在右侧 `scenario_form` 补充后触发完整重算。明确否定后 `missing_conditions`、`clarification` 和 `scenario_form` 均为空，不再询问不会改变结论的条件。

登录档案先统一转换为业务上下文，再进入检索和判断。入职日期只可靠推导 `company_tenure_years`（本公司司龄，来源为 `derived_from_hire_date`）；`tenure_years` 表示可能包含入职前经历的累计工作年限，只有档案明确配置时才可使用，二者不得互相代替。聊天文本不参与员工属性推断。

`clarification` 状态额外返回并持久化：

```json
{
  "clarification": {
    "slot": "employee_status",
    "question": "你目前处于哪种员工状态？",
    "options": [
      {"value": "probation", "label": "试用期"},
      {"value": "regular", "label": "正式员工"}
    ]
  }
}
```

可信生成与创新工作流规则：

- Top 1 向量相关度低于配置门槛时，在调用 DeepSeek 前返回 `refusal`，不展示无关条款。
- DeepSeek 首先通过独立 JSON Schema 轻量识别 `question_type/answer_focus`；该阶段失败时记录具体阶段、HTTP 状态、异常类型和服务端消息，然后使用本地语义兜底继续 RAG 与正式回答。分类结果只控制结构和检索意图，不提供任何业务事实。正式回答仍使用 Responses API JSON Schema；证据文本与用户输入均按不可信数据处理。
- 语义分类、正式回答和制度漏洞扫描共享同一个 OpenAI-compatible client，以及同一 `API Key/base_url/model/timeout` 配置。当前统一模型为 `deepseek-v4-flash`，不存在隐藏的 `deepseek-chat` 或 `deepseek-reasoner` 默认值。
- HTTP 429、500、503、超时、连接失败、空输出、非法 JSON 或不符合 Schema 的临时结构错误最多重试 2 次并指数退避；400、401、402、422 等确定性配置/请求错误不重试。SDK 自动重试关闭，避免叠加或无限重试。
- 最终失败按 `bad_request/authentication_error/insufficient_balance/parameter_error/rate_limited/service_error/service_busy/timeout/connection_error/json_parse_error/structured_output_error/project_error` 分类。日志不记录完整 API Key；员工端仅展示安全、可操作的错误提示及本地制度证据。
- 服务端逐项验证引用 ID 是否属于本次 Top 5、条款是否仍为启用版本、声明—证据语义相关度，以及声明数字是否来自条款或可信结构化业务上下文。员工自身的“3 年”等事实可以来自登录档案，但制度结论仍必须引用真实启用条款；校验门槛未降低。
- 只有全部声明都通过证据校验时才接受模型回答；否则返回拒答或降级结果。`summary` 保存结构化明确结论，不能绕过证据校验。
- API 未配置、超时、结构错误或调用失败时返回 `degraded`，只保存并展示 Top 3 本地证据，`claims` 为空。
- 条件敏感问题按“问题语义分类 → 登录员工档案 → 统一业务上下文 → 资格预判断 → 语义查询改写 → RAG → 判断是否已有结论 → 识别最小必要缺失条件 → 生成主答案 → 声明—证据校验”执行；检索扩展只注入期限、额度、审批角色等语义槽位和当前部门，不注入业务答案。只要当前画像和制度已经足以判断，就直接回答；明确拒绝时不再询问不会改变结论的条件。确实无法判断时采用渐进补充，每次只返回下一个必要条件，已配置档案字段和无关字段不会再次出现。
- LLM 返回的 `next_steps` 仍按本次已验证证据逐项校验并携带 `evidence_ids`，但它只作为回答辅助信息，不直接充当办理清单。
- 阶段 5 起，`action_card/checklist` 的主语义改为受控业务模板：`tasks` 是员工可以逐项勾选的实际动作，`process_flow` 是事项将经过的角色或环节，`basis_evidence_ids` 只负责关联制度依据。LLM 的 `next_steps` 不得直接复制为清单，RAG 条款原文也不得作为任务标题或步骤描述。模板只有在正式回答且存在已验证证据时才生成；明确拒绝、澄清、拒答和降级结果不生成可执行清单。
- `tasks[].id` 是跨条件重算稳定的任务标识，前端据此保留仍然相同的已完成状态；无法匹配的已完成任务必须重置并明确提示。`process_flow[].person_configured` 区分真实档案姓名与纯角色占位；直属负责人和 HRBP 只允许来自登录员工档案，缺少时返回“当前系统未配置具体人员”。`process_flow` 仅表示应经过的环节，不表示实时审批进度。
- `estimated_completion` 仅在结构化规则或可信业务系统能够可靠计算时返回；当前制度只有提交期限而没有实际办理完成时点时为 `null`，不得伪造预计完成时间。
- `generation_kind` 为 `query/replay/refresh`；后两者通过 `source_answer_id` 指向来源回答，旧回答不覆盖。
- `policy_updates` 对比回答证据快照与当前启用版本，返回旧版/新版版本号、生效日期和阅读器版本 ID；没有版本变化时为空数组。

### `POST /chat/replay`

请求包含原 `answer_id` 和更新后的完整 `scenario`。服务端校验匿名会话归属、合并情景并要求至少一个字段发生变化。响应与 `/chat/query` 相同，`meta` 返回：

```json
{
  "previous_answer_id": "uuid",
  "scenario_changes": [
    {
      "field": "tenure_years",
      "label": "累计工龄",
      "before": 3,
      "after": 12,
      "before_label": "3 年",
      "after_label": "12 年"
    }
  ],
  "recalculation_message": "条件已更新，回答和办理建议已重新计算。"
}
```

重算不是前端局部改文案：服务端会使用合并后的情景重新执行条件判断、制度检索、回答生成、声明—证据校验和办理清单生成。`scenario_form` 只保留当前仍需补充或用户已经补充、可继续修改的相关字段。数值字段的 `min/max/step/constraint_hint` 来自当前员工画像、真实余额/额度和本次命中的明确制度上限；没有可靠上限时不提供臆造的固定最大值。

## 3. 会话、回答和制度阅读器

| 方法与路径 | 行为 |
| --- | --- |
| `GET /conversations` | 当前匿名浏览器会话列表，按更新时间倒序 |
| `POST /conversations` | 新建空会话 |
| `GET /conversations/{id}` | 会话消息、回答摘要及过期状态 |
| `DELETE /conversations/{id}` | 删除当前浏览器拥有的会话 |
| `GET /answers/{id}` | 完整回答、声明、证据、指纹和保鲜状态 |
| `POST /answers/{id}/refresh` | 使用当前启用制度重新生成答案 |

`POST /answers/{id}/refresh` 仅接受已经过期且属于当前匿名会话的回答。它使用原问题和原情景重新执行当前可信生成链路，返回新回答，并在 `meta` 中返回来源回答 ID 及前后知识指纹；当前口径回答返回 409。
| `GET /policies/{version_id}/reader` | 制度元数据和按顺序排列的条款锚点 |

`reader` 返回的每个条款至少包含 `clause_id`、`stable_anchor`、章节路径、条款号、页码和原文。前端只能使用 `stable_anchor` 定位，不拼接数据库主键作为 DOM ID。

## 4. 意见与反馈状态

### `POST /feedback`

```json
{
  "answer_id": "uuid",
  "feedback_type": "wrong_answer",
  "content": "这条规则似乎没有考虑试用期。",
  "is_anonymous": true,
  "submitter_name": null
}
```

- `content`：1–1000 字。
- `feedback_type` 支持 `helpful`、`wrong_answer`、`missing_policy`、`outdated_policy`、`unclear`、`missing_process` 和 `suggestion`；员工端“有帮助/有问题”继续复用此接口。
- 匿名时忽略并不保存 `submitter_name`。
- 实名时服务端忽略客户端传入的 `submitter_name`，直接使用当前已认证员工账号的展示姓名与工号，防止重复填写或冒用他人姓名。
- 服务端校验回答属于当前 `X-Client-Session-ID`，并从 `answer_id` 复制原问题、用于检索的规范化问题、情景、声明、证据、制度版本及知识指纹快照；前端不得提交或覆盖这些快照。

| 方法与路径 | 行为 |
| --- | --- |
| `GET /feedback` | 当前匿名浏览器可查看的意见单 |
| `GET /feedback/{id}` | 意见状态、处理时间线和站内结果 |
| `GET /admin/feedback` | HR 按状态、类型、制度和日期筛选 |
| `PATCH /admin/feedback/{id}` | 处理、退回、解决或驳回 |
| `POST /admin/feedback/{id}/retest` | 用原问题和场景执行复测 |
| `POST /admin/feedback/{id}/regression-case` | 将通过的意见固化为回归用例 |
| `GET /admin/regression-cases` | 回归用例及最近运行结果列表 |

反馈状态流为 `open → processing → resolved`，`processing → open`，或从 `open/processing → rejected`；非法跳转返回 409。每次提交、状态变化、复测与固化均追加事件，不覆盖历史。

复测不调用生成模型，也不写入员工会话；它使用快照中的规范化问题执行现有 Top 5 混合检索，原证据的稳定锚点均被召回才视为通过。只有状态为 `resolved` 且最近复测通过的意见可固化；同一反馈最多对应一个回归用例。

## 5. 员工/管理认证、制度与索引

| 方法与路径 | 行为与关键约束 |
| --- | --- |
| `GET /auth/human-challenge` | 生成一次性滑动拼图验证，5 分钟过期 |
| `POST /employee/auth/login` | 员工用户名、密码及人机答案登录 |
| `POST /employee/auth/logout` | 清除员工会话 |
| `GET /employee/auth/session` | 当前员工登录状态和账号概要 |
| `GET /admin/auth/csrf` | 获取或复用会话 CSRF Token |
| `POST /admin/auth/login` | 管理员用户名、密码及人机答案登录，成功后轮换会话 |
| `POST /admin/auth/logout` | 清除管理员会话 |
| `GET /admin/auth/session` | 当前登录状态和管理员概要 |
| `GET /admin/policies` | 制度及版本列表 |
| `POST /admin/policies` | `multipart/form-data` 上传制度和元数据 |
| `GET /admin/policies/{id}` | 制度、全部版本及解析状态 |
| `PATCH /admin/policy-versions/{id}` | 修改版本元数据或启停状态 |
| `DELETE /admin/policy-versions/{id}` | 删除非启用版本；有回答证据引用时只允许停用 |
| `POST /admin/index/rebuild` | 对启用版本原子重建索引，已有任务时返回 409 |
| `GET /admin/index/status` | 当前指纹、构建阶段、条款数和错误 |
| `POST /admin/search/test` | 返回 Top 5 的向量分、BM25 分和 RRF 名次 |

制度上传字段：`code`、`title`、`category`、`version`、`effective_date`、`file`。同一 `code + version` 唯一；同一制度编号同一时刻只能有一个 `active` 版本。

补充约束与返回字段：

- 文件支持 `.md`、`.txt`、`.pdf`、`.docx`，文件本体最大 10 MB；扫描版 PDF 未提取到文字时返回 `UNSUPPORTED_FILE`。
- 上传成功后版本初始为 `draft`，解析结果包含 `parsed_at`、`parse_error`、`clause_count`、文件哈希和 MIME 类型。
- 制度列表包含 `active_version_id`、`version_count` 和 `versions`；版本详情不返回服务器文件路径。
- 索引状态包含 `status`、当前已发布 `fingerprint`、按启用制度实时计算的 `current_knowledge_fingerprint`、`stale`、已发布与启用条款数、模型和切分器版本。
- Top 5 检索结果包含条款与制度定位字段，以及 `vector_score/vector_rank`、`bm25_score/bm25_rank` 和 `rrf_score/rank`。

## 6. 数据洞察与健康检查

### v2.0 问题中心自动扫描

| 方法与路径 | 行为 |
| --- | --- |
| `GET /admin/policy-gaps/latest` | 返回最近扫描；超过配置周期或从未扫描时自动执行一次定期扫描 |
| `POST /admin/policy-gaps/scan` | HR 手动立即扫描并持久化新批次 |

扫描同时读取启用制度文本、匿名问答聚合和制度反馈。返回批次摘要、触发方式、扫描范围、模型名，以及按严重度排序的漏洞项；每项包含类别、描述、出现次数、整改建议和扫描依据。未配置 DeepSeek 或模型异常时使用本地规则分析，不丢弃扫描能力。

`policy-gaps` 路径作为兼容性 API 名称继续保留，员工与 HR 界面统一称为“问题中心”。

员工回答在兼容旧版 `action_card` 的同时返回 v2.0 `checklist`、`scenario_form` 和 `employee_context`。`scenario_form` 只描述仍缺失且会影响当前判断的下一个可补充字段，以及用户已经补充、可继续修改的相关字段；`employee_context` 区分档案自动获取值与影响判断的“未配置”值。`checklist.tasks` 与 `checklist.process_flow` 继续通过 `evidence_ids/basis_evidence_ids` 关联制度阅读器，但员工动作文本与制度原文保持分离。

### `GET /admin/analytics`

查询参数：`date_from`、`date_to`、`policy_id`、`feedback_status`。

返回：查询量、命中率、拒答率、澄清率、降级率、平均响应时间、反馈总数、待处理数、回归用例数、每日查询量、制度命中、热门问题、未命中问题、反馈分类和反馈处理状态。排行榜默认 Top 10；空数据时计数和比例为 0、列表为空。

### `GET /health`

无需登录，返回 API、SQLite、DeepSeek 配置和嵌入索引状态，不返回密钥、路径或异常堆栈。
