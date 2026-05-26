"use client";
/**
 * SettingsDrawer — slide-out panel for all 6 added features.
 * Opens via the ⚙️ button in the TutorialViewer toolbar.
 * Wires directly to existing feature API endpoints — nothing is rebuilt.
 */

import React, { useState } from "react";
import { useTheme } from "./ThemeProvider";
import { BASE_URL } from "@/lib/api";

interface Props {
  jobId:    string;
  hasVideo: boolean;
  open:     boolean;
  onClose:  () => void;
}

// ── Shared small styles ────────────────────────────────────────────────────
const sectionTitle: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, letterSpacing: "0.1em",
  textTransform: "uppercase", color: "#475569", marginBottom: 10,
};
const actionBtn = (active = false, danger = false): React.CSSProperties => ({
  display: "flex", alignItems: "center", gap: 7,
  width: "100%", padding: "9px 14px", borderRadius: 10,
  fontSize: 12, fontWeight: 600, cursor: "pointer",
  border: `1px solid ${active ? "#6366f160" : danger ? "#ef444430" : "#252540"}`,
  background: active ? "#6366f118" : danger ? "#ef444410" : "#141428",
  color: active ? "#a5b4fc" : danger ? "#fca5a5" : "#94a3b8",
  transition: "all .15s",
});
const statusPill = (ok: boolean): React.CSSProperties => ({
  marginLeft: "auto", fontSize: 10, fontWeight: 700,
  padding: "2px 8px", borderRadius: 99,
  background: ok ? "#22c55e18" : "#ef444418",
  color: ok ? "#4ade80" : "#f87171",
  border: `1px solid ${ok ? "#22c55e30" : "#ef444430"}`,
});
const downloadLink: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 5,
  padding: "7px 14px", borderRadius: 9, fontSize: 12, fontWeight: 600,
  background: "#22c55e18", border: "1px solid #22c55e40",
  color: "#4ade80", textDecoration: "none", marginTop: 8,
};

