import type { Metadata } from "next";
import "./globals.css";
import ThemeProvider, { themeScript } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "Code Narrator — AI Tutorial Generator",
  description: "Turn any GitHub repo into a structured tutorial with architecture diagrams and narrated video.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Anti-FOUC: set theme BEFORE page paints to avoid flash */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
