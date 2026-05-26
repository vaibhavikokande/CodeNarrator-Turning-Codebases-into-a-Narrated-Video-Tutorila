"use client";
import { useEffect, useState } from "react";
import RepoForm from "@/components/RepoForm";
import Link from "next/link";
import { api } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";

export default function Home() {
  const [ghLogin,  setGhLogin]  = useState("");
  const [ghAvatar, setGhAvatar] = useState("");

  useEffect(() => {
    const login  = localStorage.getItem("gh_login")  ?? "";
    const avatar = localStorage.getItem("gh_avatar") ?? "";
    if (login) { setGhLogin(login); setGhAvatar(avatar); }
  }, []);

  const logout = () => {
    localStorage.removeItem("gh_token");
    localStorage.removeItem("gh_login");
    localStorage.removeItem("gh_avatar");
    setGhLogin(""); setGhAvatar("");
  };

  return (
    <main style={{
      minHeight: "100vh",
      background: "radial-gradient(ellipse 80% 60% at 50% -10%, #1a1040 0%, #07070f 60%)",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "60px 20px", position: "relative", overflow: "hidden",
    }}>

      {/* Nav bar */}
      <nav style={{
        position:"fixed", top:0, left:0, right:0, zIndex:50,
        display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"14px 28px", background:"#07070fcc", backdropFilter:"blur(12px)",
        borderBottom:"1px solid #141428",
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontSize:14, fontWeight:800, letterSpacing:"-0.02em" }}>
            <span className="g-text">CodeNarrator</span>
          </span>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
          {[
            { label:"History", href:"/history", icon:"📚" },
            { label:"Admin",   href:"/admin",   icon:"⚙️" },
          ].map(link => (
            <Link key={link.label} href={link.href} style={{
              display:"flex", alignItems:"center", gap:5, padding:"6px 14px", borderRadius:9,
              fontSize:12, fontWeight:500, color:"#64748b", textDecoration:"none",
              background:"transparent", border:"1px solid transparent", transition:"all .15s",
            }}
            onMouseEnter={(e:any) => { e.currentTarget.style.color="#a5b4fc"; e.currentTarget.style.borderColor="#6366f130"; e.currentTarget.style.background="#6366f110"; }}
            onMouseLeave={(e:any) => { e.currentTarget.style.color="#64748b"; e.currentTarget.style.borderColor="transparent"; e.currentTarget.style.background="transparent"; }}>
              {link.icon} {link.label}
            </Link>
          ))}

          {/* GitHub login / user */}
          {/* Feature 5: Theme toggle — additive, one component */}
          <ThemeToggle />

          {ghLogin ? (
            <div style={{ display:"flex", alignItems:"center", gap:8, marginLeft:6 }}>
              {ghAvatar && <img src={ghAvatar} alt={ghLogin} style={{ width:26, height:26, borderRadius:"50%", border:"1px solid #6366f150" }} />}
              <span style={{ fontSize:12, color:"#a5b4fc", fontWeight:500 }}>@{ghLogin}</span>
              <button onClick={logout} style={{
                fontSize:11, color:"#64748b", background:"transparent", border:"1px solid #1a1a30",
                borderRadius:7, padding:"4px 10px", cursor:"pointer",
              }}>Logout</button>
            </div>
          ) : (
            <a href={api.githubLoginUrl()} style={{
              display:"flex", alignItems:"center", gap:6, padding:"6px 14px", borderRadius:9,
              fontSize:12, fontWeight:600, color:"#e2e8f0", textDecoration:"none",
              background:"linear-gradient(135deg,#24292e,#1a1a2e)", border:"1px solid #30363d",
              marginLeft:6, transition:"all .15s",
            }}
            onMouseEnter={(e:any) => { e.currentTarget.style.borderColor="#6366f180"; }}
            onMouseLeave={(e:any) => { e.currentTarget.style.borderColor="#30363d"; }}>
              <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
                  0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52
                  -.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2
                  -3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64
                  -.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12
                  .51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01
                  1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
              </svg>
              Login with GitHub
            </a>
          )}
        </div>
      </nav>

      {/* Background grid */}
      <div style={{
        position:"absolute", inset:0, pointerEvents:"none",
        backgroundImage:"linear-gradient(rgba(99,102,241,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,.06) 1px, transparent 1px)",
        backgroundSize:"64px 64px",
      }} />

      {/* Glow orbs */}
      <div style={{ position:"absolute", top:-120, left:"15%", width:500, height:500, borderRadius:"50%", background:"radial-gradient(circle, #6366f130, transparent 70%)", filter:"blur(80px)", pointerEvents:"none" }} />
      <div style={{ position:"absolute", bottom:-100, right:"10%", width:400, height:400, borderRadius:"50%", background:"radial-gradient(circle, #8b5cf620, transparent 70%)", filter:"blur(80px)", pointerEvents:"none" }} />
      <div style={{ position:"absolute", top:"40%", left:"5%", width:300, height:300, borderRadius:"50%", background:"radial-gradient(circle, #06b6d415, transparent 70%)", filter:"blur(60px)", pointerEvents:"none" }} />

      {/* Content */}
      <div className="anim-fade-up" style={{ position:"relative", zIndex:1, width:"100%", maxWidth:640, display:"flex", flexDirection:"column", alignItems:"center", paddingTop:40 }}>

        {/* Status badge */}
        <div style={{ display:"inline-flex", alignItems:"center", gap:8, padding:"6px 16px", borderRadius:99, background:"#6366f112", border:"1px solid #6366f128", fontSize:12, fontWeight:500, color:"#a5b4fc", marginBottom:28 }}>
          <span className="anim-pulse" style={{ display:"inline-block", width:7, height:7, borderRadius:"50%", background:"#4ade80" }} />
          Gemini 2.5 Flash · ElevenLabs TTS · FastAPI · Next.js
        </div>

        {/* Title */}
        <h1 style={{ fontSize:"clamp(2.8rem,6vw,4.2rem)", fontWeight:900, textAlign:"center", lineHeight:1.08, marginBottom:18, letterSpacing:"-0.03em" }}>
          <span className="g-text">Code Narrator</span>
        </h1>

        <p style={{ textAlign:"center", fontSize:"1.1rem", color:"#94a3b8", lineHeight:1.75, maxWidth:520, marginBottom:36 }}>
          Transform any GitHub repository into a structured, chapter-based tutorial
          with architecture diagrams — and optionally a narrated MP4 video walkthrough.
        </p>

        {/* Feature pills */}
        <div style={{ display:"flex", flexWrap:"wrap", justifyContent:"center", gap:8, marginBottom:40 }}>
          {[
            ["📖","Chapter Tutorials"],["🗺️","Architecture Diagrams"],["🎬","Video Narration"],
            ["🌐","Multi-Language"],["⚡","Gemini AI"],["🤖","AI Chatbot"],
            ["🔍","Search"],["📄","PDF Export"],["🎯","Chapter Quizzes"],
            ["📓","Notion Export"],["📘","Confluence Export"],["🔐","Private Repos"],
          ].map(([icon, lbl]) => (
            <span key={lbl} style={{
              display:"inline-flex", alignItems:"center", gap:6, padding:"5px 14px",
              borderRadius:99, fontSize:12, fontWeight:500,
              background:"#ffffff06", border:"1px solid #ffffff0f", color:"#94a3b8",
            }}>
              {icon} {lbl}
            </span>
          ))}
        </div>

        {/* Form card */}
        <div style={{
          width:"100%", borderRadius:24, padding:"36px 40px",
          background:"linear-gradient(145deg, #12122080, #0d0d1a)",
          border:"1px solid #252540",
          boxShadow:"0 0 0 1px #ffffff06, 0 32px 64px -16px #00000060, 0 0 80px #6366f108",
          backdropFilter:"blur(20px)",
        }}>
          <RepoForm />
        </div>

        <p style={{ marginTop:24, fontSize:12, color:"#3d4a5c", textAlign:"center" }}>
          {ghLogin
            ? `Signed in as @${ghLogin} · Private repositories enabled`
            : "Public repos work without login · Login with GitHub to access private repos"}
        </p>
      </div>
    </main>
  );
}
