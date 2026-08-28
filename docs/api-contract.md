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

- 员工无需登录，浏览器生成匿名 `client_session_id`，服务端只用它隔离会话历史。
- 员工端所有会话、问答和回答请求携带 `X-Client-Session-ID`；值为 8–64 位字母、数字、下划线或连字符。前端首次访问生成 UUID 并保存在浏览器本地存储。
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

服务端对短追问或含指代的追问拼接最近一个用户问题用于检索，并向模型提供最近 6 轮消息；原始问题仍单独保存。任务 3 允许的情景字段为 `employee_status`、`tenure_years`、`matter_type`、`duration_days`，未知字段直接拒绝。

回答的 `status` 只能为：

- `answer`：已通过声明—证据校验的正式答案。
- `clarification`：缺少关键条件，只返回需要补充的槽位和选项。
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
    "summary": "一句话结论",
    "claims": [
      {
        "id": "claim-1",
        "position": 1,
        "text": "试用期员工暂不享受年假。",
        "evidence_ids": ["evidence-1"],
        "evidence_validated": true
      }
    ],
    "scenario": {"employee_status": "probation"},
    "clarification": null,
    "action_card": {
      "conclusion": "当前情景不适用年假",
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
    "degraded": false
  }
}
```

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
- DeepSeek 使用 Responses API JSON Schema 输出；证据文本与用户输入均按不可信数据处理。
- 服务端逐项验证引用 ID 是否属于本次 Top 5、条款是否仍为启用版本、声明数字是否存在于证据及声明—证据语义相关度。
- 任一声明未通过时删除该声明；没有声明通过时返回 `refusal`。`summary` 取首条已验证声明，不能绕过证据校验。
- API 未配置、超时、结构错误或调用失败时返回 `degraded`，只保存并展示 Top 3 本地证据，`claims` 为空。
- 条件敏感问题缺少关键槽位时先返回 `clarification`，不执行模型生成；普通追问继承会话中的非敏感情景。
- `action_card` 只在正式 `answer` 状态生成；时间线、材料和注意事项均直接抽取自本次已验证证据并携带 `evidence_ids`。
- `generation_kind` 为 `query/replay/refresh`；后两者通过 `source_answer_id` 指向来源回答，旧回答不覆盖。

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
  ]
}
```

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
- 匿名时忽略并不保存 `submitter_name`。
- 实名时 `submitter_name` 必须为 1–80 字。
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

## 5. 管理认证、制度与索引

| 方法与路径 | 行为与关键约束 |
| --- | --- |
| `GET /admin/auth/csrf` | 获取或复用会话 CSRF Token |
| `POST /admin/auth/login` | 用户名和密码登录，成功后轮换会话 |
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

### `GET /admin/analytics`

查询参数：`date_from`、`date_to`、`policy_id`、`feedback_status`。

返回：查询量、命中率、拒答率、澄清率、降级率、平均响应时间、反馈总数、待处理数、回归用例数、每日查询量、制度命中、热门问题、未命中问题、反馈分类和反馈处理状态。排行榜默认 Top 10；空数据时计数和比例为 0、列表为空。

### `GET /health`

无需登录，返回 API、SQLite、DeepSeek 配置和嵌入索引状态，不返回密钥、路径或异常堆栈。
