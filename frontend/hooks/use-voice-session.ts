"use client"

import { useEffect, useState } from "react"

import { api, type SessionInfo } from "@/lib/api"
import { VoiceSessionManager, type SessionSnapshot } from "@/components/voice/VoiceSessionManager"

const STORAGE_KEY = "shoescout.session"

export function useVoiceSession() {
  const [manager, setManager] = useState<VoiceSessionManager | null>(null)
  const [snapshot, setSnapshot] = useState<SessionSnapshot | null>(null)
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)

  const [generation, setGeneration] = useState(0)
  const [replay, setReplay] = useState<string | null>(null)

  useEffect(() => {
    let unsub: (() => void) | undefined
    let cancelled = false
    let created: VoiceSessionManager | null = null
    ;(async () => {
      try {
        let info: SessionInfo | null = null
        try {
          const cached = generation === 0 ? sessionStorage.getItem(STORAGE_KEY) : null
          if (cached) {
            const parsed = JSON.parse(cached) as SessionInfo
            if (new Date(parsed.expires_at).getTime() > Date.now() + 60_000) info = parsed
          }
        } catch {
          /* storage unavailable */
        }
        if (!info) {
          info = await api.createSession(typeof navigator !== "undefined" ? navigator.language : undefined)
          try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(info))
          } catch {
            /* ignore */
          }
        } else {
          // Capabilities may have changed (admin saved keys); refresh them.
          const cfg = await api.publicConfig().catch(() => null)
          if (cfg) info = { ...info, mode: cfg.mode, capabilities: { ...info.capabilities, server_stt: cfg.server_stt, server_tts: cfg.server_tts } }
        }
        if (cancelled) return
        setSessionInfo(info)
        const mgr = new VoiceSessionManager(info.session_id, { server_stt: info.capabilities.server_stt, server_tts: info.capabilities.server_tts, mode: info.mode })
        created = mgr
        mgr.onSessionExpired = (pendingText) => {
          // Server forgot the session (restart or TTL): start a fresh one, keeping the UI alive.
          try {
            sessionStorage.removeItem(STORAGE_KEY)
          } catch {
            /* ignore */
          }
          mgr.disconnect()
          setReplay(pendingText ?? null)
          setGeneration((g) => g + 1)
        }
        setManager(mgr)
        unsub = mgr.subscribe(setSnapshot)
        mgr.connect()
        if (replay) {
          const text = replay
          setReplay(null)
          mgr.sendText(text)  // re-send the message that was lost with the expired session
        }
      } catch (e) {
        setBootError((e as Error).message || "Could not reach the ShoeScout API")
      }
    })()
    return () => {
      cancelled = true
      unsub?.()
      created?.disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generation])

  const resetSession = async () => {
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
    if (sessionInfo) await api.deleteSession(sessionInfo.session_id).catch(() => undefined)
    window.location.reload()
  }

  return { manager, snapshot, sessionInfo, bootError, resetSession }
}
