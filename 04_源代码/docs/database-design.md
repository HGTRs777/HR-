# 数据库设计

**数据库：** SQLite  
**ORM：** SQLAlchemy 2.x  
**迁移：** Alembic / Flask-Migrate

## 1. 实体关系

```text
Policy 1 ── N PolicyVersion 1 ── N Clause
                           └──── ClaimEvidence N ── 1 Claim N ── 1 Answer
Conversation 1 ── N Message
Conversation 1 ── N Answer
Answer 1 ── N Feedback 1 ── N FeedbackEvent
Feedback 1 ── 0..1 RegressionCase
Policy / Conversation ── N QueryLog
IndexSnapshot 保存一次可发布索引的全局指纹与构建结果
```

## 2. 表职责

| 表 | 主键 | 职责与关键约束 |
| --- | --- | --- |
| `admin_users` | 整数 | HR 管理员；用户名唯一，密码只保存哈希 |
| `employee_users` | 整数 | 员工登录账号；用户名唯一，密码只保存哈希，不接入真实员工档案 |
| `policies` | 整数 | 制度逻辑身份；制度编号唯一 |
| `policy_versions` | 整数 | 制度文件、解析错误及版本元数据；`policy_id + version` 唯一 |
| `clauses` | 整数 | 条款原文、位置、稳定锚点和向量；锚点唯一 |
| `index_snapshots` | 整数 | 知识库指纹、嵌入模型、切分器版本、构建状态及当前发布标记 |
| `conversations` | UUID 字符串 | 匿名浏览器会话及当前非敏感情景槽位 |
| `messages` | 整数 | 用户、助手和系统消息 |
| `answers` | UUID 字符串 | 一次结构化回答、检索证据快照、覆盖率、知识指纹、办事卡和降级状态 |
| `claims` | 整数 | 回答中的独立制度性声明；答案内位置唯一 |
| `claim_evidences` | 整数 | 声明与条款映射，以及生成时的引用快照 |
| `feedback` | UUID 字符串 | 实名/匿名意见、自动归因及处理状态 |
| `feedback_events` | 整数 | 不可覆盖的意见处理时间线 |
| `regression_cases` | 整数 | 从意见沉淀的原问题、情景和预期证据 |
| `query_logs` | 整数 | F18 所需的查询状态、耗时、命中和降级统计 |

## 3. 不变量与事务规则

1. 同一制度编号和版本不可重复。
2. 同一制度只允许一个 `active` 版本；启用新版和停用旧版必须在同一事务完成。
3. 已被回答引用的制度版本不得物理删除，只能停用，以保留历史证据快照。
4. 索引发布采用“内存完成全部嵌入 → 数据库事务写入向量与快照 → `is_current` 原子切换”的流程；失败回滚且不覆盖当前可用索引。
5. 回答保存生成时的知识库指纹。当前指纹不同或引用版本被停用时，答案判定为过期。
6. 每项正式声明至少关联一个经过校验的条款；全部声明无有效证据时不得保存为 `answer` 状态。
7. 匿名反馈不保存提交者姓名；反馈事件只追加，不修改或删除历史。
8. 情景槽位禁止保存身份证号、手机号、工资明细等个人敏感数据。
9. SQLite 外键必须开启；所有删除策略由外键和服务层共同校验。
10. 反馈保存 `client_session_id`、`primary_policy_id` 和不可由客户端覆盖的 `answer_snapshot`；即使原会话删除，治理记录仍保留。
11. `regression_cases.feedback_id` 唯一；只有已解决且最近一次复测通过的反馈可创建回归用例。

## 4. 索引和统计索引

- 制度：`policies.code`、`policy_versions(policy_id, status)`。
- 条款：`stable_anchor`、`policy_version_id`、`clause_number`、`text_sha256`。
- 问答：`conversation_id`、`knowledge_fingerprint`、`created_at`。
- 反馈：`client_session_id`、`primary_policy_id`、`status + created_at`、`auto_category`。
- 查询日志：`result_status + created_at`、`policy_id`、`is_degraded`。

嵌入向量以 `float32` 字节存入 `clauses.embedding`，维度由 `IndexSnapshot.embedding_model` 决定；读取时必须校验字节长度和模型一致性。

任务 3 增加 `answers.evidence_snapshot`、`evidence_coverage` 和 `degraded_reason`。证据快照保证正式回答与降级回答均可在历史中完整重放；正式声明仍必须通过 `claim_evidences` 关联不可变条款和版本快照。

任务 5 增加 `answers.clarification`、`source_answer_id` 和 `generation_kind`。澄清问题与选项随回答保存；推演和刷新生成新 Answer，并通过来源 ID 形成不可覆盖的回答谱系。`source_answer_id` 只作审计引用，不启用级联删除，完整会话删除仍由 `conversation_id` 统一处理。

任务 6 增加 `feedback.client_session_id`、`primary_policy_id` 和 `answer_snapshot`，并为 `regression_cases.feedback_id` 增加唯一约束。快照包含原问题与规范化问题，短追问复测可复用原上下文语义；反馈事件记录提交、状态变化、复测和固化全过程。
