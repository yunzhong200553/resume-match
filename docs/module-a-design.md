# 模块 A 后端设计说明

范围：简历构建、拆分、版本管理，以及**模块 A 与模块 B 共享的导出服务**的后端实现。
前端与 Playwright 端到端测试不在本轮范围内。

## 1. 目录结构

```text
backend/
├─ alembic/                     # 迁移脚本（表结构唯一来源）
├─ app/
│  ├─ api/routes/               # 接口层：resumes / resume_versions / exports
│  ├─ core/                     # 配置、错误契约、requestId、响应包装
│  ├─ db/                       # 引擎、会话、ORM 实体、迁移入口
│  ├─ schemas/                  # ResumeDocument 契约与请求/响应模型
│  └─ services/
│     ├─ parsing/               # PDF/DOCX 提取 + 规则拆分
│     ├─ export/                # 模板渲染、LibreOffice 转换、导出编排
│     ├─ analysis/              # 分析适配层接口 + Mock（模块 B 接入点）
│     ├─ resume_service.py      # 简历与草稿
│     └─ version_service.py     # 不可变版本
├─ assets/templates/            # 脱敏占位模板（入库）
├─ assets/mock/                 # Mock 分析响应（入库）
├─ scripts/                     # 模板构建脚本
└─ tests/                       # pytest 用例与脱敏样例
```

## 2. 数据模型

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `resumes` | id、title、created_at、updated_at | 简历主体 |
| `resume_versions` | id、resume_id、version、parent_version_id、source、document | 不可变 JSON 快照 |
| `drafts` | id、resume_id、base_version_id、document、updated_at | 每份简历一条草稿 |
| `export_records` | id、resume_version_id、template_id、format、status、file_path | 导出记录 |

约束与实现要点：

- **版本不可变**：`ResumeVersion` 上用 ORM 事件拦截 `before_update`，任何修改尝试都会得到
  `VALIDATION_ERROR`（"正式版本不可修改，请基于草稿创建新版本。"），而不是靠约定。
- `(resume_id, version)` 唯一，版本号由服务端自增；`parent_version_id` 记录版本链。
- `source` 取值为 `manual` / `import` / `optimized`。
- `Analysis` / `Suggestion` 表属于模块 B 的独立迁移，本模块不创建，避免两人改动同一迁移文件。

## 3. 拆分规则（`services/parsing/text_parser.py`）

流程：文本 → 模块切块 → 条目切分 → 字段抽取 → `ResumeDocument`，全过程只依赖规则，不调用模型。

### 3.1 模块切块

1. 关键词表命中（最长匹配）：教育背景/教育经历、实习经历/工作经历、项目经历、技能与工具、荣誉奖项；
2. `【自定义模块】`、`## 标题` 等显式标题；
3. 以「经历/经验/证书/爱好」等后缀结尾的短行 → `custom` 模块。

误判防护：

- 冒号后仍有内容（`求职意向：后端开发工程师`）判定为「标签：值」，不当标题；
- `项目背景` / `项目内容` / `工作成果` 这类内容标签不当标题；
- 后面 1~2 行内出现纯日期行的行，属于「名称 / 角色 / 日期」标题组，不当标题
  （参考简历里这类行是表格单元格，提取后各占一行）。

### 3.2 条目切分

支持两种常见写法，正文行（描述、项目符号）不会被误判为条目起点：

| 写法 | 示例 |
| --- | --- |
| 三列一行 | `南京理工大学 \| 软件工程专业 \| 本科 \| 2023.09 - 至今` |
| 三行式 | `南京理工大学` / `软件工程专业 \| 本科` / `2023.09 - 至今` |

条目边界 = 行尾带日期区间的行，或后 1~2 行内出现纯日期行的标题首行。
整段都是项目符号时，一条符号一个条目。

### 3.3 字段抽取

- 日期统一归一化为 `YYYY-MM`（`2023.9`、`2023年9月` → `2023-09`），`至今/现在/目前` → `至今`；
- 教育：学校（含大学/学院等词）、学历（本科/硕士/博士…）、专业；
- 实习/工作：单位、角色（优先匹配"开发/工程师/负责人"等，否则取长度 ≤ 12 的短片段）；
- 项目：项目名、角色；
- 技能：支持 `编程：Python，Java，Git` 这类「类别：内容」写法，也支持项目符号与顿号分隔；
- **任何未归类的内容都留在 `content`**，不丢弃；识别不到日期会给出 warning，交由人工校正。

## 4. 文件导入（`services/parsing/importer.py`）

1. 校验顺序：扩展名 → MIME → 大小（≤ 10 MB）；
2. 落盘使用随机文件名（`upload_<12位hex>.docx`），响应只回传展示名与大小；
3. PDF 用 PyMuPDF 提取，可提取字符数 < 20 视为扫描件 → `UNSUPPORTED_SCANNED_PDF`（422），
   不产生结构化数据，也不影响用户已填写内容；
4. DOCX 按 body 顺序遍历段落与表格：多列行拼成 `单元格1 | 单元格2 | 单元格3`，
   合并单元格（描述行）按换行保留多行。

## 5. 导出服务（`services/export/`）

```text
版本快照 -> 模板渲染 DOCX -> （可选）LibreOffice 转 PDF -> 导出记录 + 下载
```

- 输入只有 `ResumeVersion ID + templateId + format`，不区分版本来自模块 A 还是模块 B；
- 渲染规则与模板契约见 `docs/template-contract.md`；
- 转换失败会先把记录写成 `failed` 并保存错误码，再抛出异常（便于重试与排查）；
- 未安装 LibreOffice → `EXPORT_DEPENDENCY_MISSING`（503），此时 DOCX 导出仍然可用；
- 下载接口只接受 `ExportRecord` 授权的文件，不接受客户端拼接路径。

## 6. 与模块 B 的边界

- `ResumeDocument`（`app/schemas/resume_document.py`）是唯一公共契约，模块 B 直接复用；
- `app/services/analysis/provider.py` 定义 `AnalysisProvider` Protocol，并提供 `MockProvider`：
  返回 README 7.3 的标准结构，且会把示例 ID 替换为输入版本中真实存在的 `sectionId/itemId`；
- `ANALYSIS_PROVIDER=coze` 目前会明确抛 `ANALYSIS_PROVIDER_ERROR`（"由模块 B 实现"），
  不存在"看起来能跑但结果不对"的中间状态；
- 模块 A 不注册任何分析路由，禁用分析能力后 A 的全部流程仍可用（用例 `I-01`）。
