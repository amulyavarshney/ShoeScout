"use client"

import { CheckCircle2Icon, KeyRoundIcon, Loader2Icon, XCircleIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, type ProviderStatus } from "@/lib/api"

const COPY: Record<ProviderStatus["provider"], { title: string; description: string; placeholder: string }> = {
  openai: { title: "OpenAI", description: "LLM for the agent (Responses API with tool calling) and vision model for offline enrichment.", placeholder: "sk-…" },
  elevenlabs: { title: "ElevenLabs", description: "Scribe v2 realtime speech-to-text and streaming text-to-speech.", placeholder: "xi-api-key" },
}

export function ProviderCard({ status, csrf, onChange, children }: { status: ProviderStatus; csrf: string; onChange: () => void; children?: React.ReactNode }) {
  const [editing, setEditing] = useState(false)
  const [key, setKey] = useState("")
  const [busy, setBusy] = useState<"save" | "test" | "remove" | null>(null)
  const [test, setTest] = useState<{ ok: boolean; message: string; error_type: string | null } | null>(null)
  const copy = COPY[status.provider]

  const save = async () => {
    setBusy("save")
    try {
      await api.admin.putKey(csrf, status.provider, key)
      setKey("")
      setEditing(false)
      setTest(null)
      toast.success(`${copy.title} key saved (encrypted)`)
      onChange()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(null)
    }
  }
  const remove = async () => {
    if (!confirm(`Remove the ${copy.title} key? Live features that depend on it will fall back to demo mode.`)) return
    setBusy("remove")
    try {
      await api.admin.deleteKey(csrf, status.provider)
      setTest(null)
      toast.success(`${copy.title} key removed`)
      onChange()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(null)
    }
  }
  const runTest = async () => {
    setBusy("test")
    try {
      const r = await api.admin.testProvider(csrf, status.provider)
      setTest(r)
    } catch (e) {
      setTest({ ok: false, message: (e as Error).message, error_type: "exception" })
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="rounded-2xl border p-5" data-testid={`provider-${status.provider}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold tracking-tight">{copy.title}</h3>
          <p className="text-muted-foreground text-sm">{copy.description}</p>
        </div>
        <Badge variant={status.configured ? "default" : "outline"} className="rounded-full font-normal">
          {status.configured ? "Configured" : status.validation_status === "failed" ? "Validation failed" : "Not configured"}
        </Badge>
      </div>

      <div className="mt-4 space-y-3">
        <div className="grid gap-2 sm:grid-cols-[140px_1fr] sm:items-center">
          <Label className="text-muted-foreground">API key</Label>
          {editing || !status.configured ? (
            <div className="flex flex-wrap gap-2">
              <Input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={copy.placeholder} className="max-w-md font-mono" aria-label={`${copy.title} API key`} />
              <Button onClick={save} disabled={busy !== null || key.trim().length < 16} className="rounded-full">
                {busy === "save" ? <Loader2Icon className="size-4 animate-spin" /> : <KeyRoundIcon className="size-4" />} Save
              </Button>
              {status.configured && (
                <Button variant="ghost" className="rounded-full" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              )}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <code className="bg-muted rounded-md px-2 py-1 font-mono text-sm">••••••••••••{status.last4}</code>
              <span className="text-muted-foreground text-xs">
                source: {status.source}
                {status.updated_at ? ` · updated ${new Date(status.updated_at).toLocaleString()}` : ""}
              </span>
              {status.source === "settings" && (
                <>
                  <Button variant="outline" size="sm" className="rounded-full" onClick={() => setEditing(true)}>
                    Replace
                  </Button>
                  <Button variant="ghost" size="sm" className="rounded-full" onClick={remove} disabled={busy !== null}>
                    Remove
                  </Button>
                </>
              )}
              {status.source === "environment" && (
                <Button variant="outline" size="sm" className="rounded-full" onClick={() => setEditing(true)}>
                  Override in Settings
                </Button>
              )}
            </div>
          )}
        </div>
        {children}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button variant="outline" size="sm" className="rounded-full" onClick={runTest} disabled={busy !== null || !status.configured}>
            {busy === "test" ? <Loader2Icon className="size-3.5 animate-spin" /> : null} Test connection
          </Button>
          {test && (
            <span className={`inline-flex items-center gap-1.5 text-sm ${test.ok ? "text-foreground" : "text-destructive"}`} data-testid="test-result">
              {test.ok ? <CheckCircle2Icon className="size-4" /> : <XCircleIcon className="size-4" />}
              {test.message}
              {test.error_type && !test.ok && <span className="text-muted-foreground text-xs">({test.error_type})</span>}
            </span>
          )}
        </div>
      </div>
      <p className="text-muted-foreground mt-4 text-[11px]">Keys are encrypted at rest (AES-GCM), shown masked, and never sent to shoppers or browser code.</p>
    </section>
  )
}
