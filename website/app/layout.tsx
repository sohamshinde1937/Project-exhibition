import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Summit Roofing & Plumbing | 24/7 AI Dispatch · Pune, Maharashtra",
  description:
    "Licensed plumbing and roofing across the Pune region. Talk to our 24/7 AI dispatcher right in your browser.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} h-full scroll-smooth antialiased`}>
      <body className="flex min-h-full flex-col bg-white text-slate-900">{children}</body>
    </html>
  );
}
