# 导出模板契约

模板是人工维护的 Word 文件（`.docx`），渲染器只依赖下面的两类约定。
替换成新的模板文件时**不需要改代码**，只要保留占位符与样式名。

## 1. 占位符

| 占位符 | 含义 |
| --- | --- |
| `{{basicInfo.name}}` | 姓名 |
| `{{basicInfo.phone}}` | 手机 |
| `{{basicInfo.email}}` | 邮箱 |
| `{{basicInfo.location}}` | 所在地 |
| `{{basicInfo.jobTarget}}` | 求职意向 |
| `{{resumeTitle}}` | 简历标题（模块 A 中的简历名称） |
| `{{exportDate}}` | 导出日期（`YYYY-MM-DD`） |
| `{{SECTIONS}}` | **锚点**：渲染全部模块与条目 |
| `{{SKILLS}}` | **锚点**（可选）：只渲染技能类模块 |

占位符可以写在正文段落里，也可以写在表格单元格里（基本信息表格就是这种用法）。
占位符在 Word 中被拆成多个 run 也能正确替换；未知占位符输出为空字符串。

## 2. 锚点与段落样式

`{{SECTIONS}}` / `{{SKILLS}}` 所在段落会被**删除**，并在该位置插入各模块内容：

| 内容 | 使用样式 |
| --- | --- |
| 模块标题 | `ResumeSectionHeading` |
| 条目标题行 | `ResumeItem` |
| 条目描述行 | `ResumeItemContent` |
| 姓名 | `ResumeName` |
| 基本信息行 | `ResumeContact` |

模板缺少某个样式时会退回 Normal 样式，内容不会丢失。

## 3. 条目标题行的列

条目按「列」用 **制表位（Tab）** 对齐，不是表格：

```text
南京理工大学 <Tab> 计算机科学与技术 本科 <Tab> 2019.09 - 2023.06
```

各模块的列定义在 `app/services/export/renderer.py` 的 `FIELD_COLUMNS`：

| 模块 | 第 1 列 | 第 2 列 | 第 3 列 |
| --- | --- | --- | --- |
| 教育 | 学校 | 专业 + 学历 | 起止时间 |
| 实习/工作 | 单位 | 角色 | 起止时间 |
| 项目 | 项目名 | 角色 | 起止时间 |
| 荣誉奖项 | 名称 | 日期 | — |
| 技能 | `类别：内容` 整行（无 Tab） | — | — |
| 自定义 | 正文首行 | — | — |

因此模板中的 `ResumeItem` 样式需要定义两个制表位（生成脚本用的是
`6.8cm` 左对齐 + `16.0cm` 右对齐）。契约之外的额外字段会追加到第 2 列，不会丢。

## 4. 当前模板

| id | 说明 | 文件 |
| --- | --- | --- |
| `classic_single_column` | 经典单栏，格式取自参考简历（微软雅黑标题 + 姓名/角色/日期三列） | `backend/assets/templates/classic_single_column.docx` |

README 要求最终提供两份模板。仓库当前的模板是**参考简历的脱敏占位版**：

- 只从参考简历里取格式（页面尺寸、页边距、字体、字号、颜色）；
- 内容全部替换为占位符与锚点，不含任何个人信息；
- 参考简历原件本身留在 `.gitignore` 覆盖的仓库根目录，不提交。

第二份模板由人工提供后，在 `app/services/export/templates.py` 的 `TEMPLATES` 中追加一项即可，
`GET /api/export-templates` 会自动暴露。

## 5. 重新生成模板

参考简历换了（或者需要按新格式重建模板）时执行：

```powershell
cd backend
..\.venv\Scripts\python.exe scripts\build_template_from_resume.py
# 或指定文件
..\.venv\Scripts\python.exe scripts\build_template_from_resume.py --source "D:\临时\某模板.docx"
```

脚本会打印实际提取到的格式，例如：

```text
参考简历：...\private\陈仕安-南京理工大学.docx
提取格式：字体=微软雅黑 标题=16.0pt 正文=10.5pt 颜色=#0F1115
已生成：...\backend\assets\templates\classic_single_column.docx
```

若参考简历不存在，脚本使用内置默认值（微软雅黑 16pt / 10.5pt、A4、2.4cm 页边距），
因此 CI 或他人机器上也能生成可用模板。
