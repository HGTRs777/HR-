# 配置与运行说明

## 1. 环境要求

- Windows 10/11 与 PowerShell 5.1+
- Python 3.11+、Node.js 20+、npm
- 首次构建真实索引时可访问 Hugging Face，或本机已有 `BAAI/bge-small-zh-v1.5` 缓存

项目始终采用前后端分离运行：Waitress API 位于 `127.0.0.1:5000`，Vite Preview 位于 `127.0.0.1:5173`。

## 2. 首次初始化

```powershell
cd C:\Users\29919\Desktop\程序设计实训\公司HR制度智能问答
python -m venv backend\.venv
.\scripts\setup-demo.ps1
```

脚本会安装依赖、复制缺失的 `.env`、执行全部数据库迁移、幂等导入五类示例制度、构建 BGE 索引、创建 HR 管理员并构建前端。复制配置后必须将 `backend/.env` 中的 `SECRET_KEY` 改为随机长字符串；DeepSeek 密钥可留空，系统会进入本地证据降级模式。

重复初始化时可使用：

```powershell
.\scripts\setup-demo.ps1 -SkipAdminCreation
```

可选参数 `-SkipDependencyInstall` 和 `-SkipIndexBuild` 只应在依赖与索引已经可用时使用。

## 3. 一键演示

```powershell
.\scripts\start-demo.ps1
```

脚本会检查 5000/5173 端口、执行迁移、构建前端、以隐藏窗口启动 Waitress 与 Vite Preview，并轮询两个服务。只有 API 健康接口和前端首页同时返回成功才会报告“Demo is ready”。日志保存在被 Git 忽略的 `.runtime/`。

停止本次脚本记录的进程：

```powershell
.\scripts\stop-demo.ps1
```

停止脚本同时核对 PID 和启动时间，若 PID 已被系统复用，会拒绝终止不相关进程。

## 4. 开发运行

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

两个命令分别占用一个终端，后端使用 Flask 开发服务器，前端使用 Vite 开发服务器。开发模式不能替代最终 Waitress + Preview 演示验收。

## 5. 关键配置

| 变量 | 用途 | 默认/要求 |
| --- | --- | --- |
| `SECRET_KEY` | 管理员 Session 签名 | 必须替换示例值 |
| `DATABASE_URL` | SQLAlchemy 数据库 | `sqlite:///hr_policy.db` |
| `FRONTEND_ORIGINS` | 凭据 CORS 白名单 | 仅本机 5173 |
| `DEEPSEEK_API_KEY` | 在线结构化生成 | 可空；空时降级 |
| `DEEPSEEK_MODEL` | 模型名 | `deepseek-v4-flash` |
| `DEEPSEEK_TIMEOUT_SECONDS` | 模型超时 | 30 秒 |
| `EMBEDDING_MODEL` | 中文嵌入模型 | `BAAI/bge-small-zh-v1.5` |
| `UPLOAD_MAX_MB` | 制度文件上限 | 10 MB |
| `VITE_API_BASE_URL` | 前端 API 基址 | `http://127.0.0.1:5000/api/v1` |

密钥、管理员密码、SQLite 文件、上传文件和模型缓存均不得提交到版本库。

## 6. 验证命令

```powershell
.\scripts\check-foundation.ps1
```

该脚本依次运行 Pytest、Python 依赖检查、Alembic 当前版本/漂移检查、TypeScript strict、Vitest 和生产构建。

服务启动且已准备测试管理员后，可执行 Playwright：

```powershell
$env:E2E_ADMIN_USERNAME='你的管理员用户名'
$env:E2E_ADMIN_PASSWORD='你的管理员密码'
cd frontend
npm run test:e2e
```

Playwright 使用本机 Microsoft Edge，覆盖桌面和移动端；凭据只从进程环境读取。
