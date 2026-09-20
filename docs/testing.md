# 模块 A 测试说明

## 1. 运行方式

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q          # 全部
..\.venv\Scripts\python.exe -m pytest -v          # 查看每个用例名
```

测试使用独立临时 SQLite 文件与临时存储目录，不写开发库、不写 `backend/storage/`。

## 2. 用例 → 需求映射

| 编号 | 用例 | 覆盖位置 |
| --- | --- | --- |
| A-01 | 上传正常文本型 PDF → 可编辑结构化简历 | `tests/test_import_api.py` |
| A-02 | 上传正常 DOCX → 可编辑结构化简历 | `tests/test_import_api.py` |
| A-03 | 扫描版 PDF → `UNSUPPORTED_SCANNED_PDF` | `tests/test_import_api.py` |
| A-04 | 超过 10 MB → `FILE_TOO_LARGE` | `tests/test_import_api.py` |
| A-05 | 保存草稿并创建版本后，草稿可改、版本不变 | `tests/test_resume_api.py` |
| A-06 | 使用模板导出 DOCX/PDF 且内容与所选版本一致 | `tests/test_export_api.py` |
| I-01 | 禁用 Coze 后模块 A 仍可用（无分析路由） | `tests/test_mock_provider.py` |
| I-03 | 同版本 + 同模板 + 同格式 → 结果一致 | `tests/test_export_api.py` |

## 3. 其它测试组

| 文件 | 覆盖内容 |
| --- | --- |
| `test_resume_document.py` | 契约校验：camelCase、`type` 枚举、order 连续唯一、ID 唯一、契约外字段拒绝 |
| `test_text_parser.py` | 拆分规则：完整/缺失模块/乱序/重复标题/自定义模块/长文本/三行式/项目符号/契约外标签告警 |
| `test_migrations.py` | Alembic `upgrade head`、`downgrade base`、唯一约束存在性 |
| `test_mock_provider.py` | Mock 输出符合 README 7.3 契约，且引用的 ID 真实存在 |

## 4. 参考简历用例

`test_text_parser.py::test_reference_resume_can_be_parsed` 会在仓库根目录查找本机参考简历：

- 找到 → 校验它能被拆成非空结构（模块数 ≥ 3、每个模块都有条目、项目条目都有日期、正文不含表格分隔符）；
- 找不到 → 自动 skip（例如队友机器或 CI 上没有该文件）。

该用例**只断言结构，不断言个人信息**，因此用例代码本身不含隐私内容。

## 5. LibreOffice 相关

PDF 用例标记为 `@pytest.mark.requires_libreoffice`，本机未安装时自动 skip：

- 未安装 → `test_pdf_without_libreoffice_fails_but_is_recorded` 断言返回 503
  `EXPORT_DEPENDENCY_MISSING`，且导出记录被写成 `failed`（可重试）；
- 已安装 → 额外验证返回内容以 `%PDF` 开头。

安装方式：<https://www.libreoffice.org/download/>，装完重启后端即可，
或在 `.env` 里用 `LIBREOFFICE_BIN` 指定 `soffice.exe` 路径。

## 6. 数据与隐私

- 仓库内所有样例都是虚构数据（李小明 / 13800000000 / example.com）；
- 真实简历、真实 JD、上传原件、导出产物都在 `.gitignore` 覆盖范围内；
- 提交前检查：

```powershell
cd backend
git grep -n -I -E "1[3-9][0-9]{9}|[A-Za-z0-9._%+-]+@(qq|163|gmail)\.com" -- . || Write-Host "未发现电话/邮箱"
```
