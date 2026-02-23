import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TitanFlow Dashboard",
  description: "Titan Finance real-time trading dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning className="antialiased">
        {children}
      </body>
    </html>
  );
}
