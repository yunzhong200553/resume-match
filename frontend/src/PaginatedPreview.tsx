import { useEffect, useState } from "react";
import type { ResumeDocument } from "./App";
import "./paginated-preview.css";

type Preview = {
  pageCount: number;
  pages: { pageNumber: number; image: string; width: number; height: number }[];
};

export default function PaginatedPreview({ document, templateId = "classic_single_column" }: { document: ResumeDocument; templateId?: string }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const body = JSON.stringify({ document, templateId });

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const response = await fetch("/api/resume-preview", {
            method: "POST", headers: { "Content-Type": "application/json" }, body, signal: controller.signal,
          });
          const payload = await response.json();
          if (!response.ok || !payload.data) throw new Error(payload.error?.message || "分页预览生成失败。");
          if (!controller.signal.aborted) setPreview(payload.data as Preview);
        } catch (reason) {
          if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "无法生成预览。");
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      })();
    }, 650);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [body, retry]);

  return <div className="paginated-preview" aria-label="简历分页预览" aria-busy={loading}>
    <div className="pagination-status" role="status">{loading ? "正在更新实际排版…" : error ? "预览未更新" : `A4 · 共 ${preview?.pageCount ?? 0} 页 · 与 PDF 导出使用相同渲染流程`}</div>
    {error && <div role="alert" className="preview-error">{error}<button onClick={() => setRetry((value) => value + 1)}>重新生成预览</button></div>}
    {preview && <div className={`pdf-pages ${loading || error ? "outdated" : ""}`}>
      {preview.pages.map((page) => <figure className="pdf-page" key={page.pageNumber}>
        <figcaption>第 {page.pageNumber} 页 / 共 {preview.pageCount} 页</figcaption>
        <img src={page.image} alt={`简历第 ${page.pageNumber} 页`} width={page.width} height={page.height} />
        <div className="page-boundary">第 {page.pageNumber} 页结束</div>
      </figure>)}
    </div>}
  </div>;
}
