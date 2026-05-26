"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import StatusTracker from "@/components/StatusTracker";
import Link from "next/link";

function Content() {
  const params = useSearchParams();
  const jobId  = params.get("jobId");

  if (!jobId) return (
    <div style={{ textAlign:"center" }}>
      <p style={{ color:"#ef4444", marginBottom:12 }}>No job ID provided.</p>
      <Link href="/" style={{ color:"#818cf8", textDecoration:"underline" }}>← Back to home</Link>
    </div>
  );

  return <StatusTracker jobId={jobId} />;
}

export default function GeneratePage() {
  return (
    <div style={{ minHeight:"100vh", background:"radial-gradient(ellipse 70% 50% at 50% 0%, #100c2a, #07070f 55%)" }}>
      {/* Nav */}
      <header style={{
        display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"14px 28px", borderBottom:"1px solid #141428",
        background:"#07070fcc", backdropFilter:"blur(12px)",
        position:"sticky", top:0, zIndex:50,
      }}>
        <Link href="/" style={{
          display:"flex", alignItems:"center", gap:8,
          fontSize:13, fontWeight:500, color:"#64748b",
          transition:"color .15s",
        }}
        onMouseEnter={e => (e.currentTarget.style.color="#a5b4fc")}
        onMouseLeave={e => (e.currentTarget.style.color="#64748b")}>
          ← Code Narrator
        </Link>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <div className="anim-pulse" style={{ width:7, height:7, borderRadius:"50%", background:"#6366f1" }} />
          <span style={{ fontSize:13, fontWeight:600, color:"#a5b4fc" }}>Generating Tutorial</span>
        </div>
        <div style={{ width:120 }} />
      </header>

      <main style={{ display:"flex", justifyContent:"center", padding:"40px 20px" }}>
        <Suspense fallback={
          <div style={{ display:"flex", alignItems:"center", gap:10, color:"#64748b" }}>
            <svg className="anim-spin" width="18" height="18" fill="none" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="#ffffff20" strokeWidth="3"/>
              <path d="M12 2a10 10 0 0110 10" stroke="#6366f1" strokeWidth="3" strokeLinecap="round"/>
            </svg>
            Loading…
          </div>
        }>
          <Content />
        </Suspense>
      </main>
    </div>
  );
}
