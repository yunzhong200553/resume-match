import { useEffect, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import type { AIConfiguration, Analysis, Item, ResumeDocument, Rewrite, Section, Suggestion } from "./App";
import PaginatedPreview from "./PaginatedPreview";

type Props = {
  jdText: string;
  layoutName: string;
  onJdChange: (value: string) => void;
  onLayoutNameChange: (value: string) => void;
  onNewLayout: () => void;
  analysis: Analysis | null;
  document: ResumeDocument;
  configuration: AIConfiguration | null;
  busy: string | null;
  onDocumentChange: (document: ResumeDocument) => void;
  onAnalyze: (jd: string) => Promise<void>;
  onRewrite: (suggestion: Suggestion) => Promise<Rewrite | null>;
  onConfirm: (suggestion: Suggestion, rewrite: Rewrite) => Promise<boolean>;
  onSave: () => Promise<void>;
  renderFields: (section: Section, item: Item, onChange: (key: string, value: string) => void) => ReactNode;
};
type DragTarget = { kind: "section"; sectionId: string } | { kind: "item"; sectionId: string; itemId: string };
type PendingRewrite = { suggestion: Suggestion; rewrite: Rewrite };
const itemTitle = (item: Item, index: number) => item.fields.name || item.fields.company || item.fields.school || item.fields.category || `经历 ${index + 1}`;

export default function AnalysisWorkspace(props: Props) {
  const { analysis, document, configuration, busy, onDocumentChange } = props;
  const { jdText, layoutName } = props;
  const [consent, setConsent] = useState(false);
  const [selectedItem, setSelectedItem] = useState("");
  const [dragged, setDragged] = useState<DragTarget | null>(null);
  const [showHidden, setShowHidden] = useState(true);
  const [pending, setPending] = useState<PendingRewrite | null>(null);
  const [showProposed, setShowProposed] = useState(false);
  const locked = Boolean(busy);
  const matches = new Map((analysis?.itemMatches ?? []).map((match) => [`${match.sectionId}:${match.itemId}`, match]));
  const selectedSection = document.sections.find((section) => section.items.some((item) => `${section.id}:${item.id}` === selectedItem));
  const selected = selectedSection?.items.find((item) => `${selectedSection.id}:${item.id}` === selectedItem);
  const suggestion = analysis?.suggestions.find((value) => `${value.sectionId}:${value.itemId}` === selectedItem && value.status === "pending");
  const selectedMatch = matches.get(selectedItem);
  const hiddenCount = document.sections.reduce((total, section) => total + (section.hidden ? 1 : 0) + section.items.filter((item) => item.hidden).length, 0);
  const pendingOriginalMatches = !pending || document.sections.find((section) => section.id === pending.suggestion.sectionId)?.items.find((item) => item.id === pending.suggestion.itemId)?.content === pending.rewrite.original;

  useEffect(() => {
    setPending(null); setShowProposed(false);
  }, [analysis?.id]);

  function updateSection(sectionId: string, patch: Partial<Section>) {
    onDocumentChange({ ...document, sections: document.sections.map((section) => section.id === sectionId ? { ...section, ...patch } : section) });
  }
  function updateItem(sectionId: string, itemId: string, patch: Partial<Item>) {
    onDocumentChange({ ...document, sections: document.sections.map((section) => section.id !== sectionId ? section : {
      ...section, items: section.items.map((item) => item.id === itemId ? { ...item, ...patch } : item),
    }) });
  }
  function moveSection(sectionId: string, targetIndex: number) {
    const sections = [...document.sections];
    const from = sections.findIndex((section) => section.id === sectionId);
    if (from < 0 || targetIndex < 0 || targetIndex >= sections.length) return;
    const [section] = sections.splice(from, 1); sections.splice(targetIndex, 0, section);
    onDocumentChange({ ...document, sections });
  }
  function moveItem(section: Section, itemId: string, targetIndex: number) {
    const items = [...section.items]; const from = items.findIndex((item) => item.id === itemId);
    if (from < 0 || targetIndex < 0 || targetIndex >= items.length) return;
    const [item] = items.splice(from, 1); items.splice(targetIndex, 0, item);
    updateSection(section.id, { items });
  }
  function startDrag(event: DragEvent, target: DragTarget) {
    event.stopPropagation(); event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", JSON.stringify(target)); setDragged(target);
  }
  function dropAtSection(event: DragEvent, sectionIndex: number) {
    event.preventDefault(); event.stopPropagation();
    if (!locked && dragged?.kind === "section") moveSection(dragged.sectionId, Math.min(sectionIndex, document.sections.length - 1));
    setDragged(null);
  }
  async function generateRewrite(value: Suggestion) {
    const rewrite = await props.onRewrite(value);
    if (rewrite) { setPending({ suggestion: value, rewrite }); setShowProposed(true); }
  }
  async function confirmPending() {
    if (pending && await props.onConfirm(pending.suggestion, pending.rewrite)) { setPending(null); setShowProposed(false); }
  }
  let previewDocument = document;
  if (pending && showProposed) {
    previewDocument = { ...document, sections: document.sections.map((section) => section.id !== pending.suggestion.sectionId ? section : {
      ...section, items: section.items.map((item) => item.id === pending.suggestion.itemId ? { ...item, content: pending.rewrite.rewritten } : item),
    }) };
  }
  const scoreCard = <div className="analysis-score" data-testid="overall-score">
    <div className="score-card-head"><span>整体适配度</span></div>
    <strong>{analysis?.overallScore ?? "—"}<small>/100</small></strong>
    <p>{analysis?.summary || "输入 JD 后使用 AI 分析，每个条目单独评分。"}</p>
    {analysis && <details><summary>查看四维评分</summary>{analysis.scoreBreakdown.map((dimension) => <div className="dimension-row" key={dimension.dimension}><span>{({ coreRequirements: "核心要求", experienceEvidence: "经历证据", skillsCoverage: "技能覆盖", presentationQuality: "表达质量" } as Record<string, string>)[dimension.dimension]}</span><b>{dimension.score}/{dimension.weight}</b><small>{dimension.reason}</small></div>)}</details>}
  </div>;

  return <div className="analysis-page">
    <section className="analysis-launch section-card">
      <div><p className="eyebrow">JD 定向优化工作台</p><h2>用真实经历，匹配目标岗位。</h2><p className="ai-configuration">{!configuration ? "正在读取 AI 配置…" : configuration.demo ? "演示模式 · 固定测试数据，不代表真实适配度" : configuration.configured ? `DeepSeek · ${configuration.model}` : "DeepSeek 尚未配置：请设置服务端 DEEPSEEK_API_KEY 后重启后端。"}</p></div>
      <label className="jd-input">职位描述<textarea aria-label="职位描述 JD" value={jdText} maxLength={20_000} disabled={locked} onChange={(event) => props.onJdChange(event.target.value)} placeholder="粘贴完整 JD，至少 50 个字符…" /><small>{jdText.trim().length} / 20,000 字符</small></label>
      <div className="analysis-submit"><label className="ai-consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} disabled={locked} />允许将去除联系信息的经历和 JD 发送给 DeepSeek</label><button disabled={locked || !consent || !configuration?.configured || jdText.trim().length < 50} onClick={() => void props.onAnalyze(jdText)}>{analysis ? "重新分析当前内容" : "开始 AI 分析"}</button></div>
    </section>
    <section className="layout-save-bar">
      <label>岗位排版名称<input aria-label="岗位排版名称" value={layoutName} maxLength={100} disabled={locked} onChange={(event) => props.onLayoutNameChange(event.target.value)} placeholder="例如：产品经理｜某公司" /></label>
      <p>排版独立保存在当前简历下，不覆盖基础资料。保存后进入导出中心。</p>
      <button className="quiet-button" disabled={locked || Boolean(pending)} onClick={props.onNewLayout}>从基础资料新建排版</button>
    </section>
    {analysis && <p className="analysis-snapshot-note">评分基于最近一次分析时的内容，不会随手动调整虚增。修改内容或隐藏组件后，请重新分析更新评分。</p>}
    <section className="analysis-workspace">
      <aside className="analysis-sidebar" aria-label="可排序简历组件">
        {scoreCard}
        <div className="components-toolbar"><strong>组件与适配度</strong><label><input type="checkbox" checked={showHidden} onChange={(event) => setShowHidden(event.target.checked)} />显示隐藏项（{hiddenCount}）</label><small>拖动 ⠿ 排序，或使用 ↑ ↓；隐藏不会删除原文。</small></div>
        {document.sections.map((section, sectionIndex) => {
          const scores = section.items.map((item) => matches.get(`${section.id}:${item.id}`)?.score).filter((value): value is number => typeof value === "number");
          const average = scores.length ? Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length) : null;
          return <div key={section.id} className={`analysis-section ${section.hidden ? "hidden-component" : ""}`} data-section-id={section.id}
              onDragOver={(event) => event.preventDefault()} onDrop={(event) => dropAtSection(event, sectionIndex)}>
              {(!section.hidden || showHidden) && <>
                <div className="component-section-head">
                  <button className="drag-grip" draggable={!locked} onDragStart={(event) => startDrag(event, { kind: "section", sectionId: section.id })} onDragEnd={() => setDragged(null)} aria-label={`拖动${section.title}`}>⠿</button>
                  <strong>{section.title}</strong><span title="已评分条目的平均分">{average === null ? "未评分" : `${average}/100`}</span>
                  <button disabled={locked || sectionIndex === 0} onClick={() => moveSection(section.id, sectionIndex - 1)} aria-label={`上移${section.title}`}>↑</button>
                  <button disabled={locked || sectionIndex === document.sections.length - 1} onClick={() => moveSection(section.id, sectionIndex + 1)} aria-label={`下移${section.title}`}>↓</button>
                  <button disabled={locked} onClick={() => updateSection(section.id, { hidden: !section.hidden })} aria-label={`${section.hidden ? "恢复" : "隐藏"}模块${section.title}`}>{section.hidden ? "恢复" : "隐藏"}</button>
                </div>
                {section.items.map((item, index) => {
                  if (item.hidden && !showHidden) return null;
                  const key = `${section.id}:${item.id}`, match = matches.get(key);
                  return <div className={`component-entry ${item.hidden ? "hidden-component" : ""}`} key={key} data-item-id={item.id}
                    onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
                      if (dragged?.kind !== "item") return;
                      event.preventDefault(); event.stopPropagation();
                      if (!locked && dragged.sectionId === section.id) moveItem(section, dragged.itemId, index);
                      setDragged(null);
                    }}>
                    <button className="drag-grip" draggable={!locked} onDragStart={(event) => startDrag(event, { kind: "item", sectionId: section.id, itemId: item.id })} onDragEnd={() => setDragged(null)} aria-label={`拖动条目${itemTitle(item, index)}`}>⠿</button>
                    <button className={`component-row ${selectedItem === key ? "selected" : ""}`} disabled={locked} onClick={() => setSelectedItem(key)}>
                      <span className={`match-dot ${match?.level ?? "low"}`} /><span><b>{itemTitle(item, index)}</b><small>{item.hidden || section.hidden ? "已从预览和导出中隐藏" : match?.reason || "尚未获得评分"}</small></span><em>{typeof match?.score === "number" ? `${match.score}` : "—"}<small>/100</small></em>
                    </button>
                    <div className="component-entry-tools"><button disabled={locked || index === 0} onClick={() => moveItem(section, item.id, index - 1)} aria-label={`上移条目${itemTitle(item, index)}`}>↑</button><button disabled={locked || index === section.items.length - 1} onClick={() => moveItem(section, item.id, index + 1)} aria-label={`下移条目${itemTitle(item, index)}`}>↓</button><button disabled={locked} onClick={() => updateItem(section.id, item.id, { hidden: !item.hidden })} aria-label={`${item.hidden ? "恢复" : "隐藏"}条目${itemTitle(item, index)}`}>{item.hidden ? "恢复" : "隐藏"}</button></div>
                  </div>;
                })}
              </>}
            </div>;
        })}
        <div className="sidebar-drop-end" onDragOver={(event) => event.preventDefault()} onDrop={(event) => dropAtSection(event, document.sections.length)}>{dragged && "拖到此处置于末尾"}</div>
        {analysis?.missingRequirements.length ? <div className="missing-box"><p className="eyebrow">JD 缺失要求</p>{analysis.missingRequirements.map((value) => <span key={value.requirement} title={value.reason}>{value.requirement}</span>)}</div> : null}
      </aside>
      <div className="analysis-preview">
        <div className="preview-toolbar"><div><p className="eyebrow">{pending && showProposed ? "AI 改写效果 · 未确认" : "岗位排版"}</p><h2>Word / PDF 分页预览</h2></div><button disabled={locked || Boolean(pending) || !layoutName.trim()} onClick={() => void props.onSave()}>保存排版并前往导出</button></div>
        {pending && <div className="proposal-toolbar"><span>AI 修改尚未替换原文</span><button className={!showProposed ? "selected" : ""} onClick={() => setShowProposed(false)}>查看当前内容</button><button className={showProposed ? "selected" : ""} onClick={() => setShowProposed(true)}>查看 AI 效果</button></div>}
        <PaginatedPreview document={previewDocument} />
      </div>
      <aside className="component-inspector">
        {selected && selectedSection ? <>
          <p className="eyebrow">直接编辑组件</p><h2>{itemTitle(selected, 0)}</h2>
          <span className={`status-tag ${selectedMatch?.level ?? ""}`}>适配度：{typeof selectedMatch?.score === "number" ? `${selectedMatch.score}/100` : "尚未评分"}</span>
          <p className="inspector-reason">{selectedMatch?.reason || "选择岗位 JD 并分析后显示具体评分与依据。"}</p>
          <fieldset className="inspector-fields" disabled={locked}>
            {props.renderFields(selectedSection, selected, (field, value) => updateItem(selectedSection.id, selected.id, { fields: { ...selected.fields, [field]: value } }))}
            <label className="content-field">当前经历描述<textarea value={selected.content} onChange={(event) => updateItem(selectedSection.id, selected.id, { content: event.target.value })} /></label>
          </fieldset>
          {suggestion && <div className="inspector-suggestion"><span>AI 优化建议</span><p>{suggestion.reason}</p><small>{suggestion.suggested}</small><button disabled={locked || Boolean(pending) || configuration?.provider !== "deepseek"} onClick={() => void generateRewrite(suggestion)}>交给 AI 改写并预览</button></div>}
          {!suggestion && analysis && <p className="inspector-reason">该条目暂无待处理建议。修改后可重新分析。</p>}
        </> : <div className="empty-state"><strong>选择一个组件</strong><p>从左侧选择经历条目，即可编辑字段、查看评分或生成 AI 改写。</p></div>}
        {pending && <section className="rewrite-review" role="region" aria-label="AI 修改确认">
          <h3>确认后才替换</h3><p>{pending.rewrite.explanation}</p>
          <label>修改前<pre>{pending.rewrite.original}</pre></label>
          <label>AI 修改后（可校正）<textarea aria-label="AI 修改后内容" value={pending.rewrite.rewritten} disabled={locked} onChange={(event) => setPending({ ...pending, rewrite: { ...pending.rewrite, rewritten: event.target.value } })} /></label>
          <small>请核对事实。未出现的技能、成果和数字不能补写。</small>
          {!pendingOriginalMatches && <p role="alert">原文已修改，请取消此次预览并重新生成 AI 改写。</p>}
          <div><button disabled={locked || !pendingOriginalMatches || !pending.rewrite.rewritten.trim()} onClick={() => void confirmPending()}>同意并替换</button><button className="quiet-button" disabled={locked} onClick={() => { setPending(null); setShowProposed(false); }}>取消，保留原文</button></div>
        </section>}
      </aside>
    </section>
  </div>;
}
