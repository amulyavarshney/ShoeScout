"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, formatPrice, type AvailabilityResponse, type ProductDetail as ProductDetailData } from "@/lib/api"
import { cn } from "@/lib/utils"

import { LocationPrompt } from "./LocationPrompt"
import { ProductImage, colorSwatch } from "./ProductCard"
import { StoreList } from "./StoreList"

export function ProductDetailView({
  productId, initialImageGroup, initialSize, sessionId, locationKnown, locationToken, onLocated, onSimilar, onSelectVariant, asPage,
}: {
  productId: string
  initialImageGroup?: string | null
  initialSize?: string | null
  sessionId?: string | null
  locationKnown?: boolean
  locationToken?: string | null
  onLocated?: (label: string, token: string) => void
  onSimilar?: (p: ProductDetailData, color: string | null) => void
  onSelectVariant?: (variantId: string) => void
  asPage?: boolean
}) {
  const [data, setData] = useState<ProductDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [groupId, setGroupId] = useState<string | null>(initialImageGroup ?? null)
  const [size, setSize] = useState<string | null>(initialSize ?? null)
  const [availability, setAvailability] = useState<AvailabilityResponse | null>(null)
  const [loadingAvail, setLoadingAvail] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.product(productId).then((d) => !cancelled && setData(d)).catch((e) => !cancelled && setError((e as Error).message))
    return () => {
      cancelled = true
    }
  }, [productId])

  const colorway = useMemo(() => data?.colorways.find((c) => c.image_group_id === groupId) ?? data?.colorways[0] ?? null, [data, groupId])
  const variant = useMemo(() => colorway?.variants.find((v) => v.size === size) ?? null, [colorway, size])

  const variantId = variant?.variant_id ?? null
  useEffect(() => {
    if (!variantId || !variant) return
    let cancelled = false
    setLoadingAvail(true)
    api.availability(variantId, variant.size, locationToken ?? undefined)
      .then((a) => !cancelled && setAvailability(a))
      .catch(() => !cancelled && setAvailability({ variant_id: variantId, model_id: null, size: variant.size, stores: [], stock_checked_at: null, inventory_status: "unavailable", location_known: false, available_sizes: [] }))
      .finally(() => !cancelled && setLoadingAvail(false))
    onSelectVariant?.(variantId)
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variantId, locationToken])
  const shownAvailability = availability && availability.variant_id === variantId ? availability : null

  if (error) return <p className="text-destructive text-sm">{error}</p>
  if (!data || !colorway)
    return (
      <div className="space-y-4">
        <Skeleton className="aspect-[4/3] w-full rounded-xl" />
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
      </div>
    )

  return (
    <div className={cn("grid gap-6", asPage && "lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]")}>
      <div className="space-y-3">
        <ProductImage src={colorway.images[0] ?? null} alt={`${data.brand} ${data.name}`} className="rounded-xl border" sizes="(max-width: 1024px) 100vw, 640px" />
        {data.colorways.length > 1 && (
          <div className="flex gap-2">
            {data.colorways.map((c) => (
              <button
                key={c.image_group_id}
                onClick={() => {
                  setGroupId(c.image_group_id)
                  setSize(null)
                }}
                className={cn("flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs capitalize transition-colors", c.image_group_id === colorway.image_group_id ? "bg-foreground text-background" : "hover:bg-muted")}
                aria-pressed={c.image_group_id === colorway.image_group_id}
              >
                <span className="size-3 rounded-full border" style={{ background: colorSwatch(c.primary_color) }} />
                {c.primary_color ?? c.colorway_code.toLowerCase()}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="space-y-5">
        <div>
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {data.brand} · {data.model_id}
          </p>
          <h2 className="text-2xl font-semibold tracking-tight">{data.name}</h2>
          <p className="mt-1 text-lg font-semibold tabular-nums">{formatPrice(colorway.price, colorway.currency)}</p>
        </div>
        <p className="text-muted-foreground text-sm leading-relaxed">{data.description}</p>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary" className="rounded-full font-normal capitalize">
            <span className="size-2.5 rounded-full border" style={{ background: colorSwatch(colorway.primary_color) }} />
            {colorway.primary_color ?? "colour unknown"}
            {colorway.color_confidence === "unverified" && " · unverified"}
          </Badge>
          {data.category && <Badge variant="outline" className="rounded-full font-normal capitalize">{data.category}</Badge>}
          {colorway.style && <Badge variant="outline" className="rounded-full font-normal capitalize">{colorway.style}</Badge>}
          {colorway.attribute_source && (
            <Badge variant="outline" className="rounded-full font-normal">
              attributes: {colorway.attribute_source === "fixture" ? "demo fixture" : colorway.attribute_source}
            </Badge>
          )}
        </div>

        <div>
          <p className="mb-2 text-sm font-medium">Select size</p>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Size">
            {colorway.variants.map((v) => (
              <button
                key={v.variant_id}
                role="radio"
                aria-checked={size === v.size}
                onClick={() => setSize(v.size)}
                disabled={v.stock_status === "out_of_stock"}
                className={cn(
                  "min-w-11 rounded-full border px-3 py-1.5 text-sm tabular-nums transition-colors disabled:cursor-not-allowed disabled:opacity-40 disabled:line-through",
                  size === v.size ? "bg-foreground text-background" : "hover:bg-muted",
                )}
                title={v.stock_status === "unknown" ? "Availability unknown" : v.stock_status === "out_of_stock" ? "Out of stock" : `${v.store_count} store${v.store_count === 1 ? "" : "s"}`}
              >
                {v.size}
              </button>
            ))}
          </div>
          {colorway.variants.some((v) => v.stock_status === "unknown") && <p className="text-muted-foreground mt-2 text-xs">Availability temporarily unavailable.</p>}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">Available at</p>
            {size && <span className="text-muted-foreground text-xs">size {size}</span>}
          </div>
          {!size ? (
            <p className="text-muted-foreground text-sm">Choose a size to see which stores have it. Sizes shown in stock are verified per store.</p>
          ) : loadingAvail ? (
            <Skeleton className="h-24 w-full rounded-xl" />
          ) : shownAvailability?.inventory_status === "unavailable" ? (
            <p className="text-muted-foreground text-sm">Availability temporarily unavailable. Please try again shortly.</p>
          ) : shownAvailability ? (
            <StoreList stores={shownAvailability.stores} locationKnown={shownAvailability.location_known} size={size} checkedAt={shownAvailability.stock_checked_at} />
          ) : null}
          {sessionId && size && !locationKnown && <LocationPrompt sessionId={sessionId} onLocated={(l, token) => onLocated?.(l, token)} />}
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          {onSimilar && (
            <Button variant="outline" className="rounded-full" onClick={() => onSimilar(data, colorway.primary_color)}>
              Show similar shoes
            </Button>
          )}
          {!asPage && (
            <Button asChild variant="ghost" className="rounded-full">
              <Link href={`/products/${data.product_id}?group=${colorway.image_group_id}${size ? `&size=${size}` : ""}`}>Open full page</Link>
            </Button>
          )}
        </div>
        <p className="text-muted-foreground text-[11px]">Fictional demo catalogue. ShoeScout helps you discover and locate shoes; purchases happen in store.</p>
      </div>
    </div>
  )
}
