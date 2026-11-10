"use client"

import { LockIcon } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { SiteHeader } from "@/components/layout/site-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAdminAuth } from "@/hooks/use-admin"
import { api } from "@/lib/api"

export default function AdminLoginPage() {
  const router = useRouter()
  const auth = useAdminAuth()
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (auth.authenticated) router.replace("/admin/settings")
  }, [auth.authenticated, router])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.admin.login(username, password)
      router.replace("/admin/settings")
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-2xl border p-6 shadow-sm">
          <div className="space-y-1">
            <div className="bg-muted mb-3 grid size-9 place-items-center rounded-full">
              <LockIcon className="size-4" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Admin sign in</h1>
            <p className="text-muted-foreground text-sm">Settings, provider keys and catalogue tools are restricted to administrators.</p>
          </div>
          {!auth.loading && !auth.configured && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs">
              No admin password is configured on the server. Set <code>ADMIN_PASSWORD_HASH</code> (production) or <code>ADMIN_PASSWORD</code> (local dev) and restart the backend.
            </p>
          )}
          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
            <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>
          {error && <p className="text-destructive text-sm" role="alert">{error}</p>}
          <Button type="submit" className="w-full rounded-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </main>
    </div>
  )
}
