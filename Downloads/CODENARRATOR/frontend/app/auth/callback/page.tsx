"use client";
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function AuthCallback() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const token  = params.get("token")  ?? "";
    const login  = params.get("login")  ?? "";
    const avatar = params.get("avatar") ?? "";
    if (token) {
      localStorage.setItem("gh_token",  token);
      localStorage.setItem("gh_login",  login);
      localStorage.setItem("gh_avatar", avatar);
    }
    router.replace("/");
  }, [params, router]);

  return (
    <main style={{ minHeight:"100vh", display:"flex", alignItems:"center", justifyContent:"center",
      background:"#07070f", color:"#a5b4fc", fontSize:16, fontFamily:"sans-serif" }}>
      <div style={{ textAlign:"center" }}>
        <div style={{ fontSize:32, marginBottom:12 }}>⏳</div>
        <p>Completing GitHub login…</p>
      </div>
    </main>
  );
}
