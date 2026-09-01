# 检索与问答评测集

阶段 6 已在 `backend/data/retrieval_evaluation.json` 扩充为 37 条评测问题，覆盖 15 类“实训模拟企业 HR 制度知识库”制度。每条记录包含：

- `question`
- `policy_code`
- `clause_number`

自动评测不得调用外网模型；DeepSeek 在线检查使用单独、显式启用的冒烟测试。
