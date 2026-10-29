# 简历智造——ResumeMatch

简历智造（ResumeMatch） 是一个面向求职场景的简历构建与职位描述（Job Description，以下简称 JD）匹配系统。系统支持从表单、文本型 PDF 或 DOCX 中录入简历，将内容拆分为结构化条目，并根据目标 JD 分析匹配程度、提供不虚构事实的优化建议，最终导出 Word 或 PDF 简历。

本项目为两人协作的软件工程实践项目，首版面向中文简历、单用户和本机 Edge 桌面端，不包含账号系统与公网部署。

**当前交互：同一份简历反复编辑和保存，不再操作 v1/v2。** JD 分析使用服务端 DeepSeek API；必须配置新密钥，未配置或调用失败时明确提示，不会用 Mock 结果冒充 AI。旧的版本 API 保留兼容，快照仅用于固定分析/导出时的输入，不是日常编辑入口。

### Windows 一键启动

安装 Python 3.10+ 和 Node.js（20.19+ 或 22.12+）后，双击根目录的 [start.cmd](start.cmd)。

- 自动检查虚拟环境和依赖，仅在缺失时创建或安装。
- 构建前端，由一个本地服务同时提供页面和 API，无需分别开启前后端。
- 服务就绪后自动打开 `http://127.0.0.1:8000`，使用期间保留服务窗口。
- 再次运行会复用已就绪的服务；端口被其他程序占用时明确报错，不结束其他进程。
- 密钥继续从本机 `.env` 读取，不会被写进前端构建产物。
- 可执行 `.\start.cmd -NoBrowser` 启动而不自动打开浏览器。开发时仍可使用 Vite 的 `5173` 端口。

### 岗位排版与导出

基础简历与 JD 排版独立：在 JD 工作台调整顺序、隐藏条目或确认 AI 改写，不会覆盖基础资料。整体适配度固定在组件栏顶部，不提供拖动或上下移动按钮。

填写“岗位排版名称”（例如“后端工程师｜某公司”），点击“保存排版并前往导出”。名称可从 JD 中明确的“岗位名称/职位名称”等行建议，也可手动填写。保存后进入导出中心并自动选中该排版。

导出中心可以选择“简历资料”和该资料下的“岗位排版”，也可以选择基础简历。预览和 DOCX/PDF 导出使用所选排版的已保存内容，下载文件名包含岗位名称。点击“在 JD 工作台继续编辑”后，保存会更新同一套排版；“从基础资料新建排版”可创建另一个岗位排版。同一份资料下的排版不能重名，过期保存返回冲突而不静默覆盖。

### 配置真实 AI

1. 将仓库根目录的 `.env.example` 复制为本机 `.env`。
2. 设置 `ANALYSIS_PROVIDER=deepseek`、`DEEPSEEK_API_KEY=<在本机填写新密钥>`。
3. 默认模型为 `deepseek-flash`，可用 `DEEPSEEK_MODEL` 修改；请求超时由 `DEEPSEEK_TIMEOUT_SECONDS` 控制（默认 120 秒）。
4. 重启后端并刷新前端。JD 页面显示配置状态；勾选发送授权后才能开始分析。
5. 已在聊天或截图中暴露的密钥应立即撤销，切勿写入前端、README、测试或提交记录。

