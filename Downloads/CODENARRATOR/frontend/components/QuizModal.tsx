"use client";
import { useState } from "react";
import { api, QuizQuestion } from "@/lib/api";

interface Props { jobId: string; chapter: string; onClose: () => void }

export default function QuizModal({ jobId, chapter, onClose }: Props) {
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");
  const [current,   setCurrent]   = useState(0);
  const [selected,  setSelected]  = useState<number|null>(null);
  const [answered,  setAnswered]  = useState(false);
  const [score,     setScore]     = useState(0);
  const [done,      setDone]      = useState(false);

  const chapterLabel = chapter.replace(/^\d+_/, "").replace(/\.md$/, "").replace(/_/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());

  const start = async () => {
    setLoading(true); setError("");
    try {
      const res = await api.getQuiz(jobId, chapter);
      setQuestions(res.questions);
      setCurrent(0); setScore(0); setSelected(null); setAnswered(false); setDone(false);
    } catch (e: any) {
      setError(e.message ?? "Failed to generate quiz");
    } finally { setLoading(false); }
  };

  const pick = (idx: number) => {
    if (answered) return;
    setSelected(idx);
    setAnswered(true);
    if (idx === questions[current].correct) setScore(s => s + 1);
  };

  const next = () => {
    if (current + 1 >= questions.length) { setDone(true); return; }
    setCurrent(c => c + 1); setSelected(null); setAnswered(false);
  };

  const q = questions[current];

  return (
    <div style={{ position:"fixed", inset:0, zIndex:200, background:"#00000090", display:"flex",
      alignItems:"center", justifyContent:"center", padding:20 }} onClick={e => { if (e.target===e.currentTarget) onClose(); }}>
      <div style={{ width:"100%", maxWidth:560, background:"#12122a", border:"1px solid #2d2d50",
        borderRadius:20, padding:"32px 36px", boxShadow:"0 24px 64px #00000080", position:"relative" }}>

        {/* Header */}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:24 }}>
          <div>
            <h2 style={{ margin:0, fontSize:18, fontWeight:700, color:"#e2e8f0" }}>🎯 Chapter Quiz</h2>
            <p style={{ margin:"4px 0 0", fontSize:13, color:"#64748b" }}>{chapterLabel}</p>
          </div>
          <button onClick={onClose} style={{ background:"none", border:"none", color:"#64748b",
            fontSize:20, cursor:"pointer", lineHeight:1, padding:"2px 6px" }}>✕</button>
        </div>

        {/* Idle state */}
        {questions.length === 0 && !loading && !error && (
          <div style={{ textAlign:"center", padding:"24px 0" }}>
            <div style={{ fontSize:48, marginBottom:16 }}>🧠</div>
            <p style={{ color:"#94a3b8", marginBottom:24, lineHeight:1.6 }}>
              Generate 5 multiple-choice questions based on this chapter to test your understanding.
            </p>
            <button onClick={start} style={{ background:"linear-gradient(135deg,#6366f1,#8b5cf6)",
              color:"#fff", border:"none", borderRadius:10, padding:"12px 28px",
              fontSize:15, fontWeight:600, cursor:"pointer" }}>
              Generate Quiz
            </button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{ textAlign:"center", padding:"32px 0", color:"#a5b4fc" }}>
            <div style={{ fontSize:32, marginBottom:12 }}>⚙️</div>
            <p>Generating questions with AI…</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ background:"#2d1b1b", border:"1px solid #7f1d1d", borderRadius:10,
            padding:"16px 20px", color:"#fca5a5", marginBottom:20 }}>
            {error}
            <button onClick={start} style={{ display:"block", marginTop:12, background:"#7f1d1d",
              color:"#fff", border:"none", borderRadius:8, padding:"8px 16px", cursor:"pointer", fontSize:13 }}>
              Retry
            </button>
          </div>
        )}

        {/* Done screen */}
        {done && (
          <div style={{ textAlign:"center", padding:"16px 0" }}>
            <div style={{ fontSize:52, marginBottom:12 }}>{score >= 4 ? "🏆" : score >= 2 ? "👍" : "📚"}</div>
            <h3 style={{ color:"#e2e8f0", fontSize:22, margin:"0 0 8px" }}>
              {score} / {questions.length} correct
            </h3>
            <p style={{ color:"#94a3b8", marginBottom:24 }}>
              {score === questions.length ? "Perfect score! 🎉" : score >= 3 ? "Great job!" : "Keep reading and try again!"}
            </p>
            <div style={{ display:"flex", gap:12, justifyContent:"center" }}>
              <button onClick={start} style={{ background:"#1e1b4b", color:"#a5b4fc", border:"1px solid #4338ca",
                borderRadius:10, padding:"10px 22px", cursor:"pointer", fontSize:14 }}>
                Retry Quiz
              </button>
              <button onClick={onClose} style={{ background:"linear-gradient(135deg,#6366f1,#8b5cf6)",
                color:"#fff", border:"none", borderRadius:10, padding:"10px 22px", cursor:"pointer", fontSize:14 }}>
                Back to Tutorial
              </button>
            </div>
          </div>
        )}

        {/* Active question */}
        {!done && q && (
          <>
            {/* Progress bar */}
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:20 }}>
              <div style={{ flex:1, height:4, background:"#1e1b4b", borderRadius:99 }}>
                <div style={{ height:"100%", borderRadius:99, width:`${((current)/questions.length)*100}%`,
                  background:"linear-gradient(90deg,#6366f1,#8b5cf6)", transition:"width .3s" }} />
              </div>
              <span style={{ fontSize:12, color:"#64748b", whiteSpace:"nowrap" }}>
                {current+1} / {questions.length}
              </span>
            </div>

            {/* Question */}
            <p style={{ color:"#e2e8f0", fontSize:16, fontWeight:500, lineHeight:1.6, marginBottom:20 }}>
              {q.question}
            </p>

            {/* Options */}
            <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
              {q.options.map((opt, i) => {
                const isCorrect  = i === q.correct;
                const isSelected = i === selected;
                let bg = "#1a1a3a", border = "#2d2d50", color = "#cbd5e1";
                if (answered) {
                  if (isCorrect)       { bg="#14291a"; border="#16a34a"; color="#4ade80"; }
                  else if (isSelected) { bg="#2d1b1b"; border="#dc2626"; color="#fca5a5"; }
                }
                return (
                  <button key={i} onClick={() => pick(i)} style={{
                    background:bg, border:`1px solid ${border}`, borderRadius:10, color,
                    padding:"12px 16px", textAlign:"left", cursor: answered?"default":"pointer",
                    fontSize:14, lineHeight:1.5, transition:"all .15s",
                  }}>
                    <span style={{ fontWeight:600, marginRight:8 }}>{["A","B","C","D"][i]}.</span> {opt}
                    {answered && isCorrect && <span style={{ float:"right" }}>✓</span>}
                    {answered && isSelected && !isCorrect && <span style={{ float:"right" }}>✗</span>}
                  </button>
                );
              })}
            </div>

            {/* Explanation + Next */}
            {answered && (
              <div style={{ marginTop:16 }}>
                <div style={{ background:"#1a1a3a", border:"1px solid #2d2d50", borderRadius:10,
                  padding:"12px 16px", color:"#94a3b8", fontSize:13, lineHeight:1.6, marginBottom:14 }}>
                  💡 {q.explanation}
                </div>
                <button onClick={next} style={{ width:"100%", background:"linear-gradient(135deg,#6366f1,#8b5cf6)",
                  color:"#fff", border:"none", borderRadius:10, padding:"12px", fontSize:15,
                  fontWeight:600, cursor:"pointer" }}>
                  {current + 1 >= questions.length ? "See Results →" : "Next Question →"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
