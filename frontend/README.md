# frontend（尚未开始）

React + TypeScript + Vite 前端，对应仓库 README 第 5 节技术栈与第 8 节页面定义。

**当前状态：占位目录，没有任何实现。** 后端（模块 A）与共享导出服务已完成，
前端可以基于 `/api` 接口独立开发，不会阻塞。

## 计划使用的技术栈

| 用途 | 选型 |
| --- | --- |
| 构建 | Vite + TypeScript |
| 路由 | React Router |
| 服务端状态 | TanStack Query |
| 拖动排序 | dnd-kit |
| 测试 | Vitest + Testing Library |

## 初始化方式（开始实现时执行）

```powershell
cd frontend
npm create vite@latest . -- --template react-ts
npm install react-router-dom @tanstack/react-query @dnd-kit/core @dnd-kit/sortable
```

## 需要对接的后端接口

- 简历与版本：`/api/resumes`、`/api/resumes/{resumeId}/draft`、`/api/resume-versions/{versionId}`
- 导入与拆分：`/api/resumes/import`、`/api/resumes/parse-text`
- 导出：`/api/export-templates`、`/api/resume-versions/{versionId}/exports`、`/api/exports/{exportId}/download`
- 尚未实现（模块 B）：`/api/analyses`、`/api/suggestions/{suggestionId}`

本机开发时后端默认运行在 `http://127.0.0.1:8000`，
CORS 已放行 `localhost` 与 `127.0.0.1` 的任意端口。
