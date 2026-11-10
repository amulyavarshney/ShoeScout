"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { MoonIcon, SettingsIcon, SunIcon } from "lucide-react"
import { useTheme } from "next-themes"
import { useSyncExternalStore } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function Wordmark({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn("flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span className="bg-foreground text-background grid size-7 place-items-center rounded-md text-[13px] font-bold">S</span>
      <span className="text-[15px]">ShoeScout</span>
    </Link>
  )
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const mounted = useSyncExternalStore(() => () => undefined, () => true, () => false)
  return (
    <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
      {mounted && resolvedTheme === "dark" ? <SunIcon className="size-4" /> : <MoonIcon className="size-4" />}
    </Button>
  )
}

export function SiteHeader({ mode, context }: { mode?: "mock" | "live"; context?: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <header className="bg-background/80 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Wordmark />
          <nav className="hidden items-center gap-1 text-sm md:flex">
            <Link href="/" className={cn("text-muted-foreground hover:text-foreground rounded-md px-2.5 py-1.5 transition-colors", pathname === "/" && "text-foreground")}>
              Discover
            </Link>
            <Link href="/admin/settings" className={cn("text-muted-foreground hover:text-foreground rounded-md px-2.5 py-1.5 transition-colors", pathname.startsWith("/admin") && "text-foreground")}>
              Admin
            </Link>
          </nav>
        </div>
        <div className="hidden min-w-0 flex-1 justify-center md:flex">{context}</div>
        <div className="flex items-center gap-1.5">
          {mode && (
            <Badge variant={mode === "live" ? "default" : "secondary"} className="hidden rounded-full font-medium sm:inline-flex">
              {mode === "live" ? "Live" : "Demo mode"}
            </Badge>
          )}
          <ThemeToggle />
          <Button asChild variant="ghost" size="icon" aria-label="Admin settings">
            <Link href="/admin/settings">
              <SettingsIcon className="size-4" />
            </Link>
          </Button>
        </div>
      </div>
    </header>
  )
}
