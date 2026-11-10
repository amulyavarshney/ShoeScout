"use client"

import { LocateFixedIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"

/** Location is requested only after an explicit user action (FR-18). Postcode/city is the alternative. */
export function LocationPrompt({ sessionId, onLocated, compact }: { sessionId: string; onLocated: (label: string, token: string) => void; compact?: boolean }) {
  const [postcode, setPostcode] = useState("")
  const [busy, setBusy] = useState(false)
  const [denied, setDenied] = useState(false)

  const useDevice = () => {
    if (!("geolocation" in navigator)) return setDenied(true)
    setBusy(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const r = await api.locationConsent(sessionId, { latitude: pos.coords.latitude, longitude: pos.coords.longitude })
          onLocated(r.label, r.location_token)
          toast.success("Location shared for this session only")
        } catch (e) {
          toast.error((e as Error).message)
        } finally {
          setBusy(false)
        }
      },
      () => {
        setBusy(false)
        setDenied(true)
      },
      { enableHighAccuracy: false, timeout: 8000 },
    )
  }

  const submitPostcode = async () => {
    if (!postcode.trim()) return
    setBusy(true)
    try {
      const r = await api.locationConsent(sessionId, { postcode: postcode.trim() })
      onLocated(r.label, r.location_token)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={compact ? "space-y-2" : "bg-surface space-y-3 rounded-xl border p-4"}>
      {!compact && (
        <div>
          <p className="text-sm font-medium">Find nearby stores</p>
          <p className="text-muted-foreground text-xs">We only use your location for this session to sort stores by distance. Nothing is stored.</p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" className="rounded-full" onClick={useDevice} disabled={busy} data-testid="use-location">
          <LocateFixedIcon className="size-3.5" /> Use my location
        </Button>
        <span className="text-muted-foreground text-xs">or</span>
        <form
          className="flex items-center gap-1.5"
          onSubmit={(e) => {
            e.preventDefault()
            submitPostcode()
          }}
        >
          <Input value={postcode} onChange={(e) => setPostcode(e.target.value)} placeholder="Postcode or city" className="h-8 w-40 rounded-full text-sm" aria-label="Postcode or city" />
          <Button size="sm" type="submit" className="rounded-full" disabled={busy || !postcode.trim()}>
            Go
          </Button>
        </form>
      </div>
      {denied && <p className="text-muted-foreground text-xs">Location permission was not granted. Enter a postcode or city instead; stores will not be labelled “nearest” without it.</p>}
    </div>
  )
}
