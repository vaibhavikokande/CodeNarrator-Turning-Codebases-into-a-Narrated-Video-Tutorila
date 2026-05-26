"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, AdminStats } from "@/lib/api";

function StatCard({ icon, label, value, color, sub }: {
  icon:string; label:string; value:string|number; color:string; sub?:string
}) {
  return (
    <div style={{
      borderRadius:16, padding:"22px 24px",
      background:`${color}0d`, border:`1px solid ${color}22`,
    }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
        <span style={{ fontSize:22 }}>{icon}</span>
        {sub && <span style={{ fontSize:11, color:"#475569", fontFamily:"var(--mono)" }}>{sub}</span>}
      </div>
      <div style={{ fontSize:30, fontWeight:800, color, fontFamily:"var(--mono)" }}>{value}</div>
      <div style={{ fontSize:12, color:"#64748b", marginTop:4 }}>{label}</div>
    </div>
  );
}

function KeyVal({ label, value, ok }: { label:string; value:string; ok?:boolean }) {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 0", borderBottom:"1px solid #141428" }}>
      <span style={{ fontSize:13, color:"#64748b" }}>{label}</span>
      <span style={{
        fontFamily:"var(--mono)", fontSize:12, padding:"3px 10px", borderRadius:7,
        background: ok===undefined ? "#1a1a30" : ok ? "#10b98115" : "#ef444415",
        color: ok===undefined ? "#94a3b8" : ok ? "#10b981" : "#ef4444",
        border:`1px solid ${ok===undefined ? "#252540" : ok ? "#10b98125" : "#ef444425"}`,
      }}>{value}</span>
    </div>
  );
}

