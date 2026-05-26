import TutorialViewer from "@/components/TutorialViewer";
import Link from "next/link";

interface Props { params: Promise<{ jobId: string }> }

export default async function TutorialPage({ params }: Props) {
  const { jobId } = await params;
  return (
    <div style={{ minHeight:"100vh", display:"flex", flexDirection:"column", background:"#08080f" }}>
      <header style={{
        height:64, flexShrink:0, display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"0 24px", borderBottom:"1px solid #141428",
        background:"#07070fdd", backdropFilter:"blur(12px)",
        position:"sticky", top:0, zIndex:50,
      }}>
        <Link href="/" style={{ fontSize:13, fontWeight:500, color:"#64748b", display:"flex", alignItems:"center", gap:6 }}>
          ← Code Narrator
        </Link>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontSize:14, fontWeight:700 }}>
            <span className="g-text">Tutorial Viewer</span>
          </span>
        </div>
        <div style={{
          fontSize:11, fontFamily:"var(--mono)", color:"#3d4a5c",
          padding:"4px 10px", borderRadius:7, background:"#141428",
          border:"1px solid #1a1a30",
        }}>
          {jobId.slice(0,8)}…
        </div>
      </header>
      <TutorialViewer jobId={jobId} />
    </div>
  );
}
