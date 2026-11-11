/** Owns the voice session: WebSocket transport, audio capture/playback, state machine, and the demo-mode
 *  browser fallback (Web Speech API) when the server has no STT/TTS provider configured.
 *  Orb/VoiceButton are presentational; all transport lives here. */
import { WS_BASE, type Preferences, type ProductCardData, type StoreAvailabilityData } from "@/lib/api"
import { AudioCapture } from "./AudioCapture"
import { AudioPlayback } from "./AudioPlayback"

export type VoiceState = "idle" | "listening" | "finalizing" | "thinking" | "searching" | "speaking" | "error" | "disconnected"

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  text: string
  partial?: boolean
  turnId: string
  isDemo?: boolean
}

export interface SessionSnapshot {
  state: VoiceState
  statusLabel: string
  messages: ChatMessage[]
  products: ProductCardData[]
  relaxed: string[]
  inventoryStatus: string
  stores: StoreAvailabilityData[] | null
  storeContext: { variant_id: string | null; size: string | null; location_known: boolean } | null
  preferences: Preferences | null
  selectedVariantId: string | null
  error: string | null
  serverStt: boolean
  serverTts: boolean
  mode: "mock" | "live"
  micPermission: "unknown" | "granted" | "denied"
  connected: boolean
  usingBrowserSpeech: boolean
}

type Listener = (s: SessionSnapshot) => void

const uuid = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2))

export class VoiceSessionManager {
  private ws: WebSocket | null = null
  private capture = new AudioCapture()
  private playback = new AudioPlayback()
  private listeners = new Set<Listener>()
  private snap: SessionSnapshot
  private currentTurn: string | null = null
  private pendingTurn: string | null = null
  private speechRecognition: SpeechRecognition | null = null
  private synthUtterance: SpeechSynthesisUtterance | null = null
  private speechGeneration = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private closedByUser = false
  private reconnectAttempts = 0
  /** Called when the server no longer knows this session (restart / TTL). The host should create a new session. */
  onSessionExpired: ((pendingText?: string) => void) | null = null
  private pendingText: string | null = null
  inputLevel = 0

  constructor(public sessionId: string, caps: { server_stt: boolean; server_tts: boolean; mode: "mock" | "live" }) {
    this.snap = {
      state: "idle", statusLabel: "Ready", messages: [], products: [], relaxed: [], inventoryStatus: "ok", stores: null,
      storeContext: null, preferences: null, selectedVariantId: null, error: null, serverStt: caps.server_stt,
      serverTts: caps.server_tts, mode: caps.mode, micPermission: "unknown", connected: false, usingBrowserSpeech: false,
    }
  }

  subscribe(fn: Listener) {
    this.listeners.add(fn)
    fn(this.snap)
    return () => this.listeners.delete(fn)
  }

  get snapshot() {
    return this.snap
  }

  private synthPhase = 0
  outputLevel() {
    if (this.snap.state !== "speaking") return 0
    if (this.synthUtterance) {
      // Browser speechSynthesis exposes no audio graph; synthesise a gentle speech-like envelope for the Orb.
      this.synthPhase += 0.12
      return 0.25 + 0.2 * Math.abs(Math.sin(this.synthPhase)) * (0.7 + 0.3 * Math.sin(this.synthPhase * 0.37))
    }
    return this.playback.level()
  }

  private set(patch: Partial<SessionSnapshot>) {
    this.snap = { ...this.snap, ...patch }
    this.listeners.forEach((l) => l(this.snap))
  }

  private setState(state: VoiceState, label?: string) {
    const labels: Record<VoiceState, string> = {
      idle: "Ready", listening: "Listening…", finalizing: "Finishing transcript…", thinking: "Thinking…", searching: "Finding shoes…",
      speaking: "Speaking…", error: "Something went wrong", disconnected: "Disconnected",
    }
    this.set({ state, statusLabel: label ?? labels[state] })
  }