export default function AdminPage() {
  const [stats,    setStats]    = useState<AdminStats | null>(null);
  const [provider, setProvider] = useState<Record<string,any> | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [clearing, setClearing] = useState(false);
  const [msg,      setMsg]      = useState("");

  const load = async () => {
    try {
      const [s, p] = await Promise.all([api.adminStats(), api.adminProvider()]);
      setStats(s);
      setProvider(p);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const clearCache = async () => {
    setClearing(true);
    try {
      const r = await api.adminClearCache();
      setMsg(r.message);
      await load();
      setTimeout(() => setMsg(""), 4000);
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    }
    setClearing(false);
  };

  return (
    <div style={{ minHeight:"100vh", background:"#07070f" }}>
      {/* Header */}
      <header style={{
        height:60, display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"0 28px", borderBottom:"1px solid #141428",
        background:"#07070fdd", backdropFilter:"blur(12px)",
        position:"sticky", top:0, zIndex:50,
      }}>
        <Link href="/" style={{ fontSize:13, fontWeight:500, color:"#64748b" }}>
          ← Code Narrator
        </Link>
        <span style={{ fontSize:15, fontWeight:700 }}>
          <span className="g-text">Admin Dashboard</span>
        </span>
        <button onClick={load} style={{
          fontSize:12, padding:"6px 14px", borderRadius:8,
          background:"#6366f115", border:"1px solid #6366f130",
          color:"#818cf8", cursor:"pointer", fontWeight:500,
        }}>↻ Refresh</button>
      </header>

      <main style={{ maxWidth:960, margin:"0 auto", padding:"40px 24px" }}>
        {loading ? (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14 }}>
            {[1,2,3,4].map(i => (
              <div key={i} className="skeleton" style={{ height:110, borderRadius:16 }} />
            ))}
          </div>
        ) : !stats ? (
          <div style={{ textAlign:"center", padding:80 }}>
            <p style={{ color:"#ef4444" }}>Could not reach backend</p>
            <p style={{ fontSize:12, color:"#64748b", marginTop:6 }}>Is the backend running on :8000?</p>
          </div>
        ) : (
          <>
            {/* Stats grid */}
            <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14, marginBottom:28 }}>
              <StatCard icon="📋" label="Total Jobs"     value={stats.total_jobs}     color="#6366f1" />
              <StatCard icon="✅" label="Completed"       value={stats.completed_jobs} color="#10b981" />
              <StatCard icon="⚡" label="Active Now"      value={stats.active_jobs}    color="#f59e0b" />
              <StatCard icon="❌" label="Failed"          value={stats.failed_jobs}    color="#ef4444" />
            </div>

            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:20, marginBottom:28 }}>
              {/* LLM Cache */}
              <div style={{ borderRadius:18, padding:"24px", background:"#0d0d1a", border:"1px solid #1a1a30" }}>
                <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:20 }}>
                  <h2 style={{ fontSize:15, fontWeight:700, color:"#e2e8f0", margin:0 }}>🧠 LLM Cache</h2>
                  <button onClick={clearCache} disabled={clearing} style={{
                    padding:"7px 16px", borderRadius:9, border:"1px solid #ef444430",
                    background:"#ef444410", color:"#f87171", cursor:clearing?"not-allowed":"pointer",
                    fontSize:12, fontWeight:600, opacity:clearing?.6:1,
                  }}>
                    {clearing ? "Clearing…" : "🗑 Clear Cache"}
                  </button>
                </div>
                <KeyVal label="Cached Entries"   value={`${stats.llm_cache.entries} responses`} />
                <KeyVal label="Cache Size"        value={`${stats.llm_cache.size_kb} KB`} />
                <KeyVal label="Active Provider"   value={stats.llm_cache.provider.toUpperCase()} />
                <KeyVal label="Output Store"      value={`${stats.output_dir_size_mb} MB`} />
                {msg && (
                  <div style={{ marginTop:14, padding:"10px 14px", borderRadius:10, fontSize:12,
                    background:"#10b98115", border:"1px solid #10b98125", color:"#34d399" }}>
                    {msg}
                  </div>
                )}
              </div>

              {/* Provider Config */}
              {provider && (
                <div style={{ borderRadius:18, padding:"24px", background:"#0d0d1a", border:"1px solid #1a1a30" }}>
                  <h2 style={{ fontSize:15, fontWeight:700, color:"#e2e8f0", marginBottom:20 }}>🔑 API Keys & Providers</h2>
                  <KeyVal label="LLM Provider"   value={provider.llm_provider_env?.toUpperCase()}   ok={undefined} />
                  <KeyVal label="TTS Provider"   value={provider.tts_provider_env?.toUpperCase()}   ok={undefined} />
                  <KeyVal label="Anthropic Key"  value={provider.has_anthropic_key  ? "✓ Set" : "✗ Missing"} ok={provider.has_anthropic_key} />
                  <KeyVal label="Gemini Key"     value={provider.has_gemini_key     ? "✓ Set" : "✗ Missing"} ok={provider.has_gemini_key} />
                  <KeyVal label="ElevenLabs Key" value={provider.has_elevenlabs_key ? "✓ Set" : "✗ Missing"} ok={provider.has_elevenlabs_key} />
                  <KeyVal label="GitHub Token"   value={provider.has_github_token   ? "✓ Set" : "○ Optional"} ok={provider.has_github_token} />
                </div>
              )}
            </div>

            {/* Quick links */}
            <div style={{ borderRadius:18, padding:"24px", background:"#0d0d1a", border:"1px solid #1a1a30" }}>
              <h2 style={{ fontSize:15, fontWeight:700, color:"#e2e8f0", marginBottom:18 }}>⚡ Quick Actions</h2>
              <div style={{ display:"flex", flexWrap:"wrap", gap:10 }}>
                {[
                  { label:"📚 View History",      href:"/history" },
                  { label:"🚀 Generate Tutorial", href:"/" },
                  { label:"📖 API Docs",          href:"http://localhost:8000/docs" },
                ].map(link => (
                  <a key={link.label} href={link.href} target={link.href.startsWith("http") ? "_blank" : undefined}
                    style={{
                      padding:"10px 20px", borderRadius:12, fontSize:13, fontWeight:600,
                      background:"#6366f115", border:"1px solid #6366f130",
                      color:"#818cf8", textDecoration:"none",
                      transition:"all .15s",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background="#6366f125")}
                    onMouseLeave={e => (e.currentTarget.style.background="#6366f115")}
                  >
                    {link.label}
                  </a>
                ))}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
