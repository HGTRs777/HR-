# 数据库设计

## v2.0 制度漏洞扫描

- `policy_gap_scans`：记录定期/手动触发方式、执行状态、扫描范围、摘要、模型与起止时间。
- `policy_gap_issues`：从属于扫描批次，记录漏洞类别、严重度、标题、描述、整改建议、出现次数与扫描依据 JSON；批次删除时级联删除问题项。

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
| `employee_users` | 整数 | 员工登录账号及最小业务档案；部门、岗位、入职日期、状态、累计工龄、直属负责人、HRBP、年假额度/余额均可空，未配置时不得生成默认业务值 |
| `policies` | 整数 | 制度逻辑身份；制度编号唯一 |
| `policy_versions` | 整数 | 制度文件、解析错误及版本元数据；`policy_id + version` 唯一 |
| `clauses` | 整数 | 条款原文、位置、稳定锚点和向量；锚点唯一 |
| `index_snapshots` | 整数 | 知识库指纹、嵌入模型、切分器版本、构建状态及当前发布标记 |
| `conversations` | UUID 字符串 | 匿名浏览器会话及当前非敏感情景槽位 |
| `messages` | 整数 | 用户、助手和系统消息 |
| `answers` | UUID 字符串 | 一次结构化回答；保存问题类型、答案焦点、已验证主答案、资格判断、员工档案快照、检索证据快照、覆盖率、知识指纹、办事卡和降级状态 |
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
7. 匿名反馈不保存提交者姓名；实名反馈从当前已认证员工账号复制展示姓名与工号，不接受客户端自填身份；反馈事件只追加，不修改或删除历史。
8. 情景槽位禁止保存身份证号、手机号、工资明细等个人敏感数据。
9. SQLite 外键必须开启；所有删除策略由外键和服务层共同校验。
10. 反馈保存 `client_session_id`、`primary_policy_id` 和不可由客户端覆盖的 `answer_snapshot`；即使原会话删除，治理记录仍保留。
11. `regression_cases.feedback_id` 唯一；只有已解决且最近一次复测通过的反馈可创建回归用例。
12. 回答生成时保存登录员工档案快照；已配置档案字段覆盖客户端同名情景值，聊天文本不得用于推断员工属性。
13. 空档案字段保持 `NULL` 并在影响当前判断时显示“未配置”，不得用默认部门、状态、工龄或假期余额补齐。
14. `hire_date` 只用于计算本公司司龄；`tenure_years` 是独立的累计工作年限业务字段，可能包含入职前经历，禁止由入职日期直接回填。
15. 回答中的员工个性化数字可由已保存的档案快照证明，但制度资格、档位和流程声明仍必须关联当前启用条款并通过原有语义门槛。
16. `primary_answer` 必须等于第一条已验证声明；`question_type/answer_focus` 只能决定展示优先级，不能作为制度事实或证据来源。

## 4. 索引和统计索引

- 制度：`policies.code`、`policy_versions(policy_id, status)`。
- 条款：`stable_anchor`、`policy_version_id`、`clause_number`、`text_sha256`。
- 问答：`conversation_id`、`knowledge_fingerprint`、`created_at`。
- 反馈：`client_session_id`、`primary_policy_id`、`status + created_at`、`auto_category`。
- 查询日志：`result_status + created_at`、`policy_id`、`is_degraded`。

嵌入向量以 `float32` 字节存入 `clauses.embedding`，维度由 `IndexSnapshot.embedding_model` 决定；读取时必须校验字节长度和模型一致性。

阶段 6 不新增数据库表或列。模拟制度目录以 `demo_policy_catalog.py` 作为结构化源数据，导入时仍落入既有 `policies → policy_versions → clauses` 模型。制度名称、编号、类别、版本和生效日期继续使用既有字段；适用对象、适用部门、资格/排除条件、时限、上限、材料、步骤、提交对象、审批角色和 HR 处理角色以统一标签写入每条 `clauses.text`，因此旧版 reader、稳定锚点、引用关系和声明—证据校验保持兼容。

任务 3 增加 `answers.evidence_snapshot`、`evidence_coverage` 和 `degraded_reason`。证据快照保证正式回答与降级回答均可在历史中完整重放；正式声明仍必须通过 `claim_evidences` 关联不可变条款和版本快照。

任务 5 增加 `answers.clarification`、`source_answer_id` 和 `generation_kind`。澄清问题与选项随回答保存；推演和刷新生成新 Answer，并通过来源 ID 形成不可覆盖的回答谱系。`source_answer_id` 只作审计引用，不启用级联删除，完整会话删除仍由 `conversation_id` 统一处理。

任务 6 增加 `feedback.client_session_id`、`primary_policy_id` 和 `answer_snapshot`，并为 `regression_cases.feedback_id` 增加唯一约束。快照包含原问题与规范化问题，短追问复测可复用原上下文语义；反馈事件记录提交、状态变化、复测和固化全过程。

员工画像改造增加 `employee_users.job_title`、`hire_date`、`employee_status`、`tenure_years`、`direct_manager`、`hrbp`、`annual_leave_entitlement` 和 `annual_leave_balance`，并将原 `department` 改为可空。`answers.employee_profile_snapshot` 保存生成当时使用的业务档案，保证历史判断可审计。