  // ---------- transport ----------
  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return
    this.closedByUser = false
    const ws = new WebSocket(`${WS_BASE}/ws/voice?session_id=${encodeURIComponent(this.sessionId)}`)
    ws.binaryType = "arraybuffer"
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "session.start", session_id: this.sessionId, audio_format: "pcm_s16le", sample_rate: 16000, auto_endpoint: true }))
    }
    ws.onmessage = (ev) => (typeof ev.data === "string" ? this.handleEvent(JSON.parse(ev.data)) : this.playback.push(ev.data as ArrayBuffer))
    ws.onclose = (ev) => {
      this.set({ connected: false })
      if (this.snap.state === "listening") this.stopListening()
      if (this.closedByUser) return
      if (ev.code === 4401 || this.reconnectAttempts >= 5) {
        // Session unknown to the server (restart/expiry) or persistent failure: hand over to the host.
        this.setState("disconnected", "Session expired, reconnecting…")
        const pending = this.pendingText
        this.pendingText = null
        this.onSessionExpired?.(pending ?? undefined)
        return
      }
      this.reconnectAttempts += 1
      this.setState("disconnected")
      this.reconnectTimer = setTimeout(() => this.connect(), Math.min(8000, 1000 * 2 ** this.reconnectAttempts))
    }
    ws.onerror = () => undefined
    this.ws = ws
  }

  disconnect() {
    this.closedByUser = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.stopListening()
    this.stopSpeaking()
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "session.stop" }))
    this.ws?.close()
    this.ws = null
  }

  private send(obj: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj))
  }

  private handleEvent(ev: Record<string, unknown>) {
    const turnId = ev.turn_id as string | undefined
    const stale = turnId && this.currentTurn && turnId !== this.currentTurn && !["session.ready", "pong"].includes(ev.type as string)
    switch (ev.type) {
      case "session.ready":
        this.reconnectAttempts = 0
        this.set({ connected: true, serverStt: !!ev.server_stt, serverTts: !!ev.server_tts, mode: ev.mode as "mock" | "live", error: null })
        if (this.snap.state === "disconnected") this.setState("idle")
        break
      case "stt.partial":
        if (stale) return
        this.upsertMessage({ id: `u-${turnId}`, role: "user", text: ev.text as string, partial: true, turnId: turnId! })
        break
      case "stt.final":
        if (stale) return
        if ((ev.text as string).trim()) this.upsertMessage({ id: `u-${turnId}`, role: "user", text: ev.text as string, partial: false, turnId: turnId! })
        else this.removeMessage(`u-${turnId}`)
        break
      case "vad.speech_start":
        if (!stale) this.setState("listening", "Listening…")
        break
      case "vad.no_speech":
        if (!stale) this.set({ statusLabel: "I didn't hear anything." })
        break
      case "agent.state":
        if (stale) return
        {
          const s = ev.state as string
          if (s === "listening") this.setState("listening")
          else if (s === "finalizing") this.setState("finalizing")
          else if (s === "thinking") this.setState("thinking")
          else if (s === "searching") this.setState("searching")
          else if (s === "speaking") this.setState("speaking")
        }
        break
      case "search.results":
        if (stale) return
        this.set({ products: ev.products as ProductCardData[], relaxed: (ev.relaxed_constraints as string[]) || [], inventoryStatus: (ev.inventory_status as string) || "ok", stores: null, storeContext: null })
        break
      case "store.results":
        if (stale) return
        this.set({ stores: ev.stores as StoreAvailabilityData[], storeContext: { variant_id: (ev.variant_id as string) || null, size: (ev.size as string) || null, location_known: !!ev.location_known } })
        break
      case "agent.message":
        if (stale) return
        this.pendingText = null
        this.upsertMessage({ id: `a-${turnId}`, role: "assistant", text: ev.text as string, turnId: turnId!, isDemo: !!ev.is_demo })
        this.set({ preferences: (ev.preferences as Preferences) || this.snap.preferences, selectedVariantId: (ev.selected_variant_id as string | null) ?? this.snap.selectedVariantId })
        if (!this.snap.serverTts) this.speakInBrowser(ev.text as string)
        break
      case "tts.start":
        if (stale) return
        this.playback.onEnded = () => this.afterSpeaking()
        this.playback.start(ev.codec as string, ev.sample_rate as number)
        this.setState("speaking")
        break
      case "tts.end":
        if (stale) return
        if (ev.cancelled) this.playback.stop()
        else this.playback.end()
        break
      case "tts.unavailable":
        break
      case "turn.complete":
        if (stale) return
        if (this.snap.state !== "speaking") this.afterSpeaking()
        break
      case "error":
        if (stale) return
        this.set({ error: ev.message as string })
        this.setState("error", "Retry or type instead")
        this.stopListening()
        break
    }
  }

  private upsertMessage(m: ChatMessage) {
    const existing = this.snap.messages.findIndex((x) => x.id === m.id)
    const messages = [...this.snap.messages]
    if (existing >= 0) messages[existing] = m
    else messages.push(m)
    this.set({ messages })
  }

  private removeMessage(id: string) {
    this.set({ messages: this.snap.messages.filter((m) => m.id !== id) })
  }

  private afterSpeaking() {
    this.synthUtterance = null
    if (this.pendingTurn) return
    this.setState("idle")
  }

  // ---------- turns ----------
  async sendText(text: string) {
    const trimmed = text.trim()
    if (!trimmed) return
    this.stopSpeaking()
    const turnId = uuid()
    this.currentTurn = turnId
    this.upsertMessage({ id: `u-${turnId}`, role: "user", text: trimmed, turnId })
    this.set({ error: null })
    this.setState("thinking")
    this.pendingText = trimmed
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.send({ type: "text.turn", turn_id: turnId, text: trimmed, speak: true })
    } else {
      // HTTP fallback: identical agent path on the server.
      const { api } = await import("@/lib/api")
      try {
        const r = await api.sendMessage(this.sessionId, trimmed, turnId)
        if (this.currentTurn !== turnId) return
        this.set({ products: r.products, relaxed: r.relaxed_constraints, stores: r.stores, preferences: r.preferences, selectedVariantId: r.selected_variant_id,
          storeContext: r.stores ? { variant_id: r.selected_variant_id, size: r.preferences.size, location_known: false } : null })
        this.pendingText = null
        this.upsertMessage({ id: `a-${turnId}`, role: "assistant", text: r.message, turnId, isDemo: r.is_demo })
        if (!this.snap.serverTts) this.speakInBrowser(r.message)
        else this.setState("idle")
      } catch (e) {
        const err = e as { code?: string; message: string }
        if (err.code === "SESSION_NOT_FOUND") {
          this.pendingText = null
          this.onSessionExpired?.(trimmed)
          return
        }
        this.set({ error: err.message })
        this.setState("error", "Retry or type instead")
      }
    }
  }

  async startListening() {
    if (this.snap.state === "listening") return
    this.stopSpeaking()
    if (!this.snap.serverStt) return this.startBrowserSpeech()
    const turnId = uuid()
    this.currentTurn = turnId
    try {
      await this.capture.start((pcm, level) => {
        this.inputLevel = level
        if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(pcm)
      })
      this.set({ micPermission: "granted", error: null })
    } catch {
      this.set({ micPermission: "denied", error: "Microphone access was denied. You can type your request instead." })
      this.setState("error", "Type instead")
      return
    }
    this.send({ type: "audio.start", turn_id: turnId })
    this.setState("listening")
  }

  async stopListening() {
    if (this.speechRecognition) {
      try { this.speechRecognition.stop() } catch { /* ignore */ }
      return
    }
    if (this.capture.mediaStream) {
      await this.capture.stop()
      this.inputLevel = 0
      if (this.snap.state === "listening") {
        this.send({ type: "audio.end", turn_id: this.currentTurn })
        this.setState("finalizing")
      }
    }
  }

  toggleListening() {
    return this.snap.state === "listening" ? this.stopListening() : this.startListening()
  }

  cancelTurn() {
    this.send({ type: "turn.cancel", turn_id: this.currentTurn })
    this.stopSpeaking()
    this.stopListening()
    this.setState("idle")
  }

  stopSpeaking() {
    this.speechGeneration += 1
    this.playback.stop()
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel()
    this.synthUtterance = null
    if (this.snap.state === "speaking") {
      this.send({ type: "turn.cancel", turn_id: this.currentTurn })
      this.setState("idle")
    }
  }

  // ---------- demo-mode browser speech (Web Speech API) ----------
  private startBrowserSpeech() {
    const SR = (window as unknown as { SpeechRecognition?: typeof SpeechRecognition; webkitSpeechRecognition?: typeof SpeechRecognition }).SpeechRecognition
      || (window as unknown as { webkitSpeechRecognition?: typeof SpeechRecognition }).webkitSpeechRecognition
    if (!SR) {
      this.set({ error: "Server speech recognition is not configured and this browser has no built-in speech recognition. Please type your request." })
      this.setState("error", "Type instead")
      return
    }
    const turnId = uuid()
    this.currentTurn = turnId
    const rec = new SR()
    rec.continuous = false
    rec.interimResults = true
    rec.lang = navigator.language || "en-GB"
    let finalText = ""
    rec.onresult = (e: SpeechRecognitionEvent) => {
      let interim = ""
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript
        if (e.results[i].isFinal) finalText += t
        else interim += t
      }
      const shown = (finalText + interim).trim()
      if (shown) this.upsertMessage({ id: `u-${turnId}`, role: "user", text: shown, partial: !finalText, turnId })
      this.inputLevel = 0.4 + Math.random() * 0.3
    }
    rec.onerror = (e: SpeechRecognitionErrorEvent) => {
      this.speechRecognition = null
      this.inputLevel = 0
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        this.set({ micPermission: "denied", error: "Microphone access was denied. You can type your request instead." })
        this.setState("error", "Type instead")
      } else if (e.error !== "aborted" && e.error !== "no-speech") {
        this.set({ error: `Speech recognition error (${e.error}). Please type instead.` })
        this.setState("error", "Type instead")
      } else {
        this.setState("idle", e.error === "no-speech" ? "I didn't hear anything." : "Ready")
      }
    }
    rec.onend = () => {
      this.speechRecognition = null
      this.inputLevel = 0
      const text = finalText.trim()
      if (text) {
        this.removeMessage(`u-${turnId}`)
        this.sendText(text)
      } else if (this.snap.state === "listening") this.setState("idle")
    }
    this.speechRecognition = rec
    this.set({ usingBrowserSpeech: true, micPermission: "granted", error: null })
    this.setState("listening")
    rec.start()
  }

  private speakInBrowser(text: string) {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return this.setState("idle")
    const generation = ++this.speechGeneration
    // Chrome interrupts an utterance spoken in the same turn as cancel().
    window.speechSynthesis.cancel()
    window.setTimeout(() => {
      if (generation !== this.speechGeneration) return
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = navigator.language || "en-GB"
      utterance.rate = 1.03
      utterance.onend = () => {
        if (generation === this.speechGeneration) this.afterSpeaking()
      }
      utterance.onerror = (event) => {
        const error = (event as SpeechSynthesisErrorEvent).error
        if (error === "interrupted" || error === "canceled") return
        if (generation === this.speechGeneration) this.afterSpeaking()
      }
      this.synthUtterance = utterance
      this.setState("speaking")
      window.speechSynthesis.speak(utterance)
    }, 50)
  }

  selectVariant(variantId: string | null) {
    this.set({ selectedVariantId: variantId })
  }

  clearError() {
    this.set({ error: null })
    if (this.snap.state === "error") this.setState("idle")
  }
}
