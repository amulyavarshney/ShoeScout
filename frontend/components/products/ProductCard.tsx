"use client"

import Image from "next/image"
import { CheckIcon, ImageOffIcon, MapPinIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { formatPrice, type ProductCardData } from "@/lib/api"
import { cn } from "@/lib/utils"

export function ProductImage({ src, alt, className, sizes = "(max-width: 768px) 80vw, 320px" }: { src: string | null; alt: string; className?: string; sizes?: string }) {
  const ok = src && (src.startsWith("/") || src.startsWith("http"))
  const broken = !ok || src.includes("example.invalid")
  return (
    <div className={cn("bg-muted relative aspect-[4/3] w-full overflow-hidden", className)}>
      {broken ? (
        <div className="text-muted-foreground absolute inset-0 flex flex-col items-center justify-center gap-2 text-xs">
          <ImageOffIcon className="size-5" />
          Image unavailable
        </div>
      ) : (
        <Image src={src!} alt={alt} fill unoptimized sizes={sizes} className="object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
      )}
    </div>
  )
}

export function StockBadge({ product, size }: { product: Pick<ProductCardData, "stock_status" | "store_count">; size?: string | null }) {
  if (product.stock_status === "unknown")
    return <Badge variant="outline" className="rounded-full font-normal">Availability unavailable</Badge>
  if (product.stock_status === "out_of_stock")
    return <Badge variant="outline" className="rounded-full font-normal">Out of stock</Badge>
  return (
    <Badge variant="secondary" className="rounded-full font-normal">
      <CheckIcon className="size-3" />
      In stock{size ? ` · size ${size}` : ""} · {product.store_count} store{product.store_count === 1 ? "" : "s"}
    </Badge>
  )
}

export function ProductCard({
  product, selected, onSelect, onDetails, sizeContext,
}: { product: ProductCardData; selected?: boolean; onSelect?: (p: ProductCardData) => void; onDetails?: (p: ProductCardData) => void; sizeContext?: string | null }) {
  return (
    <article
      className={cn(
        "group bg-card text-card-foreground flex flex-col overflow-hidden rounded-xl border transition-all hover:shadow-[0_8px_30px_-12px_rgba(0,0,0,0.25)]",
        selected && "ring-foreground ring-2 ring-offset-2 ring-offset-background",
      )}
      data-testid="product-card"
    >
      <button type="button" onClick={() => onDetails?.(product)} className="relative text-left" aria-label={`View ${product.name}`}>
        <ProductImage src={product.image_url} alt={`${product.brand} ${product.name}`} />
        {product.is_alternative && (
          <Badge className="absolute top-2 left-2 rounded-full" variant="default">
            Alternative · {product.relaxed.map((r) => r.replace("_", " ")).join(", ")} relaxed
          </Badge>
        )}
      </button>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{product.brand}</p>
            <h3 className="truncate text-[15px] font-semibold tracking-tight">{product.name}</h3>
          </div>
          <p className="shrink-0 text-[15px] font-semibold tabular-nums">{formatPrice(product.price, product.currency)}</p>
        </div>
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="inline-flex items-center gap-1.5 capitalize">
            <span className="size-2.5 rounded-full border" style={{ background: colorSwatch(product.primary_color) }} aria-hidden />
            {product.primary_color ?? "colour unknown"}
            {product.color_confidence === "unverified" && <span className="text-[10px]">(unverified)</span>}
          </span>
          {product.category && <span>· {product.category}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <StockBadge product={product} size={sizeContext && product.available_sizes.includes(sizeContext) ? sizeContext : null} />
        </div>
        {product.available_sizes.length > 0 && (
          <p className="text-muted-foreground text-xs">
            Sizes in stock: <span className="text-foreground font-medium">{product.available_sizes.join(", ")}</span>
          </p>
        )}
        <div className="mt-auto flex gap-2 pt-2">
          <Button size="sm" variant={selected ? "default" : "outline"} className="flex-1 rounded-full" onClick={() => onSelect?.(product)}>
            {selected ? <CheckIcon className="size-3.5" /> : <MapPinIcon className="size-3.5" />}
            {selected ? "Selected" : "Find in store"}
          </Button>
          <Button size="sm" variant="ghost" className="rounded-full" onClick={() => onDetails?.(product)}>
            Details
          </Button>
        </div>
      </div>
    </article>
  )
}

export function colorSwatch(color: string | null) {
  const map: Record<string, string> = {
    red: "#D62828", blue: "#2457C5", black: "#1B1B1B", white: "#F3F3F3", grey: "#8C8C8C", green: "#2E8B57", burgundy: "#6E1423",
    navy: "#1F2A5A", brown: "#6B4226", tan: "#C8A165", orange: "#E8732A", pink: "#E87BA6", yellow: "#D9A400", purple: "#6F2DBD",
  }
  return color ? map[color] ?? "transparent" : "transparent"
}
