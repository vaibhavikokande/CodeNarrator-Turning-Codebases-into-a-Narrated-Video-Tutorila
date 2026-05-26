"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, GenerateRequest } from "@/lib/api";

const LANGUAGES = ["English","Spanish","French","German","Japanese","Chinese","Portuguese","Hindi","Arabic","Korean"];

// Each language maps to its best native neural voice
const LANG_VOICE_MAP: Record<string, { value: string; label: string }> = {
  English:    { value: "en-US-AriaNeural",    label: "Aria — US English" },
  Spanish:    { value: "es-ES-ElviraNeural",  label: "Elvira — Spanish" },
  French:     { value: "fr-FR-DeniseNeural",  label: "Denise — French" },
  German:     { value: "de-DE-KatjaNeural",   label: "Katja — German" },
  Japanese:   { value: "ja-JP-NanamiNeural",  label: "Nanami — Japanese" },
  Chinese:    { value: "zh-CN-XiaoxiaoNeural",label: "Xiaoxiao — Chinese" },
  Portuguese: { value: "pt-BR-FranciscaNeural", label: "Francisca — Portuguese" },
  Hindi:      { value: "hi-IN-SwaraNeural",   label: "Swara — Hindi" },
  Arabic:     { value: "ar-SA-ZariyahNeural", label: "Zariyah — Arabic" },
  Korean:     { value: "ko-KR-SunHiNeural",   label: "SunHi — Korean" },
};

const VOICES = Object.values(LANG_VOICE_MAP);

