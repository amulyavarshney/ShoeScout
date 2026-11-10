"use client"

import { ArrowLeftIcon } from "lucide-react"
import Link from "next/link"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { useState } from "react"

import { SiteHeader } from "@/components/layout/site-header"
import { ProductDetailView } from "@/components/products/ProductDetail"
import { Button } from "@/components/ui/button"
import { useVoiceSession } from "@/hooks/use-voice-session"

export function ProductPage() {
  const params = useParams<{ id: string }>()
  const search = useSearchParams()
  const router = useRouter()
  const { sessionInfo, manager } = useVoiceSession()
  const [locationToken, setLocationToken] = useState<string | null>(null)
  const productId = params.id === "placeholder" ? (search.get("id") ?? "") : params.id

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader mode={sessionInfo?.mode} />
      <main className="mx-auto w-full max-w-[1100px] flex-1 px-4 py-6 sm:px-6">
        <Button asChild variant="ghost" className="mb-4 -ml-2 rounded-full">
          <Link href="/">
            <ArrowLeftIcon className="size-4" /> Back to discovery
          </Link>
        </Button>
        {productId ? (
          <ProductDetailView
            productId={productId}
            initialImageGroup={search.get("group")}
            initialSize={search.get("size")}
            sessionId={sessionInfo?.session_id}
            locationKnown={!!locationToken}
            locationToken={locationToken}
            onLocated={(_l, token) => setLocationToken(token)}
            onSimilar={(p, color) => {
              manager?.sendText(`Show me shoes similar to the ${p.brand} ${p.name}${color ? ` in ${color}` : ""}`)
              router.push("/")
            }}
            asPage
          />
        ) : (
          <p className="text-muted-foreground text-sm">Open a product from discovery to see its details.</p>
        )}
      </main>
    </div>
  )
}
