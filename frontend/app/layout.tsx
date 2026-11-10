import type { Metadata, Viewport } from "next"
import { Inter, Geist_Mono } from "next/font/google"
import { ThemeProvider } from "next-themes"

import { Toaster } from "@/components/ui/sonner"
import "./globals.css"

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" })
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: "ShoeScout — voice-first footwear discovery",
  description: "Describe the shoes you want. ShoeScout finds in-stock options and the stores that carry your size.",
}

export const viewport: Viewport = { themeColor: [{ media: "(prefers-color-scheme: light)", color: "#ffffff" }, { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" }] }

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="bg-background text-foreground flex min-h-full flex-col font-sans">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          {children}
          <Toaster position="bottom-center" />
        </ThemeProvider>
      </body>
    </html>
  )
}
