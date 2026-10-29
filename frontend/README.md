# frontend

React + TypeScript + Vite 前端，对应仓库 README 第 5 节技术栈与第 8 节页面定义。

当前实现提供完整的本地简历工作台：

- 来个简历闪填：上传 PDF/DOCX、粘贴简历文本，或从空白简历开始。
- 导入校对：自动提取基本信息、教育、实习/工作、项目和技能；结果先保存为草稿。
- 持续编辑：同一份内容可反复修改和保存，界面不再显示版本选择或 v1/v2。
- JD 分析与定向优化：服务端 DeepSeek 分析，显示总体、模块平均和逐条数字评分；仅简历模块和条目可拖动，整体适配度固定在顶部。
- 可恢复隐藏：排除不重要的模块和条目，不删除原文；点击保存后持久化。
- 确认式 AI 改写：按建议生成修改前后对比及整页预览，可手工校正、取消，确认后应用到独立 JD 副本；显式保存岗位排版，不覆盖基础资料。
- 岗位命名排版：同一份简历可保存多个独立排版，保存后自动进入导出中心；选择资料、岗位排版、模板和格式后导出，也可继续编辑已有排版。
- 分页预览：复用实际 PDF 渲染，标明每页开始与结束；Word 实际分页可能受本机字体和排版软件影响。
- 导出中心：选择模板、DOCX/PDF 格式并下载结果；缺少 LibreOffice 时会使用本地渲染器生成中文 PDF。

PDF 解析按视觉坐标重建阅读顺序，以兼容包含多列的常见简历版式。Vite 会将 `/api`
请求代理到本机 FastAPI 后端 `http://127.0.0.1:8000`。

## 本机启动

推荐双击根目录的 [start.cmd](../start.cmd)，自动构建并打开 `http://127.0.0.1:8000`。构建后的页面由 FastAPI 提供，不需要单独运行 Vite。密钥只放在被 Git 忽略的本机 `.env`，不要填入 `.env.example`。

以下是开发模式的手动启动方法：

先在仓库根目录启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

另开一个终端启动前端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。

## DeepSeek 配置

在仓库根目录的本机 `.env` 配置 `ANALYSIS_PROVIDER=deepseek`、`DEEPSEEK_API_KEY` 和可选的 `DEEPSEEK_MODEL`（默认 `deepseek-flash`），然后重启后端并刷新页面。不要将密钥放进 `VITE_*` 环境变量或前端代码。暴露过的密钥请撤销并重新生成。

JD 页会显示配置状态；必须勾选发送授权，才会将去除联系信息的经历和 JD 发往 DeepSeek。`ANALYSIS_PROVIDER=mock` 仅用于演示，明确标记固定数据，不支持真实改写。没有有效新密钥时不进行真实调用验证，也不会伪造分析成功。

## 当前使用的技术栈

| 用途 | 选型 |
| --- | --- |
| 构建 | Vite + TypeScript |
| 页面与状态 | React hooks |
| HTTP | Fetch + Vite API 代理 |
| 拖动排序 | 原生拖动 + 上下按钮 |
| 验证 | TypeScript 构建 + 浏览器交互检查，后端 pytest/模拟 HTTP |

## 需要对接的后端接口

- 当前简历：`/api/resumes`、`/api/resumes/{resumeId}/draft`
- 内部快照：`/api/resumes/{resumeId}/snapshot`，仅供分析/导出固定输入，普通保存不创建快照
- 导入与拆分：`/api/resumes/import`、`/api/resumes/parse-text`
- 导出：`/api/export-templates`、`/api/resume-versions/{versionId}/exports`、`/api/exports/{exportId}/download`
- 分析配置与评分：`/api/analyses/configuration`、`/api/analyses`
- AI 修改预览与确认：`/api/suggestions/{suggestionId}/rewrite`、`/api/suggestions/{suggestionId}/confirm`
- 实际分页预览：`/api/resume-preview`
- 命名岗位排版：`/api/resumes/{resumeId}/layouts`、`/api/resume-layouts/{layoutId}`
- 选中排版导出：`/api/resume-layouts/{layoutId}/exports`
- 独立副本 AI 确认：`/api/suggestions/{suggestionId}/preview-confirm`

本机开发时后端默认运行在 `http://127.0.0.1:8000`，
CORS 已放行 `localhost` 与 `127.0.0.1` 的任意端口。
