# 检索与问答评测集

任务 2 已在 `backend/data/retrieval_evaluation.json` 加入 25 条评测问题。每条记录包含：

- `question`
- `policy_code`
- `clause_number`

自动评测不得调用外网模型；DeepSeek 在线检查使用单独、显式启用的冒烟测试。
