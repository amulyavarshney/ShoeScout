"use client"

import { MapPinIcon, StoreIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { StoreAvailabilityData } from "@/lib/api"

export function StoreList({ stores, locationKnown, size, checkedAt }: { stores: StoreAvailabilityData[]; locationKnown: boolean; size?: string | null; checkedAt?: string | null }) {
  if (!stores.length)
    return <p className="text-muted-foreground text-sm">No stores currently have this{size ? ` in size ${size}` : ""}.</p>
  return (
    <div className="space-y-2">
      {!locationKnown && <p className="text-muted-foreground text-xs">Listed alphabetically. Share your location to sort by distance.</p>}
      <ul className="divide-y rounded-xl border">
        {stores.map((s, i) => (
          <li key={s.store_id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="bg-muted grid size-9 shrink-0 place-items-center rounded-full">
                <StoreIcon className="size-4" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {s.name}
                  {locationKnown && i === 0 && <span className="text-muted-foreground ml-2 text-xs font-normal">Nearest</span>}
                </p>
                <p className="text-muted-foreground truncate text-xs">
                  {s.address}, {s.city} {s.postcode}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge variant={s.quantity_status === "low_stock" ? "outline" : "secondary"} className="rounded-full font-normal">
                {s.quantity_status === "low_stock" ? "Low stock" : s.quantity_status === "in_stock" ? "In stock" : s.quantity_status === "unknown" ? "Unknown" : "Out of stock"}
                {s.size ? ` · ${s.size}` : ""}
              </Badge>
              {s.distance_km != null && (
                <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
                  <MapPinIcon className="size-3" /> {s.distance_km} km
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
      {checkedAt && <p className="text-muted-foreground text-[11px]">Last checked {new Date(checkedAt).toLocaleTimeString()}. Stock can change before you arrive.</p>}
    </div>
  )
}
