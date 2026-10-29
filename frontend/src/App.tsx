import { ChangeEvent, useCallback, useEffect, useState } from "react";
import AnalysisWorkspace from "./AnalysisWorkspace";
import PaginatedPreview from "./PaginatedPreview";

export type BasicInfo = { name: string; phone: string; email: string; location: string; jobTarget: string };
export type Item = { id: string; order: number; fields: Record<string, string>; content: string; hidden?: boolean };
export type Section = { id: string; type: SectionType; title: string; order: number; items: Item[]; hidden?: boolean };
export type ResumeDocument = { basicInfo: BasicInfo; sections: Section[] };
export type SectionType = "education" | "experience" | "project" | "skill" | "award" | "custom";
type Resume = { id: string; title: string; createdAt: string; updatedAt: string; latestVersion: number };
type Version = { id: string; resumeId: string; version: number; parentVersionId: string | null; source: string; createdAt: string; document?: ResumeDocument };
type ResumeDetail = { resume: Resume; draft: { id: string; baseVersionId: string | null; document: ResumeDocument; updatedAt: string } | null; versions: Version[]; latestAnalysis?: Analysis | null };
type LayoutSummary = { id: string; resumeId: string; name: string; jdText: string; analysisId: string | null; createdAt: string; updatedAt: string };
type ResumeLayout = LayoutSummary & { document: ResumeDocument };
export type Suggestion = { id: string; sectionId: string; itemId: string; original: string; suggested: string; reason: string; status: "pending" | "accepted" | "rejected" | "edited"; editedText: string | null };
export type Analysis = {
  id: string; status: "processing" | "completed" | "partial_failed" | "failed"; resumeVersionId: string; jdText: string;
  overallScore: number | null; scoreLevel: string | null; summary: string | null;
  scoreBreakdown: { dimension: string; weight: number; score: number; reason: string }[];
  itemMatches: { sectionId: string; itemId: string; level: "high" | "medium" | "low"; score: number | null; reason: string; matchedRequirements: string[] }[];
  missingRequirements: { requirement: string; importance: string; reason: string }[];
  suggestions: Suggestion[];
  providers: Record<string, { status: string; errorMessage: string | null }>;
};
export type Rewrite = { original: string; rewritten: string; explanation: string };
export type AIConfiguration = { provider: string; model: string | null; configured: boolean; demo: boolean };
const cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "无锡", "成都", "重庆", "武汉", "西安", "长沙", "合肥", "厦门", "天津", "青岛", "郑州", "济南", "其他城市"];
type Template = { id: string; name: string; description: string; formats: ("docx" | "pdf")[] };
type ExportRecord = { id: string; status: "processing" | "completed" | "failed"; format: string; templateId: string; downloadUrl: string | null; errorMessage?: string | null };
type Page = "home" | "editor" | "analysis" | "export";

