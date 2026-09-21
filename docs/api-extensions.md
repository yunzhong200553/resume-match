# 接口契约补充说明

统一响应与错误码以 README 第 7.1 节为准。实现过程中遇到了 README 未列举、但必须明确区分的场景，
这里补充登记，避免前后端对返回码的理解不一致。

## 1. 新增错误码

| 错误码 | HTTP 状态 | 场景 | 为什么不能复用既有码 |
| --- | --- | --- | --- |
| `EXPORT_NOT_FOUND` | 404 | 导出记录不存在（`GET /api/exports/{id}`、下载接口） | `VERSION_NOT_FOUND` 语义是简历版本，用它会让前端误判为版本问题 |
| `TEMPLATE_NOT_FOUND` | 404 | `templateId` 不存在，或模板文件缺失 | 同上，属于资源不存在而不是请求格式错误 |
| `INTERNAL_ERROR` | 500 | 未预期异常（已记日志，不含个人信息） | README 的 500 只有 `EXPORT_FAILED`，无法覆盖普通服务端异常 |
| `HTTP_ERROR` | 同原状态码 | 框架层错误（路由不存在、方法不允许等） | 保证这些路径也返回 `{error, requestId}` 结构，而不是 FastAPI 默认的 `{"detail": ...}` |

`VALIDATION_ERROR` 的 `details.errors` 会给出 Pydantic 校验明细：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数校验失败。",
    "details": {
      "errors": [
        {"loc": ["body", "document", "sections", "1", "order"], "msg": "...", "type": "value_error"}
      ]
    }
  },
  "requestId": "req_xxx"
}
```

## 2. 实现的接口清单

模块 A 与共享导出服务共实现 13 个端点：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/resumes` | 创建简历（201），同时创建空草稿 |
| GET | `/api/resumes` | 历史简历列表（按最近编辑倒序） |
| GET | `/api/resumes/{resumeId}` | 简历详情 + 当前草稿 + 版本列表 |
| POST | `/api/resumes/import` | 上传 PDF/DOCX，返回待确认结构（200） |
| POST | `/api/resumes/parse-text` | 拆分粘贴文本（200） |
| PUT | `/api/resumes/{resumeId}/draft` | 保存草稿与排序 |
| POST | `/api/resumes/{resumeId}/versions` | 从草稿创建不可变版本（201） |
| GET | `/api/resumes/{resumeId}/versions` | 版本列表 |
| GET | `/api/resume-versions/{versionId}` | 版本快照 |
| GET | `/api/export-templates` | 可用模板列表 |
| POST | `/api/resume-versions/{versionId}/exports` | 创建导出任务（201） |
| GET | `/api/exports/{exportId}` | 导出状态 |
| GET | `/api/exports/{exportId}/download` | 下载文件（非 JSON，直接返回文件流） |

未实现的接口：`/api/analyses*`、`/api/suggestions*`（模块 B）。

## 3. 约定补充

- 所有响应带 `X-Request-Id` 头；客户端可用同名请求头指定，服务端会沿用。
- 创建类接口返回 201，查询类与计算类返回 200。
- 下载文件名形如 `<简历标题>-v<版本号>.<扩展名>`，内容来自不可变版本。
- 文件上传同时校验扩展名、MIME 与大小（≤ 10 MB），通用类型
  （`application/octet-stream`、`application/zip`）被接受，但要能通过解析校验。
- `ResumeDocument` 使用 `extra="forbid"`：任何契约外字段都会被拒绝，包括 Coze 返回的多余字段。
