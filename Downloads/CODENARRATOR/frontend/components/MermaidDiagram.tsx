"use client";

import { useEffect, useRef, useState } from "react";

interface Props { chart: string }

let _mermaidId = 0;

/** Strip characters that reliably break Mermaid's parser */
function sanitize(src: string): string {
  return src
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/[^\x09\x0A\x20-\x7E -￿]/g, " ")  // keep printable only
    .trim();
}

export default function MermaidDiagram({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError]     = useState("");
  const [ready, setReady]     = useState(false);

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      setError("");
      setReady(false);

      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "loose",
          fontFamily: "Inter, sans-serif",
          flowchart: { useMaxWidth: true, htmlLabels: true },
        });

        const clean = sanitize(chart);
        const id    = `mermaid-${++_mermaidId}`;

        const { svg } = await mermaid.render(id, clean);

        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setReady(true);
        }
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(msg.slice(0, 200));
        }
      }
    };

    render();
    return () => { cancelled = true; };
  }, [chart]);

  if (error) {
    return (
      <div style={{
        margin: "16px 0", padding: "14px 16px",
        borderRadius: 10, background: "#12080a",
        border: "1px solid #7f1d1d",
      }}>
        <p style={{ fontSize: 11, color: "#f87171", marginBottom: 8, fontWeight: 600 }}>
          ⚠ Mermaid diagram could not render
        </p>
        <pre style={{
          fontSize: 11, color: "#64748b", overflowX: "auto",
          fontFamily: "var(--mono)", whiteSpace: "pre-wrap", wordBreak: "break-word",
        }}>
          {chart.slice(0, 400)}
        </pre>
      </div>
    );
  }

  return (
    <div style={{ margin: "20px 0", textAlign: "center", overflowX: "auto" }}>
      {!ready && (
        <div style={{ height: 60, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: 12, color: "#475569" }}>Rendering diagram…</span>
        </div>
      )}
      <div
        ref={containerRef}
        style={{
          display: ready ? "block" : "none",
          maxWidth: "100%",
        }}
      />
    </div>
  );
}