// ── Feature 1: Avatar ──────────────────────────────────────────────────────
function AvatarSection({ jobId }: { jobId: string }) {
  const [apiKey,   setApiKey]   = useState("");
  const [provider, setProvider] = useState<"did"|"heygen">("did");
  const [position, setPosition] = useState("bottomright");
  const [status,   setStatus]   = useState<"idle"|"loading"|"done"|"error">("idle");
  const [url,      setUrl]      = useState("");
  const [err,      setErr]      = useState("");

  const run = async () => {
    if (!apiKey.trim()) { setErr("Enter your API key first."); return; }
    setStatus("loading"); setErr("");
    try {
      const r = await fetch(`${BASE_URL}/api/jobs/${jobId}/avatar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: apiKey, position }),
      });
      const d = await r.json();
      if (d.success) { setStatus("done"); setUrl(`${BASE_URL}${d.download_url}`); }
      else           { setStatus("error"); setErr(d.detail ?? d.error ?? "Failed"); }
    } catch (e: unknown) { setStatus("error"); setErr(e instanceof Error ? e.message : "Error"); }
  };

  return (
    <div>
      <p style={sectionTitle}>🤖 Talking Avatar</p>
      <div style={{ display:"flex", gap:6, marginBottom:8 }}>
        {(["did","heygen"] as const).map(p => (
          <button key={p} onClick={() => setProvider(p)} style={{
            ...actionBtn(provider===p), flex:1, justifyContent:"center",
          }}>{p === "did" ? "D-ID" : "HeyGen"}</button>
        ))}
      </div>
      <input
        type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
        placeholder={`${provider === "did" ? "D-ID" : "HeyGen"} API key`}
        style={{ width:"100%", padding:"8px 12px", borderRadius:8, marginBottom:6,
          background:"#08080f", border:"1px solid #252540", color:"#e2e8f0",
          fontSize:12, outline:"none", boxSizing:"border-box" as const }}
      />
      <select value={position} onChange={e => setPosition(e.target.value)} style={{
        width:"100%", padding:"8px 12px", borderRadius:8, marginBottom:8,
        background:"#08080f", border:"1px solid #252540", color:"#94a3b8",
        fontSize:12, outline:"none", boxSizing:"border-box" as const,
      }}>
        {["bottomright","bottomleft","topright","topleft"].map(p => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>
      {status === "done"
        ? <a href={url} download="tutorial_with_avatar.mp4" style={downloadLink}>⬇ Download avatar video</a>
        : <button onClick={run} disabled={status==="loading"} style={actionBtn(false)}>
            {status==="loading" ? "⏳ Generating (2–5 min)…" : "✨ Generate & Overlay"}
          </button>
      }
      {err && <p style={{ fontSize:11, color:"#f87171", marginTop:6 }}>⚠ {err}</p>}
    </div>
  );
}

// ── Feature 2: Code Zoom ───────────────────────────────────────────────────
function ZoomSection({ jobId }: { jobId: string }) {
  const [status, setStatus] = useState<"idle"|"loading"|"done"|"error">("idle");
  const [url,    setUrl]    = useState("");
  const [info,   setInfo]   = useState("");
  const [err,    setErr]    = useState("");

  const run = async () => {
    setStatus("loading"); setErr("");
    try {
      const r = await fetch(`${BASE_URL}/api/jobs/${jobId}/zoom-code`, { method:"POST" });
      const d = await r.json();
      if (d.success) {
        setStatus("done");
        setUrl(`${BASE_URL}${d.download_url}`);
        setInfo(`${d.zoomed_clips} clips zoomed`);
      } else { setStatus("error"); setErr(d.detail ?? "Failed"); }
    } catch (e: unknown) { setStatus("error"); setErr(e instanceof Error ? e.message : "Error"); }
  };

  return (
    <div>
      <p style={sectionTitle}>🔍 Code Zoom-in</p>
      <p style={{ fontSize:11, color:"#475569", marginBottom:8, lineHeight:1.5 }}>
        Animates a smooth zoom into highlighted lines on all code slides.
      </p>
      {status === "done"
        ? <>
            <span style={{ ...statusPill(true), display:"inline-block", marginBottom:6 }}>✓ {info}</span>
            <br />
            <a href={url} download="tutorial_with_zoom.mp4" style={downloadLink}>⬇ Download zoomed video</a>
          </>
        : <button onClick={run} disabled={status==="loading"} style={actionBtn(false)}>
            {status==="loading" ? "⏳ Processing clips…" : "🔍 Apply Zoom Effects"}
          </button>
      }
      {err && <p style={{ fontSize:11, color:"#f87171", marginTop:6 }}>⚠ {err}</p>}
    </div>
  );
}

// ── Feature 3: Chapter Shorts ──────────────────────────────────────────────
function ShortsSection({ jobId }: { jobId: string }) {
  const [status, setStatus] = useState<"idle"|"loading"|"done"|"error">("idle");
  const [clips,  setClips]  = useState<{filename:string;title?:string;duration?:number;download_url:string}[]>([]);
  const [err,    setErr]    = useState("");

  const run = async () => {
    setStatus("loading"); setErr("");
    try {
      const r = await fetch(`${BASE_URL}/api/jobs/${jobId}/shorts`, { method:"POST" });
      const d = await r.json();
      if (d.clips) { setStatus("done"); setClips(d.clips); }
      else         { setStatus("error"); setErr(d.detail ?? "Failed"); }
    } catch (e: unknown) { setStatus("error"); setErr(e instanceof Error ? e.message : "Error"); }
  };

  return (
    <div>
      <p style={sectionTitle}>✂️ Chapter Shorts (60 s)</p>
      <p style={{ fontSize:11, color:"#475569", marginBottom:8, lineHeight:1.5 }}>
        Cuts the video into one clip per chapter. Chapters over 60 s are split for YouTube Shorts.
      </p>
      {status !== "done"
        ? <button onClick={run} disabled={status==="loading"} style={actionBtn(false)}>
            {status==="loading" ? "⏳ Cutting clips…" : "✂️ Generate Shorts"}
          </button>
        : <div style={{ marginTop:6, display:"flex", flexDirection:"column", gap:4 }}>
            {clips.map((c, i) => (
              <div key={i} style={{ display:"flex", alignItems:"center", justifyContent:"space-between",
                padding:"7px 10px", borderRadius:8, background:"#0a0a14", border:"1px solid #141428" }}>
                <span style={{ fontSize:11, color:"#94a3b8", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:180 }}>
                  {c.title ?? c.filename}
                </span>
                <a href={`${BASE_URL}${c.download_url}`} download={c.filename}
                  style={{ ...downloadLink, marginTop:0, padding:"4px 10px", fontSize:11 }}>⬇</a>
              </div>
            ))}
          </div>
      }
      {err && <p style={{ fontSize:11, color:"#f87171", marginTop:6 }}>⚠ {err}</p>}
    </div>
  );
}

// ── Feature 5: Theme ───────────────────────────────────────────────────────
function ThemeSection() {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <p style={sectionTitle}>🎨 Theme</p>
      <div style={{ display:"flex", gap:8 }}>
        {(["dark","light"] as const).map(t => (
          <button key={t} onClick={() => setTheme(t)} style={{
            ...actionBtn(theme===t), flex:1, justifyContent:"center",
          }}>
            {t === "dark" ? "🌙 Dark" : "☀️ Light"}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Feature 6: Mobile ──────────────────────────────────────────────────────
function MobileSection() {
  return (
    <div>
      <p style={sectionTitle}>📱 Mobile View</p>
      <p style={{ fontSize:11, color:"#475569", lineHeight:1.6 }}>
        Responsive CSS is already active. To test:
      </p>
      <ul style={{ fontSize:11, color:"#64748b", paddingLeft:16, lineHeight:2, margin:"6px 0 0" }}>
        <li>Open DevTools → Toggle device toolbar</li>
        <li>Set width to <code style={{ color:"#a5b4fc" }}>375px</code> for mobile</li>
        <li>Set width to <code style={{ color:"#a5b4fc" }}>768px</code> for tablet</li>
      </ul>
    </div>
  );
}

// ── Main Drawer ────────────────────────────────────────────────────────────
export default function SettingsDrawer({ jobId, hasVideo, open, onClose }: Props) {
  const divider = <div style={{ height:1, background:"#1a1a30", margin:"18px 0" }} />;

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          onClick={onClose}
          style={{
            position:"fixed", inset:0, zIndex:200,
            background:"#00000050", backdropFilter:"blur(2px)",
          }}
        />
      )}

      {/* Drawer panel */}
      <div style={{
        position:   "fixed", top:0, right:0, bottom:0,
        width:      380, zIndex:201,
        background: "#0d0d1a",
        borderLeft: "1px solid #252540",
        boxShadow:  "-20px 0 60px #00000060",
        transform:  open ? "translateX(0)" : "translateX(100%)",
        transition: "transform .28s cubic-bezier(.4,0,.2,1)",
        display:    "flex", flexDirection:"column",
        overflowY:  "auto",
      }}>

        {/* Header */}
        <div style={{
          display:"flex", alignItems:"center", justifyContent:"space-between",
          padding:"16px 20px", borderBottom:"1px solid #1a1a30",
          position:"sticky", top:0, background:"#0d0d1a", zIndex:1,
        }}>
          <div>
            <p style={{ fontSize:14, fontWeight:700, color:"#e2e8f0", margin:0 }}>⚙️ Features</p>
            <p style={{ fontSize:11, color:"#475569", margin:0, marginTop:2 }}>
              Video enhancement tools
            </p>
          </div>
          <button onClick={onClose} style={{
            width:30, height:30, borderRadius:8,
            background:"#141428", border:"1px solid #252540",
            color:"#64748b", cursor:"pointer", fontSize:16,
            display:"flex", alignItems:"center", justifyContent:"center",
          }}>×</button>
        </div>

        {/* Body */}
        <div style={{ padding:"20px", display:"flex", flexDirection:"column", gap:0, flex:1 }}>

          {/* PPTX — already in toolbar, just link it */}
          <div>
            <p style={sectionTitle}>📊 PPTX Export</p>
            <a
              href={`${BASE_URL}/api/jobs/${jobId}/export/pptx`}
              download={`tutorial_${jobId.slice(0,8)}.pptx`}
              style={{ ...actionBtn(false), textDecoration:"none", display:"flex" }}
            >
              📊 Download as PowerPoint
              <span style={{ ...statusPill(true), fontSize:9 }}>Also in toolbar</span>
            </a>
          </div>

          {divider}
          <ThemeSection />

          {hasVideo && (
            <>
              {divider}
              <ZoomSection   jobId={jobId} />
              {divider}
              <ShortsSection jobId={jobId} />
              {divider}
              <AvatarSection jobId={jobId} />
            </>
          )}

          {!hasVideo && (
            <p style={{ fontSize:11, color:"#475569", marginTop:12, lineHeight:1.6 }}>
              💡 Video features (Zoom, Shorts, Avatar) become available after
              generating a video tutorial.
            </p>
          )}

          {divider}
          <MobileSection />

        </div>

        {/* Footer */}
        <div style={{
          padding:"12px 20px", borderTop:"1px solid #1a1a30",
          fontSize:10, color:"#3d4a5c",
        }}>
          6 features active · Original tutorial.mp4 is never modified
        </div>
      </div>
    </>
  );
}
