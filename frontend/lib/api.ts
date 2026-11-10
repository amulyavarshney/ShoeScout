/** Typed client for the ShoeScout backend. No provider secrets ever pass through here. */
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/$/, "")
export const WS_BASE = API_BASE.replace(/^http/, "ws")

export type StockStatus = "in_stock" | "out_of_stock" | "unknown"

export interface ProductCardData {
  product_id: string
  variant_id: string
  model_id: string
  name: string
  brand: string
  primary_color: string | null
  color_confidence: "verified" | "unverified" | "unknown"
  category: string | null
  price: number
  currency: string
  image_url: string | null
  available_sizes: string[]
  in_stock: boolean
  stock_status: StockStatus
  stock_checked_at: string | null
  store_count: number
  image_group_id: string
  is_alternative: boolean
  relaxed: string[]
}

export interface StoreAvailabilityData {
  store_id: string
  name: string
  address: string
  city: string
  postcode: string
  size: string | null
  quantity_status: "in_stock" | "low_stock" | "out_of_stock" | "unknown"
  quantity: number | null
  distance_km: number | null
  updated_at: string | null
}

export interface Preferences {
  brand: string | null
  model: string | null
  color: string | null
  category: string | null
  size: string | null
  max_price: number | null
  use_case: string | null
}

export interface SessionInfo {
  session_id: string
  expires_at: string
  mode: "mock" | "live"
  capabilities: { server_stt: boolean; server_tts: boolean; llm: string; currency: string; silence_ms: number }
}

export interface MessageResponse {
  turn_id: string
  message: string
  products: ProductCardData[]
  stores: StoreAvailabilityData[] | null
  preferences: Preferences
  selected_variant_id: string | null
  state: "complete" | "error" | "needs_clarification"
  relaxed_constraints: string[]
  is_demo: boolean
}

export interface ProductDetail {
  product_id: string
  model_id: string
  brand: string
  name: string
  description: string
  category: string | null
  base_price: number
  currency: string
  colorways: Array<{
    image_group_id: string
    colorway_code: string
    images: string[]
    primary_color: string | null
    color_confidence: "verified" | "unverified" | "unknown"
    secondary_colors: string[]
    style: string | null
    tags: string[]
    attribute_source: string | null
    review_status: string | null
    price: number
    currency: string
    variants: Array<{ variant_id: string; sku: string; size: string; price: number; stock_status: StockStatus; store_count: number }>
  }>
}

export interface AvailabilityResponse {
  variant_id: string | null
  model_id: string | null
  size: string | null
  stores: StoreAvailabilityData[]
  stock_checked_at: string | null
  inventory_status: "ok" | "unavailable"
  location_known: boolean
  available_sizes: string[]
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "content-type": "application/json", ...(init.headers || {}) },
  })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = body?.error || {}
    throw new ApiError(res.status, err.code || "HTTP_ERROR", err.message || `Request failed (${res.status})`)
  }
  return body as T
}

