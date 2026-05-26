"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, JobStatus, LogEntry } from "@/lib/api";

interface Props { jobId: string }

const STEPS = [
  { key: "FetchRepo",            label: "Fetch Repo",     icon: "📥", pct: 10  },
  { key: "IdentifyAbstractions", label: "Abstractions",   icon: "🔍", pct: 25  },
  { key: "AnalyzeRelationships", label: "Relationships",  icon: "🕸️", pct: 40  },
  { key: "OrderChapters",        label: "Ordering",       icon: "📋", pct: 50  },
  { key: "WriteChapters",        label: "Writing",        icon: "✍️", pct: 85  },
  { key: "CombineTutorial",      label: "Assembling",     icon: "📚", pct: 100 },
];

export default function StatusTracker({ jobId }: Props) {
  const router = useRouter();
  const [status,   setStatus]   = useState<JobStatus["status"]>("queued");
  const [progress, setProgress] = useState(0);
  const [logs,     setLogs]     = useState<LogEntry[]>([]);
  const [cursor,   setCursor]   = useState(0);
  const [chDone,   setChDone]   = useState(0);
  const [chTotal,  setChTotal]  = useState(0);
  const [cd,       setCd]       = useState<number|null>(null);
  const [cancelled,setCancelled]= useState(false);
  const logRef  = useRef<HTMLDivElement>(null);
  const cdRef   = useRef<ReturnType<typeof setInterval>|null>(null);

  // Status + chapter poll
  useEffect(() => {
    if (status === "completed" || status === "failed") return;
    const poll = async () => {
      try {
        const [s,c] = await Promise.all([api.getStatus(jobId), api.getChapters(jobId)]);
        setStatus(s.status); setProgress(s.progress);
        setChDone(c.completed_chapters.length); setChTotal(c.total_chapters);
      } catch {}
    };
    poll(); const id = setInterval(poll, 2000); return () => clearInterval(id);
  }, [jobId, status]);

  // Log poll
  useEffect(() => {
    if (status === "completed" || status === "failed") return;
    const poll = async () => {
      try {
        const r = await api.getLogs(jobId, cursor);
        if (r.logs.length) { setLogs(p => [...p, ...r.logs]); setCursor(r.total); }
      } catch {}
    };
    poll(); const id = setInterval(poll, 2000); return () => clearInterval(id);
  }, [jobId, cursor, status]);

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [logs]);

  // Countdown tick
  useEffect(() => {
    if (status !== "completed" || cancelled) return;
    setCd(7);
    cdRef.current = setInterval(() => setCd(p => (p !== null && p > 1 ? p - 1 : 0)), 1000);
    return () => { if (cdRef.current) clearInterval(cdRef.current); };
  }, [status, cancelled]);

  // Redirect when countdown hits 0 — separate effect to avoid setState-during-render
  useEffect(() => {
    if (cd === 0 && !cancelled) {
      if (cdRef.current) clearInterval(cdRef.current);
      router.push(`/tutorial/${jobId}`);
    }
  }, [cd, cancelled, jobId, router]);

  const activeStep = STEPS.findIndex(s => progress < s.pct);
  const curStep    = activeStep < 0 ? STEPS.length - 1 : Math.max(0, activeStep - 1);

  const statusColor = { queued:"#f59e0b", processing:"#6366f1", completed:"#10b981", failed:"#ef4444" }[status] ?? "#6366f1";
  const statusLabel = { queued:"Queued", processing:"Processing", completed:"Completed", failed:"Failed" }[status];

  return (
    <div className="anim-fade-up" style={{ width:"100%", maxWidth:700, display:"flex", flexDirection:"column", gap:20 }}>

      {/* Status header */}
      <div style={{
        borderRadius:18, padding:"20px 24px",
        background:`${statusColor}0d`, border:`1px solid ${statusColor}28`,
        display:"flex", alignItems:"center", justifyContent:"space-between",
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          <div style={{
            width:42, height:42, borderRadius:12,
            background:`${statusColor}18`, border:`1px solid ${statusColor}30`,
            display:"flex", alignItems:"center", justifyContent:"center", fontSize:20,
          }}>
            {{ queued:"⏳", processing:"⚡", completed:"✅", failed:"❌" }[status]}
          </div>
          <div>
            <p style={{ fontSize:15, fontWeight:700, color:statusColor }}>{statusLabel}</p>
            <p style={{ fontSize:12, color:"#64748b", marginTop:2, fontFamily:"var(--mono)" }}>
              {jobId.slice(0,8)}…{jobId.slice(-4)}
            </p>
          </div>
        </div>
        {chTotal > 0 && (
          <div style={{
            display:"flex", alignItems:"center", gap:7,
            padding:"7px 14px", borderRadius:99,
            background:"#6366f115", border:"1px solid #6366f130",
            fontSize:12, fontWeight:600, color:"#a5b4fc",
          }}>
            <span>📖</span> {chDone} / {chTotal} chapters
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
        <div style={{ display:"flex", justifyContent:"space-between", fontSize:12 }}>
          <span style={{ color:"#64748b" }}>{status === "processing" ? (STEPS[curStep]?.label ?? "Working…") : statusLabel}</span>
          <span style={{ color:"#a5b4fc", fontFamily:"var(--mono)", fontWeight:600 }}>{progress}%</span>
        </div>
        <div style={{ height:6, borderRadius:99, background:"#1a1a30", overflow:"hidden" }}>
          <div style={{
            height:"100%", borderRadius:99,
            width:`${progress}%`,
            background: status === "failed" ? "#ef4444"
              : "linear-gradient(90deg, #6366f1, #8b5cf6, #06b6d4)",
            boxShadow: status !== "failed" ? "0 0 12px #6366f180" : "none",
            transition:"width .8s cubic-bezier(.34,1,.64,1)",
          }} />
        </div>
      </div>

      {/* Pipeline steps */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:8 }}>
        {STEPS.map((step, i) => {
          const done   = progress >= step.pct;
          const active = i === curStep && status === "processing";
          return (
            <div key={step.key} style={{
              display:"flex", flexDirection:"column", alignItems:"center", gap:6,
              padding:"12px 4px", borderRadius:12, textAlign:"center",
              background: done ? "#6366f112" : "#0d0d1a",
              border:`1px solid ${active ? "#6366f1" : done ? "#6366f128" : "#1a1a30"}`,
              boxShadow: active ? "0 0 16px #6366f128" : "none",
              transition:"all .3s",
            }}>
              <span style={{ fontSize:18 }}>{step.icon}</span>
              <span style={{ fontSize:10, color: done ? "#a5b4fc" : "#475569", fontWeight:500, lineHeight:1.3 }}>
                {step.label}
              </span>
              {active && (
                <div className="anim-pulse" style={{ width:5, height:5, borderRadius:"50%", background:"#818cf8" }} />
              )}
              {done && i < STEPS.length - 1 && (
                <span style={{ fontSize:10, color:"#10b981" }}>✓</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Terminal */}
      <div style={{ borderRadius:16, overflow:"hidden", border:"1px solid #1a1a30" }}>
        {/* Terminal titlebar */}
        <div style={{
          display:"flex", alignItems:"center", gap:8,
          padding:"10px 16px", background:"#0a0a16",
          borderBottom:"1px solid #1a1a30",
        }}>
          <div style={{ display:"flex", gap:6 }}>
            {["#ef4444","#f59e0b","#10b981"].map(c => (
              <div key={c} style={{ width:11, height:11, borderRadius:"50%", background:c, opacity:.8 }} />
            ))}
          </div>
          <span style={{ fontSize:11, color:"#3d4a5c", fontFamily:"var(--mono)", marginLeft:4 }}>
            pipeline — stdout/stderr
          </span>
          <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:6 }}>
            {status === "processing" && (
              <div className="anim-pulse" style={{ width:6, height:6, borderRadius:"50%", background:"#10b981" }} />
            )}
            <span style={{ fontSize:10, color:"#3d4a5c" }}>{logs.length} lines</span>
          </div>
        </div>

        {/* Log body */}
        <div ref={logRef} style={{
          height:260, overflowY:"auto", padding:"14px 16px",
          background:"#06060e", fontFamily:"var(--mono)", fontSize:12, lineHeight:1.7,
        }}>
          {logs.length === 0 ? (
            <span style={{ color:"#2a2a40" }}>
              Initializing pipeline<span className="anim-blink">▋</span>
            </span>
          ) : (
            logs.map((e, i) => (
              <div key={i} className="anim-slide-in" style={{ display:"flex", gap:12, marginBottom:2 }}>
                <span style={{ color:"#1e3a5f", flexShrink:0, userSelect:"none" }}>
                  {new Date(e.timestamp * 1000).toLocaleTimeString("en", { hour12:false })}
                </span>
                <span style={{
                  color: e.message.startsWith("ERROR") ? "#f87171"
                    : e.message.startsWith("CHAPTER_READY") ? "#34d399"
                    : e.message.startsWith("Job completed") ? "#a78bfa"
                    : "#4ade80",
                }}>
                  {e.message}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Completed */}
      {status === "completed" && (
        <div className="anim-fade-up" style={{
          borderRadius:16, padding:"20px 24px",
          background:"#10b98110", border:"1px solid #10b98128",
          display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:12,
        }}>
          <div>
            <p style={{ fontSize:15, fontWeight:700, color:"#34d399" }}>🎉 Tutorial Generated!</p>
            {cd !== null && !cancelled && (
              <p style={{ fontSize:12, color:"#64748b", marginTop:4 }}>
                Auto-opening in <b style={{ color:"#fff" }}>{cd}s</b> ·{" "}
                <button onClick={() => { setCancelled(true); if (cdRef.current) clearInterval(cdRef.current); setCd(null); }}
                  style={{ background:"none", border:"none", color:"#818cf8", cursor:"pointer", textDecoration:"underline", fontSize:12 }}>
                  cancel
                </button>
              </p>
            )}
          </div>
          <button onClick={() => router.push(`/tutorial/${jobId}`)} style={{
            padding:"11px 20px", borderRadius:12, border:"none", cursor:"pointer",
            background:"linear-gradient(135deg, #10b981, #059669)",
            color:"#fff", fontWeight:700, fontSize:14,
            boxShadow:"0 4px 20px #10b98130",
          }}>
            View Tutorial →
          </button>
        </div>
      )}

      {/* Failed */}
      {status === "failed" && (
        <div className="anim-fade-up" style={{
          borderRadius:16, padding:"20px 24px",
          background:"#ef444410", border:"1px solid #ef444428",
        }}>
          <p style={{ fontSize:15, fontWeight:700, color:"#f87171" }}>Generation failed</p>
          <p style={{ fontSize:13, color:"#64748b", marginTop:6 }}>Check the terminal above for details.</p>
          <button onClick={() => router.push("/")} style={{
            marginTop:14, padding:"9px 18px", borderRadius:10, border:"1px solid #ef444430",
            background:"#ef444412", color:"#f87171", cursor:"pointer", fontWeight:600, fontSize:13,
          }}>
            ← Try Again
          </button>
        </div>
      )}
    </div>
  );
}
