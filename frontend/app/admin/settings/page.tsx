"use client"

import { LogOutIcon, RefreshCwIcon } from "lucide-react"
import { useRouter } from "next/navigation"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { ProviderCard } from "@/components/admin/ProviderSettingsForm"
import { SiteHeader } from "@/components/layout/site-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAdminAuth } from "@/hooks/use-admin"
import { api, type AdminSettings, type EnrichmentJob, type MetricsSummary, type ProviderStatus, type ReviewItem } from "@/lib/api"

export default function AdminSettingsPage() {
  const router = useRouter()
  const auth = useAdminAuth()
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null)
  const [settings, setSettings] = useState<AdminSettings | null>(null)
  const [draft, setDraft] = useState<Partial<AdminSettings>>({})
  const [saving, setSaving] = useState(false)
  const [voices, setVoices] = useState<Array<{ voice_id: string; name: string; category: string }>>([])

  const load = useCallback(async () => {
    const [p, s] = await Promise.all([api.admin.providers(), api.admin.settings()])
    setProviders(p)
    setSettings(s)
    setDraft({})
    if (p.find((x) => x.provider === "elevenlabs")?.configured) api.admin.voices().then((v) => setVoices(v.voices)).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (auth.loading) return
    if (!auth.authenticated) router.replace("/admin/login")
    else load().catch((e) => toast.error((e as Error).message))
  }, [auth.loading, auth.authenticated, router, load])

  const csrf = auth.csrf || ""
  const value = <K extends keyof AdminSettings>(k: K): AdminSettings[K] | undefined => (draft[k] ?? settings?.[k]) as AdminSettings[K] | undefined
  const dirty = Object.keys(draft).length > 0

  const save = async () => {
    setSaving(true)
    try {
      const s = await api.admin.patchSettings(csrf, draft)
      setSettings(s)
      setDraft({})
      toast.success("Settings saved")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (auth.loading || (auth.authenticated && (!providers || !settings)))
    return (
      <div className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="mx-auto w-full max-w-[1000px] space-y-4 px-4 py-8 sm:px-6">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-40 w-full rounded-2xl" />
          <Skeleton className="h-40 w-full rounded-2xl" />
        </main>
      </div>
    )
  if (!auth.authenticated || !providers || !settings) return null

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader mode={settings.effective_mode} />
      <main className="mx-auto w-full max-w-[1000px] flex-1 px-4 py-8 sm:px-6">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-muted-foreground text-xs">Settings</p>
            <h1 className="text-2xl font-semibold tracking-tight">AI providers &amp; catalogue</h1>
            <p className="text-muted-foreground mt-1 text-sm">
              Signed in as <span className="text-foreground font-medium">{auth.username}</span> · config v{settings.config_version} ·{" "}
              <Badge variant={settings.effective_mode === "live" ? "default" : "secondary"} className="rounded-full align-middle font-normal">
                {settings.effective_mode === "live" ? "Live mode" : "Demo mode"}
              </Badge>
            </p>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <Button onClick={save} disabled={saving} className="rounded-full" data-testid="save-settings">
                {saving ? "Saving…" : "Save changes"}
              </Button>
            )}
            <Button
              variant="ghost"
              className="rounded-full"
              onClick={async () => {
                await api.admin.logout(csrf).catch(() => undefined)
                router.replace("/admin/login")
              }}
            >
              <LogOutIcon className="size-4" /> Sign out
            </Button>
          </div>
        </div>

        <Tabs defaultValue="providers" className="gap-6">
          <TabsList>
            <TabsTrigger value="providers">Providers</TabsTrigger>
            <TabsTrigger value="voice">Models &amp; voice</TabsTrigger>
            <TabsTrigger value="catalog">Catalogue &amp; enrichment</TabsTrigger>
            <TabsTrigger value="metrics">Observability</TabsTrigger>
          </TabsList>

          <TabsContent value="providers" className="space-y-4">
            {!settings.mock_mode && !providers.find((p) => p.provider === "openai")?.configured && (
              <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm">
                Mock mode is off but no OpenAI key is configured. Shoppers see the demo assistant until a key is saved.
              </p>
            )}
            {providers.map((p) => (
              <ProviderCard key={p.provider} status={p} csrf={csrf} onChange={load}>
                {p.provider === "openai" ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="LLM model" hint="Responses API model ID, e.g. gpt-4.1-mini">
                      <Input value={value("llm_model") ?? ""} onChange={(e) => setDraft({ ...draft, llm_model: e.target.value })} className="font-mono" />
                    </Field>
                    <Field label="Vision model" hint="Used only by offline enrichment jobs">
                      <Input value={value("vision_model") ?? ""} onChange={(e) => setDraft({ ...draft, vision_model: e.target.value })} className="font-mono" />
                    </Field>
                  </div>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="STT model" hint="Realtime transcription model">
                      <Input value={value("stt_model") ?? ""} onChange={(e) => setDraft({ ...draft, stt_model: e.target.value })} className="font-mono" />
                    </Field>
                    <Field label="TTS model" hint="Streaming endpoint; eleven_v3/v4 are dialogue-only and not supported here">
                      <Input value={value("tts_model") ?? ""} onChange={(e) => setDraft({ ...draft, tts_model: e.target.value })} className="font-mono" />
                    </Field>
                    <Field label="Voice ID" hint={voices.length ? "Pick from your account or paste an ID" : "Paste a voice ID from your ElevenLabs account"}>
                      {voices.length ? (
                        <Select value={value("voice_id") || undefined} onValueChange={(v) => setDraft({ ...draft, voice_id: v })}>
                          <SelectTrigger className="w-full"><SelectValue placeholder="Choose a voice" /></SelectTrigger>
                          <SelectContent>
                            {voices.map((v) => (
                              <SelectItem key={v.voice_id} value={v.voice_id}>
                                {v.name} <span className="text-muted-foreground">· {v.category}</span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input value={value("voice_id") ?? ""} onChange={(e) => setDraft({ ...draft, voice_id: e.target.value })} className="font-mono" placeholder="voice id" />
                      )}
                    </Field>
                    <Field label="TTS output format" hint="MP3 is the safest default; PCM lowers latency once validated">
                      <Select value={value("tts_output_format")} onValueChange={(v) => setDraft({ ...draft, tts_output_format: v })}>
                        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {["mp3_44100_128", "mp3_22050_32", "pcm_16000", "pcm_24000"].map((f) => (
                            <SelectItem key={f} value={f}>{f}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                  </div>
                )}
              </ProviderCard>
            ))}
          </TabsContent>

          <TabsContent value="voice" className="space-y-4">
            <section className="space-y-5 rounded-2xl border p-5">
              <div>
                <h3 className="font-semibold tracking-tight">Voice behaviour</h3>
                <p className="text-muted-foreground text-sm">Server-side endpointing and language policy for the custom voice loop.</p>
              </div>
              <Field label={`Silence endpoint · ${value("silence_ms")} ms`} hint="Silence after speech before the turn is committed (initial 750 ms; raise for slower speakers)">
                <Slider min={300} max={2000} step={50} value={[value("silence_ms") ?? 750]} onValueChange={([v]) => setDraft({ ...draft, silence_ms: v })} className="max-w-md" />
              </Field>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Language" hint="auto preserves the shopper's language when providers support it">
                  <Select value={value("language")} onValueChange={(v) => setDraft({ ...draft, language: v })}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {[["auto", "Auto-detect"], ["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["pt", "Portuguese"]].map(([v, l]) => (
                        <SelectItem key={v} value={v}>{l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Provider timeout (s)">
                  <Input type="number" min={3} max={120} value={value("provider_timeout_s") ?? 20} onChange={(e) => setDraft({ ...draft, provider_timeout_s: Number(e.target.value) })} />
                </Field>
                <Field label="Currency">
                  <Input value={value("currency") ?? "GBP"} maxLength={3} onChange={(e) => setDraft({ ...draft, currency: e.target.value.toUpperCase() })} className="font-mono uppercase" />
                </Field>
              </div>
              <div className="flex items-center justify-between rounded-xl border p-4">
                <div>
                  <p className="text-sm font-medium">Mock mode</p>
                  <p className="text-muted-foreground text-xs">Force the demo assistant and browser speech even when keys are configured. Outputs are labelled as demo data.</p>
                </div>
                <Switch checked={value("mock_mode") ?? true} onCheckedChange={(v) => setDraft({ ...draft, mock_mode: v })} aria-label="Mock mode" data-testid="mock-mode" />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={save} disabled={!dirty || saving} className="rounded-full">Save</Button>
                <Button
                  variant="outline"
                  className="rounded-full"
                  onClick={async () => {
                    const s = await api.admin.resetDefaults(csrf)
                    setSettings(s)
                    setDraft({})
                    toast.success("Non-secret defaults restored")
                  }}
                >
                  Reset non-secret defaults
                </Button>
              </div>
            </section>
          </TabsContent>

          <TabsContent value="catalog">
            <CatalogPanel csrf={csrf} />
          </TabsContent>
          <TabsContent value="metrics">
            <MetricsPanel />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">{label}</Label>
      {children}
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
    </div>
  )
}

function CatalogPanel({ csrf }: { csrf: string }) {
  const [jobs, setJobs] = useState<{ counts: Record<string, number>; jobs: EnrichmentJob[] } | null>(null)
  const [review, setReview] = useState<ReviewItem[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const refresh = useCallback(async () => {
    const [j, r] = await Promise.all([api.admin.jobs(), api.admin.reviewQueue()])
    setJobs(j)
    setReview(r)
  }, [])
  useEffect(() => {
    refresh().catch(() => undefined)
    const t = setInterval(() => refresh().catch(() => undefined), 5000)
    return () => clearInterval(t)
  }, [refresh])

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label)
    try {
      const r = await fn()
      toast.success(`${label}: ${JSON.stringify(r).slice(0, 140)}`)
      await refresh()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <section className="space-y-4 rounded-2xl border p-5">
        <div>
          <h3 className="font-semibold tracking-tight">Catalogue</h3>
          <p className="text-muted-foreground text-sm">Seed the fictional demo dataset or import supplier JSON/CSV (products, variants, image URLs, stores, stock).</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" className="rounded-full" disabled={!!busy} onClick={() => run("Seed demo", () => api.admin.seedDemo(csrf))}>Seed demo data</Button>
          <Button variant="ghost" className="rounded-full" disabled={!!busy} onClick={() => confirm("Re-seed and replace the current catalogue?") && run("Re-seed", () => api.admin.seedDemo(csrf, true))}>Force re-seed</Button>
          <label className="hover:bg-muted cursor-pointer rounded-full border px-3 py-1.5 text-sm transition-colors">
            Import JSON/CSV…
            <input type="file" accept=".json,.csv" className="sr-only" onChange={(e) => e.target.files?.[0] && run("Import", () => api.admin.importCatalog(csrf, e.target.files![0]))} />
          </label>
        </div>
      </section>

      <section className="space-y-4 rounded-2xl border p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold tracking-tight">Image enrichment</h3>
            <p className="text-muted-foreground text-sm">Offline vision jobs derive colour/style per colourway. Idempotent on image hash + model version; failures retry with backoff.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="rounded-full" disabled={!!busy} onClick={() => run("Enrichment", () => api.admin.runEnrichment(csrf))}>Run for changed images</Button>
            <Button variant="ghost" size="sm" className="rounded-full" disabled={!!busy} onClick={() => run("Enrichment (all)", () => api.admin.runEnrichment(csrf, true))}>Re-run all</Button>
            <Button variant="ghost" size="icon" className="rounded-full" onClick={() => refresh()} aria-label="Refresh"><RefreshCwIcon className="size-4" /></Button>
          </div>
        </div>
        {jobs && (
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(jobs.counts).map(([k, v]) => (
              <Badge key={k} variant={k === "dead" || k === "failed" ? "destructive" : "secondary"} className="rounded-full font-normal">{k}: {v}</Badge>
            ))}
            {Object.keys(jobs.counts).length === 0 && <span className="text-muted-foreground">No jobs yet.</span>}
          </div>
        )}
        {review.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Needs review ({review.length})</p>
            <ul className="divide-y rounded-xl border text-sm">
              {review.map((r) => (
                <li key={r.image_group_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                  <div>
                    <span className="font-mono text-xs">{r.image_group_id}</span>
                    <p className="text-muted-foreground text-xs">
                      supplier: {String(r.evidence.supplier_color ?? "—")} · vision: {String(r.evidence.vision_color ?? "—")} · current: {r.primary_color ?? "unknown"}
                    </p>
                  </div>
                  <div className="flex gap-1.5">
                    {[r.evidence.supplier_color, r.evidence.vision_color].filter((c, i, a) => c && a.indexOf(c) === i).map((c) => (
                      <Button key={String(c)} size="sm" variant="outline" className="rounded-full capitalize" onClick={() => run(`Set ${c}`, () => api.admin.decideReview(csrf, r.image_group_id, String(c)))}>
                        Use {String(c)}
                      </Button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {jobs && jobs.jobs.length > 0 && (
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Image group</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Attempts</th>
                  <th className="px-3 py-2 font-medium">Result</th>
                  <th className="px-3 py-2 font-medium">Error</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {jobs.jobs.slice(0, 40).map((j) => (
                  <tr key={j.id}>
                    <td className="px-3 py-2 font-mono">{j.image_group_id}</td>
                    <td className="px-3 py-2"><Badge variant={j.status === "done" ? "secondary" : j.status === "dead" || j.status === "failed" ? "destructive" : "outline"} className="rounded-full font-normal">{j.status}</Badge></td>
                    <td className="px-3 py-2 tabular-nums">{j.attempts}</td>
                    <td className="px-3 py-2">{j.attributes ? `${j.attributes.primary_color ?? "unknown"} · ${j.attributes.source} · ${j.attributes.review_status}` : "—"}</td>
                    <td className="text-muted-foreground max-w-[240px] truncate px-3 py-2" title={j.error_message ?? ""}>{j.error_code ?? "—"}</td>
                    <td className="px-3 py-2 text-right">
                      {(j.status === "failed" || j.status === "dead") && (
                        <Button size="xs" variant="outline" className="rounded-full" onClick={() => run("Retry", () => api.admin.retryJob(csrf, j.id))}>Retry</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function MetricsPanel() {
  const [m, setM] = useState<MetricsSummary | null>(null)
  useEffect(() => {
    const load = () => api.admin.metrics().then(setM).catch(() => undefined)
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [])
  if (!m) return <Skeleton className="h-48 w-full rounded-2xl" />
  return (
    <div className="space-y-4">
      <section className="grid gap-3 sm:grid-cols-4">
        {[["Products", m.catalog.products], ["Variants", m.catalog.variants], ["Stores", m.catalog.stores], ["Needs review", m.catalog.needs_review]].map(([l, v]) => (
          <div key={String(l)} className="rounded-2xl border p-4">
            <p className="text-muted-foreground text-xs">{l}</p>
            <p className="text-2xl font-semibold tabular-nums">{v}</p>
          </div>
        ))}
      </section>
      <section className="rounded-2xl border p-5">
        <h3 className="mb-3 font-semibold tracking-tight">Pipeline latency (ms, since start)</h3>
        {Object.keys(m.stages).length === 0 ? (
          <p className="text-muted-foreground text-sm">No turns recorded yet.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-muted-foreground text-xs"><tr><th className="py-1 font-medium">Stage</th><th className="py-1 font-medium">Count</th><th className="py-1 font-medium">p50</th><th className="py-1 font-medium">p95</th><th className="py-1 font-medium">Mean</th></tr></thead>
            <tbody className="divide-y">
              {Object.entries(m.stages).map(([k, v]) => (
                <tr key={k}><td className="py-1.5 font-mono text-xs">{k}</td><td className="py-1.5 tabular-nums">{v.count}</td><td className="py-1.5 tabular-nums">{v.p50}</td><td className="py-1.5 tabular-nums">{v.p95}</td><td className="py-1.5 tabular-nums">{v.mean}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="rounded-2xl border p-5">
        <h3 className="mb-3 font-semibold tracking-tight">Event counters (anonymised)</h3>
        <div className="flex flex-wrap gap-2">
          {Object.entries(m.counters).map(([k, v]) => (
            <Badge key={k} variant="secondary" className="rounded-full font-normal">{k}: {v}</Badge>
          ))}
          {Object.keys(m.counters).length === 0 && <span className="text-muted-foreground text-sm">Nothing yet.</span>}
        </div>
      </section>
    </div>
  )
}