export const api = {
  createSession: (locale?: string) => request<SessionInfo>("/api/v1/sessions", { method: "POST", body: JSON.stringify({ locale }) }),
  sendMessage: (sessionId: string, text: string, turnId: string) =>
    request<MessageResponse>(`/api/v1/sessions/${sessionId}/messages`, { method: "POST", body: JSON.stringify({ text, turn_id: turnId }) }),
  selectVariant: (sessionId: string, variantId: string) =>
    request(`/api/v1/sessions/${sessionId}/select`, { method: "POST", body: JSON.stringify({ variant_id: variantId }) }),
  locationConsent: (sessionId: string, body: { latitude?: number; longitude?: number; postcode?: string; city?: string }) =>
    request<{ location_token: string; expires_at: string; label: string }>(`/api/v1/sessions/${sessionId}/location/consent`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteSession: (sessionId: string) => request(`/api/v1/sessions/${sessionId}`, { method: "DELETE" }),
  publicConfig: () => request<{ mode: "mock" | "live"; server_stt: boolean; server_tts: boolean; currency: string; silence_ms: number }>("/api/v1/config/public"),
  searchProducts: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && qs.set(k, String(v)))
    return request<{ products: ProductCardData[]; relaxed_constraints: string[]; route: string; inventory_status: string }>(`/api/v1/products/search?${qs}`)
  },
  product: (id: string) => request<ProductDetail>(`/api/v1/products/${id}`),
  availability: (variantId: string, size?: string, locationToken?: string) => {
    const qs = new URLSearchParams()
    if (size) qs.set("size", size)
    if (locationToken) qs.set("location_token", locationToken)
    return request<AvailabilityResponse>(`/api/v1/variants/${variantId}/availability?${qs}`)
  },
  admin: {
    status: () => request<{ configured: boolean; authenticated: boolean; username: string | null; csrf: string | null }>("/api/v1/admin/auth/status"),
    login: (username: string, password: string) =>
      request<{ authenticated: boolean; username: string; csrf: string }>("/api/v1/admin/login", { method: "POST", body: JSON.stringify({ username, password }) }),
    logout: (csrf: string) => request("/api/v1/admin/logout", { method: "POST", headers: { "x-csrf-token": csrf } }),
    providers: () => request<ProviderStatus[]>("/api/v1/admin/providers"),
    putKey: (csrf: string, provider: string, apiKey: string) =>
      request<ProviderStatus>(`/api/v1/admin/providers/${provider}/key`, { method: "PUT", headers: { "x-csrf-token": csrf }, body: JSON.stringify({ api_key: apiKey }) }),
    deleteKey: (csrf: string, provider: string) => request(`/api/v1/admin/providers/${provider}/key`, { method: "DELETE", headers: { "x-csrf-token": csrf } }),
    testProvider: (csrf: string, provider: string) =>
      request<{ ok: boolean; message: string; error_type: string | null; details: Record<string, unknown> }>(`/api/v1/admin/providers/${provider}/test`, {
        method: "POST",
        headers: { "x-csrf-token": csrf },
      }),
    voices: () => request<{ voices: Array<{ voice_id: string; name: string; category: string; preview_url: string | null }>; reason?: string }>("/api/v1/admin/providers/elevenlabs/voices"),
    settings: () => request<AdminSettings>("/api/v1/admin/settings"),
    patchSettings: (csrf: string, patch: Partial<AdminSettings>) =>
      request<AdminSettings>("/api/v1/admin/settings", { method: "PATCH", headers: { "x-csrf-token": csrf }, body: JSON.stringify(patch) }),
    resetDefaults: (csrf: string) => request<AdminSettings>("/api/v1/admin/settings/reset-defaults", { method: "POST", headers: { "x-csrf-token": csrf } }),
    seedDemo: (csrf: string, force = false) => request<Record<string, unknown>>(`/api/v1/admin/catalog/seed-demo?force=${force}`, { method: "POST", headers: { "x-csrf-token": csrf } }),
    importCatalog: async (csrf: string, file: File) => {
      const fd = new FormData()
      fd.append("file", file)
      const res = await fetch(`${API_BASE}/api/v1/admin/catalog/import`, { method: "POST", body: fd, credentials: "include", headers: { "x-csrf-token": csrf } })
      const body = await res.json()
      if (!res.ok) throw new ApiError(res.status, body?.error?.code || "HTTP_ERROR", body?.error?.message || "Import failed")
      return body as { records: number; variants_upserted: number; errors: string[]; indexed_docs: number }
    },
    runEnrichment: (csrf: string, force = false) => request<{ queued: number; groups: number; model_version: string }>(`/api/v1/admin/enrichment/run?force=${force}`, { method: "POST", headers: { "x-csrf-token": csrf } }),
    jobs: (status?: string) => request<{ counts: Record<string, number>; jobs: EnrichmentJob[] }>(`/api/v1/admin/enrichment/jobs${status ? `?status=${status}` : ""}`),
    retryJob: (csrf: string, id: string) => request(`/api/v1/admin/enrichment/jobs/${id}/retry`, { method: "POST", headers: { "x-csrf-token": csrf } }),
    reviewQueue: () => request<ReviewItem[]>("/api/v1/admin/enrichment/review"),
    decideReview: (csrf: string, gid: string, color: string) =>
      request(`/api/v1/admin/enrichment/review/${gid}`, { method: "POST", headers: { "x-csrf-token": csrf }, body: JSON.stringify({ primary_color: color }) }),
    metrics: () => request<MetricsSummary>("/api/v1/admin/metrics/summary"),
  },
}

export interface ProviderStatus {
  provider: "openai" | "elevenlabs"
  configured: boolean
  source: "settings" | "environment" | "none"
  last4: string | null
  updated_at: string | null
  validation_status: "unknown" | "ok" | "failed"
}

export interface AdminSettings {
  llm_model: string
  vision_model: string
  stt_model: string
  tts_model: string
  voice_id: string
  tts_output_format: string
  silence_ms: number
  language: string
  provider_timeout_s: number
  mock_mode: boolean
  currency: string
  config_version: number
  updated_at: string | null
  effective_mode: "mock" | "live"
}

export interface EnrichmentJob {
  id: string
  image_group_id: string
  status: string
  attempts: number
  error_code: string | null
  error_message: string | null
  created_at: string
  finished_at: string | null
  model_version: string
  attributes: { primary_color: string | null; secondary_colors: string[]; source: string; review_status: string; evidence: Record<string, unknown> } | null
}

export interface ReviewItem {
  image_group_id: string
  primary_color: string | null
  secondary_colors: string[]
  source: string
  evidence: Record<string, unknown>
  processed_at: string
}

export interface MetricsSummary {
  catalog: { products: number; variants: number; stores: number; needs_review: number; enrichment_jobs: Record<string, number> }
  stages: Record<string, { count: number; p50: number; p95: number; mean: number }>
  counters: Record<string, number>
}

export function formatPrice(price: number, currency: string) {
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: price % 1 === 0 ? 0 : 2 }).format(price)
  } catch {
    return `${currency} ${price}`
  }
}
