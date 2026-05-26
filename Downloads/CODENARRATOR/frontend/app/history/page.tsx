"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, DiskJob } from "@/lib/api";

function timeAgo(ts: number) {
  const diff = (Date.now() / 1000) - ts;
  if (diff < 60)    return "just now";
  if (diff < 3600)  return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}

function statusColor(s: string) {
  return { completed:"#10b981", failed:"#ef4444", processing:"#6366f1", queued:"#f59e0b" }[s] ?? "#64748b";
}

function StatusBadge({ status }: { status: string }) {
  const color = statusColor(status);
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"3px 10px", borderRadius:99, fontSize:11, fontWeight:600,
      background:`${color}18`, border:`1px solid ${color}30`, color,
    }}>
      <span style={{ width:5, height:5, borderRadius:"50%", background:color, display:"inline-block" }}/>
      {status}
    </span>
  );
}

export default function HistoryPage() {
  const [jobs,    setJobs]    = useState<DiskJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");
  const [filter,  setFilter]  = useState<"all"|"completed"|"failed">("all");

  useEffect(() => {
    api.adminDiskJobs()
      .then(d => { setJobs(d.jobs); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const filtered = jobs.filter(j =>
    filter === "all" ? true :
    filter === "completed" ? j.md_count > 0 :
    j.status === "failed"
  );

  return (
    <div style={{ minHeight:"100vh", background:"#07070f" }}>
      {/* Header */}
      <header style={{
        height:60, display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"0 28px", borderBottom:"1px solid #141428",
        background:"#07070fdd", backdropFilter:"blur(12px)",
        position:"sticky", top:0, zIndex:50,
      }}>
        <Link href="/" style={{ fontSize:13, fontWeight:500, color:"#64748b", display:"flex", alignItems:"center", gap:6 }}>
          ← Code Narrator
        </Link>
        <span style={{ fontSize:15, fontWeight:700 }}>
          <span className="g-text">Tutorial History</span>
        </span>
        <Link href="/generate?jobId=" style={{ fontSize:12, color:"#6366f1", fontWeight:500 }}>
          + New
        </Link>
      </header>

      <main style={{ maxWidth:900, margin:"0 auto", padding:"40px 24px" }}>
        {/* Stats row */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:14, marginBottom:32 }}>
          {[
            { label:"Total Tutorials", value: jobs.length, icon:"📚", color:"#6366f1" },
            { label:"With Video",      value: jobs.filter(j => j.has_video).length, icon:"🎬", color:"#8b5cf6" },
            { label:"Total Size",      value: `${jobs.reduce((s,j)=>s+j.size_mb,0).toFixed(1)} MB`, icon:"💾", color:"#06b6d4" },
          ].map(stat => (
            <div key={stat.label} style={{
              borderRadius:16, padding:"20px 22px",
              background:`${stat.color}0d`, border:`1px solid ${stat.color}22`,
            }}>
              <div style={{ fontSize:24, marginBottom:6 }}>{stat.icon}</div>
              <div style={{ fontSize:26, fontWeight:800, color:stat.color }}>{stat.value}</div>
              <div style={{ fontSize:12, color:"#64748b", marginTop:3 }}>{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Filter tabs */}
        <div style={{ display:"flex", gap:8, marginBottom:24 }}>
          {(["all","completed","failed"] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding:"7px 18px", borderRadius:10, border:"1px solid",
              fontSize:13, fontWeight:500, cursor:"pointer",
              background: filter===f ? "#6366f118" : "transparent",
              borderColor: filter===f ? "#6366f150" : "#1a1a30",
              color: filter===f ? "#a5b4fc" : "#64748b",
              transition:"all .15s",
            }}>
              {f.charAt(0).toUpperCase()+f.slice(1)}
              <span style={{ marginLeft:6, fontSize:11, color:"#475569" }}>
                {f==="all" ? jobs.length : f==="completed" ? jobs.filter(j=>j.md_count>0).length : jobs.filter(j=>j.status==="failed").length}
              </span>
            </button>
          ))}
        </div>

        {/* Job list */}
        {loading ? (
          <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
            {[1,2,3,4,5].map(i => (
              <div key={i} className="skeleton" style={{ height:80, borderRadius:14, opacity:1-i*.12 }} />
            ))}
          </div>
        ) : error ? (
          <div style={{ textAlign:"center", padding:60 }}>
            <p style={{ color:"#ef4444", marginBottom:8 }}>Could not load history</p>
            <p style={{ fontSize:12, color:"#64748b" }}>{error}</p>
            <p style={{ fontSize:12, color:"#475569", marginTop:8 }}>Is the backend running on port 8000?</p>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign:"center", padding:80 }}>
            <div style={{ fontSize:48, marginBottom:16 }}>📂</div>
            <p style={{ color:"#64748b", fontSize:15 }}>No tutorials yet.</p>
            <Link href="/" style={{ display:"inline-block", marginTop:16, color:"#818cf8", fontSize:13, textDecoration:"underline" }}>
              Generate your first tutorial →
            </Link>
          </div>
        ) : (
          <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
            {filtered.map(job => (
              <div key={job.job_id} style={{
                borderRadius:16, padding:"18px 22px",
                background:"#0d0d1a", border:"1px solid #1a1a30",
                display:"flex", alignItems:"center", gap:16,
                transition:"border-color .15s",
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor="#252545")}
              onMouseLeave={e => (e.currentTarget.style.borderColor="#1a1a30")}>

                {/* Icon */}
                <div style={{
                  width:44, height:44, borderRadius:12, flexShrink:0,
                  background:"#6366f115", border:"1px solid #6366f125",
                  display:"flex", alignItems:"center", justifyContent:"center", fontSize:20,
                }}>
                  {job.has_video ? "🎬" : "📖"}
                </div>

                {/* Info */}
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:4 }}>
                    <span style={{
                      fontFamily:"var(--mono)", fontSize:12, color:"#a5b4fc",
                      overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                    }}>
                      {job.job_id}
                    </span>
                    <StatusBadge status={job.md_count > 0 ? "completed" : job.status} />
                    {job.in_memory && (
                      <span style={{ fontSize:10, color:"#10b981", background:"#10b98115", padding:"2px 6px", borderRadius:6, border:"1px solid #10b98120" }}>
                        live
                      </span>
                    )}
                  </div>
                  <div style={{ display:"flex", gap:16, fontSize:12, color:"#475569" }}>
                    <span>📄 {job.md_count} chapters</span>
                    {job.has_video && <span>🎬 video</span>}
                    <span>💾 {job.size_mb} MB</span>
                    <span>🕐 {timeAgo(job.mtime)}</span>
                  </div>
                </div>

                {/* Actions */}
                <div style={{ display:"flex", gap:8, flexShrink:0 }}>
                  {job.md_count > 0 && (
                    <Link href={`/tutorial/${job.job_id}`} style={{
                      padding:"8px 16px", borderRadius:10, fontSize:13, fontWeight:600,
                      background:"linear-gradient(135deg,#6366f1,#8b5cf6)",
                      color:"#fff", textDecoration:"none",
                      boxShadow:"0 2px 12px #6366f130",
                    }}>
                      View →
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
