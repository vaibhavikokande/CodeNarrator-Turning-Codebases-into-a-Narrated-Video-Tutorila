"use client";
import { BASE_URL } from "@/lib/api";
/**
 * AvatarPanel — Talking Avatar feature (ADDITIVE, standalone component).
 *
 * Shown below the VideoPlayer after a video is generated.
 * Lets users add a D-ID or HeyGen talking-head overlay to their video.
 * Does NOT touch any existing component or pipeline logic.
 */

import { useState } from "react";

interface Props {
  jobId: string;
  hasVideo: boolean;
}

type Provider = "did" | "heygen";
type Status   = "idle" | "loading" | "success" | "error";

const POSITIONS = ["bottomright", "bottomleft", "topright", "topleft"] as const;

export default function AvatarPanel({ jobId, hasVideo }: Props) {
  const [open,      setOpen]      = useState(false);
  const [provider,  setProvider]  = useState<Provider>("did");
  const [apiKey,    setApiKey]    = useState("");
  const [position,  setPosition]  = useState<typeof POSITIONS[number]>("bottomright");
  const [status,    setStatus]    = useState<Status>("idle");
  const [error,     setError]     = useState("");
  const [outputUrl, setOutputUrl] = useState("");

  if (!hasVideo) return null;   // only show when a video exists

  const apply = async () => {
    if (!apiKey.trim()) { setError("Please enter your API key."); return; }
    setStatus("loading");
    setError("");
    try {
      const resp = await fetch(`${BASE_URL}/api/jobs/${jobId}/avatar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: apiKey, position }),
      });
      const data = await resp.json();
      if (data.success) {
        setStatus("success");
        setOutputUrl(`${BASE_URL}/api/jobs/${jobId}/file/tutorial_with_avatar.mp4`);
      } else {
        setStatus("error");
        setError(data.error ?? "Avatar generation failed.");
      }
    } catch (e: unknown) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "Network error.");
    }
  };

  return (
    <div style={{ marginTop: 24 }}>
      {/* Collapsed trigger button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "10px 20px", borderRadius: 12,
            background: "#141428", border: "1px solid #252550",
            color: "#94a3b8", cursor: "pointer", fontSize: 13, fontWeight: 500,
            transition: "all .15s",
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = "#6366f150"; e.currentTarget.style.color = "#a5b4fc"; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = "#252550";   e.currentTarget.style.color = "#94a3b8"; }}
        >
          🤖 Add Talking Avatar
        </button>
      )}

      {/* Expanded panel */}
      {open && (
        <div style={{
          borderRadius: 16, padding: "22px 24px",
          background: "#0d0d1a", border: "1px solid #252540",
          display: "flex", flexDirection: "column", gap: 16,
        }}>
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#e2e8f0" }}>
              🤖 Talking Avatar Overlay
            </span>
            <button onClick={() => setOpen(false)}
              style={{ background: "none", border: "none", color: "#475569", cursor: "pointer", fontSize: 18 }}>
              ×
            </button>
          </div>

          <p style={{ fontSize: 12, color: "#64748b", margin: 0, lineHeight: 1.6 }}>
            Generate a talking-head avatar from your tutorial narration and overlay it
            in the corner of your video. Requires a D-ID or HeyGen API key.
          </p>

          {/* Provider selector */}
          <div>
            <label style={labelStyle}>Provider</label>
            <div style={{ display: "flex", gap: 8 }}>
              {(["did", "heygen"] as Provider[]).map(p => (
                <button key={p} onClick={() => setProvider(p)} style={{
                  padding: "7px 16px", borderRadius: 9, cursor: "pointer",
                  fontSize: 12, fontWeight: 600, border: "1px solid",
                  background:   provider === p ? "#6366f118" : "#141428",
                  borderColor:  provider === p ? "#6366f1"   : "#252540",
                  color:        provider === p ? "#a5b4fc"   : "#64748b",
                  transition: "all .15s",
                }}>
                  {p === "did" ? "D-ID" : "HeyGen"}
                </button>
              ))}
            </div>
          </div>

          {/* API Key */}
          <div>
            <label style={labelStyle}>
              {provider === "did" ? "D-ID API Key" : "HeyGen API Key"}
              <a
                href={provider === "did"
                  ? "https://studio.d-id.com/account-settings"
                  : "https://app.heygen.com/settings?nav=API"}
                target="_blank" rel="noreferrer"
                style={{ marginLeft: 8, fontSize: 11, color: "#6366f1" }}>
                Get key ↗
              </a>
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={`Paste your ${provider === "did" ? "D-ID" : "HeyGen"} API key`}
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 10,
                background: "#08080f", border: "1.5px solid #252540",
                color: "#e2e8f0", fontSize: 13, outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>

          {/* Position */}
          <div>
            <label style={labelStyle}>Avatar Position</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {POSITIONS.map(pos => (
                <button key={pos} onClick={() => setPosition(pos)} style={{
                  padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                  fontSize: 11, fontWeight: 500, border: "1px solid",
                  background:  position === pos ? "#6366f118" : "#141428",
                  borderColor: position === pos ? "#6366f1"   : "#252540",
                  color:       position === pos ? "#a5b4fc"   : "#64748b",
                  transition: "all .15s",
                }}>
                  {pos}
                </button>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{ padding: "10px 14px", borderRadius: 9, background: "#ef444412",
              border: "1px solid #ef444430", color: "#fca5a5", fontSize: 12 }}>
              ⚠ {error}
            </div>
          )}

          {/* Success */}
          {status === "success" && outputUrl && (
            <div style={{ padding: "12px 16px", borderRadius: 10, background: "#22c55e12",
              border: "1px solid #22c55e30", display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{ fontSize: 13, color: "#4ade80", fontWeight: 600 }}>
                ✅ Avatar video ready!
              </span>
              <a href={outputUrl} download="tutorial_with_avatar.mp4" style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "8px 16px", borderRadius: 9, fontSize: 12, fontWeight: 600,
                background: "#22c55e20", border: "1px solid #22c55e40",
                color: "#4ade80", textDecoration: "none", width: "fit-content",
              }}>
                ⬇ Download video with avatar
              </a>
            </div>
          )}

          {/* Apply button */}
          {status !== "success" && (
            <button
              onClick={apply}
              disabled={status === "loading"}
              style={{
                padding: "12px 20px", borderRadius: 12, border: "none",
                fontSize: 13, fontWeight: 700, cursor: status === "loading" ? "not-allowed" : "pointer",
                color: "#fff", opacity: status === "loading" ? 0.7 : 1,
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                boxShadow: "0 4px 16px #6366f130",
              }}
            >
              {status === "loading"
                ? "⏳ Generating avatar… (this takes 2–5 min)"
                : "✨ Generate & Overlay Avatar"}
            </button>
          )}

          <p style={{ fontSize: 11, color: "#3d4a5c", margin: 0 }}>
            💡 The original <code style={{ color: "#6366f1" }}>tutorial.mp4</code> is never modified.
            The avatar version is saved as <code style={{ color: "#6366f1" }}>tutorial_with_avatar.mp4</code>.
          </p>
        </div>
      )}
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: "block", fontSize: 11, fontWeight: 600,
  color: "#64748b", textTransform: "uppercase",
  letterSpacing: "0.08em", marginBottom: 6,
};
