"use client"

import { Skeleton } from "@/components/ui/skeleton"
import type { ProductCardData } from "@/lib/api"

import { ProductCard } from "./ProductCard"

export function ProductGrid({
  products, selectedVariantId, onSelect, onDetails, sizeContext, loading,
}: {
  products: ProductCardData[]
  selectedVariantId?: string | null
  onSelect?: (p: ProductCardData) => void
  onDetails?: (p: ProductCardData) => void
  sizeContext?: string | null
  loading?: boolean
}) {
  if (loading)
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="overflow-hidden rounded-xl border">
            <Skeleton className="aspect-[4/3] w-full rounded-none" />
            <div className="space-y-2 p-4">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-5 w-32 rounded-full" />
            </div>
          </div>
        ))}
      </div>
    )
  return (
    <div className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2 md:mx-0 md:grid md:grid-cols-2 md:overflow-visible md:px-0 xl:grid-cols-3">
      {products.map((p) => (
        <div key={p.variant_id} className="w-[80vw] shrink-0 snap-center sm:w-[340px] md:w-auto">
          <ProductCard product={p} selected={selectedVariantId === p.variant_id} onSelect={onSelect} onDetails={onDetails} sizeContext={sizeContext} />
        </div>
      ))}
    </div>
  )
}
