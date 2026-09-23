import type { Metadata } from "next";
import "@xyflow/react/dist/style.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aetheris Core — Autonomous GraphRAG Engine",
  description:
    "Live multi-agent orchestration canvas for an autonomous, self-healing enterprise intelligence mesh.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
