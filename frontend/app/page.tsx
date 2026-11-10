"use client"

import { AlertTriangleIcon, SparklesIcon } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { SiteHeader } from "@/components/layout/site-header"
import { LocationPrompt } from "@/components/products/LocationPrompt"
import { ProductDetailView } from "@/components/products/ProductDetail"
import { ProductGrid } from "@/components/products/ProductGrid"
import { StoreList } from "@/components/products/StoreList"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { VoiceAssistant, SUGGESTIONS } from "@/components/voice/VoiceAssistant"
import { useVoiceSession } from "@/hooks/use-voice-session"
import { api, type ProductCardData } from "@/lib/api"

const CATEGORIES = ["Running", "Casual", "Walking", "Formal", "Trail", "Work", "Boots", "Kids"]

export default function DiscoveryPage() {
  const { manager, snapshot, sessionInfo, bootError, resetSession } = useVoiceSession()
  const [detail, setDetail] = useState<ProductCardData | null>(null)
  const [locationLabel, setLocationLabel] = useState<string | null>(null)
  const [locationToken, setLocationToken] = useState<string | null>(null)

  // Keyboard shortcut: Space toggles the microphone when not typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (e.code !== "Space" || !manager || ["INPUT", "TEXTAREA", "BUTTON", "A", "SELECT"].includes(target?.tagName ?? "") || target?.isContentEditable) return
      e.preventDefault()
      manager.toggleListening()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [manager])

  const selectProduct = useCallback(
    async (p: ProductCardData) => {
      if (!manager || !sessionInfo) return
      manager.selectVariant(p.variant_id)
      await api.selectVariant(sessionInfo.session_id, p.variant_id).catch(() => undefined)
      const size = snapshot?.preferences?.size
      manager.sendText(size ? `Which stores have ${p.name} in size ${size}?` : `Which stores have the ${p.name}?`)
    },
    [manager, sessionInfo, snapshot?.preferences?.size],
  )

  const prefs = snapshot?.preferences
  const contextChips = prefs ? Object.entries(prefs).filter(([, v]) => v != null && v !== "").map(([k, v]) => (k === "max_price" ? `under ${formatMoney(Number(v), sessionInfo?.capabilities.currency || "GBP")}` : String(v))) : []
  const hasResults = (snapshot?.products.length ?? 0) > 0 || (snapshot?.stores?.length ?? 0) > 0 || (snapshot?.messages.length ?? 0) > 0

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader
        mode={sessionInfo?.mode}
        context={
          contextChips.length > 0 ? (
            <div className="flex items-center gap-1.5 text-xs" data-testid="search-context">
              <span className="text-muted-foreground">Search context</span>
              {contextChips.map((c) => (
                <Badge key={c} variant="secondary" className="rounded-full font-normal capitalize">
                  {c}
                </Badge>
              ))}
            </div>
          ) : null
        }
      />

      {sessionInfo?.mode === "mock" && (
        <div className="bg-surface border-b">
          <div className="text-muted-foreground mx-auto flex max-w-[1400px] items-center gap-2 px-4 py-2 text-xs sm:px-6">
            <SparklesIcon className="size-3.5" />
            Demo mode: fictional catalogue and a rule-based assistant. Add OpenAI and ElevenLabs keys in Admin → Settings for the live voice agent.
          </div>
        </div>
      )}

      <main className="mx-auto grid w-full max-w-[1400px] flex-1 grid-cols-1 gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(320px,38%)_minmax(0,1fr)] lg:gap-8">
        {/* Left: voice assistant */}
        <aside className={sessionInfo?.mode === "mock" ? "lg:sticky lg:top-[7.25rem] lg:h-[calc(100vh-8.75rem)]" : "lg:sticky lg:top-20 lg:h-[calc(100vh-6.5rem)]"}>
          {bootError ? (
            <div className="rounded-xl border p-6 text-sm">
              <div className="mb-2 flex items-center gap-2 font-medium">
                <AlertTriangleIcon className="size-4" /> Can&apos;t reach the ShoeScout API
              </div>
              <p className="text-muted-foreground">{bootError}. Start the backend (see README) and reload.</p>
            </div>
          ) : manager && snapshot ? (
            <VoiceAssistant manager={manager} snap={snapshot} onReset={resetSession} />
          ) : (
            <div className="space-y-4">
              <Skeleton className="mx-auto size-40 rounded-full" />
              <Skeleton className="mx-auto h-4 w-32" />
              <Skeleton className="h-64 w-full rounded-xl" />
            </div>
          )}
        </aside>

        {/* Right: results */}
        <section className="min-w-0 space-y-6" aria-label="Results">
          {!hasResults ? (
            <div className="space-y-8">
              <div className="space-y-3 pt-2">
                <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Find your next pair.</h1>
                <p className="text-muted-foreground max-w-xl text-base">
                  Describe what you want in your own words. ShoeScout shows 3–5 in-stock options and tells you which store has your size.
                </p>
              </div>
              <div>
                <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">Popular</p>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((c) => (
                    <Button key={c} variant="outline" className="rounded-full" onClick={() => manager?.sendText(`${c} shoes`)} disabled={!manager}>
                      {c}
                    </Button>
                  ))}
                </div>
              </div>
              <FeaturedStrip onPick={(p) => setDetail(p)} />
              <div className="bg-surface rounded-xl border p-5">
                <p className="text-sm font-medium">Try saying</p>
                <ul className="text-muted-foreground mt-2 grid gap-1.5 text-sm sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <li key={s}>
                      <button className="hover:text-foreground text-left underline-offset-4 hover:underline" onClick={() => manager?.sendText(s)}>
                        “{s}”
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <>
              {snapshot?.stores && snapshot.storeContext && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold tracking-tight">
                      Store availability{snapshot.storeContext.size ? ` · size ${snapshot.storeContext.size}` : ""}
                    </h2>
                    {locationLabel && <Badge variant="secondary" className="rounded-full font-normal">Near {locationLabel}</Badge>}
                  </div>
                  <StoreList stores={snapshot.stores} locationKnown={snapshot.storeContext.location_known} size={snapshot.storeContext.size} />
                  {!snapshot.storeContext.location_known && sessionInfo && (
                    <LocationPrompt
                      sessionId={sessionInfo.session_id}
                      onLocated={(label, token) => {
                        setLocationLabel(label)
                        setLocationToken(token)
                        const size = snapshot.storeContext?.size ?? snapshot.preferences?.size
                        manager?.sendText(size ? `Which nearest store has this in size ${size}?` : "Which nearest store has this?")
                      }}
                    />
                  )}
                </div>
              )}
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-semibold tracking-tight" data-testid="results-heading">
                    {snapshot?.products.length ? `Matching shoes (${snapshot.products.length})` : snapshot?.state === "searching" || snapshot?.state === "thinking" ? "Searching…" : "No matches yet"}
                  </h2>
                  <div className="flex items-center gap-2">
                    {snapshot?.inventoryStatus === "unavailable" && <Badge variant="outline" className="rounded-full font-normal">Availability temporarily unavailable</Badge>}
                    {snapshot && snapshot.relaxed.length > 0 && (
                      <Badge variant="outline" className="rounded-full font-normal">Alternatives relax: {snapshot.relaxed.map((r) => r.replace("_", " ")).join(", ")}</Badge>
                    )}
                  </div>
                </div>
                {snapshot?.products.length ? (
                  <ProductGrid products={snapshot.products} selectedVariantId={snapshot.selectedVariantId} onSelect={selectProduct} onDetails={setDetail} sizeContext={snapshot.preferences?.size} />
                ) : snapshot?.state === "searching" || snapshot?.state === "thinking" ? (
                  <ProductGrid products={[]} loading />
                ) : (
                  <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
                    Nothing to show yet. Ask for a brand, colour, type of shoe, or what you need them for.
                  </div>
                )}
                {!!snapshot?.products.length && !snapshot.preferences?.size && (
                  <p className="text-muted-foreground text-xs">Sizes shown are in stock somewhere. Tell me your size and I&apos;ll check it per store.</p>
                )}
              </div>
            </>
          )}
        </section>
      </main>

      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent side="bottom" className="max-h-[92vh] overflow-y-auto rounded-t-2xl p-6 sm:max-w-none lg:inset-y-0 lg:right-0 lg:left-auto lg:h-full lg:max-h-none lg:w-[640px] lg:rounded-none lg:rounded-l-2xl">
          <SheetHeader className="p-0 pb-4">
            <SheetTitle className="sr-only">{detail?.name}</SheetTitle>
            <SheetDescription className="sr-only">Product details and store availability</SheetDescription>
          </SheetHeader>
          {detail && (
            <ProductDetailView
              productId={detail.product_id}
              initialImageGroup={detail.image_group_id}
              initialSize={snapshot?.preferences?.size}
              sessionId={sessionInfo?.session_id}
              locationKnown={!!locationLabel}
              locationToken={locationToken}
              onLocated={(l, token) => {
                setLocationLabel(l)
                setLocationToken(token)
                toast.success(`Sorting stores near ${l}`)
              }}
              onSelectVariant={(vid) => manager?.selectVariant(vid)}
              onSimilar={(p, color) => {
                setDetail(null)
                manager?.sendText(`Show me shoes similar to the ${p.brand} ${p.name}${color ? ` in ${color}` : ""}`)
              }}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}

function formatMoney(n: number, currency: string) {
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: 0 }).format(n)
  } catch {
    return `${currency} ${n}`
  }
}

function FeaturedStrip({ onPick }: { onPick: (p: ProductCardData) => void }) {
  const [items, setItems] = useState<ProductCardData[] | null>(null)
  useEffect(() => {
    api.searchProducts({ color: "red", limit: 5 }).then((r) => setItems(r.products)).catch(() => setItems([]))
  }, [])
  if (!items?.length) return null
  return (
    <div>
      <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">Featured · in stock now</p>
      <ProductGrid products={items} onDetails={onPick} onSelect={onPick} />
    </div>
  )
}
