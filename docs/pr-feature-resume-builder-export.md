# PR 说明：模块 A 后端与共享导出服务

- **base ← head**：`main` ← `feature/resume-builder-export`
- **提交**：`14b4fd9`（65 files changed, +5567 / -5）
- **创建入口**：<https://github.com/yunzhong200553/resume-match/compare/main...feature/resume-builder-export?quick_pull=1>
- **当前状态**：分支已推送到 GitHub；**PR 尚未创建**（需要仓库成员登录 GitHub 后在网页创建）

> 说明：本文件是 PR 描述的存档版本。分支推上去之后，任何人登录 GitHub 打开上面的链接，
> 把下面的「标题」与「正文」复制进表单即可创建 PR；创建后本文件可以删除。

## 标题

```text
feat(backend): 模块 A 后端与共享导出服务
```

## 正文

```markdown
## 功能范围

模块 A（简历构建与基础导出）+ 共享导出服务的后端实现。本轮不含前端与 Playwright（按项目计划分阶段推进）。

- 简历与版本：创建、列表、详情（含草稿与版本列表）、草稿保存与排序、不可变版本创建、版本快照查询
- 录入与拆分：分模块手动录入、文本粘贴规则拆分、文本型 PDF（PyMuPDF）/ DOCX（python-docx）导入；扫描件返回 `UNSUPPORTED_SCANNED_PDF`
- 共享导出服务：模板渲染 DOCX → LibreOffice Headless 转 PDF → 导出记录 → 授权下载；模块 A 与模块 B 使用同一组端点

## 接口变化

新增 13 个端点（前缀 `/api`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/resumes` | 创建简历（201，同时建空草稿） |
| GET | `/api/resumes` | 历史简历列表 |
| GET | `/api/resumes/{resumeId}` | 详情 + 当前草稿 + 版本列表 |
| POST | `/api/resumes/import` | 上传 PDF/DOCX，返回待确认结构 |
| POST | `/api/resumes/parse-text` | 拆分粘贴文本 |
| PUT | `/api/resumes/{resumeId}/draft` | 保存草稿与排序 |
| POST | `/api/resumes/{resumeId}/versions` | 从草稿创建不可变版本（201） |
| GET | `/api/resumes/{resumeId}/versions` | 版本列表 |
| GET | `/api/resume-versions/{versionId}` | 版本快照 |
| GET | `/api/export-templates` | 可用模板 |
| POST | `/api/resume-versions/{versionId}/exports` | 创建导出任务（201） |
| GET | `/api/exports/{exportId}` | 导出状态 |
| GET | `/api/exports/{exportId}/download` | 下载文件 |

补充错误码（README 7.1 未列举，已登记在 `docs/api-extensions.md`）：
`EXPORT_NOT_FOUND`(404)、`TEMPLATE_NOT_FOUND`(404)、`INTERNAL_ERROR`(500)、`HTTP_ERROR`(框架层错误)。

## 关键设计决定

1. **版本不可变是结构约束**：`ResumeVersion` 由 ORM `before_update` 事件强制，修改一律进草稿。
2. **`ResumeDocument` 为唯一公共契约**：camelCase、`extra="forbid"`、`order` 连续唯一，模块 B 直接复用。
3. **只建 A 需要的 4 张表**（resumes / resume_versions / drafts / export_records），`Analysis`/`Suggestion` 留给模块 B 的独立迁移，避免两人改同一迁移文件。
4. **导出模板 = 参考简历的脱敏占位版**：只取格式（A4、微软雅黑 16pt/10.5pt、色值 `#0F1115`），条目用制表位列对齐；参考简历原件不入库。
5. **分析适配层只提供 Protocol + Mock**，`ANALYSIS_PROVIDER=coze` 明确抛错，不存在“看着能跑但结果不对”的中间状态；模块 A 不注册分析路由，禁用分析能力后 A 全流程可用。
6. **隐私边界**：真实简历、上传件、导出产物、数据库、`.env` 全部在 `.gitignore` 内，日志不记完整简历内容。

## 测试结果

`cd backend && pytest` → **70 passed, 1 skipped**（skip 为需要 LibreOffice 的 PDF 用例）

| 编号 | 用例 | 结果 |
| --- | --- | --- |
| A-01 | 上传文本型 PDF | ✅ |
| A-02 | 上传 DOCX | ✅ |
| A-03 | 扫描版 PDF → `UNSUPPORTED_SCANNED_PDF` | ✅ |
| A-04 | 超 10 MB → `FILE_TOO_LARGE` | ✅ |
| A-05 | 草稿可继续修改、已建版本不变 | ✅ |
| A-06 | 模板导出内容与所选版本一致 | ✅ DOCX / ⏭ PDF（本机无 LibreOffice） |
| I-01 | 禁用分析能力后模块 A 仍可用 | ✅ |
| I-03 | 同版本 + 同模板 + 同格式结果一致 | ✅ |

另有契约校验、拆分规则（完整/缺失模块/乱序/重复标题/长文本/三行式）、Alembic 升降级等 60+ 用例。
额外人工验证：用真实简历跑通「导入 → 拆分 → 建版本 → 导出 DOCX」，导出结构与参考简历一致。

## 未包含 / 待办

- `frontend/`（React 页面）与 `e2e/`（Playwright）
- 模块 B 的 `/api/analyses`、`/api/suggestions` 与真实 Coze 接入
- 第二份 Word 模板（当前仅 `classic_single_column`）
- 本机未装 LibreOffice，PDF 端到端待装有该依赖的环境验证

## 评审关注点

- `docs/template-contract.md`：模板占位符与样式契约，第二份模板需要哪些额外样式
- `ResumeDocument` 当前 `extra="forbid"`，Coze 返回多余字段会被拒绝 —— 是否需要为模块 B 预留字段
- 错误码扩展是否可接受（`docs/api-extensions.md`）
```