请求遵循 [DeepSeek 官方首次调用文档](https://api-docs.deepseek.com/zh-cn/) 的 `/chat/completions` 与 JSON 输出格式。评分和建议并行调用；“交给 AI 改写并预览”会再调用一次，产生 API 费用。分析输入只包含目标岗位与经历模块，基本信息中的姓名、电话、邮箱、城市不会发送，正文和 JD 中的电话、邮箱也会过滤。**经历中的学校、公司等仍会发送给 DeepSeek，使用前请核对授权。**

`ANALYSIS_PROVIDER=mock` 仅用于开发演示，页面明确标记固定数据，不能生成真实 AI 改写。自动化测试使用模拟 HTTP 响应，不消耗 API 额度。

## 1. 项目目标

- 降低简历创建、整理和格式调整成本。
- 将非结构化简历转换为可编辑、可排序、可复用的结构化数据。
- 根据不同 JD 展示简历条目的相关程度和缺失要求。
- 在不虚构技能、经历和成果的前提下辅助用户改进表达。
- 使用同一导出服务生成普通简历和针对特定 JD 优化后的简历。
- 持续更新同一份简历，保存分析记录；AI 修改只有确认后才替换正文。

## 2. 项目范围

- 中文简历和中文 JD。
- 分模块手动录入。
- 文本型 PDF、DOCX 文件导入，单文件最大 10 MB。
- 简历结构化拆分、人工校正和可反复编辑的当前内容。
- JD 总体及逐条 0–100 数字评分、缺失要求和改进建议。
- 模块排序和模块内条目排序。
- 两个人工提供的 Word 模板。
- DOCX 与 PDF 导出。
- SQLite 本地持久化。

## 3. 业务模块

系统由两个独立业务闭环和一个共享导出服务组成。导出能力不单独作为业务模块。

### 3.1 模块 A：简历构建与基础导出

负责人：A1。

业务流程：

```text
创建简历 -> 手动录入或文件拆分 -> 校正编辑 -> 保存简历（可反复修改） -> 导出普通简历
```

功能定义：

1. 创建简历：新建简历名称和基础信息。
2. 手动录入：通过分模块表单新增、编辑和删除条目。
3. 文件导入：从文本型 PDF 或 DOCX 提取文本并拆分。
4. 拆分校正：用户确认和修正识别结果后保存。
5. 持续编辑：保存更新同一份内容，不创建用户可见的新版本。
6. 基础导出：自动保存当前内容，按模板和文件格式导出。

简历模块包括：

- 基本信息。
- 教育经历。
- 工作或实习经历。
- 项目经历。
- 技能、证书和奖项。
- 用户自定义模块。

拆分采用规则优先策略，根据中文模块标题、联系方式、日期区间等特征识别结构。所有结果均允许人工修正。无法提取文字时，系统提示扫描件暂不支持，并保留用户已填写的数据。

### 3.2 模块 B：JD 匹配与定向优化导出

负责人：A2。

业务流程：

```text
打开当前简历 -> 输入 JD 并授权 -> AI 分析 -> 排序/隐藏/编辑 -> AI 改写预览 -> 确认替换 -> 保存命名排版 -> 导出中心选择排版
```

功能定义：

1. 当前内容：使用独立的 JD 排版副本，分析时固定后台输入快照，不重复上传和拆分、不覆盖基础资料。
2. JD 输入：录入目标岗位的完整职位描述。
3. 匹配分析：展示 0-100 总分、四维分数和每个可见简历条目的独立数字评分及依据；模块分显示已评分条目的平均分。旧记录缺少数字时显示“未评分”，不将高/中/低伪造为数字。
4. 缺失分析：展示 JD 要求但当前简历未体现的关键词或能力。
5. 内容建议：对照展示原文、建议文本和修改理由。
6. 建议确认：AI 按建议改写后先展示前后对比和整页效果；可校正或取消，只有“同意并替换”才应用到当前排版，之后显式保存命名排版。基础资料不被修改，原文已变化时拒绝过期替换。
7. 拖动调整：仅调整简历模块顺序和同一模块内条目顺序，同时提供上下移动按钮；整体适配度固定显示。隐藏模块/条目仅排除预览、分析与导出，保留全文并可恢复。
8. 持续保存：点击“保存排版并前往导出”持久化当前岗位排版；已有排版可反复编辑，基础资料独立保留。评分属于上次分析，不随编辑自动升高。
9. 定制导出：调用共享导出服务生成针对该 JD 的 DOCX 或 PDF。

DeepSeek Provider 并行完成契合度评分与条目建议，不参与文件解析。数值评分来自 AI；总分由后端对四维分数求和，高/中/低档位也按同一套 80/60 阈值计算，避免模型算错总分或把 55 分误标为中适配。模型输出仍须通过结构校验，且逐条数字评分必须完整、不重复，分数范围和固定权重不可越界。改写禁止添加未经证实的事实，并拦截原文/字段中不存在的数字；用户仍需核对事实，缺失能力只能作为提示。

### 3.3 共享导出服务

负责人：A1主责，A2通过统一接口调用。

共享服务接收 `ResumeVersion ID`、模板 ID 和导出格式，不区分版本来自模块 A 还是模块 B。相同版本、模板和格式应生成一致结果。

导出流程：

1. 读取不可变的 `ResumeVersion` 快照。
2. 将结构化字段渲染到人工提供的 Word 模板。
3. 生成可编辑的 DOCX 文件。
4. 使用 LibreOffice Headless 将 DOCX 转换为 PDF。
5. 保存导出记录并提供下载。

## 4. 系统架构

```mermaid
flowchart LR
		U[Edge 浏览器] --> F[React 前端]
		F --> API[FastAPI REST API]
		API --> DB[(SQLite)]
		API --> P[PDF/DOCX 解析服务]
		API --> A[分析协调器]
		A --> M[Mock Provider]
		A --> C1[DeepSeek 契合度评分]
		A --> C2[DeepSeek 条目建议与确认式改写]
		API --> E[共享导出服务]
		E --> T[Word 模板]
		E --> L[LibreOffice]
```

建议采用 Monorepo：

```text
resume-match/
├─ frontend/                 # React + Vite 简历工作台（见 frontend/README.md）
├─ backend/                  # FastAPI 后端（模块 A 已实现）
├─ e2e/                      # 端到端测试（占位，见 e2e/README.md）
├─ docs/                     # 需求、设计、接口和测试报告
│  └─ pr/                    # PR 描述存档
├─ private/                  # 本机私人文件（真实简历原件等，不入库）
├─ .env.example              # 环境变量示例，不包含真实密钥
├─ resume-match.code-workspace  # VS Code 工作区（解释器、测试与排除规则）
└─ README.md
```

模块之间以 REST API 和 `ResumeVersion ID` 对接，不直接访问对方内部服务。`ResumeDocument` 是解析、分析、编辑和导出的唯一公共数据契约。

## 5. 技术栈

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite | 页面与交互 |
| 路由 | React Router | 模块和页面路由 |
| 服务端状态 | TanStack Query | API 请求、缓存和错误状态 |
| 拖动排序 | dnd-kit | 模块和条目排序 |
| 后端 | Python + FastAPI | REST API 与业务服务 |
| 数据校验 | Pydantic | API 和 AI 输出校验 |
| ORM | SQLAlchemy | 数据持久化 |
| 数据迁移 | Alembic | SQLite 表结构版本管理 |
| 数据库 | SQLite | 本机简历、版本和分析历史 |
| PDF 提取 | PyMuPDF | 文本型 PDF 内容提取 |
| Word 处理 | python-docx | DOCX 读取和生成 |
| PDF 导出 | LibreOffice Headless | DOCX 转 PDF |
| AI | DeepSeek API / HTTPX | JD 匹配、数字评分与确认式改写 |
| 后端测试 | pytest + HTTPX | 单元测试和 API 测试 |
| 前端测试 | Vitest + Testing Library | 组件和交互测试 |
| 端到端测试 | Playwright | Edge/Chromium 主流程测试 |

## 6. 核心数据定义

### 6.1 ResumeDocument

```json
{
	"basicInfo": {
		"name": "张三",
		"phone": "13800000000",
		"email": "example@example.com",
		"nativePlace": "浙江杭州",
		"birthDate": "2002-06",
		"jobTarget": "后端开发工程师"
	},
	"sections": [
		{
			"id": "section_project",
			"type": "project",
			"title": "项目经历",
			"order": 0,
			"items": [
				{
					"id": "item_project_1",
					"order": 0,
					"fields": {
						"projectName": "ResumeMatch",
						"role": "后端开发",
						"startDate": "2026-09",
						"endDate": "2026-12"
					},
					"content": "负责简历解析、版本管理和导出服务。"
				}
			]
		}
	]
}
```

约束：

- section 和 item 的 ID 创建后保持稳定。
- `order` 为从 0 开始的整数，同一层级内不得重复。
- `type` 允许 `education`、`experience`、`project`、`skill`、`award`、`custom`。
- 当前内容（`Draft`）可反复修改；分析/导出内部快照不可变，旧接口仍兼容。
- section 与 item 支持 `hidden: true`，隐藏不删除数据；输出前会过滤并重新连续排序。

### 6.2 持久化实体

| 实体 | 关键字段 | 说明 |
| --- | --- | --- |
| Resume | id、title、createdAt、updatedAt | 一份简历的逻辑主体 |
| ResumeVersion | id、resumeId、version、parentVersionId、source、document | 不可变 JSON 快照 |
| Draft | id、resumeId、baseVersionId、document、updatedAt | 可变编辑内容 |
| ResumeLayout | id、resumeId、name、jdText、document、analysisId、updatedAt | 独立命名的岗位排版，可更新，不覆盖基础草稿 |
| Analysis | id、resumeVersionId、jdText、status、overallScore | 一次 JD 分析 |
| Suggestion | id、analysisId、sectionId、itemId、original、suggested、status | 条目建议 |
| ExportRecord | id、resumeVersionId、templateId、format、status、filePath | 导出记录 |

`ResumeVersion.source` 取值：

- `manual`：手动录入。
- `import`：PDF 或 DOCX 文件拆分。
- `optimized`：根据 JD 优化形成的新版本。

## 7. API 接口定义

统一前缀为 `/api`，请求和响应采用 JSON；文件上传使用 `multipart/form-data`，文件下载除外。FastAPI 自动生成 Swagger 文档。

PDF/DOCX 导入的完整接入流程、接口参数、数据结构和 JSON 示例见 [简历导入 API 开发者文档](docs/简历导入接口/文档目录.md)。

JD 输入、契合度评分和条目建议的基础契约见 [JD 分析 API 开发者文档](docs/JD分析接口/文档目录.md)。新增当前编辑工作流接口如下：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| PUT | `/api/resumes/{resumeId}/draft` | 反复保存当前简历，不创建新版本 |
| POST | `/api/resumes/{resumeId}/snapshot` | 内部分析/导出快照；内容未改变时复用 |
| GET | `/api/analyses/configuration` | 配置与演示状态，不返回密钥 |
| POST | `/api/suggestions/{suggestionId}/rewrite` | `{currentContent, document?}`，可传独立 JD 副本，返回 `{original, rewritten, explanation}`，不修改基础资料 |
| POST | `/api/suggestions/{suggestionId}/preview-confirm` | `{original, replacement, document}`，确认建议并返回更新后的排版副本，不覆盖基础草稿 |
| POST | `/api/suggestions/{suggestionId}/confirm` | 兼容原基础草稿流程：`{original, replacement, document, expectedUpdatedAt}`，过期请求返回 409 |
| GET / POST | `/api/resumes/{resumeId}/layouts` | 列出 / 创建当前资料下的命名排版 |
| GET / PUT | `/api/resume-layouts/{layoutId}` | 读取 / 更新排版；更新需 `expectedUpdatedAt` |
| POST | `/api/resume-layouts/{layoutId}/exports` | 按已保存排版生成 DOCX/PDF，文件名包含岗位名称 |
| GET | `/api/health` | 一键启动程序使用的服务就绪检查 |
| POST | `/api/resume-preview` | `{document, templateId}`，返回 `{pageCount, pages: [{pageNumber, image, width, height}]}` |

分页预览与 PDF 导出共享渲染流程，临时预览文件自动清理，不新增简历或导出记录。未安装 LibreOffice 时使用本地中文 PDF 渲染器；此时 Word 软件的实际分页可能因字体与排版引擎而不同。

模板查询、异步导出任务、状态查询和文件下载的完整契约见 [简历导出 API 开发者文档](docs/简历导出接口/文档目录.md)。

### 7.1 通用响应和错误

成功响应：

```json
{
	"data": {},
	"requestId": "req_123"
}
```

错误响应：

```json
{
	"error": {
		"code": "UNSUPPORTED_SCANNED_PDF",
		"message": "未检测到可提取文本，请改用手动录入。",
		"details": {}
	},
	"requestId": "req_123"
}
```

主要错误码：

| 错误码 | HTTP 状态 | 场景 |
| --- | --- | --- |
| VALIDATION_ERROR | 422 | 请求字段或模型输出不符合契约 |
| FILE_TYPE_NOT_SUPPORTED | 415 | 上传非 PDF/DOCX 文件 |
| FILE_TOO_LARGE | 413 | 文件超过 10 MB |
| UNSUPPORTED_SCANNED_PDF | 422 | PDF 无可提取文本 |
| RESUME_NOT_FOUND | 404 | 简历不存在 |
| VERSION_NOT_FOUND | 404 | 简历版本不存在 |
| ANALYSIS_PROVIDER_ERROR | 502 / 503 | AI 调用、配置或响应校验失败 |
| ANALYSIS_TIMEOUT | 504 | AI 调用超时 |
| EXPORT_DEPENDENCY_MISSING | 503 | LibreOffice 不可用 |
| EXPORT_FAILED | 500 | 模板渲染或格式转换失败 |

### 7.2 简历与版本接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/resumes` | 创建简历 |
| GET | `/api/resumes` | 获取历史简历列表 |
| GET | `/api/resumes/{resumeId}` | 获取简历详情和当前草稿 |
| POST | `/api/resumes/import` | 上传 PDF/DOCX 并返回待确认结构 |
| GET | `/api/imports/{importId}` | 获取待确认的文件导入结果 |
| POST | `/api/imports/{importId}/confirm` | 确认文件导入结果并写入草稿 |
| PUT | `/api/resumes/{resumeId}/draft` | 保存草稿和排序 |
| POST | `/api/resumes/{resumeId}/versions` | 从草稿创建不可变版本 |
| GET | `/api/resumes/{resumeId}/versions` | 获取历史版本列表 |
| GET | `/api/resume-versions/{versionId}` | 获取指定版本快照 |

创建版本请求：

```json
{
	"baseVersionId": "version_1",
	"source": "optimized",
	"document": {
		"basicInfo": {},
		"sections": []
	}
}
```

创建版本响应：

```json
{
	"data": {
		"id": "version_2",
		"resumeId": "resume_1",
		"version": 2,
		"parentVersionId": "version_1",
		"source": "optimized"
	},
	"requestId": "req_123"
}
```

### 7.3 JD 分析接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/analyses` | 对指定简历版本执行 JD 分析 |
| GET | `/api/analyses/{analysisId}` | 获取分析结果 |
| POST | `/api/analyses/{analysisId}/retry` | 重试失败的分析 |
| PATCH | `/api/suggestions/{suggestionId}` | 接受、拒绝或编辑建议 |

分析请求：

```json
{
	"resumeVersionId": "version_1",
	"jdText": "负责后端服务开发，熟悉 Python、FastAPI 和数据库设计。"
}
```

标准分析响应：

```json
{
	"data": {
		"id": "analysis_1",
		"resumeVersionId": "version_1",
		"status": "completed",
		"overallScore": 78,
		"itemMatches": [
			{
				"sectionId": "section_project",
				"itemId": "item_project_1",
				"level": "high",
				"reason": "项目使用 FastAPI，符合 JD 的后端框架要求。"
			}
		],
		"missingRequirements": [
			{
				"requirement": "高并发服务经验",
				"reason": "当前简历中没有可验证的相关描述。"
			}
		],
		"suggestions": [
			{
				"id": "suggestion_1",
				"sectionId": "section_project",
				"itemId": "item_project_1",
				"original": "负责后端开发。",
				"suggested": "使用 FastAPI 完成后端接口与数据模型开发。",
				"reason": "突出与 JD 相关且原简历已有依据的技术。",
				"status": "pending"
			}
		]
	},
	"requestId": "req_123"
}
```

分析契约约束：

- `overallScore` 必须为 0-100 的整数。
- `level` 只能为 `high`、`medium`、`low`。
- 每个 sectionId 和 itemId 必须存在于输入版本中。
- Suggestion 状态只能为 `pending`、`accepted`、`rejected`、`edited`。
- AI 超时或响应非法时保留当前内容，不静默覆盖正文。
- 重试沿用原 Analysis 记录或建立明确关联，不得产生重复建议。

### 7.4 导出接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/export-templates` | 获取两份可用模板 |
| POST | `/api/resume-versions/{versionId}/exports` | 创建 DOCX/PDF 导出任务 |
| GET | `/api/exports/{exportId}` | 获取导出状态 |
| GET | `/api/exports/{exportId}/download` | 下载生成文件 |

导出请求：

```json
{
	"templateId": "classic_single_column",
	"format": "pdf"
}
```

导出响应：

```json
{
	"data": {
		"id": "export_20260318_001",
		"resumeVersionId": "version_2",
		"templateId": "classic_single_column",
		"templateVersion": "1.0.0",
		"format": "pdf",
		"status": "queued",
		"downloadUrl": null
	},
	"requestId": "req_123"
}
```

创建接口返回 `202 Accepted`。客户端使用 `exportId` 查询状态，仅在 `status=completed` 后下载文件。

## 8. 页面与交互定义

| 页面 | 核心操作 |
| --- | --- |
| 简历列表 | 查看、创建、打开历史简历 |
| 简历创建 | 分模块填写、上传 PDF/DOCX 文件 |
| 简历编辑 | 编辑识别结果、新增删除条目、重复保存当前内容 |
| JD 分析 | 输入 JD、授权发送、查看真实 AI 数字评分和结果 |
| 定向优化 | 拖动排序、隐藏/恢复、手改、AI 改写对比与确认 |
| 导出 | 选择模板和格式、生成、查看状态、下载 |

分析调用期间页面显示明确进度。DeepSeek 配置、鉴权、余额、限流、超时或输出校验失败时明确报错，保留 JD 与已保存内容，允许重试，绝不使用固定评分兜底。页面切换保留当前编辑；切换简历或关闭有未保存内容的页面前提示。简历编辑、JD 和导出中心均显示真实 PDF 页边界。

## 9. 测试方案

### 9.1 测试分层

| 层级 | 工具 | 重点范围 |
| --- | --- | --- |
| 后端单元测试 | pytest | 文本拆分、数据校验、版本、分析适配、模板渲染 |
| 后端接口测试 | pytest + HTTPX | 状态码、响应契约、数据库副作用、异常处理 |
| 前端组件测试 | Vitest + Testing Library | 表单、错误提示、建议状态、拖动后的顺序 |
| 契约测试 | Pydantic + 模拟 HTTP | DeepSeek 数字评分校验、API 错误与确认式改写 |
| 端到端测试 | Playwright | Edge 桌面端的模块 A、模块 B 完整闭环 |
| 人工视觉测试 | 测试记录表 | 两份模板的字体、顺序、分页和 DOCX/PDF 一致性 |

### 9.2 测试数据

- 真实简历与真实 JD 只保存在 `.gitignore` 覆盖的本地目录。
- 仓库只提交脱敏 PDF、DOCX、文本、预期结构 JSON 和模拟 AI 响应。
- 测试样本覆盖完整简历、缺失模块、乱序模块、重复标题、中文长文本和多页内容。
- AI 测试不固定具体措辞和精确分数，只验证 JSON 契约、分数范围、引用有效性和禁止虚构规则。

### 9.3 核心测试用例

| 编号 | 场景 | 预期结果 |
| --- | --- | --- |
| A-01 | 上传正常文本型 PDF | 返回可编辑的结构化简历 |
| A-02 | 上传正常 DOCX | 返回可编辑的结构化简历 |
| A-03 | 上传扫描版 PDF | 返回 `UNSUPPORTED_SCANNED_PDF`，提示手动录入 |
| A-04 | 上传超过 10 MB 文件 | 返回 `FILE_TOO_LARGE` |
| A-05 | 多次保存当前内容 | 更新同一份简历；普通保存不增加快照数量 |
| A-06 | 当前内容导出 | DOCX/PDF 排除隐藏项，保留全部可见内容 |
| B-01 | 当前内容分析 JD | 返回总分、逐条数字评分、缺失要求和建议 |
| B-02 | DeepSeek 超时 | 返回明确错误，保留当前内容 |
| B-03 | AI 返回非法 ID/分数或遗漏条目 | 后端拒绝非法响应 |
| B-04 | AI 改写预览与确认 | 预览/取消不改原文，确认后保存，过期原文拒绝替换 |
| B-05 | 拖动模块和模块内条目 | 刷新后顺序保持正确 |
| B-06 | 排序、隐藏与恢复 | 保存并重新打开保持正确；原文可恢复 |
| I-01 | 未配置 AI 时使用模块 A | 仍可创建、编辑、排序、隐藏、预览和导出 |
| I-02 | 使用种子版本启动模块 B | B 无需文件解析即可分析、优化和导出 |
| I-03 | A/B 导出同一版本 | 相同模板和格式生成一致结果 |

### 9.4 验收标准

- 模块 A 可独立完成“创建或导入 -> 校正 -> 保存 -> 导出”。
- 模块 B 可从当前内容独立完成“分析 -> 优化预览 -> 确认 -> 保存 -> 导出”。
- 日常编辑始终更新同一份内容；内部快照和旧接口保留兼容。
- AI 失败、文件异常或导出失败时不丢失用户数据。
- DOCX/PDF 字段内容与所选版本一致，两份模板不存在明显溢出和错位。
- Edge 桌面端可完整执行两条主流程。
- 自动化测试通过，并完成包含环境、用例、结果、截图和缺陷记录的测试报告。

## 10. 安全与隐私

- DeepSeek 密钥等敏感配置只通过后端环境变量读取；分析前需要用户明确授权。
- `.env`、真实简历、真实 JD、上传原件和导出文件必须加入 `.gitignore`。
- `.env.example` 只提供变量名和非敏感示例。
- 服务端同时校验文件扩展名、MIME 类型和大小，生成随机存储文件名。
- 下载接口校验 ExportRecord，不允许客户端直接拼接本地文件路径。
- 日志不得记录完整简历、JD、Token、电话或邮箱。
- 提交代码前执行密钥和个人信息检查，避免敏感内容进入 Git 历史。

## 11. 团队分工与协作

| 成员 | 主要职责 |
| --- | --- |
| A1 | 模块 A、PDF/DOCX 解析、简历版本、共享导出服务、两份模板接入 |
| A2 | 模块 B、DeepSeek/Mock 适配、数字评分、建议确认、拖动调整 |
| 共同负责 | 公共数据契约、数据库迁移、跨模块联调、测试和课程文档 |

Git 协作约定：

- A1 主要使用 `feature/resume-builder-export`。
- A2 主要使用 `feature/jd-analysis-optimizer`。
- 公共契约和数据库变更使用独立的小型分支与 Pull Request。
- 每个 Pull Request 写明功能范围、接口变化和测试结果，由另一位成员评审。
- `main` 分支始终保持可启动，不在项目结束时一次性合并长期分支。

## 12. 最终交付物

- 可运行的前后端源代码。
- SQLite 数据迁移和初始化方式。
- 两份可用的 Word 导出模板。
- README 与本机部署说明。
- 需求说明和概要设计文档。
- 完整测试计划、测试用例、执行结果与缺陷记录。
- 演示 PPT 或视频。
- 包含两位成员持续提交和 Pull Request 记录的 GitHub 仓库。

## 13. 本机运行说明

### 13.1 本轮已完成

- 模块 A 后端 13 个接口：简历 CRUD、文本粘贴拆分、PDF/DOCX 导入、草稿与排序、
  不可变版本、版本快照查询。
- 共享导出服务：模板渲染 DOCX → LibreOffice Headless 转 PDF，导出记录与授权下载。
  模块 A 与模块 B 使用同一组端点，输入只有 `ResumeVersion ID`、模板 ID 与格式。
- 规则优先的中文拆分：模块标题识别、名称/角色/日期三列与三行式条目、
  「类别：内容」技能行、日期归一化、无法归类内容一律保留并给出提示。
- 公共契约 `ResumeDocument`（Pydantic，`extra="forbid"`）、统一响应与错误码、
  requestId 透传、SQLite + Alembic 迁移。
- 可重复保存的 React 简历工作台、结构化编辑、JD 拖动/隐藏工作台和真实分页预览。
- DeepSeek 数字评分、建议、AI 改写预览和显式确认接口；无密钥时明确提示，不回退到演示结果。
- 自动化测试包括模拟 DeepSeek HTTP 成功/失败、确认式替换和预览/导出页数一致性；真实 API 联调需自行配置有效新密钥。

设计细节见 `docs/module-a-design.md`、模板契约见 `docs/template-contract.md`、
测试说明见 `docs/testing.md`、补充错误码见 `docs/api-extensions.md`。

### 13.2 尚未包含

- Coze Provider 仍为预留，当前使用 DeepSeek；`e2e/` 的独立 Playwright 工程仍为占位。
- 第二份 Word 模板：当前只有 `classic_single_column`（格式取自参考简历的脱敏占位版）。

### 13.3 环境要求

- Python 3.10+（本机实测 3.12）。
- LibreOffice 可选：安装后由 Word 模板转换 PDF；未安装时用 ReportLab 生成中文 PDF。

### 13.4 启动步骤

```powershell
# 在仓库根目录执行
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env          # 按需修改，切勿提交 .env

cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head          # 建库（应用启动时也会自动执行）
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- Swagger 文档：<http://127.0.0.1:8000/docs>
- 数据位置：`backend/data/resume_match.db`、`backend/storage/{uploads,exports}`
  （均在 `.gitignore` 覆盖范围内）

### 13.5 导出模板

模板是脱敏占位版，只从参考简历取格式（页面设置、字体、字号、颜色），不含任何个人信息。
参考简历换了以后重新生成：

```powershell
cd backend
..\.venv\Scripts\python.exe scripts\build_template_from_resume.py
```

同时验证导出效果（导入参考简历 → 建版本 → 导出 DOCX）：

```powershell
Copy-Item "你的参考简历.docx" ..\private\ -Force   # private/ 不入库，脚本会自动查找
..\.venv\Scripts\python.exe -m pytest tests\test_text_parser.py -k reference -v
```

### 13.6 测试

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
```

### 13.7 数据与隐私提醒

- 真实简历、真实 JD、上传原件、导出产物、数据库文件、`.env` 均已加入 `.gitignore`，
  只保存在本机；真实简历原件建议统一放在 `private/`。
- DeepSeek 密钥只允许通过后端环境变量注入，仓库内只保留 `.env.example`；不要使用已暴露的密钥。
- 仓库内测试样例全部为虚构数据。