export default function RepoForm() {
  const router = useRouter();
  const [repoUrl, setRepoUrl]   = useState("");
  const [runVideo, setRunVideo] = useState(false);
  const [language, setLanguage] = useState("English");
  const [theme, setTheme]       = useState<"dark"|"light"|"cyberpunk">("dark");
  const [voice, setVoice]       = useState("en-US-AriaNeural");

  // Auto-switch voice whenever language changes
  const handleLanguageChange = (lang: string) => {
    setLanguage(lang);
    const mapped = LANG_VOICE_MAP[lang];
    if (mapped) setVoice(mapped.value);
  };
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [focused, setFocused]   = useState(false);
  const [ghLogin, setGhLogin]   = useState("");

  useEffect(() => {
    setGhLogin(localStorage.getItem("gh_login") ?? "");
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!repoUrl.trim())              { setError("Please enter a GitHub repository URL."); return; }
    if (!repoUrl.includes("github.com")) { setError("Please enter a valid GitHub URL (e.g. https://github.com/owner/repo)."); return; }
    setLoading(true);
    try {
      const ghToken = localStorage.getItem("gh_token") ?? undefined;
      const req: GenerateRequest = { repo_url: repoUrl.trim(), run_video: runVideo, language, theme, voice, github_token: ghToken };
      const { job_id } = await api.generate(req);
      router.push(`/generate?jobId=${job_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start. Is the backend running on :8000?");
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} style={{ display:"flex", flexDirection:"column", gap:20 }}>

      {/* Section label */}
      <div>
        <p style={{ fontSize:11, fontWeight:600, letterSpacing:"0.1em", color:"#64748b", textTransform:"uppercase", marginBottom:12 }}>
          Repository
        </p>

        {/* URL input */}
        <div style={{
          display:"flex", alignItems:"center", gap:10,
          background:"#08080f", borderRadius:12, padding:"0 14px",
          border: `1.5px solid ${focused ? "#6366f1" : "#252540"}`,
          boxShadow: focused ? "0 0 0 3px #6366f118" : "none",
          transition:"border-color .2s, box-shadow .2s",
        }}>
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" style={{ color:"#64748b", flexShrink:0 }}>
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93V18c0-.55.45-1 1-1s1 .45 1 1v1.93c-3.06-.45-5.48-2.87-5.93-5.93H9c.55 0 1 .45 1 1s-.45 1-1 1H7.07A8.007 8.007 0 0111 19.93z" fill="currentColor" opacity=".5"/>
            <path d="M10.59 6.59 12 8l1.41-1.41C13.79 6.21 14 5.7 14 5.17V3.07A9.994 9.994 0 0012 3c-.68 0-1.35.07-2 .19v2.04c0 .46.18.9.51 1.22z" fill="currentColor"/>
          </svg>
          <input
            type="text" value={repoUrl}
            onChange={e => setRepoUrl(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="https://github.com/owner/repo"
            style={{
              flex:1, background:"transparent", border:"none", outline:"none",
              padding:"13px 0", fontSize:14, fontFamily:"var(--mono)",
              color:"#e2e8f0",
            }}
            spellCheck={false}
          />
          {repoUrl && (
            <button type="button" onClick={() => setRepoUrl("")}
              style={{ background:"none", border:"none", cursor:"pointer", color:"#475569", fontSize:16, padding:"0 2px" }}>×</button>
          )}
        </div>
      </div>

      {/* Options row */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
        <Field label="🌐 Language">
          <StyledSelect value={language} onChange={handleLanguageChange}>
            {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
          </StyledSelect>
        </Field>
        <Field label="🎨 Theme">
          <StyledSelect value={theme} onChange={v => setTheme(v as "dark"|"light"|"cyberpunk")}>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
            <option value="cyberpunk">Cyberpunk</option>
          </StyledSelect>
        </Field>
      </div>

      <Field label="🎙️ TTS Voice">
        <StyledSelect value={voice} onChange={setVoice}>
          {VOICES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
        </StyledSelect>
      </Field>
      {language !== "English" && (
        <p style={{ fontSize:12, color:"#6366f1", marginTop:-10, marginBottom:0 }}>
          ✓ Native {language} voice auto-selected — narration will be in {language}
        </p>
      )}

      {/* Video toggle — fully clickable card */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setRunVideo(v => !v)}
        onKeyDown={e => (e.key === " " || e.key === "Enter") && setRunVideo(v => !v)}
        style={{
          display:"flex", alignItems:"center", gap:16,
          padding:"16px 18px", borderRadius:14, cursor:"pointer",
          background: runVideo ? "#6366f118" : "#0d0d1a",
          border: `2px solid ${runVideo ? "#6366f1" : "#252540"}`,
          transition:"all .2s", userSelect:"none",
          boxShadow: runVideo ? "0 0 0 3px #6366f122" : "none",
        }}
      >
        {/* Toggle knob */}
        <div style={{ position:"relative", flexShrink:0,
                      width:48, height:26, borderRadius:99,
                      background: runVideo ? "#6366f1" : "#1e1e35",
                      border:`2px solid ${runVideo ? "#818cf8" : "#3a3a55"}`,
                      transition:"background .25s, border-color .25s" }}>
          <div style={{
            position:"absolute", top:3, left: runVideo ? 24 : 3,
            width:16, height:16, borderRadius:"50%",
            background: runVideo ? "#fff" : "#94a3b8",
            boxShadow:"0 1px 4px #00000080",
            transition:"left .2s cubic-bezier(.34,1.56,.64,1), background .2s",
          }} />
        </div>

        {/* Text */}
        <div style={{ flex:1 }}>
          <p style={{ fontSize:14, fontWeight:600,
                      color: runVideo ? "#a5b4fc" : "#94a3b8",
                      margin:0, transition:"color .2s" }}>
            🎬 Generate narrated MP4 video
          </p>
          <p style={{ fontSize:11, color:"#475569", marginTop:3, margin:"3px 0 0" }}>
            Animated slides · Neural TTS · ~5–10 min
          </p>
        </div>

        {/* ON/OFF badge */}
        <span style={{
          fontSize:10, fontWeight:700, letterSpacing:"0.08em",
          padding:"3px 8px", borderRadius:6,
          background: runVideo ? "#6366f130" : "#1a1a30",
          color: runVideo ? "#818cf8" : "#475569",
          border:`1px solid ${runVideo ? "#6366f150" : "#2a2a40"}`,
          transition:"all .2s",
        }}>
          {runVideo ? "ON" : "OFF"}
        </span>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          display:"flex", alignItems:"flex-start", gap:10,
          padding:"12px 14px", borderRadius:10, fontSize:13,
          background:"#ef444410", border:"1px solid #ef444428", color:"#fca5a5",
        }}>
          <span style={{ flexShrink:0 }}>⚠</span> {error}
        </div>
      )}

      {/* Submit button */}
      <button type="submit" disabled={loading} style={{
        display:"flex", alignItems:"center", justifyContent:"center", gap:10,
        padding:"15px 24px", borderRadius:14, border:"none",
        fontSize:15, fontWeight:700, cursor: loading ? "not-allowed" : "pointer",
        color:"#fff", letterSpacing:"-0.01em",
        background: loading
          ? "#4338ca"
          : "linear-gradient(135deg, #6366f1 0%, #8b5cf6 60%, #7c3aed 100%)",
        boxShadow: loading ? "none" : "0 4px 24px #6366f140, inset 0 1px 0 #ffffff20",
        opacity: loading ? .8 : 1,
        transition:"all .2s",
        position:"relative", overflow:"hidden",
      }}>
        {/* Shimmer on idle */}
        {!loading && (
          <div style={{
            position:"absolute", inset:0,
            background:"linear-gradient(90deg, transparent 30%, #ffffff18 50%, transparent 70%)",
            backgroundSize:"200% 100%",
            animation:"shimmer 2.5s ease infinite",
          }} />
        )}
        {loading ? (
          <>
            <svg className="anim-spin" width="17" height="17" fill="none" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="#ffffff40" strokeWidth="3" />
              <path d="M12 2a10 10 0 0110 10" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
            </svg>
            Starting pipeline…
          </>
        ) : (
          <>✨ Generate Tutorial</>
        )}
      </button>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
      <label style={{ fontSize:11, fontWeight:600, letterSpacing:"0.08em", color:"#64748b", textTransform:"uppercase" }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function StyledSelect({ value, onChange, children }: { value:string; onChange:(v:string)=>void; children:React.ReactNode }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={{
      background:"#08080f", border:"1.5px solid #252540", borderRadius:10,
      padding:"11px 12px", fontSize:13, color:"#e2e8f0", cursor:"pointer",
      outline:"none", width:"100%", appearance:"auto",
    }}>
      {children}
    </select>
  );
}
