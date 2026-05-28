"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

interface Msg { role: "user" | "bot"; text: string }

interface Props {
  jobId: string;
  contextFile?: string | null;
}

export default function ChatBot({ jobId, contextFile }: Props) {
  const [open,    setOpen]    = useState(false);
  const [msgs,    setMsgs]    = useState<Msg[]>([
    { role:"bot", text:"👋 Hi! I'm your CodeNarrator assistant. Ask me anything about this tutorial or the code." }
  ]);
  const [input,   setInput]   = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior:"smooth" });
  }, [msgs]);

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
  }, [open]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMsgs(p => [...p, { role:"user", text }]);
    setLoading(true);
    try {
      const r = await api.chat(jobId, text, contextFile ?? undefined);
      setMsgs(p => [...p, { role:"bot", text: r.reply }]);
    } catch (e: any) {
      const raw = e.message ?? "";
      let friendly = `⚠️ ${raw}`;
      if (raw.includes("not found") || raw.includes("404")) {
        friendly = "⚠️ This tutorial was not found on the server. It may have been generated on a different machine or the server restarted. Please regenerate the tutorial from the home page.";
      } else if (raw.includes("500") || raw.includes("failed")) {
        friendly = "⚠️ The AI assistant hit an error. Please try again in a moment.";
      } else if (raw.includes("fetch") || raw.includes("network")) {
        friendly = "⚠️ Cannot reach the backend. Make sure the server is running.";
      }
      setMsgs(p => [...p, { role:"bot", text: friendly }]);
    }
    setLoading(false);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          position:"fixed", bottom:24, right:24, zIndex:200,
          width:56, height:56, borderRadius:"50%", border:"none",
          background:"linear-gradient(135deg,#6366f1,#8b5cf6)",
          boxShadow: open
            ? "0 0 0 4px #6366f140, 0 8px 32px #6366f160"
            : "0 4px 20px #6366f150",
          cursor:"pointer", fontSize:22,
          display:"flex", alignItems:"center", justifyContent:"center",
          transition:"all .25s cubic-bezier(.34,1.56,.64,1)",
          transform: open ? "rotate(0deg) scale(1.05)" : "scale(1)",
        }}
        title={open ? "Close chat" : "Ask CodeNarrator AI"}
      >
        {open ? "✕" : "🤖"}
      </button>

      {/* Chat panel */}
      {open && (
        <div style={{
          position:"fixed", bottom:92, right:24, zIndex:199,
          width:370, height:500, borderRadius:20,
          background:"#0d0d1a", border:"1px solid #252540",
          boxShadow:"0 20px 60px #00000080, 0 0 0 1px #ffffff06",
          display:"flex", flexDirection:"column", overflow:"hidden",
          animation:"slideUp .2s ease",
        }}>
          {/* Header */}
          <div style={{
            padding:"14px 18px", borderBottom:"1px solid #141428",
            background:"linear-gradient(135deg,#6366f115,#8b5cf610)",
            display:"flex", alignItems:"center", gap:10,
          }}>
            <div style={{
              width:34, height:34, borderRadius:10,
              background:"linear-gradient(135deg,#6366f1,#8b5cf6)",
              display:"flex", alignItems:"center", justifyContent:"center",
              fontSize:16, flexShrink:0,
            }}>🤖</div>
            <div>
              <p style={{ fontSize:13, fontWeight:700, color:"#e2e8f0", margin:0 }}>CodeNarrator AI</p>
              <p style={{ fontSize:10, color:"#64748b", margin:0 }}>
                Powered by Claude · {contextFile ? `Context: ${contextFile.replace(".md","")}` : "Full tutorial context"}
              </p>
            </div>
            <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:5 }}>
              <div style={{ width:6, height:6, borderRadius:"50%", background:"#10b981" }} />
              <span style={{ fontSize:10, color:"#10b981" }}>online</span>
            </div>
          </div>

          {/* Messages */}
          <div style={{
            flex:1, overflowY:"auto", padding:"14px 16px",
            display:"flex", flexDirection:"column", gap:10,
          }}>
            {msgs.map((m, i) => (
              <div key={i} style={{
                display:"flex",
                justifyContent: m.role === "user" ? "flex-end" : "flex-start",
              }}>
                <div style={{
                  maxWidth:"82%", padding:"10px 14px", borderRadius:14,
                  borderBottomRightRadius: m.role==="user" ? 4 : 14,
                  borderBottomLeftRadius: m.role==="bot" ? 4 : 14,
                  fontSize:13, lineHeight:1.55,
                  background: m.role==="user"
                    ? "linear-gradient(135deg,#6366f1,#8b5cf6)"
                    : "#141428",
                  color: m.role==="user" ? "#fff" : "#e2e8f0",
                  border: m.role==="bot" ? "1px solid #1e1e35" : "none",
                  boxShadow: m.role==="user" ? "0 2px 12px #6366f130" : "none",
                  whiteSpace:"pre-wrap",
                }}>
                  {m.text}
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display:"flex", gap:5, padding:"8px 14px" }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{
                    width:7, height:7, borderRadius:"50%", background:"#6366f1",
                    animation:`bounce 1s ease ${i*0.15}s infinite`,
                  }} />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input row */}
          <div style={{
            padding:"10px 12px", borderTop:"1px solid #141428",
            display:"flex", gap:8, alignItems:"center",
            background:"#09090f",
          }}>
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask about the code…"
              disabled={loading}
              style={{
                flex:1, background:"#141428", border:"1px solid #252540",
                borderRadius:10, padding:"9px 13px", fontSize:13, color:"#e2e8f0",
                outline:"none", transition:"border-color .15s",
              }}
              onFocus={e => (e.target.style.borderColor="#6366f1")}
              onBlur={e => (e.target.style.borderColor="#252540")}
            />
            <button
              onClick={send}
              disabled={!input.trim() || loading}
              style={{
                width:38, height:38, borderRadius:10, border:"none",
                background: input.trim() && !loading
                  ? "linear-gradient(135deg,#6366f1,#8b5cf6)"
                  : "#1a1a30",
                color: input.trim() && !loading ? "#fff" : "#475569",
                cursor: input.trim() && !loading ? "pointer" : "not-allowed",
                fontSize:16, display:"flex", alignItems:"center", justifyContent:"center",
                flexShrink:0, transition:"all .15s",
              }}
            >
              ➤
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes slideUp {
          from { opacity:0; transform:translateY(16px) scale(.97); }
          to   { opacity:1; transform:translateY(0) scale(1); }
        }
        @keyframes bounce {
          0%,80%,100% { transform:translateY(0); }
          40%          { transform:translateY(-6px); }
        }
      `}</style>
    </>
  );
}
