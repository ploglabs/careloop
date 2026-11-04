import type { Metadata } from "next";
import { Cal_Sans, Geist_Mono } from "next/font/google";
import "./globals.css";

const calSans = Cal_Sans({ variable: "--font-cal-sans", weight: "400", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const DESCRIPTION = "Post-discharge follow-up voice agent for clinics and hospitals, built on Gnani Prisma and Timbre.";

export const metadata: Metadata = {
  metadataBase: new URL("https://app.careloop.puang.in"),
  title: "CareLoop",
  description: DESCRIPTION,
  openGraph: { type: "website", siteName: "CareLoop", title: "CareLoop", description: DESCRIPTION },
  twitter: { card: "summary_large_image", title: "CareLoop", description: DESCRIPTION },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${calSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
