"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import dynamic from "next/dynamic";
import { api, BASE_URL, ArtifactsResponse, SearchResult } from "@/lib/api";
import VideoPlayer from "./VideoPlayer";
import SettingsDrawer from "./SettingsDrawer";
import ChatBot from "./ChatBot";
import QuizModal from "./QuizModal";
import ExportModal from "./ExportModal";

const MermaidDiagram = dynamic(() => import("./MermaidDiagram"), { ssr: false });

interface Props { jobId: string }

// ── Feature 3: Shorts Panel (additive, self-contained) ───────────────────────
function ShortsPanel({ jobId, hasVideo }: { jobId: string; hasVideo: boolean }) {
  const [open,   setOpen]   = React.useState(false);
  const [status, setStatus] = React.useState<"idle"|"loading"|"done"|"error">("idle");
  const [clips,  setClips]  = React.useState<{filename:string;title?:string;duration?:number;download_url:string;chapter?:number}[]>([]);
  const [err,    setErr]    = React.useState("");

  if (!hasVideo) return null;

  const generate = async () => {
    setStatus("loading"); setErr("");
    try {
      const r = await fetch(`${BASE_URL}/api/jobs/${jobId}/shorts`, { method:"POST" });
      const d = await r.json();
      if (d.clips) { setStatus("done"); setClips(d.clips); setOpen(true); }
      else         { setStatus("error"); setErr(d.detail ?? "Failed"); }
    } catch(e: unknown) { setStatus("error"); setErr(e instanceof Error ? e.message : "Error"); }
  };

  return (
    <div style={{ marginTop:16 }}>
      {/* Trigger row */}
      <div style={{ display:"flex", alignItems:"center", gap:10 }}>
        <button onClick={generate} disabled={status==="loading"} style={{
          display:"flex", alignItems:"center", gap:7, padding:"9px 18px",
          borderRadius:10, fontSize:12, fontWeight:600,
          cursor: status==="loading" ? "not-allowed" : "pointer",
          background:"#141428", border:"1px solid #252550",
          color: status==="loading" ? "#64748b" : "#94a3b8",
          opacity: status==="loading" ? 0.7 : 1, transition:"all .15s",
        }}
        onMouseEnter={e=>{ if(status!=="loading"){ e.currentTarget.style.borderColor="#f59e0b50"; e.currentTarget.style.color="#fcd34d"; }}}
        onMouseLeave={e=>{ e.currentTarget.style.borderColor="#252550"; e.currentTarget.style.color="#94a3b8"; }}>
          {status==="loading" ? "⏳ Cutting clips…" : "✂️ Generate Chapter Shorts"}
        </button>
        {status==="done" && clips.length > 0 && (
          <button onClick={() => setOpen(o=>!o)} style={{
            fontSize:11, color:"#64748b", background:"transparent",
            border:"1px solid #1a1a30", borderRadius:7, padding:"5px 10px", cursor:"pointer",
          }}>{open ? "▲ Hide" : `▼ Show ${clips.length} clips`}</button>
        )}
      </div>

      {err && <p style={{ fontSize:11, color:"#f87171", marginTop:6 }}>⚠ {err}</p>}

      {/* Clips list */}
      {open && clips.length > 0 && (
        <div style={{ marginTop:12, borderRadius:12, border:"1px solid #1a1a30",
          background:"#0a0a14", overflow:"hidden" }}>
          {/* Header */}
          <div style={{ padding:"10px 14px", borderBottom:"1px solid #141428",
            display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <span style={{ fontSize:12, fontWeight:700, color:"#e2e8f0" }}>
              ✂️ {clips.length} Chapter Clips
            </span>
            <span style={{ fontSize:11, color:"#475569" }}>Saved in shorts/</span>
          </div>
          {clips.map((clip, i) => (
            <div key={i} style={{
              display:"flex", alignItems:"center", justifyContent:"space-between",
              padding:"10px 14px", borderBottom: i < clips.length-1 ? "1px solid #141428" : "none",
            }}>
              <div>
                <p style={{ margin:0, fontSize:13, color:"#e2e8f0", fontWeight:500 }}>
                  {clip.title ?? clip.filename}
                </p>
                <p style={{ margin:0, fontSize:11, color:"#475569" }}>
                  {clip.duration ? `${clip.duration}s` : ""} · {clip.filename}
                </p>
              </div>
              <a href={`${BASE_URL}${clip.download_url}`}
                download={clip.filename}
                style={{
                  display:"inline-flex", alignItems:"center", gap:5,
                  padding:"6px 14px", borderRadius:8, fontSize:11, fontWeight:600,
                  background:"#6366f118", border:"1px solid #6366f140",
                  color:"#a5b4fc", textDecoration:"none", flexShrink:0,
                }}>
                ⬇ Download
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function label(f: string) {
  if (f === "index.md") return "Overview";
  return f.replace(/^\d+_/, "").replace(/\.md$/, "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}
function num(f: string) { const m = f.match(/^(\d+)_/); return m ? m[1] : null; }

// ── Video Tutorials sidebar section ──────────────────────────────────────────
function VideoTutorialsSection({
  jobId, videoUrl, onScrollToVideo,
}: { jobId: string; videoUrl: string | null; onScrollToVideo: () => void }) {
  const [shorts, setShorts] = React.useState<{filename:string;title?:string;duration?:number;download_url:string}[]>([]);
  const [loadingShorts, setLoadingShorts] = React.useState(false);
  const [expanded, setExpanded] = React.useState(false);

  // Load existing shorts if any
  React.useEffect(() => {
    if (!videoUrl) return;
    fetch(`${BASE_URL}/api/jobs/${jobId}/shorts`)
      .then(r => r.json())
      .then(d => { if (d.clips) setShorts(d.clips); })
      .catch(() => {});
  }, [jobId, videoUrl]);

  const generateShorts = async () => {
    setLoadingShorts(true);
    try {
      const r = await fetch(`${BASE_URL}/api/jobs/${jobId}/shorts`, { method: "POST" });
      const d = await r.json();
      if (d.clips) setShorts(d.clips);
    } catch {}
    setLoadingShorts(false);
  };

  const itemStyle = (active = false): React.CSSProperties => ({
    width: "100%", display: "flex", alignItems: "center", gap: 8,
    padding: "8px 10px", borderRadius: 8, border: "1px solid transparent",
    background: active ? "#6366f115" : "transparent",
    borderColor: active ? "#6366f130" : "transparent",
    cursor: "pointer", textAlign: "left", marginBottom: 2,
    transition: "all .15s",
    opacity: 1,
  });

  return (
    <div style={{ borderTop: "1px solid #141428", paddingTop: 8 }}>
      {/* Section header */}
      <div style={{ padding: "6px 14px 4px", display: "flex", alignItems: "center",
        justifyContent: "space-between" }}>
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
          color: "#3d4a5c", textTransform: "uppercase", margin: 0 }}>
          Video Tutorials
        </p>
        {shorts.length > 0 && (
          <button onClick={() => setExpanded(e => !e)} style={{
            background: "none", border: "none", color: "#3d4a5c",
            cursor: "pointer", fontSize: 10, padding: "2px 4px",
          }}>
            {expanded ? "▲" : "▼"}
          </button>
        )}
      </div>

      <div style={{ padding: "4px 8px" }}>
        {/* Full tutorial video */}
        {videoUrl ? (
          <button onClick={onScrollToVideo} style={itemStyle()} title="Watch full tutorial video"
            onMouseEnter={e => { e.currentTarget.style.background = "#ffffff06"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
            <div style={{
              width: 26, height: 26, borderRadius: 7, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "#141428", fontSize: 13,
            }}>🎬</div>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <span style={{ fontSize: 12, fontWeight: 500, color: "#94a3b8",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                display: "block" }}>
                Full Tutorial
              </span>
              <span style={{ fontSize: 10, color: "#3d4a5c" }}>Click to play</span>
            </div>
            <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 99,
              background: "#22c55e18", color: "#4ade80",
              border: "1px solid #22c55e30", flexShrink: 0 }}>
              Ready
            </span>
          </button>
        ) : (
          <div style={{ ...itemStyle(), opacity: 0.4, cursor: "default" }}>
            <div style={{ width: 26, height: 26, borderRadius: 7, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "#141428", fontSize: 13 }}>🎬</div>
            <div style={{ flex: 1 }}>
              <span style={{ fontSize: 12, fontWeight: 500, color: "#475569",
                display: "block" }}>Full Tutorial</span>
              <span style={{ fontSize: 10, color: "#3d4a5c" }}>Generating...</span>
            </div>
          </div>
        )}

        {/* Chapter shorts */}
        {shorts.length > 0 && expanded && shorts.map((clip, i) => (
          <a key={i} href={`${BASE_URL}${clip.download_url}`}
            download={clip.filename}
            style={{ ...itemStyle(), textDecoration: "none" }}
            onMouseEnter={e => { e.currentTarget.style.background = "#ffffff06"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
            <div style={{ width: 26, height: 26, borderRadius: 7, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "#141428", color: "#6366f1", fontSize: 10, fontWeight: 800 }}>
              {i + 1}
            </div>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <span style={{ fontSize: 12, fontWeight: 500, color: "#94a3b8",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                display: "block" }}>
                {clip.title ?? `Clip ${i + 1}`}
              </span>
              {clip.duration && (
                <span style={{ fontSize: 10, color: "#3d4a5c" }}>{clip.duration}s</span>
              )}
            </div>
            <span style={{ fontSize: 10, color: "#475569", flexShrink: 0 }}>⬇</span>
          </a>
        ))}

        {/* Generate shorts CTA */}
        {videoUrl && shorts.length === 0 && (
          <button onClick={generateShorts} disabled={loadingShorts}
            style={{ ...itemStyle(), justifyContent: "center", opacity: loadingShorts ? 0.6 : 1 }}
            onMouseEnter={e => { if (!loadingShorts) e.currentTarget.style.background = "#ffffff06"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
            <span style={{ fontSize: 11, color: "#475569" }}>
              {loadingShorts ? "Cutting clips..." : "✂ Cut into chapter clips"}
            </span>
          </button>
        )}

        {/* No video yet hint */}
        {!videoUrl && (
          <p style={{ fontSize: 10, color: "#2d3748", padding: "4px 8px",
            lineHeight: 1.5, margin: 0 }}>
            Video will appear here once generation completes.
          </p>
        )}
      </div>
    </div>
  );
}

export default function TutorialViewer({ jobId }: Props) {
  const [arts,    setArts]    = useState<ArtifactsResponse>({ markdown_files:[], video_url:null });
  const [sel,     setSel]     = useState<string|null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [done,    setDone]    = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const videoRef  = useRef<HTMLDivElement>(null);

  // Search
  const [searchQ,      setSearchQ]      = useState("");
  const [searchOpen,   setSearchOpen]   = useState(false);
  const [searchResults,setSearchResults]= useState<SearchResult[]>([]);
  const [searching,    setSearching]    = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout>|null>(null);

  // Modals
  const [showQuiz,     setShowQuiz]     = useState(false);
  const [showExport,   setShowExport]   = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const scrollToVideo = useCallback(() => {
    videoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const loadArts = useCallback(async () => {
    try {
      const d = await api.getArtifacts(jobId);
      setArts(d);
      if (!sel && d.markdown_files.length)
        setSel(d.markdown_files.includes("index.md") ? "index.md" : d.markdown_files[0]);
    } catch {}
  }, [jobId, sel]);

  const loadContent = useCallback(async (f: string) => {
    setLoading(true);
    try { setContent(await (await fetch(api.fileUrl(jobId, f))).text()); }
    catch { setContent("*Failed to load.*"); }
    finally { setLoading(false); }
  }, [jobId]);

  useEffect(() => { loadArts(); }, [loadArts]);

  useEffect(() => {
    if (done) return;
    const id = setInterval(async () => {
      try {
        const s = await api.getStatus(jobId);
        if (s.status==="completed"||s.status==="failed") { setDone(true); clearInterval(id); }
        loadArts();
      } catch {}
    }, 3000);
    return () => clearInterval(id);
  }, [jobId, done, loadArts]);

  useEffect(() => { if (sel) loadContent(sel); }, [sel, loadContent]);

  // Search debounce
  useEffect(() => {
    if (!searchOpen) return;
    if (!searchQ.trim()) { setSearchResults([]); return; }
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await api.search(jobId, searchQ);
        setSearchResults(r.results);
      } catch {}
      setSearching(false);
    }, 350);
  }, [searchQ, jobId, searchOpen]);

  // Cmd+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(o => !o);
        setTimeout(() => searchRef.current?.focus(), 50);
      }
      if (e.key === "Escape") { setSearchOpen(false); setShowQuiz(false); setShowExport(false); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const files = [...arts.markdown_files].sort((a, b) => {
    if (a === "index.md") return -1;
    if (b === "index.md") return 1;
    return a.localeCompare(b);
  });

  const btnStyle = {
    display:"flex" as const, alignItems:"center" as const, gap:6,
    padding:"6px 12px", borderRadius:9, border:"1px solid #1a1a30",
    background:"#141428", color:"#64748b", cursor:"pointer" as const,
    fontSize:12, fontWeight:500 as const, transition:"all .15s",
    textDecoration:"none" as const,
  };

  return (
    <div style={{ display:"flex", height:"calc(100vh - 64px)", overflow:"hidden", position:"relative" }}>

      {/* Sidebar */}
      <aside style={{
        width: sidebar ? 260 : 0, flexShrink:0, overflow: sidebar ? "auto" : "hidden",
        background:"#0a0a14", borderRight:"1px solid #141428",
        transition:"width .25s cubic-bezier(.4,0,.2,1)", display:"flex", flexDirection:"column",
      }}>
        <div style={{ padding:"14px 14px 10px", borderBottom:"1px solid #141428" }}>
          <p style={{ fontSize:10, fontWeight:700, letterSpacing:"0.12em", color:"#3d4a5c", textTransform:"uppercase", marginBottom:0 }}>
            Chapters
          </p>
        </div>
        <nav style={{ padding:"8px", flex:1 }}>
          {files.length === 0 ? (
            <div style={{ padding:"8px 4px", display:"flex", flexDirection:"column", gap:6 }}>
              {[1,2,3,4,5].map(i => (
                <div key={i} className="skeleton" style={{ height:38, opacity:1-i*.12 }} />
              ))}
            </div>
          ) : files.map(f => {
            const active = sel === f;
            const n = num(f);
            return (
              <button key={f} onClick={() => setSel(f)} style={{
                width:"100%", display:"flex", alignItems:"center", gap:10,
                padding:"9px 10px", borderRadius:10, border:"1px solid transparent",
                background: active ? "#6366f115" : "transparent",
                borderColor: active ? "#6366f130" : "transparent",
                cursor:"pointer", textAlign:"left", marginBottom:2, transition:"all .15s",
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background="#ffffff06"; }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background="transparent"; }}>
                <div style={{
                  width:26, height:26, borderRadius:7, flexShrink:0,
                  display:"flex", alignItems:"center", justifyContent:"center",
                  fontSize:11, fontWeight:800, fontFamily:"var(--mono)",
                  background: active ? "#6366f130" : "#141428",
                  color: active ? "#818cf8" : "#475569",
                }}>
                  {f === "index.md" ? "≡" : n ?? "?"}
                </div>
                <span style={{
                  fontSize:13, fontWeight: active ? 600 : 400,
                  color: active ? "#c7d2fe" : "#64748b",
                  overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", flex:1,
                }}>
                  {label(f)}
                </span>
                {active && <div style={{ width:3, height:20, borderRadius:99, background:"#6366f1", flexShrink:0 }} />}
              </button>
            );
          })}
        </nav>

        {/* Video Tutorials section */}
        <VideoTutorialsSection
          jobId={jobId}
          videoUrl={arts.video_url}
          onScrollToVideo={scrollToVideo}
        />
      </aside>

      {/* Main */}
      <main style={{ flex:1, overflowY:"auto", background:"#08080f", position:"relative" }}>

        {/* Toolbar */}
        <div style={{
          position:"sticky", top:0, zIndex:10,
          display:"flex", alignItems:"center", gap:8, flexWrap:"wrap" as const,
          padding:"10px 20px", borderBottom:"1px solid #141428",
          background:"#08080fdd", backdropFilter:"blur(12px)",
        }}>
          <button onClick={() => setSidebar(o => !o)} style={{
            width:32, height:32, borderRadius:8, border:"1px solid #1a1a30",
            background:"#141428", color:"#64748b", cursor:"pointer", fontSize:14,
            display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
          }}>
            {sidebar ? "◀" : "▶"}
          </button>

          {sel && <span style={{ fontSize:13, fontWeight:500, color:"#94a3b8", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:200 }}>{label(sel)}</span>}

          <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:6, flexWrap:"wrap" as const }}>
            {/* Search */}
            <button onClick={() => { setSearchOpen(o=>!o); setTimeout(()=>searchRef.current?.focus(),50); }}
              style={btnStyle}
              onMouseEnter={e=>(e.currentTarget.style.borderColor="#6366f150")}
              onMouseLeave={e=>(e.currentTarget.style.borderColor="#1a1a30")}>
              🔍 Search
              <kbd style={{ fontSize:10, color:"#3d4a5c", background:"#0d0d1a", border:"1px solid #252540", borderRadius:4, padding:"1px 5px" }}>⌘K</kbd>
            </button>

            {/* Quiz — only on chapter files */}
            {sel && sel !== "index.md" && (
              <button onClick={() => setShowQuiz(true)} style={btnStyle}
                onMouseEnter={e=>(e.currentTarget.style.borderColor="#f59e0b50")}
                onMouseLeave={e=>(e.currentTarget.style.borderColor="#1a1a30")}>
                🎯 Quiz
              </button>
            )}

            {/* Export to Notion / Confluence */}
            <button onClick={() => setShowExport(true)} style={btnStyle}
              onMouseEnter={e=>(e.currentTarget.style.borderColor="#6366f150")}
              onMouseLeave={e=>(e.currentTarget.style.borderColor="#1a1a30")}>
              📤 Export
            </button>

            {/* PDF Download */}
            <a href={api.exportPdfUrl(jobId)} download style={btnStyle}
              onMouseEnter={e=>(e.currentTarget.style.borderColor="#6366f150")}
              onMouseLeave={e=>(e.currentTarget.style.borderColor="#1a1a30")}>
              ⬇ PDF
            </a>

            {/* Feature 4: PPTX Export — additive, one link only */}
            <a href={`${BASE_URL}/api/jobs/${jobId}/export/pptx`}
              download={`tutorial_${jobId.slice(0,8)}.pptx`}
              style={btnStyle}
              onMouseEnter={e=>{ e.currentTarget.style.borderColor="#f59e0b50"; e.currentTarget.style.color="#fcd34d"; }}
              onMouseLeave={e=>{ e.currentTarget.style.borderColor="#1a1a30";   e.currentTarget.style.color="#64748b"; }}>
              📊 PPTX
            </a>

            {/* FIX 3: Settings / Features drawer trigger */}
            <button
              onClick={() => setShowSettings(o => !o)}
              style={btnStyle}
              onMouseEnter={e=>(e.currentTarget.style.borderColor="#6366f150")}
              onMouseLeave={e=>(e.currentTarget.style.borderColor="#1a1a30")}
              title="Open features panel"
            >
              ⚙️ Features
            </button>

            {arts.markdown_files.length > 0 && (
              <span style={{ fontSize:11, color:"#3d4a5c", fontFamily:"var(--mono)" }}>
                {arts.markdown_files.length} files
              </span>
            )}
          </div>
        </div>

        {/* Search overlay */}
        {searchOpen && (
          <div style={{ position:"sticky", top:53, zIndex:9, borderBottom:"1px solid #141428", background:"#09090f", padding:"12px 20px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, background:"#0d0d1a", borderRadius:12,
              border:`1px solid ${searchQ ? "#6366f150" : "#252540"}`, padding:"0 14px" }}>
              <span style={{ color:"#475569" }}>🔍</span>
              <input ref={searchRef} value={searchQ} onChange={e=>setSearchQ(e.target.value)}
                placeholder="Search tutorial content…"
                style={{ flex:1, background:"transparent", border:"none", outline:"none", padding:"11px 0", fontSize:14, color:"#e2e8f0" }} />
              {searching && (
                <svg className="anim-spin" width="14" height="14" fill="none" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" stroke="#ffffff20" strokeWidth="3"/>
                  <path d="M12 2a10 10 0 0110 10" stroke="#6366f1" strokeWidth="3" strokeLinecap="round"/>
                </svg>
              )}
              {searchQ && <button onClick={()=>{ setSearchQ(""); setSearchResults([]); }} style={{ background:"none", border:"none", color:"#475569", cursor:"pointer", fontSize:16 }}>×</button>}
            </div>

            {searchResults.length > 0 && (
              <div style={{ marginTop:10, borderRadius:12, border:"1px solid #1a1a30", background:"#0a0a14", maxHeight:280, overflowY:"auto" }}>
                {searchResults.map((r, i) => (
                  <button key={i} onClick={() => { setSel(r.file); setSearchOpen(false); setSearchQ(""); setSearchResults([]); }}
                    style={{ width:"100%", padding:"10px 14px", border:"none", borderBottom:"1px solid #141428",
                      background:"transparent", textAlign:"left", cursor:"pointer" }}
                    onMouseEnter={e=>(e.currentTarget.style.background="#6366f108")}
                    onMouseLeave={e=>(e.currentTarget.style.background="transparent")}>
                    <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:3 }}>
                      <span style={{ fontSize:11, color:"#6366f1", fontFamily:"var(--mono)", fontWeight:600 }}>{label(r.file)}</span>
                      <span style={{ fontSize:10, color:"#3d4a5c" }}>line {r.line}</span>
                    </div>
                    <p style={{ fontSize:12, color:"#64748b", margin:0, lineHeight:1.5, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.snippet}</p>
                  </button>
                ))}
              </div>
            )}
            {searchQ && !searching && searchResults.length === 0 && (
              <p style={{ fontSize:12, color:"#3d4a5c", padding:"10px 0" }}>No results for "{searchQ}"</p>
            )}
          </div>
        )}

        {/* Content — FIX 1: 860px centered card, comfortable padding */}
        <div style={{ maxWidth:860, margin:"0 auto", padding:"28px 32px 80px" }}>
          {loading ? (
            <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
              {[100,75,90,60,80,50].map((w, i) => (
                <div key={i} className="skeleton" style={{ height:16, width:`${w}%` }} />
              ))}
            </div>
          ) : (
            <div className="md">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                code({ className, children }) {
                  const lang = /language-(\w+)/.exec(className ?? "")?.[1] ?? "";
                  if (lang === "mermaid") return <MermaidDiagram chart={String(children).trim()} />;
                  return <code>{children}</code>;
                },
              }}>
                {content}
              </ReactMarkdown>
            </div>
          )}

          {arts.video_url && (
            <div ref={videoRef} style={{ marginTop:48, paddingTop:32, borderTop:"1px solid #141428" }}>
              <h2 style={{ fontSize:18, fontWeight:700, color:"#e2e8f0", marginBottom:16, display:"flex", alignItems:"center", gap:8 }}>
                🎬 Video Walkthrough
              </h2>
              <VideoPlayer src={arts.video_url} />
              <p style={{ fontSize:11, color:"#3d4a5c", marginTop:10, textAlign:"center" }}>
                Use <strong style={{ color:"#6366f1" }}>⚙️ Features</strong> in the toolbar to add Avatar, Zoom, Shorts &amp; more
              </p>
            </div>
          )}
        </div>
      </main>

      {/* FIX 3: Settings drawer — all 6 features in one panel */}
      <SettingsDrawer
        jobId={jobId}
        hasVideo={!!arts.video_url}
        open={showSettings}
        onClose={() => setShowSettings(false)}
      />

      {/* Floating ChatBot */}
      <ChatBot jobId={jobId} contextFile={sel} />

      {/* Quiz Modal */}
      {showQuiz && sel && (
        <QuizModal jobId={jobId} chapter={sel} onClose={() => setShowQuiz(false)} />
      )}

      {/* Export Modal */}
      {showExport && (
        <ExportModal jobId={jobId} onClose={() => setShowExport(false)} />
      )}
    </div>
  );
}
