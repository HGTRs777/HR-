# F01–F19 需求追踪矩阵（v2.0）

状态定义：`骨架`表示契约、实体或页面占位已建立；`后端完成`表示服务、接口和后端测试已验收，配套页面仍在计划任务中；`完成`表示前后端及测试均验收。

| ID | 功能 | 后端/数据 | 前端 | 计划任务 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| F01 | 中文自然语言问答 | `/chat/query`、Answer 已完成 | 员工对话区已完成 | 3、4 | 完成 |
| F02 | 多轮对话 | 最近 6 轮、追问独立检索已完成 | 会话历史和追问已完成 | 3、4 | 完成 |
| F03 | 可点击证据链 | 声明证据快照、reader 已完成 | 稳定锚点定位与原文高亮已完成 | 3、4 | 完成 |
| F04 | 可信生成 | JSON Schema、逐声明校验、低分拒答已完成 | 覆盖率、拒答和降级状态已完成 | 3、4 | 完成 |
| F05 | 会话历史 | 新建、列表、详情、删除及隔离已完成 | 会话新建、切换和删除已完成 | 3、4 | 完成 |
| F06 | 管理认证 | session、密码哈希、CSRF 已完成 | 登录、退出和登录态控制已完成 | 2、4 | 完成 |
| F07 | 制度管理 | 四类解析、上传、预览、启停、约束删除已完成 | 制度管理页面已完成 | 2、4 | 完成 |
| F08 | 版本管理 | 编号版本唯一、单一启用版本事务已完成 | 版本状态和生效日期已完成 | 2、4 | 完成 |
| F09 | 索引管理 | 指纹、过期检测、原子重建已完成 | 状态、统计和重建操作已完成 | 2、4 | 完成 |
| F10 | 检索测试 | BGE + BM25 + RRF Top 5 已完成 | 三路分数与名次页面已完成 | 2、4 | 完成 |
| F11 | 稳定性 | 健康、索引回滚、DeepSeek 本地证据降级已完成 | 服务、过期、拒答和降级标识已完成 | 2、3、4 | 完成 |
| F12 | 情景澄清 | 条件识别、clarification 持久化已完成 | 澄清选项与条件标签已完成 | 3、5 | 完成 |
| F13 | 情景推演 | `/chat/replay`、情景差异与回答谱系已完成 | 条件沙盘、重放和差异摘要已完成 | 5 | 完成 |
| F14 | 反向提问与办理清单 | 按事项逐项澄清、动态 scenario_form、证据约束 checklist 已完成 | 所需条件表、办理清单和可点击依据已完成 | v2.0 | 完成 |
| F15 | 答案保鲜 | 指纹过期判定、refresh 和历史保留已完成 | 过期提示、历史版本和刷新入口已完成 | 5 | 完成 |
| F16 | 共创意见箱 | 回答归属校验、快照、匿名规则已完成 | 实名/匿名提交与本人时间线已完成 | 5、6 | 完成 |
| F17 | 反馈闭环 | 状态机、只追加事件、复测、唯一回归用例已完成 | HR 筛选、处理、复测、固化及员工结果可见已完成 | 5、6 | 完成 |
| F18 | 数据洞察 | QueryLog/Feedback 聚合及过滤已完成 | 指标、排行与反馈分布仪表盘已完成 | 6 | 完成 |
| F19 | AI 制度漏洞扫描 | 定期/手动扫描、AI/规则降级、批次与漏洞持久化已完成 | 风险列表、扫描依据与建议动作已完成 | v2.0 | 完成 |

每个后续任务完成时必须将对应行改为“完成”，并在交接文档中附测试命令和结果。

## 任务 7 最终证据索引

| ID | 接口/服务证据 | 页面证据 | 自动化与验收证据 |
| --- | --- | --- | --- |
| F01 | `POST /chat/query` | `EmployeeWorkbenchView.vue` 对话区 | `test_valid_claim_and_evidence_are_persisted`、Playwright 员工流程 |
| F02 | 多轮规范化与最近 6 轮上下文 | 会话消息与追问输入 | `test_follow_up_uses_previous_question_and_last_messages` |
| F03 | `GET /policies/{version_id}/reader` | 制度阅读器稳定锚点高亮 | `test_upload_version_activation_reader_and_index`、员工组件测试 |
| F04 | 声明—证据校验与拒答 | 证据覆盖率、拒答/降级提示 | 伪造证据、数字幻觉、任务 7 JSON 契约测试 |
| F05 | `/conversations/*` | 会话新建、切换、删除 | `test_conversations_are_isolated_and_deletable` |
| F06 | `/admin/auth/*` | HR 登录/退出 | `test_admin_authentication_required_and_session`、Playwright HR 流程 |
| F07 | `/admin/policies`、reader | 制度上传、预览、删除 | 上传/解析/受约束删除测试 |
| F08 | `/admin/policy-versions/*` | 版本状态与生效日期 | 重复版本、单一启用版本测试 |
| F09 | `/admin/index/*` | 索引状态与原子重建 | 索引过期、回滚、并发重建 409 测试 |
| F10 | `/admin/search/test` | Top 5 三路分数表 | `Recall@3 100% (25/25)`、检索接口测试 |
| F11 | `/health`、降级链路 | 服务/拒答/降级状态 | 模型缺失、非法 JSON、模拟超时、索引过期测试 |
| F12 | clarification 持久化 | 澄清选项 | 工龄/员工状态澄清测试 |
| F13 | `POST /chat/replay` | 情景沙盘和变化摘要 | 推演差异、无变化及跨会话测试 |
| F14 | `scenario_form`、证据约束 `checklist` | 反向提问、条件表与办理清单 | `test_reverse_questions_collect_conditions_then_return_checklist` |
| F15 | `POST /answers/{id}/refresh` | 过期提示、版本历史、刷新 | 过期刷新与当前答案冲突测试 |
| F16 | `POST/GET /feedback` | 实名/匿名意见及本人时间线 | 快照、匿名、实名规则和会话隔离测试 |
| F17 | 管理反馈、复测和回归接口 | HR 状态流、复测和固化 | 状态机、事件追加、复测及唯一回归测试 |
| F18 | `GET /admin/analytics` | 洞察指标、排行和筛选 | 聚合/空数据/过滤测试、Playwright HR 流程 |
| F19 | `/admin/policy-gaps/*`、后台周期扫描 | AI 制度漏洞扫描区 | `test_policy_gap_scan_persists_ai_findings`、管理员组件测试 |

最终命令、12 场景映射和异常验证结果见 `docs/test-report.md`。
