"use client";
import { useState } from "react";
import { api, ExportResult } from "@/lib/api";

interface Props { jobId: string; onClose: () => void }

type Tab = "notion" | "confluence";

export default function ExportModal({ jobId, onClose }: Props) {
  const [tab,        setTab]        = useState<Tab>("notion");
  const [loading,    setLoading]    = useState(false);
  const [result,     setResult]     = useState<ExportResult|null>(null);

  // Notion fields
  const [notionToken,    setNotionToken]    = useState("");
  const [notionParentId, setNotionParentId] = useState("");

  // Confluence fields
  const [confUrl,      setConfUrl]      = useState("");
  const [confUser,     setConfUser]     = useState("");
  const [confToken,    setConfToken]    = useState("");
  const [confSpace,    setConfSpace]    = useState("");
  const [confParentId, setConfParentId] = useState("");

  const submit = async () => {
    setLoading(true); setResult(null);
    try {
      let res: ExportResult;
      if (tab === "notion") {
        res = await api.exportToNotion(jobId, notionToken, notionParentId);
      } else {
        res = await api.exportToConfluence(jobId, confUrl, confUser, confToken, confSpace, confParentId || undefined);
      }
      setResult(res);
    } catch (e: any) {
      setResult({ success: false, message: e.message ?? "Export failed" });
    } finally { setLoading(false); }
  };

  const field = (label: string, value: string, onChange: (v:string)=>void, placeholder: string, type="text") => (
    <div style={{ marginBottom:14 }}>
      <label style={{ display:"block", fontSize:12, color:"#94a3b8", marginBottom:5, fontWeight:500 }}>{label}</label>
      <input type={type} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} style={{
        width:"100%", background:"#1a1a3a", border:"1px solid #2d2d50", borderRadius:8, color:"#e2e8f0",
        padding:"9px 12px", fontSize:13, outline:"none", boxSizing:"border-box",
      }} />
    </div>
  );

  return (
    <div style={{ position:"fixed", inset:0, zIndex:200, background:"#00000090", display:"flex",
      alignItems:"center", justifyContent:"center", padding:20 }}
      onClick={e => { if (e.target===e.currentTarget) onClose(); }}>
      <div style={{ width:"100%", maxWidth:500, background:"#12122a", border:"1px solid #2d2d50",
        borderRadius:20, padding:"32px 36px", boxShadow:"0 24px 64px #00000080" }}>

        {/* Header */}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:24 }}>
          <h2 style={{ margin:0, fontSize:18, fontWeight:700, color:"#e2e8f0" }}>📤 Export Tutorial</h2>
          <button onClick={onClose} style={{ background:"none", border:"none", color:"#64748b", fontSize:20, cursor:"pointer" }}>✕</button>
        </div>

        {/* Tabs */}
        <div style={{ display:"flex", gap:4, marginBottom:24, background:"#0d0d1e", borderRadius:10, padding:4 }}>
          {(["notion","confluence"] as Tab[]).map(t => (
            <button key={t} onClick={()=>{ setTab(t); setResult(null); }} style={{
              flex:1, padding:"8px 0", borderRadius:8, border:"none", fontSize:13, fontWeight:600, cursor:"pointer",
              background: tab===t ? "linear-gradient(135deg,#6366f1,#8b5cf6)" : "transparent",
              color: tab===t ? "#fff" : "#64748b", transition:"all .15s",
            }}>
              {t === "notion" ? "📓 Notion" : "📘 Confluence"}
            </button>
          ))}
        </div>

        {/* Notion form */}
        {tab === "notion" && (
          <div>
            <p style={{ fontSize:12, color:"#64748b", marginBottom:16, lineHeight:1.6 }}>
              Create a Notion integration at <a href="https://www.notion.so/my-integrations" target="_blank" rel="noreferrer"
                style={{ color:"#a5b4fc" }}>notion.so/my-integrations</a>, then share your parent page with the integration.
            </p>
            {field("Integration Token", notionToken, setNotionToken, "secret_xxx...", "password")}
            {field("Parent Page ID", notionParentId, setNotionParentId, "32-char page ID from Notion URL")}
          </div>
        )}

        {/* Confluence form */}
        {tab === "confluence" && (
          <div>
            <p style={{ fontSize:12, color:"#64748b", marginBottom:16, lineHeight:1.6 }}>
              Use your Confluence Cloud URL, email, and an API token from{" "}
              <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" rel="noreferrer"
                style={{ color:"#a5b4fc" }}>id.atlassian.com</a>.
            </p>
            {field("Confluence URL", confUrl, setConfUrl, "https://yoursite.atlassian.net")}
            {field("Email / Username", confUser, setConfUser, "you@company.com")}
            {field("API Token", confToken, setConfToken, "Your Atlassian API token", "password")}
            {field("Space Key", confSpace, setConfSpace, "e.g. ENG or DEV")}
            {field("Parent Page ID (optional)", confParentId, setConfParentId, "Leave blank for space root")}
          </div>
        )}

        {/* Result */}
        {result && (
          <div style={{ borderRadius:10, padding:"12px 16px", marginBottom:16, fontSize:13,
            background: result.success ? "#14291a" : "#2d1b1b",
            border: `1px solid ${result.success ? "#16a34a" : "#dc2626"}`,
            color: result.success ? "#4ade80" : "#fca5a5",
          }}>
            {result.success ? "✅" : "❌"} {result.message}
            {result.success && result.url && (
              <div style={{ marginTop:8 }}>
                <a href={result.url} target="_blank" rel="noreferrer" style={{ color:"#a5b4fc", fontSize:12 }}>
                  Open in {tab === "notion" ? "Notion" : "Confluence"} →
                </a>
              </div>
            )}
          </div>
        )}

        {/* Submit */}
        <button onClick={submit} disabled={loading} style={{
          width:"100%", background:"linear-gradient(135deg,#6366f1,#8b5cf6)",
          color:"#fff", border:"none", borderRadius:10, padding:"12px",
          fontSize:15, fontWeight:600, cursor: loading ? "not-allowed" : "pointer",
          opacity: loading ? 0.7 : 1,
        }}>
          {loading ? "Exporting…" : `Export to ${tab === "notion" ? "Notion" : "Confluence"}`}
        </button>
      </div>
    </div>
  );
}