const sectionTitles: Record<SectionType, string> = {
  education: "教育经历", experience: "工作 / 实习经历", project: "项目经历",
  skill: "技能与工具", award: "荣誉奖项", custom: "自定义模块",
};
const emptyDocument = (): ResumeDocument => ({
  basicInfo: { name: "", phone: "", email: "", location: "", jobTarget: "" },
  sections: [],
});
const id = (prefix: string) => `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => null) as { data?: T; error?: { message?: string } } | null;
  if (!response.ok || !payload?.data) throw new Error(payload?.error?.message || `请求失败（${response.status}）`);
  return payload.data;
}

function normalizeDocument(document: ResumeDocument): ResumeDocument {
  return {
    ...document,
    sections: document.sections.map((section, sectionIndex) => ({
      ...section, order: sectionIndex,
      items: section.items.map((item, itemIndex) => ({ ...item, order: itemIndex })),
    })),
  };
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function suggestedLayoutName(jd: string, document: ResumeDocument) {
  const match = jd.match(/(?:岗位名称|招聘岗位|职位名称|应聘岗位)\s*[:：]\s*([^\r\n，。;；]{1,60})/);
  return match?.[1]?.trim() || document.basicInfo.jobTarget || "";
}

function workspaceSignature(document: ResumeDocument, name: string, jdText: string) {
  return JSON.stringify({ document, name, jdText });
}

export default function App() {
  const [page, setPage] = useState<Page>("home");
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [detail, setDetail] = useState<ResumeDetail | null>(null);
  const [document, setDocument] = useState<ResumeDocument>(emptyDocument());
  const [jdDocument, setJdDocument] = useState<ResumeDocument>(emptyDocument());
  const [jdText, setJdText] = useState("");
  const [layoutName, setLayoutName] = useState("");
  const [layouts, setLayouts] = useState<LayoutSummary[]>([]);
  const [activeLayout, setActiveLayout] = useState<ResumeLayout | null>(null);
  const [exportLayout, setExportLayout] = useState<ResumeLayout | null>(null);
  const [workspaceBaseline, setWorkspaceBaseline] = useState("");
  const [workspaceKey, setWorkspaceKey] = useState(0);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [aiConfiguration, setAIConfiguration] = useState<AIConfiguration | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [exportRecord, setExportRecord] = useState<ExportRecord | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const jdIsDirty = Boolean(detail && workspaceSignature(jdDocument, layoutName, jdText) !== workspaceBaseline);
  const hasUnsavedChanges = Boolean(detail && (JSON.stringify(document) !== JSON.stringify(detail.draft?.document ?? emptyDocument()) || jdIsDirty));

  const clearMessage = () => { setNotice(null); setError(null); };
  const report = (message: string) => { setError(message); setNotice(null); };

  function initializeWorkspace(source: ResumeDocument, name: string, text: string, layout: ResumeLayout | null = null) {
    setJdDocument(structuredClone(source)); setLayoutName(name); setJdText(text);
    setActiveLayout(layout); setWorkspaceBaseline(workspaceSignature(source, name, text));
    setWorkspaceKey((value) => value + 1);
  }

  const loadResumes = useCallback(async () => {
    try {
      const data = await request<{ items: Resume[] }>("/api/resumes");
      setResumes(data.items);
    } catch (reason) { report(reason instanceof Error ? reason.message : "无法读取简历列表。"); }
  }, []);

  async function openResume(resumeId: string, nextPage: Page = "editor") {
    if (busy) return;
    if (detail?.resume.id === resumeId) { setPage(nextPage); return; }
    if (hasUnsavedChanges && !window.confirm("当前简历有未保存的修改。切换会放弃这些修改，确定继续吗？")) return;
    setBusy("正在加载简历…"); clearMessage();
    try {
      const data = await request<ResumeDetail>(`/api/resumes/${resumeId}`);
      const [savedLayouts, analyzedVersion] = await Promise.all([
        request<{ items: LayoutSummary[] }>(`/api/resumes/${resumeId}/layouts`),
        data.latestAnalysis ? request<Version>(`/api/resume-versions/${data.latestAnalysis.resumeVersionId}`) : Promise.resolve(null),
      ]);
      const base = data.draft?.document ?? emptyDocument();
      const workspace = analyzedVersion?.document ?? base;
      const text = data.latestAnalysis?.jdText ?? "";
      setDetail(data);
      setDocument(base); setLayouts(savedLayouts.items); setExportLayout(null);
      initializeWorkspace(workspace, suggestedLayoutName(text, workspace), text);
      setAnalysis(data.latestAnalysis ?? null); setExportRecord(null);
      setPage(nextPage);
    } catch (reason) { report(reason instanceof Error ? reason.message : "无法打开简历。"); }
    finally { setBusy(null); }
  }

  useEffect(() => { void loadResumes(); }, [loadResumes]);
  useEffect(() => {
    if (!hasUnsavedChanges) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasUnsavedChanges]);
  useEffect(() => {
    void request<AIConfiguration>("/api/analyses/configuration")
      .then(setAIConfiguration).catch((reason: Error) => report(reason.message));
  }, []);
  useEffect(() => {
    if (page === "export" && templates.length === 0) {
      void request<{ items: Template[] }>("/api/export-templates").then((data) => setTemplates(data.items)).catch((reason: Error) => report(reason.message));
    }
  }, [page, templates.length]);
  useEffect(() => {
    if (!analysis || analysis.status !== "processing") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    setBusy("AI 正在分析 JD，请稍候…");
    const poll = async () => {
      try {
        const result = await request<Analysis>(`/api/analyses/${analysis.id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (result.status !== "processing") {
          setAnalysis(result); setBusy(null);
          if (result.status === "completed") setNotice("分析已完成。评分基于分析时的内容；修改后请重新分析。");
          else report(Object.values(result.providers).filter((value) => value.status === "failed").map((value) => value.errorMessage).join("；") || "分析未完成，请重试。");
        } else if (++attempts < 180) timer = setTimeout(() => void poll(), 1000);
        else { setBusy(null); report("分析等待超时，请刷新后查看或重试；不会使用演示评分替代。"); }
      } catch (reason) {
        if (!controller.signal.aborted) { setBusy(null); report(reason instanceof Error ? reason.message : "无法读取分析结果。"); }
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [analysis?.id, analysis?.status]);

  async function createResume(title: string, basicInfo: BasicInfo = emptyDocument().basicInfo) {
    if (hasUnsavedChanges && !window.confirm("当前简历有未保存的修改，创建新简历会放弃修改。确定继续吗？")) return;
    setBusy("正在创建简历…"); clearMessage();
    try {
      const data = await request<ResumeDetail>("/api/resumes", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, basicInfo }),
      });
      setResumes((current) => [data.resume, ...current]);
      setDetail(data); setDocument(data.draft?.document ?? emptyDocument()); setAnalysis(null); setExportRecord(null); setPage("editor");
      initializeWorkspace(data.draft?.document ?? emptyDocument(), basicInfo.jobTarget, "");
      setLayouts([]); setExportLayout(null);
      setNotice("已创建简历，内容可以反复编辑和保存。");
    } catch (reason) { report(reason instanceof Error ? reason.message : "创建失败。"); }
    finally { setBusy(null); }
  }

  async function deleteResume(resume: Resume) {
    if (!window.confirm(`确定删除「${resume.title}」吗？此操作会同时删除内容、分析和导出记录，且无法恢复。`)) return;
    setBusy("正在删除简历…"); clearMessage();
    try {
      const response = await fetch(`/api/resumes/${resume.id}`, { method: "DELETE" });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { error?: { message?: string } } | null;
        throw new Error(payload?.error?.message || "删除简历失败。");
      }
      setResumes((current) => current.filter((item) => item.id !== resume.id));
      if (detail?.resume.id === resume.id) {
        setDetail(null); setDocument(emptyDocument()); setAnalysis(null); setPage("home");
      }
      setNotice(`已删除「${resume.title}」。`);
    } catch (reason) { report(reason instanceof Error ? reason.message : "删除简历失败。"); }
    finally { setBusy(null); }
  }

  async function createFromDocument(title: string, initialDocument: ResumeDocument, origin: string, warnings: string[] = []) {
    if (hasUnsavedChanges && !window.confirm("当前简历有未保存的修改，导入新简历会放弃修改。确定继续吗？")) return;
    setBusy("正在创建并填充草稿…"); clearMessage();
    try {
      const created = await request<ResumeDetail>("/api/resumes", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, basicInfo: initialDocument.basicInfo }),
      });
      const normalized = normalizeDocument(initialDocument);
      const saved = await request<{ draft: ResumeDetail["draft"] }>(`/api/resumes/${created.resume.id}/draft`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document: normalized }),
      });
      setResumes((current) => [created.resume, ...current]);
      setDetail({ ...created, draft: saved.draft });
      setDocument(saved.draft?.document ?? normalized); setAnalysis(null); setExportRecord(null); setPage("editor");
      initializeWorkspace(saved.draft?.document ?? normalized, normalized.basicInfo.jobTarget, "");
      setLayouts([]); setExportLayout(null);
      setNotice(warnings.length ? `${origin}完成；有 ${warnings.length} 项内容需要校对。` : `${origin}完成，请检查后保存，之后可随时继续修改。`);
    } catch (reason) { report(reason instanceof Error ? reason.message : "创建闪填草稿失败。"); }
    finally { setBusy(null); }
  }

  async function flashFillFile(file: File) {
    setBusy("正在读取并识别简历…"); clearMessage();
    try {
      const form = new FormData(); form.append("file", file);
      const data = await request<{ document: ResumeDocument; warnings: string[] }>("/api/resumes/import", { method: "POST", body: form });
      const title = file.name.replace(/\.[^.]+$/, "").trim() || "导入简历";
      await createFromDocument(title, data.document, "简历闪填", data.warnings);
    } catch (reason) { report(reason instanceof Error ? reason.message : "简历闪填失败。"); }
    finally { setBusy(null); }
  }

  async function flashFillText(text: string, title: string) {
    if (!text.trim()) return report("请先粘贴简历内容。");
    setBusy("正在识别粘贴内容…"); clearMessage();
    try {
      const data = await request<{ document: ResumeDocument; warnings: string[] }>("/api/resumes/parse-text", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
      });
      await createFromDocument(title.trim() || "闪填简历", data.document, "文本闪填", data.warnings);
    } catch (reason) { report(reason instanceof Error ? reason.message : "文本闪填失败。"); }
    finally { setBusy(null); }
  }

  async function persistCurrent() {
    if (!detail) throw new Error("请先打开一份简历。");
    const saved = await request<{ draft: NonNullable<ResumeDetail["draft"]> }>(`/api/resumes/${detail.resume.id}/draft`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document: normalizeDocument(document) }),
    });
    setDocument(saved.draft.document);
    setDetail((current) => current ? { ...current, draft: saved.draft } : current);
    setResumes((current) => current.map((resume) => resume.id === detail.resume.id ? { ...resume, updatedAt: saved.draft.updatedAt } : resume));
    setExportRecord(null);
    return saved.draft;
  }

  async function saveDraft() {
    setBusy("正在保存简历…"); clearMessage();
    try { await persistCurrent(); setNotice("简历已保存，可以继续修改。"); }
    catch (reason) { report(reason instanceof Error ? reason.message : "保存失败。"); }
    finally { setBusy(null); }
  }

  async function parseText(text: string) {
    if (!text.trim()) return report("请先粘贴简历文本。");
    setBusy("正在拆分文本…"); clearMessage();
    try {
      const data = await request<{ document: ResumeDocument; warnings: string[] }>("/api/resumes/parse-text", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
      });
      setDocument(data.document);
      setNotice(data.warnings.length ? `文本已拆分；请留意 ${data.warnings.length} 项待校正提示。` : "文本已拆分到草稿，请检查后保存。");
    } catch (reason) { report(reason instanceof Error ? reason.message : "文本拆分失败。"); }
    finally { setBusy(null); }
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy("正在解析文件…"); clearMessage();
    try {
      const form = new FormData(); form.append("file", file);
      const data = await request<{ document: ResumeDocument; warnings: string[] }>("/api/resumes/import", { method: "POST", body: form });
      setDocument(data.document);
      setNotice(data.warnings.length ? `已解析文件，请人工校正 ${data.warnings.length} 项提示。` : "文件解析成功，已填入当前草稿。");
    } catch (reason) { report(reason instanceof Error ? reason.message : "文件解析失败。"); }
    finally { event.target.value = ""; setBusy(null); }
  }

  function updateBasic(field: keyof BasicInfo, value: string) {
    setDocument((current) => ({ ...current, basicInfo: { ...current.basicInfo, [field]: value } }));
  }
  function addSection(type: SectionType) {
    setDocument((current) => ({ ...current, sections: [...current.sections, { id: id("section"), type, title: sectionTitles[type], order: current.sections.length, items: [] }] }));
  }
  function updateSection(sectionId: string, patch: Partial<Section>) {
    setDocument((current) => ({ ...current, sections: current.sections.map((section) => section.id === sectionId ? { ...section, ...patch } : section) }));
  }
  function removeSection(sectionId: string) {
    setDocument((current) => normalizeDocument({ ...current, sections: current.sections.filter((section) => section.id !== sectionId) }));
  }
  function addItem(sectionId: string) {
    setDocument((current) => ({
      ...current, sections: current.sections.map((section) => section.id !== sectionId ? section : {
        ...section, items: [...section.items, { id: id("item"), order: section.items.length, fields: {}, content: "" }],
      }),
    }));
  }
  function updateItem(sectionId: string, itemId: string, content: string) {
    setDocument((current) => ({ ...current, sections: current.sections.map((section) => section.id !== sectionId ? section : {
      ...section, items: section.items.map((item) => item.id === itemId ? { ...item, content } : item),
    }) }));
  }
  function updateItemField(sectionId: string, itemId: string, field: string, value: string) {
    setDocument((current) => ({ ...current, sections: current.sections.map((section) => section.id !== sectionId ? section : {
      ...section, items: section.items.map((item) => item.id === itemId ? { ...item, fields: { ...item.fields, [field]: value } } : item),
    }) }));
  }
  function removeItem(sectionId: string, itemId: string) {
    setDocument((current) => normalizeDocument({ ...current, sections: current.sections.map((section) => section.id !== sectionId ? section : { ...section, items: section.items.filter((item) => item.id !== itemId) }) }));
  }
  function moveSection(from: number, to: number) {
    setDocument((current) => {
      const sections = [...current.sections]; const [moved] = sections.splice(from, 1); sections.splice(to, 0, moved);
      return normalizeDocument({ ...current, sections });
    });
  }
  function moveItem(sectionId: string, from: number, to: number) {
    setDocument((current) => normalizeDocument({ ...current, sections: current.sections.map((section) => {
      if (section.id !== sectionId) return section;
      const items = [...section.items]; const [moved] = items.splice(from, 1); items.splice(to, 0, moved);
      return { ...section, items };
    }) }));
  }

  async function runAnalysis(jdText: string) {
    if (!detail) return;
    if (jdText.trim().length < 50) return report("请粘贴至少 50 个字符的完整 JD。");
    if (!jdDocument.sections.some((section) => !section.hidden && section.items.some((item) => !item.hidden))) return report("请至少填写一个未隐藏的经历条目，再进行分析。");
    if (!aiConfiguration?.configured) return report("请先在后端配置 DEEPSEEK_API_KEY，并重启后端、刷新页面。");
    setBusy("正在分析 JD…"); clearMessage();
    try {
      const snapshot = await request<Version>(`/api/resumes/${detail.resume.id}/versions`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: "optimized", document: normalizeDocument(jdDocument) }),
      });
      const created = await request<Pick<Analysis, "id" | "resumeVersionId" | "providers">>("/api/analyses", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resumeVersionId: snapshot.id, jdText }),
      });
      setAnalysis({
        ...created, status: "processing", jdText, overallScore: null, scoreLevel: null, summary: null,
        scoreBreakdown: [], itemMatches: [], missingRequirements: [], suggestions: [],
      });
    } catch (reason) { report(reason instanceof Error ? reason.message : "JD 分析失败。"); }
    finally { setBusy(null); }
  }

  async function rewriteSuggestion(suggestion: Suggestion): Promise<Rewrite | null> {
    const item = jdDocument.sections.find((section) => section.id === suggestion.sectionId)?.items.find((value) => value.id === suggestion.itemId);
    if (!item) return null;
    setBusy("AI 正在按建议改写，尚未修改原文…"); clearMessage();
    try {
      return await request<Rewrite>(`/api/suggestions/${suggestion.id}/rewrite`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ currentContent: item.content, document: normalizeDocument(jdDocument) }),
      });
    } catch (reason) { report(reason instanceof Error ? reason.message : "AI 改写失败。"); return null; }
    finally { setBusy(null); }
  }

  async function confirmRewrite(suggestion: Suggestion, rewrite: Rewrite): Promise<boolean> {
    if (!detail) return false;
    setBusy("正在应用 AI 修改到排版…"); clearMessage();
    try {
      const saved = await request<{ document: ResumeDocument }>(`/api/suggestions/${suggestion.id}/preview-confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ original: rewrite.original, replacement: rewrite.rewritten, document: normalizeDocument(jdDocument) }),
      });
      setJdDocument(saved.document);
      setAnalysis((current) => current ? { ...current, suggestions: current.suggestions.map((value) => value.id === suggestion.id ? { ...value, status: "edited", editedText: rewrite.rewritten } : value) } : current);
      setNotice("已应用到当前 JD 排版，基础资料未改变。点击“保存排版并前往导出”后可导出。");
      return true;
    } catch (reason) { report(reason instanceof Error ? reason.message : "确认修改失败。"); return false; }
    finally { setBusy(null); }
  }

  function changeJdText(value: string) {
    setJdText(value);
    if (!layoutName.trim() || (!activeLayout && layoutName === suggestedLayoutName(jdText, jdDocument))) {
      setLayoutName(suggestedLayoutName(value, jdDocument));
    }
  }

  function newJdLayout() {
    if (jdIsDirty && !window.confirm("当前 JD 排版尚未保存，确定放弃修改并从基础资料新建吗？")) return;
    initializeWorkspace(document, document.basicInfo.jobTarget, "");
    setAnalysis(null); setPage("analysis"); clearMessage();
  }

  function openJdWorkspace() {
    if (!jdIsDirty && !activeLayout && !analysis) initializeWorkspace(document, document.basicInfo.jobTarget, "");
    setPage("analysis");
  }

  async function saveJdLayout() {
    if (!detail) return;
    if (!layoutName.trim()) return report("请先填写岗位排版名称，例如“产品经理｜某公司”。");
    setBusy("正在保存岗位排版…"); clearMessage();
    try {
      const saved = await request<ResumeLayout>(activeLayout ? `/api/resume-layouts/${activeLayout.id}` : `/api/resumes/${detail.resume.id}/layouts`, {
        method: activeLayout ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: layoutName.trim(), jdText, document: normalizeDocument(jdDocument),
          analysisId: analysis?.id ?? null,
          ...(activeLayout ? { expectedUpdatedAt: activeLayout.updatedAt } : {}),
        }),
      });
      setLayouts((current) => [saved, ...current.filter((layout) => layout.id !== saved.id)]);
      initializeWorkspace(saved.document, saved.name, saved.jdText, saved);
      setExportLayout(saved); setExportRecord(null); setPage("export"); void loadResumes();
      setNotice(`已保存「${saved.name}」。导出中心已选中该排版，基础资料未被覆盖。`);
    } catch (reason) { report(reason instanceof Error ? reason.message : "保存排版失败。"); }
    finally { setBusy(null); }
  }

  async function selectExportLayout(layoutId: string) {
    setExportRecord(null);
    if (!layoutId) { setExportLayout(null); return; }
    setBusy("正在读取岗位排版…"); clearMessage();
    try { setExportLayout(await request<ResumeLayout>(`/api/resume-layouts/${layoutId}`)); }
    catch (reason) { report(reason instanceof Error ? reason.message : "读取排版失败。"); }
    finally { setBusy(null); }
  }

  async function editSelectedLayout() {
    if (jdIsDirty && !window.confirm("当前 JD 排版尚未保存，确定放弃它并打开所选排版吗？")) return;
    setBusy("正在打开排版…"); clearMessage();
    try {
      const savedAnalysis = exportLayout?.analysisId ? await request<Analysis>(`/api/analyses/${exportLayout.analysisId}`) : null;
      const source = exportLayout?.document ?? document;
      initializeWorkspace(source, exportLayout?.name ?? source.basicInfo.jobTarget, exportLayout?.jdText ?? "", exportLayout);
      setAnalysis(savedAnalysis); setPage("analysis");
    } catch (reason) { report(reason instanceof Error ? reason.message : "打开排版失败。"); }
    finally { setBusy(null); }
  }

  async function createExport(templateId: string, format: "docx" | "pdf") {
    if (!detail) return;
    setBusy("正在生成导出文件…"); clearMessage();
    try {
      let endpoint: string;
      if (exportLayout) endpoint = `/api/resume-layouts/${exportLayout.id}/exports`;
      else {
        await persistCurrent();
        const snapshot = await request<Version>(`/api/resumes/${detail.resume.id}/snapshot`, { method: "POST" });
        endpoint = `/api/resume-versions/${snapshot.id}/exports`;
      }
      const data = await request<ExportRecord>(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ templateId, format }),
      });
      setExportRecord(data);
      setNotice(data.status === "completed" ? "导出文件已生成，可立即下载。" : "导出任务已创建。");
    } catch (reason) { report(reason instanceof Error ? reason.message : "导出失败。"); }
    finally { setBusy(null); }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" disabled={Boolean(busy)} onClick={() => setPage("home")}><span>R</span><strong>ResumeMatch</strong></button>
        <p className="workspace-label">简历智造工作台</p>
        <nav>
          <NavButton icon="⌂" active={page === "home"} disabled={Boolean(busy)} onClick={() => setPage("home")}>简历库</NavButton>
          <NavButton icon="▤" active={page === "editor"} disabled={!detail || Boolean(busy)} onClick={() => setPage("editor")}>简历编辑</NavButton>
          <NavButton icon="◌" active={page === "analysis"} disabled={!detail || Boolean(busy)} onClick={openJdWorkspace}>JD 分析</NavButton>
          <NavButton icon="⇩" active={page === "export"} disabled={!detail || Boolean(busy)} onClick={() => setPage("export")}>导出中心</NavButton>
        </nav>
        <div className="sidebar-tip"><span className="tip-dot" />简历存本机 · AI 分析需联网</div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div><p className="crumb">RESUME MATCH / {page.toUpperCase()}</p><h1>{page === "home" ? "简历库" : detail?.resume.title ?? "简历工作台"}</h1></div>
          {detail && <div className="resume-switcher"><span>{hasUnsavedChanges ? "有未保存修改" : "当前简历"}</span><select disabled={Boolean(busy)} value={detail.resume.id} onChange={(event) => void openResume(event.target.value, page)}>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.title}</option>)}</select></div>}
        </header>
        {(notice || error || busy) && <div className={`banner ${error ? "banner-error" : ""}`} role={error ? "alert" : "status"}>{busy || error || notice}</div>}
        {page === "home" && <HomePage resumes={resumes} onCreate={createResume} onOpen={openResume} onDelete={deleteResume} onFile={flashFillFile} onText={flashFillText} busy={busy} />}
        {page === "editor" && detail && <EditorPage document={document} detail={detail} busy={busy} onBasic={updateBasic} onAddSection={addSection} onUpdateSection={updateSection} onRemoveSection={removeSection} onAddItem={addItem} onUpdateItem={updateItem} onUpdateItemField={updateItemField} onRemoveItem={removeItem} onMoveSection={moveSection} onMoveItem={moveItem} onSave={saveDraft} onParse={parseText} onImport={importFile} />}
        {page === "analysis" && detail && <AnalysisWorkspace key={`${detail.resume.id}:${workspaceKey}`} jdText={jdText} layoutName={layoutName} onJdChange={changeJdText} onLayoutNameChange={setLayoutName} onNewLayout={newJdLayout} analysis={analysis} document={jdDocument} configuration={aiConfiguration} busy={busy} onDocumentChange={(value) => setJdDocument(normalizeDocument(value))} onAnalyze={runAnalysis} onRewrite={rewriteSuggestion} onConfirm={confirmRewrite} onSave={saveJdLayout} renderFields={(section, item, onChange) => <ItemFields sectionType={section.type} item={item} onChange={onChange} />} />}
        {page === "export" && detail && <ExportPage document={exportLayout?.document ?? document} resumes={resumes} resumeId={detail.resume.id} onSelectResume={(value) => void openResume(value, "export")} layouts={layouts} selectedLayoutId={exportLayout?.id ?? ""} onSelectLayout={selectExportLayout} onEditLayout={editSelectedLayout} templates={templates} busy={busy} record={exportRecord} onExport={createExport} />}
      </main>
    </div>
  );
}

function NavButton({ icon, active, disabled, onClick, children }: { icon: string; active: boolean; disabled?: boolean; onClick: () => void; children: string }) {
  return <button className={`nav-button ${active ? "active" : ""}`} disabled={disabled} onClick={onClick}><span>{icon}</span>{children}</button>;
}

function ItemFields({ sectionType, item, onChange }: { sectionType: SectionType; item: Item; onChange: (field: string, value: string) => void }) {
  const fieldConfig: Record<SectionType, [string, string, string?][]> = {
    education: [["school", "学校名称", "例如：示例大学"], ["major", "专业", "例如：软件工程"], ["degree", "学历", "例如：本科"], ["startDate", "开始时间", "YYYY-MM"], ["endDate", "结束时间", "YYYY-MM / 至今"]],
    experience: [["company", "公司 / 组织", "例如：某某科技有限公司"], ["role", "职位 / 角色", "例如：产品实习生"], ["startDate", "开始时间", "YYYY-MM"], ["endDate", "结束时间", "YYYY-MM / 至今"]],
    project: [["name", "项目名称", "例如：接口管理系统"], ["role", "项目职责", "例如：接口开发与测试"], ["startDate", "开始时间", "YYYY-MM"], ["endDate", "结束时间", "YYYY-MM / 至今"]],
    skill: [["category", "技能类别", "例如：编程工具"], ["name", "补充名称", "可选"]],
    award: [["name", "奖项 / 证书名称", ""], ["date", "获奖时间", "YYYY / YYYY-MM"]],
    custom: [["name", "条目标题", "可选"]],
  };
  return <div className={`field-grid ${sectionType}`}>{fieldConfig[sectionType].map(([key, label, placeholder]) => <label key={key}>{label}{!item.fields[key] && <em>待填写</em>}<StructuredFieldInput field={key} value={item.fields[key] ?? ""} placeholder={placeholder} onChange={(value) => onChange(key, value)} /></label>)}</div>;
}

function BasicInfoFields({ info, onChange }: { info: BasicInfo; onChange: (field: keyof BasicInfo, value: string) => void }) {
  return <div className="basic-grid">
    <label>姓名<input value={info.name} onChange={(event) => onChange("name", event.target.value)} placeholder="填写姓名" /></label>
    <label>目标岗位<input value={info.jobTarget} onChange={(event) => onChange("jobTarget", event.target.value)} placeholder="例如：产品实习生" /></label>
    <label>电话<input type="tel" inputMode="numeric" pattern="1[3-9][0-9]{9}" maxLength={11} value={info.phone} onChange={(event) => onChange("phone", event.target.value.replace(/[\s-]/g, ""))} placeholder="11 位中国大陆手机号" /><small>仅支持 11 位中国大陆手机号</small></label>
    <label>邮箱<input type="email" value={info.email} onChange={(event) => onChange("email", event.target.value)} placeholder="name@example.com" /><small>例如 name@example.com</small></label>
    <label>所在城市<select value={info.location} onChange={(event) => onChange("location", event.target.value)}><option value="">选择城市</option>{cities.map((city) => <option key={city} value={city}>{city}</option>)}</select></label>
  </div>;
}

function StructuredFieldInput({ field, value, placeholder, onChange }: { field: string; value: string; placeholder?: string; onChange: (value: string) => void }) {
  if (field === "startDate") return <input type="month" value={value} onChange={(event) => onChange(event.target.value)} />;
  if (field === "endDate") return <span className="month-field"><input type="month" value={value === "至今" ? "" : value} disabled={value === "至今"} onChange={(event) => onChange(event.target.value)} /><label><input type="checkbox" checked={value === "至今"} onChange={(event) => onChange(event.target.checked ? "至今" : "")} />至今</label></span>;
  if (field === "date") return <input type="month" value={value} onChange={(event) => onChange(event.target.value)} />;
  return <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />;
}

function HomePage({ resumes, onCreate, onOpen, onDelete, onFile, onText, busy }: { resumes: Resume[]; onCreate: (title: string) => Promise<void>; onOpen: (id: string) => Promise<void>; onDelete: (resume: Resume) => Promise<void>; onFile: (file: File) => Promise<void>; onText: (text: string, title: string) => Promise<void>; busy: string | null }) {
  const [title, setTitle] = useState(""); const [text, setText] = useState(""); const [mode, setMode] = useState<"file" | "text" | "blank">("file");
  return <div className="page-stack">
    <section className="welcome-panel"><div><p className="eyebrow">来个简历闪填</p><h2>上传已有简历，快速生成可编辑内容。</h2><p>先自动提取，再逐步校对；同一份简历可以反复编辑和保存。</p></div><div className="stat"><strong>{resumes.length}</strong><span>份简历</span></div></section>
    <section className="section-card flash-fill"><div className="flash-steps"><span className="active">1. 导入内容</span><i /> <span>2. 校对信息</span><i /> <span>3. 保存简历</span></div><div className="flash-heading"><div><p className="eyebrow">快速开始</p><h2>把现有简历变成可编辑资料</h2></div><div className="source-tabs"><button className={mode === "file" ? "selected" : ""} onClick={() => setMode("file")}>上传文件</button><button className={mode === "text" ? "selected" : ""} onClick={() => setMode("text")}>粘贴文本</button><button className={mode === "blank" ? "selected" : ""} onClick={() => setMode("blank")}>从空白开始</button></div></div>
      {mode === "file" && <label className="drop-zone"><span className="upload-icon">↑</span><strong>点击选择简历文件</strong><small>支持 PDF、DOCX，最大 10 MB。系统会先生成草稿供你校对。</small><input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={Boolean(busy)} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onFile(file); event.target.value = ""; }} /></label>}
      {mode === "text" && <form className="paste-form" onSubmit={(event) => { event.preventDefault(); void onText(text, title); }}><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="简历名称（可选）" maxLength={200} /><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="粘贴简历全文，支持姓名、教育背景、项目/工作经历、技能等常见格式…" /><button disabled={Boolean(busy)} type="submit">识别并创建草稿 <span>→</span></button></form>}
      {mode === "blank" && <form className="blank-form" onSubmit={(event) => { event.preventDefault(); if (title.trim()) void onCreate(title.trim()); }}><p>适合从零开始录入。创建后可随时添加模块、经历和技能。</p><div><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：2026 春招产品经理简历" maxLength={200} /><button disabled={Boolean(busy)} type="submit">创建空白简历 <span>→</span></button></div></form>}
    </section>
    <section><div className="section-heading"><div><p className="eyebrow">最近编辑</p><h2>我的简历</h2></div></div><div className="resume-grid">{resumes.length === 0 ? <EmptyState title="还没有简历" text="创建第一份简历，开始整理你的职业经历。" /> : resumes.map((resume) => <article className="resume-card" key={resume.id}><button className="resume-open" disabled={Boolean(busy)} onClick={() => void onOpen(resume.id)}><span className="resume-monogram">简</span><span><strong>{resume.title}</strong><small>最近保存 · {formatTime(resume.updatedAt)}</small></span><i>→</i></button><button className="resume-delete" disabled={Boolean(busy)} onClick={() => void onDelete(resume)} aria-label={`删除${resume.title}`}>删除</button></article>)}</div></section>
  </div>;
}

function EditorPage(props: {
  document: ResumeDocument; detail: ResumeDetail; busy: string | null; onBasic: (field: keyof BasicInfo, value: string) => void; onAddSection: (type: SectionType) => void; onUpdateSection: (id: string, patch: Partial<Section>) => void; onRemoveSection: (id: string) => void; onAddItem: (id: string) => void; onUpdateItem: (sectionId: string, itemId: string, value: string) => void; onUpdateItemField: (sectionId: string, itemId: string, field: string, value: string) => void; onRemoveItem: (sectionId: string, itemId: string) => void; onMoveSection: (from: number, to: number) => void; onMoveItem: (sectionId: string, from: number, to: number) => void; onSave: () => Promise<void>; onParse: (text: string) => Promise<void>; onImport: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
}) {
  const [showImport, setShowImport] = useState(false); const [rawText, setRawText] = useState(""); const [draggedSection, setDraggedSection] = useState<number | null>(null);
  return <div className="editor-layout">
    <div className="editor-canvas" inert={Boolean(props.busy)}>
      <div className="editor-actions"><div><span className="muted">最后保存：{props.detail.draft ? formatTime(props.detail.draft.updatedAt) : "尚未保存"}</span></div><div><button className="quiet-button" onClick={() => setShowImport((value) => !value)}>导入 / 粘贴文本</button><button disabled={Boolean(props.busy)} onClick={() => void props.onSave()}>保存简历</button></div></div>
      {showImport && <section className="import-panel"><div><h3>导入已有内容</h3><p>上传不超过 10 MB 的 PDF/DOCX，或粘贴简历文本。解析后请在下方人工校正。</p><label className="file-button">选择 PDF / DOCX<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void props.onImport(event)} /></label></div><div><textarea value={rawText} onChange={(event) => setRawText(event.target.value)} placeholder="在此粘贴简历全文…" /><button className="quiet-button" onClick={() => void props.onParse(rawText)}>拆分文本</button></div></section>}
      <section className="document-card"><div className="document-heading"><div><p className="eyebrow">基本信息</p><h2>{props.document.basicInfo.name || "未命名候选人"}</h2></div><span>可编辑草稿</span></div><BasicInfoFields info={props.document.basicInfo} onChange={props.onBasic} /></section>
      <div className="document-heading section-divider"><div><p className="eyebrow">经历模块</p><h2>结构化内容</h2></div><span>拖动模块可调整顺序</span></div>
      {props.document.sections.map((section, index) => <section className="section-editor" key={section.id} draggable onDragStart={() => setDraggedSection(index)} onDragOver={(event) => event.preventDefault()} onDrop={() => { if (draggedSection !== null && draggedSection !== index) props.onMoveSection(draggedSection, index); setDraggedSection(null); }}><div className="section-editor-head"><span className="drag-handle">⠿</span><input aria-label="模块标题" value={section.title} onChange={(event) => props.onUpdateSection(section.id, { title: event.target.value })} /><select aria-label="模块类型" value={section.type} onChange={(event) => props.onUpdateSection(section.id, { type: event.target.value as SectionType })}>{(Object.keys(sectionTitles) as SectionType[]).map((type) => <option key={type} value={type}>{sectionTitles[type]}</option>)}</select><button className="icon-button danger" onClick={() => props.onRemoveSection(section.id)} aria-label="删除模块">×</button></div><div className="item-list">{section.items.map((item, itemIndex) => <div className="item-editor structured-item" key={item.id}><div className="item-topline"><div className="item-index">{String(itemIndex + 1).padStart(2, "0")}</div><span className="item-caption">{section.title} · 第 {itemIndex + 1} 条</span><div className="item-tools"><button className="icon-button" disabled={itemIndex === 0} onClick={() => props.onMoveItem(section.id, itemIndex, itemIndex - 1)} aria-label="上移条目">↑</button><button className="icon-button" disabled={itemIndex === section.items.length - 1} onClick={() => props.onMoveItem(section.id, itemIndex, itemIndex + 1)} aria-label="下移条目">↓</button><button className="icon-button danger" onClick={() => props.onRemoveItem(section.id, item.id)} aria-label="删除条目">×</button></div></div><ItemFields sectionType={section.type} item={item} onChange={(field, value) => props.onUpdateItemField(section.id, item.id, field, value)} /><label className="content-field">经历描述<textarea value={item.content} onChange={(event) => props.onUpdateItem(section.id, item.id, event.target.value)} placeholder="填写经历描述、职责和成果…" /></label></div>)}</div><button className="add-link" onClick={() => props.onAddItem(section.id)}>＋ 添加条目</button></section>)}
      <div className="add-section"><span>添加模块</span>{(Object.keys(sectionTitles) as SectionType[]).map((type) => <button key={type} className="tag-button" onClick={() => props.onAddSection(type)}>＋ {sectionTitles[type]}</button>)}</div>
    </div>
    <aside className="preview-panel"><p className="eyebrow">实时分页预览</p><PaginatedPreview document={props.document} /><p className="preview-footnote">显示真实 PDF 页边界。保存后仍可继续修改；JD 中隐藏的条目不参与预览与导出，原文仍保留。</p></aside>
  </div>;
}

function ExportPage({ document, resumes, resumeId, onSelectResume, layouts, selectedLayoutId, onSelectLayout, onEditLayout, templates, busy, record, onExport }: {
  document: ResumeDocument; resumes: Resume[]; resumeId: string; onSelectResume: (id: string) => void;
  layouts: LayoutSummary[]; selectedLayoutId: string; onSelectLayout: (id: string) => Promise<void>; onEditLayout: () => Promise<void>;
  templates: Template[]; busy: string | null; record: ExportRecord | null; onExport: (id: string, format: "docx" | "pdf") => Promise<void>;
}) {
  const [templateId, setTemplateId] = useState(""); const [format, setFormat] = useState<"docx" | "pdf">("docx");
  useEffect(() => { if (!templateId && templates[0]) setTemplateId(templates[0].id); }, [templateId, templates]);
  const selectedName = layouts.find((layout) => layout.id === selectedLayoutId)?.name ?? "基础简历";
  return <div className="page-stack">
    <section className="export-hero"><p className="eyebrow">导出中心</p><h2>选择简历资料与岗位排版</h2><p>同一份简历可保存多套岗位排版。选择后预览和下载都使用对应的已保存内容，隐藏项不会出现在文件中。</p></section>
    <section className="section-card export-source">
      <label>简历资料<select aria-label="导出的简历资料" value={resumeId} disabled={Boolean(busy)} onChange={(event) => onSelectResume(event.target.value)}>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.title}</option>)}</select></label>
      <label>岗位排版<select aria-label="导出的岗位排版" value={selectedLayoutId} disabled={Boolean(busy)} onChange={(event) => void onSelectLayout(event.target.value)}><option value="">基础简历（当前内容）</option>{layouts.map((layout) => <option key={layout.id} value={layout.id}>{layout.name}</option>)}</select></label>
      <button className="quiet-button" disabled={Boolean(busy)} onClick={() => void onEditLayout()}>{selectedLayoutId ? "在 JD 工作台继续编辑" : "创建岗位排版"}</button>
      <p>{selectedLayoutId ? `已选排版：${selectedName}。下载文件名会包含该岗位名称。` : "基础简历会在导出时保存当前编辑内容。JD 专用排版不会覆盖它。"}</p>
    </section>
    <div className="export-current-layout">
      <section className="section-card export-config">
        <div><p className="form-label">选择模板</p><div className="template-grid">{templates.map((template) => <button disabled={Boolean(busy)} className={`template-card ${templateId === template.id ? "selected" : ""}`} key={template.id} onClick={() => setTemplateId(template.id)}><span className="template-sheet"><i /><i /><i /><i /></span><strong>{template.name}</strong><small>{template.description}</small></button>)}</div></div>
        <div className="format-options"><p className="form-label">文件格式</p><button disabled={Boolean(busy)} className={format === "docx" ? "selected" : ""} onClick={() => setFormat("docx")}>DOCX <small>可编辑</small></button><button disabled={Boolean(busy)} className={format === "pdf" ? "selected" : ""} onClick={() => setFormat("pdf")}>PDF <small>适合投递</small></button></div>
        <button className="export-button" disabled={Boolean(busy) || !templateId} onClick={() => void onExport(templateId, format)}>生成 {format.toUpperCase()} 文件 <span>→</span></button>
      </section>
      {templateId && <PaginatedPreview document={document} templateId={templateId} />}
    </div>
    {record && <section className={`export-result ${record.status}`}><div><p className="eyebrow">导出任务 · {selectedName}</p><h2>{record.status === "completed" ? "文件已准备完成" : record.status === "failed" ? "导出未完成" : "正在生成文件"}</h2><p>{record.errorMessage || `已生成「${selectedName}」的 ${record.format.toUpperCase()} 文件。`}</p></div>{record.downloadUrl && <a className="download-button" href={record.downloadUrl}>下载文件 ↓</a>}</section>}
  </div>;
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><span>✦</span><strong>{title}</strong><p>{text}</p></div>;
}
