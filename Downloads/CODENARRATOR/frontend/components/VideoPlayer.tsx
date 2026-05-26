"use client";

import { useRef, useState } from "react";

interface Props { src: string }

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

export default function VideoPlayer({ src }: Props) {
  const ref  = useRef<HTMLVideoElement>(null);
  const [speed, setSpeed]   = useState(1);
  const [bri,   setBri]     = useState(100);
  const [con,   setCon]     = useState(100);
  const [sat,   setSat]     = useState(100);
  const [mini,  setMini]    = useState(false);

  const applySpeed = (s: number) => { setSpeed(s); if (ref.current) ref.current.playbackRate = s; };
  const filter     = { filter:`brightness(${bri}%) contrast(${con}%) saturate(${sat}%)` };

  if (mini) return (
    <div style={{
      position:"fixed", bottom:20, right:20, zIndex:100,
      width:300, borderRadius:16, overflow:"hidden",
      border:"1px solid #252540", background:"#0d0d1a",
      boxShadow:"0 20px 60px #00000080",
    }}>
      <video ref={ref} src={src} controls style={{ ...filter, width:"100%", display:"block" }} />
      <button onClick={() => setMini(false)} style={{
        position:"absolute", top:8, right:8,
        background:"#00000090", border:"1px solid #ffffff20",
        color:"#fff", borderRadius:7, padding:"3px 9px",
        fontSize:11, cursor:"pointer", fontWeight:500,
      }}>⊡ Expand</button>
    </div>
  );

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
      <div style={{ position:"relative", borderRadius:16, overflow:"hidden", background:"#000", border:"1px solid #141428" }}>
        {/* paddingTop 56.25% = 9/16 — forces a true 16:9 container so the full
            1920×1080 frame is always visible without any cropping */}
        <div style={{ position:"relative", paddingTop:"56.25%", width:"100%" }}>
          <video
            ref={ref}
            src={src}
            controls
            style={{
              ...filter,
              position:"absolute", top:0, left:0,
              width:"100%", height:"100%",
              display:"block",
              objectFit:"contain",
            }}
          />
        </div>
        <button onClick={() => setMini(true)} style={{
          position:"absolute", top:12, right:12,
          background:"#00000080", border:"1px solid #ffffff18",
          color:"#e2e8f0", borderRadius:9, padding:"5px 12px",
          fontSize:11, cursor:"pointer", fontWeight:500,
          backdropFilter:"blur(6px)",
        }}>⊡ Mini-player</button>
      </div>

      <div style={{ borderRadius:14, padding:"16px 18px", background:"#0d0d1a", border:"1px solid #1a1a30" }}>
        {/* Speed */}
        <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14 }}>
          <span style={{ fontSize:12, color:"#64748b", width:80, flexShrink:0 }}>⏩ Speed</span>
          <div style={{ display:"flex", gap:6 }}>
            {SPEEDS.map(s => (
              <button key={s} onClick={() => applySpeed(s)} style={{
                padding:"5px 11px", borderRadius:8, cursor:"pointer",
                fontSize:12, fontFamily:"var(--mono)", fontWeight:600,
                background: speed === s ? "#6366f1" : "#141428",
                color:       speed === s ? "#fff"    : "#64748b",
                border:`1px solid ${speed === s ? "#6366f1" : "#252540"}`,
                transition:"all .15s",
              }}>{s}×</button>
            ))}
          </div>
        </div>
        <Slider emoji="☀️" label="Brightness" value={bri} min={50}  max={150} onChange={setBri} />
        <Slider emoji="◑"  label="Contrast"   value={con} min={50}  max={150} onChange={setCon} />
        <Slider emoji="🎨" label="Saturation"  value={sat} min={0}   max={200} onChange={setSat} />
      </div>
    </div>
  );
}

function Slider({ emoji, label, value, min, max, onChange }: {
  emoji:string; label:string; value:number; min:number; max:number; onChange:(v:number)=>void;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:10 }}>
      <span style={{ fontSize:12, color:"#64748b", width:80, flexShrink:0 }}>{emoji} {label}</span>
      <div style={{ flex:1, position:"relative", height:4, borderRadius:99, background:"#1a1a30" }}>
        <div style={{ position:"absolute", inset:"0", borderRadius:99, width:`${pct}%`, background:"linear-gradient(90deg,#6366f1,#8b5cf6)" }} />
        <input type="range" min={min} max={max} value={value}
          onChange={e => onChange(Number(e.target.value))}
          style={{ position:"absolute", inset:"-6px 0", width:"100%", opacity:0, cursor:"pointer", height:16 }} />
      </div>
      <span style={{ fontSize:11, color:"#94a3b8", fontFamily:"var(--mono)", width:34, textAlign:"right" }}>{value}%</span>
    </div>
  );
}
