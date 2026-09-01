# 公司 HR 制度智能问答

基于 Vue 3、Flask、SQLAlchemy、SQLite、混合检索与 DeepSeek 的企业 HR 制度 RAG 助手（v2.0）。

v2.0 员工端优先复用当前登录员工的部门、岗位、入职日期、状态、累计工龄、负责人、HRBP 和真实年假余额；只反向确认仍缺失且会改变结论的条件，条件齐全后输出办理清单及可点击制度依据。HR 端会定期联合扫描启用知识库、匿名问答结果与制度反馈，自动发现制度缺失、规则不清、冲突、疑似过期及高频未回答问题，也支持手动立即扫描。

员工工作台采用可折叠历史会话侧栏与双列主工作区：左侧聊天，右侧情景沙盘和办理清单；意见记录与制度原文分别通过弹窗按需查看，减少主页面平铺模块。

制度漏洞扫描默认每 24 小时运行一次，可通过 `POLICY_GAP_SCAN_INTERVAL_HOURS` 调整；未配置 DeepSeek 时自动使用本地规则分析，扫描结果仍会持久化并展示。

项目继续采用传统的前后端分开运行方式：

- 后端：`http://127.0.0.1:5000`
- 前端：`http://127.0.0.1:5173`

## 推荐交付运行

首次初始化、生产演示启动与停止：

```powershell
.\scripts\setup-demo.ps1
.\scripts\start-demo.ps1
.\scripts\stop-demo.ps1
```

详细要求见 [配置与运行说明](docs/configuration-guide.md)，业务操作见 [用户手册](docs/user-manual.md)。

演示账号（员工端与 HR 端登录时都需要完成页面上的一次性滑动拼图验证）：

- 员工：`staff` / `88888888`
- HR：`admin` / `88888888`

初始化会生成员工查询记录、意见箱投递记录、HR 处理进度和数据洞察样例。

## 本地开发启动

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m flask --app run.py db upgrade
.\.venv\Scripts\python.exe -m flask --app run.py seed-policies
.\.venv\Scripts\python.exe -m flask --app run.py seed-demo-data
.\.venv\Scripts\python.exe -m flask --app run.py build-index
.\.venv\Scripts\python.exe run.py
```

### 前端

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

默认不提交任何密钥、SQLite 数据库、上传文件、模型缓存或前端构建产物。DeepSeek 未配置或调用异常时，问答接口进入本地证据降级模式。

`build-index` 首次运行会下载 `BAAI/bge-small-zh-v1.5`。可用 `flask --app run.py evaluate-retrieval` 运行 37 题 Recall@3 验收。内置制度统一标记为“实训模拟企业 HR 制度知识库”，仅用于教学与功能验证，不代表任何真实企业的正式制度或承诺。

## 基础检查

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest

cd ..\frontend
npm run typecheck
npm run test:run
npm run build
```

服务启动后可设置 `E2E_ADMIN_USERNAME`、`E2E_ADMIN_PASSWORD` 并在 `frontend` 运行 `npm run test:e2e`，执行 Microsoft Edge 桌面与移动端 Playwright 回归。

接口、数据模型、测试报告和阶段交接要求见 `docs/`。

任务 6 的意见复测复用现有混合检索，不调用生成模型；回归用例只允许从“已解决且最近复测通过”的意见生成。完整契约和最终验收结果见 `docs/api-contract.md` 与 `docs/development-handoff.md`。
