"""规则优先的中文简历文本拆分。

设计要点（README 3.1）：

* 先按「模块标题」切块，再在块内切条目；
* 条目边界识别同时支持两种常见写法：
  1. 三列表格行 —— ``名称 | 角色 | 2025.12 - 至今``（日期在同一行结尾）；
  2. 分行写法 —— 名称行 / 角色行 / 纯日期行（日期自成一行的三行式）；
* 技能模块支持 ``编程：python，java，git`` 这类「类别：内容」写法；
* 任何无法归类的内容都不丢弃，一律回落到 ``content``，交由人工校正；
* 识别不确定的地方以 ``warnings`` 返回，不静默猜测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.ids import item_id, section_id
from app.schemas.resume_document import (
    BasicInfo,
    ResumeDocument,
    Section,
    SectionItem,
    SectionType,
)

# --------------------------------------------------------------------------
# 词表与正则
# --------------------------------------------------------------------------

#: 已知模块标题关键词；匹配时取最长命中，避免「技能证书」被「技能」抢先
SECTION_KEYWORDS: tuple[tuple[SectionType, tuple[str, ...]], ...] = (
    (
        SectionType.education,
        ("教育经历", "教育背景", "学习经历", "学历背景", "教育"),
    ),
    (
        SectionType.experience,
        ("实习经历", "实习经验", "工作经历", "工作经验", "职业经历", "工作"),
    ),
    (
        SectionType.project,
        ("项目经历", "项目经验", "科研经历", "实践经历", "项目"),
    ),
    (
        SectionType.skill,
        ("技能与工具", "技能特长", "专业技能", "技能清单", "技术栈", "技能"),
    ),
    (
        SectionType.award,
        ("荣誉奖项", "获奖情况", "奖项荣誉", "荣誉", "奖项", "证书", "获奖"),
    ),
)

#: 这些「标题」实际是基本信息块的开始，不作为独立模块
HEAD_LIKE_TITLES = {"个人信息", "基本信息", "个人资料", "联系方式", "基本资料"}

CUSTOM_TITLE_SUFFIXES = (
    "经历", "经验", "情况", "能力", "信息", "技能", "证书", "奖项", "荣誉",
    "介绍", "概述", "评价", "兴趣", "爱好", "实践", "培训", "成果", "作品", "活动",
)

BRACKET_TITLE_RE = re.compile(r"^[【\[]\s*(?P<title>[^】\]]{2,14})\s*[】\]]$")
HEADING_TITLE_RE = re.compile(r"^#{1,4}\s*(?P<title>.{2,14})$")

BULLET_RE = re.compile(
    r"^\s*(?:[-–—•·▪◦●○*◆]|(?:\d{1,2}|[一二三四五六七八九十]{1,2})\s*[.、)）]|\(\d{1,2}\)|（\d{1,2}）)\s*"
)

SEPARATOR_RE = re.compile(r"^[-=_~·*—\s]{3,}$")

PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_DATE_TOKEN = r"\d{4}\s*[./年]\s*\d{1,2}\s*月?|\d{4}"
_PRESENT = "至今|现在|今|目前"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:[-–—~～]|至|到|--)\s*(?P<end>{_DATE_TOKEN}|{_PRESENT})"
)
SINGLE_DATE_RE = re.compile(rf"(?P<date>{_DATE_TOKEN})")
PURE_DATE_RE = re.compile(rf"^(?:{_DATE_TOKEN})(?:\s*(?:[-–—~～]|至|到|--)\s*(?:{_DATE_TOKEN}|{_PRESENT}))?$")

DEGREE_WORDS = ("博士", "硕士", "研究生", "本科", "学士", "专科", "大专", "高中")
ROLE_WORDS = (
    "工程师", "开发", "研发", "实习生", "经理", "负责人", "主管", "设计师",
    "分析师", "运维", "测试", "架构师", "专员", "组长", "组员", "队长", "训练",
)

LABEL_MAP: dict[str, str] = {
    "姓名": "name",
    "名字": "name",
    "电话": "phone",
    "手机": "phone",
    "手机号": "phone",
    "联系电话": "phone",
    "邮箱": "email",
    "电子邮箱": "email",
    "email": "email",
    "E-mail": "email",
    "籍贯": "location",
    "地址": "location",
    "现居": "location",
    "现居地": "location",
    "所在地": "location",
    "居住地": "location",
    "所在城市": "location",
    "城市": "location",
    "求职意向": "job_target",
    "求职目标": "job_target",
    "目标岗位": "job_target",
    "应聘岗位": "job_target",
    "应聘职位": "job_target",
    "期望职位": "job_target",
}

CONTACT_LABELS = {"联系方式", "联系方法"}

_NAME_RE = re.compile(r"^[\u4e00-\u9fa5·]{2,4}$")
_CITY_RE = re.compile(r"^[\u4e00-\u9fa5]{2,8}(市|省)$")

CONTENT_STOP_CHARS = "。；;！!"
CONTENT_PUNCTUATION = "。；;！!，,"
#: 条目标题行的最大长度，「项目背景：…」这类长句不会被误判为标题行
HEADER_MAX_LENGTH = 40


@dataclass(slots=True)
class ParseOutcome:
    """拆分结果：结构化文档 + 需要人工确认的提示。"""

    document: ResumeDocument
    warnings: list[str] = field(default_factory=list)
    source_text_length: int = 0


def parse_resume_text(text: str) -> ParseOutcome:
    return _ResumeTextParser(text).run()


# --------------------------------------------------------------------------
# 标题识别
# --------------------------------------------------------------------------


def _strip_decoration(line: str) -> str:
    return line.strip(" \t\u3000【】[]（）()<>《》#*＊-—·:：")


#: 「项目背景」「工作内容」这类是条目正文的标签，不是模块标题
CONTENT_LABEL_MODIFIERS = (
    "项目", "工作", "实习", "主要", "个人", "研究", "课题", "产品", "活动", "职责", "岗位",
)
CONTENT_LABEL_SUFFIXES = ("内容", "背景", "成果", "职责", "业绩", "收获", "描述", "亮点", "难点")


def _is_content_label(text: str) -> bool:
    for suffix in CONTENT_LABEL_SUFFIXES:
        if text.endswith(suffix):
            prefix = text[: -len(suffix)]
            if prefix and len(prefix) <= 4 and prefix.endswith(CONTENT_LABEL_MODIFIERS):
                return True
    return False


def match_known_title(line: str) -> tuple[SectionType, str] | None:
    cleaned = _strip_decoration(line)
    if not cleaned or len(cleaned) > 12:
        return None
    # 冒号后面还有内容 => 这是「标签：值」而不是模块标题
    if re.search(r"[：:]\s*\S", line):
        return None
    if _is_content_label(cleaned):
        return None
    compact = re.sub(r"\s+", "", cleaned)
    best: tuple[SectionType, str, int] | None = None
    for section_type, keywords in SECTION_KEYWORDS:
        for keyword in keywords:
            if keyword in compact and len(compact) - len(keyword) <= 4:
                if best is None or len(keyword) > best[2]:
                    best = (section_type, cleaned, len(keyword))
    if best is None:
        return None
    return best[0], best[1]


def match_custom_title(line: str, *, allow_suffix_rule: bool) -> str | None:
    if BULLET_RE.match(line):
        return None

    bracket = BRACKET_TITLE_RE.match(line.strip())
    if bracket:
        return bracket.group("title").strip()

    heading = HEADING_TITLE_RE.match(line.strip())
    if heading:
        return heading.group("title").strip()

    if not allow_suffix_rule:
        return None

    cleaned = _strip_decoration(line)
    if not (2 <= len(cleaned) <= 10):
        return None
    if re.search(r"[\d。，,；;！!？?、|｜]", cleaned):
        return None
    if "：" in cleaned or ":" in cleaned:
        return None
    if cleaned.endswith(CUSTOM_TITLE_SUFFIXES):
        return cleaned
    return None


# --------------------------------------------------------------------------
# 日期
# --------------------------------------------------------------------------


def normalize_date(raw: str) -> str:
    value = re.sub(r"\s+", "", raw or "")
    if value in {"至今", "现在", "今", "目前"}:
        return "至今"
    match = re.match(r"(\d{4})\s*[./年-]?\s*(\d{1,2})?", value)
    if not match:
        return value
    year, month = match.group(1), match.group(2)
    if month:
        return f"{year}-{int(month):02d}"
    return year


def _has_trailing_date(line: str) -> bool:
    """行尾是日期区间或单个日期，且日期前面还有内容 —— 典型的条目标题行。"""

    for pattern in (DATE_RANGE_RE, SINGLE_DATE_RE):
        match = None
        for candidate in pattern.finditer(line):
            match = candidate
        if match is None or match.end() != len(line.rstrip(" \t；;。")):
            continue
        if line[: match.start()].strip(" \t|｜·-–—,，、"):
            return True
    return False


def _is_pure_date(line: str) -> bool:
    return bool(PURE_DATE_RE.match(line.strip(" \t|｜·")))


def _is_header_like(line: str) -> bool:
    """是否是「名称 / 角色」这类短标题片段（而非正文句子）。"""

    text = line.strip()
    if not text or len(text) > HEADER_MAX_LENGTH:
        return False
    if BULLET_RE.match(text):
        return False
    if any(char in text for char in CONTENT_STOP_CHARS):
        return False
    if any(char in text for char in "，,、"):
        return False
    if "：" in text or ":" in text:
        return False
    return True


def _is_inside_header_group(lines: list[str], index: int) -> bool:
    """该行后面 1~2 行内出现纯日期行时，它是「名称/角色/日期」标题组的一部分。

    参考简历里这两行是表格单元格，提取后各占一行，很容易被误判为模块标题
    （例如「个人项目」），因此在这里先排除。
    """

    if _is_pure_date(lines[index]):
        return True
    for offset in (1, 2):
        candidate = index + offset
        if candidate >= len(lines):
            break
        if _is_pure_date(lines[candidate]):
            return True
        if not _is_header_like(lines[candidate]):
            break
    return False


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


class _ResumeTextParser:
    def __init__(self, text: str) -> None:
        self.raw_text = text
        self.warnings: list[str] = []
        self.ignored_labels: list[str] = []
        self.lines = self._normalize_lines(text)

    # ---- 对外 ----

    def run(self) -> ParseOutcome:
        head_lines, blocks = self._split_sections()
        basic_info = self._extract_basic_info(head_lines)
        sections = self._build_sections(blocks)
        if not sections:
            self.warnings.append("未能识别出任何简历模块，请手动新增模块并补充内容。")
        if self.ignored_labels:
            labels = "、".join(dict.fromkeys(self.ignored_labels))
            self.warnings.append(
                f"以下信息未纳入 ResumeDocument 契约字段，已跳过，请在基本信息或自定义模块中人工补充：{labels}。"
            )
        document = ResumeDocument(basic_info=basic_info, sections=sections)
        return ParseOutcome(
            document=document,
            warnings=self.warnings,
            source_text_length=len(self.raw_text),
        )

    # ---- 预处理 ----

    def _normalize_lines(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
        lines: list[str] = []
        for raw in normalized.split("\n"):
            line = raw.strip()
            if not line or SEPARATOR_RE.match(line):
                continue
            lines.append(line)
        return lines

    # ---- 切模块 ----

    def _split_sections(self) -> tuple[list[str], list[list]]:
        head_lines: list[str] = []
        blocks: list[list] = []
        title_counts: dict[str, int] = {}

        for index, line in enumerate(self.lines):
            if not BULLET_RE.match(line) and not _is_inside_header_group(self.lines, index):
                known = match_known_title(line)
                if known is not None:
                    section_type, title = known
                    title_counts[title] = title_counts.get(title, 0) + 1
                    if title_counts[title] > 1:
                        self.warnings.append(
                            f"检测到重复的模块标题「{title}」，已保留为多个独立模块，请人工合并或重命名。"
                        )
                    blocks.append([section_type, title, []])
                    continue

                custom = match_custom_title(line, allow_suffix_rule=bool(blocks))
                if custom is not None:
                    if not blocks and custom in HEAD_LIKE_TITLES:
                        # 顶部「个人信息」标题本身不产生模块，后续行仍属基本信息区
                        continue
                    blocks.append([SectionType.custom, custom, []])
                    continue

            if blocks:
                blocks[-1][2].append(line)
            else:
                head_lines.append(line)

        return head_lines, blocks

    # ---- 切条目 ----

    def _build_sections(self, blocks: list[list]) -> list[Section]:
        sections: list[Section] = []
        counters: dict[SectionType, int] = {}
        for order, (section_type, title, lines) in enumerate(blocks):
            counters[section_type] = counters.get(section_type, 0) + 1
            items = self._build_items(section_type, lines)
            sections.append(
                Section(
                    id=section_id(section_type.value, counters[section_type]),
                    type=section_type,
                    title=title,
                    order=order,
                    items=items,
                )
            )
        return sections

    def _build_items(self, section_type: SectionType, lines: list[str]) -> list[SectionItem]:
        drafts = self._split_item_drafts(section_type, lines)
        items: list[SectionItem] = []
        for index, draft in enumerate(drafts, start=1):
            fields, content, missing_date = self._extract_item(section_type, draft)
            if missing_date:
                self.warnings.append(
                    f"「{draft[0][:20]}」未识别到日期区间，请人工补充。"
                )
            items.append(
                SectionItem(
                    id=item_id(section_type.value, index),
                    order=index - 1,
                    fields=fields,
                    content=content,
                )
            )
        return items

    def _split_item_drafts(
        self, section_type: SectionType, lines: list[str]
    ) -> list[list[str]]:
        body = [line for line in lines if line.strip()]
        if not body:
            return []

        if section_type is SectionType.skill:
            return self._split_skill_drafts(body)

        bullet_starts = [index for index, line in enumerate(body) if BULLET_RE.match(line)]
        # 整段都是项目符号：一条符号一个条目
        if len(bullet_starts) >= 2 and bullet_starts[0] == 0:
            return _group_by_starts(body, bullet_starts)

        return _group_by_starts(body, self._item_starts(body))

    def _item_starts(self, body: list[str]) -> list[int]:
        """识别条目起始行。

        两种写法都支持：

        * ``名称 | 角色 | 2025.12 - 至今``（日期在行尾）；
        * 名称行 / 角色行 / 纯日期行 三行式（日期行自成一行）。

        正文行（描述、项目符号）不会被当成新的条目起点。
        """

        starts: list[int] = []
        cursor = 0
        while cursor < len(body):
            if cursor == 0 or _is_item_header(body, cursor):
                starts.append(cursor)
                group_end = (
                    None
                    if _has_trailing_date(body[cursor])
                    else _header_group_end(body, cursor)
                )
                cursor = group_end + 1 if group_end is not None else cursor + 1
            else:
                cursor += 1
        return starts

    def _split_skill_drafts(self, lines: list[str]) -> list[list[str]]:
        bullet_starts = [index for index, line in enumerate(lines) if BULLET_RE.match(line)]
        if len(bullet_starts) >= 2 and bullet_starts[0] == 0:
            return _group_by_starts(lines, bullet_starts)

        # 「编程：python，java，git」这类一行一个类别
        if all(_split_label(line)[0] for line in lines):
            return [[line] for line in lines]

        tokens = [
            token.strip()
            for token in re.split(r"[、,，;；/|｜]+", " ".join(lines))
            if token.strip()
        ]
        if len(tokens) >= 2:
            return [[token] for token in tokens]
        return [lines]

    # ---- 条目字段 ----

    def _extract_item(
        self, section_type: SectionType, draft: list[str]
    ) -> tuple[dict[str, str], str, bool]:
        # 三行式（名称行 / 角色行 / 纯日期行）时，把标题行合并成一行再解析字段
        group_end = _header_group_end(draft, 0)
        header_lines = draft[: group_end + 1] if group_end is not None else draft[:1]
        first_line = " | ".join(header_lines)
        rest = [
            BULLET_RE.sub("", line).strip() for line in draft[len(header_lines) :] if line.strip()
        ]

        if section_type is SectionType.skill:
            return self._extract_skill_item(first_line, rest)

        fields: dict[str, str] = {}
        date_match = DATE_RANGE_RE.search(first_line)
        if date_match:
            fields["startDate"] = normalize_date(date_match.group("start"))
            fields["endDate"] = normalize_date(date_match.group("end"))
            remainder = DATE_RANGE_RE.sub(" ", first_line)
        else:
            remainder = first_line
            single = SINGLE_DATE_RE.search(first_line)
            if single and section_type in {SectionType.award, SectionType.custom}:
                fields["date"] = normalize_date(single.group("date"))
                remainder = SINGLE_DATE_RE.sub(" ", first_line, count=1)

        tokens = _tokenize(remainder)
        has_fields, consumed = _assign_fields(section_type, tokens, fields)
        leftovers = [token for token in tokens if token not in consumed]

        content_parts: list[str] = []
        if leftovers:
            content_parts.append(" ".join(leftovers))
        content_parts.extend(rest)
        content = "\n".join(part for part in content_parts if part).strip()

        if not has_fields and not content:
            content = first_line

        missing_date = (
            section_type in {SectionType.education, SectionType.experience, SectionType.project}
            and "startDate" not in fields
        )
        return fields, content, missing_date

    def _extract_skill_item(
        self, first_line: str, rest: list[str]
    ) -> tuple[dict[str, str], str, bool]:
        label, value = _split_label(first_line)
        if label:
            fields = {"category": label}
            content = " ".join([value.strip(" ；;。"), *rest]).strip(" ；;。")
            return fields, content, False

        tokens = _tokenize(first_line)
        fields: dict[str, str] = {}
        consumed: set[str] = set()
        if len(tokens) == 1:
            fields["name"] = tokens[0]
            consumed = {tokens[0]}
        leftovers = [token for token in tokens if token not in consumed]
        content_parts: list[str] = []
        if leftovers:
            content_parts.append(" ".join(leftovers))
        content_parts.extend(rest)
        content = "\n".join(part for part in content_parts if part).strip()
        return fields, content, False

    # ---- 基本信息 ----

    def _extract_basic_info(self, head_lines: list[str]) -> BasicInfo:
        info = BasicInfo()

        phone = PHONE_RE.search(self.raw_text)
        if phone:
            info.phone = phone.group(1)
        email = EMAIL_RE.search(self.raw_text)
        if email:
            info.email = email.group(0)

        for line in head_lines:
            # 参考简历把「姓名：… | 性别：…」放在同一表格行；文本简历常用多个空格分隔，
            # 两种写法都按片段拆开逐段识别
            for segment in _split_segments(line):
                label, value = _split_label(segment)
                if label is None:
                    continue
                if label in CONTACT_LABELS:
                    _apply_contact(info, value)
                    continue
                key = LABEL_MAP.get(label)
                if key == "phone":
                    phone_match = PHONE_RE.search(value)
                    info.phone = phone_match.group(1) if phone_match else (value or info.phone)
                elif key == "email":
                    email_match = EMAIL_RE.search(value)
                    info.email = email_match.group(0) if email_match else (value or info.email)
                elif key in {"name", "location", "job_target"}:
                    setattr(info, key, value)
                else:
                    self.ignored_labels.append(label)

        if not info.name:
            for line in head_lines:
                if _strip_decoration(line) in HEAD_LIKE_TITLES:
                    continue
                for segment in _split_segments(line):
                    candidate = segment.strip()
                    if _NAME_RE.match(candidate) and not PHONE_RE.search(candidate):
                        info.name = candidate
                        break
                if info.name:
                    break

        if not info.location:
            for line in head_lines:
                if _CITY_RE.match(line.strip()):
                    info.location = line.strip()
                    break

        if not info.name and not info.phone and not info.email:
            self.warnings.append("未能识别姓名或联系方式，请人工补充基本信息。")
        return info


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------


def _header_group_end(body: list[str], index: int) -> int | None:
    """若 ``index`` 是「名称 / 角色 / 纯日期」这类三行式的首行，返回日期行下标。"""

    if not _is_header_like(body[index]):
        return None
    for offset in (1, 2):
        candidate = index + offset
        if candidate >= len(body):
            break
        if _is_pure_date(body[candidate]):
            if all(_is_header_like(body[position]) for position in range(index, candidate)):
                return candidate
            return None
        if not _is_header_like(body[candidate]):
            break
    return None


def _is_item_header(body: list[str], index: int) -> bool:
    """该行是否是新条目的标题行（行尾日期，或三行式标题组的首行）。"""

    line = body[index]
    if _has_trailing_date(line):
        return True
    if not _is_header_like(line):
        return False
    return _header_group_end(body, index) is not None


def _group_by_starts(lines: list[str], starts: list[int]) -> list[list[str]]:
    normalized_starts = sorted({0, *[start for start in starts if 0 <= start < len(lines)]})
    groups: list[list[str]] = []
    for position, start in enumerate(normalized_starts):
        end = (
            normalized_starts[position + 1]
            if position + 1 < len(normalized_starts)
            else len(lines)
        )
        groups.append(lines[start:end])
    return [group for group in groups if any(line.strip() for line in group)]


def _tokenize(text: str) -> list[str]:
    # 注意：不把中点「·」当分隔符，中文机构名常用它（如「成都问问大象·柴大官人项目组」）
    tokens = []
    for token in re.split(r"[|｜•]|\s+", text):
        cleaned = token.strip(" \t·|/-–—,，、。;；")
        if cleaned:
            tokens.append(cleaned)
    return tokens


def _first_matching(tokens: list[str], words: tuple[str, ...]) -> str | None:
    for token in tokens:
        for word in words:
            if word in token:
                return token
    return None


def _is_short_role(value: str) -> bool:
    text = value.strip()
    if not text or len(text) > 12:
        return False
    if _is_pure_date(text):
        return False
    # 形如「2025.12」的残留片段不是角色名
    return not re.fullmatch(r"[\d.\-/年月日\s]+", text)


def _assign_fields(
    section_type: SectionType, tokens: list[str], fields: dict[str, str]
) -> tuple[bool, set[str]]:
    """把标题行切出的片段分配到结构化字段，返回 (是否有字段产出, 已消费片段)。"""

    consumed: set[str] = set()

    if section_type is SectionType.education:
        school = _first_matching(tokens, ("大学", "学院", "学校", "中学", "高中", "技校", "书院"))
        if school:
            fields["school"] = school
            consumed.add(school)
        degree = _first_matching(
            [token for token in tokens if token not in consumed], DEGREE_WORDS
        )
        if degree:
            fields["degree"] = degree
            consumed.add(degree)
        major = next((token for token in tokens if token not in consumed), None)
        if major:
            fields["major"] = major
            consumed.add(major)

    elif section_type is SectionType.experience:
        if tokens:
            fields["company"] = tokens[0]
            consumed.add(tokens[0])
        remaining = [token for token in tokens if token not in consumed]
        role = _first_matching(remaining, ROLE_WORDS)
        if role is None and remaining and _is_short_role(remaining[0]):
            role = remaining[0]
        if role:
            fields["role"] = role
            consumed.add(role)

    elif section_type is SectionType.project:
        if tokens:
            fields["name"] = tokens[0]
            consumed.add(tokens[0])
        remaining = [token for token in tokens if token not in consumed]
        role = _first_matching(remaining, ROLE_WORDS)
        if role is None and remaining and _is_short_role(remaining[0]):
            role = remaining[0]
        if role:
            fields["role"] = role
            consumed.add(role)

    elif section_type is SectionType.award:
        if tokens:
            fields["name"] = tokens[0]
            consumed.add(tokens[0])

    return bool(fields), consumed


def _split_segments(line: str) -> list[str]:
    """把「姓名：张三 | 手机：138…」这类合并行拆成若干片段。"""

    return [segment for segment in re.split(r"[|｜]|\s{2,}", line) if segment.strip()]


def _split_label(line: str) -> tuple[str | None, str]:
    for separator in ("：", ":"):
        if separator in line:
            label, _, value = line.partition(separator)
            label = label.strip(" \t【】[]")
            if label and len(label) <= 12:
                return label, value.strip()
    return None, line.strip()


def _apply_contact(info: BasicInfo, value: str) -> None:
    phone_match = PHONE_RE.search(value)
    if phone_match and not info.phone:
        info.phone = phone_match.group(1)
    email_match = EMAIL_RE.search(value)
    if email_match and not info.email:
        info.email = email_match.group(0)
