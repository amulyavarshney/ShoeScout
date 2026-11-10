"use client"

import { ArrowUpIcon, MicIcon, MicOffIcon, RotateCcwIcon, SquareIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Conversation, ConversationContent, ConversationEmptyState, ConversationScrollButton } from "@/components/ui/conversation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Message, MessageContent } from "@/components/ui/message"
import { Orb, type AgentState } from "@/components/ui/orb"
import { Response } from "@/components/ui/response"
import { ShimmeringText } from "@/components/ui/shimmering-text"
import { VoiceButton, type VoiceButtonState } from "@/components/ui/voice-button"
import { Waveform } from "@/components/ui/waveform"
import type { SessionSnapshot, VoiceSessionManager, VoiceState } from "@/components/voice/VoiceSessionManager"
import { cn } from "@/lib/utils"

const ORB_STATE: Record<VoiceState, AgentState> = {
  idle: null, listening: "listening", finalizing: "thinking", thinking: "thinking", searching: "thinking", speaking: "talking", error: null, disconnected: null,
}
const BUTTON_STATE: Record<VoiceState, VoiceButtonState> = {
  idle: "idle", listening: "recording", finalizing: "processing", thinking: "processing", searching: "processing", speaking: "idle", error: "error", disconnected: "idle",
}

export const SUGGESTIONS = ["Red Nike shoes under £100", "Comfortable shoes for standing all day", "Is MODEL-101 available in size 9?", "Black formal shoes for a wedding"]

export function VoiceAssistant({ manager, snap, onReset, compact }: { manager: VoiceSessionManager; snap: SessionSnapshot; onReset: () => void; compact?: boolean }) {
  const [text, setText] = useState("")
  const inputVolume = useRef(0)
  const outputVolume = useRef(0)
  const [bars, setBars] = useState<number[]>(() => Array(48).fill(0.05))

  // Drive Orb + waveform from the real capture/playback levels (no second mic stream).
  useEffect(() => {
    let raf = 0
    const tick = () => {
      inputVolume.current = snap.state === "listening" ? Math.min(1, manager.inputLevel * 4) : 0
      outputVolume.current = manager.outputLevel()
      if (snap.state === "listening" || snap.state === "speaking") {
        const v = Math.max(inputVolume.current, outputVolume.current)
        setBars((prev) => [...prev.slice(1), Math.max(0.05, Math.min(1, v + (Math.random() - 0.5) * 0.08))])
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [manager, snap.state])

  useEffect(() => {
    if (snap.state === "idle") setBars(Array(48).fill(0.05))
  }, [snap.state])

  const submit = (value?: string) => {
    const v = (value ?? text).trim()
    if (!v) return
    setText("")
    manager.sendText(v)
  }

  const busy = snap.state === "thinking" || snap.state === "searching" || snap.state === "finalizing"
  const voiceLabel = snap.state === "listening" ? "Stop listening" : snap.state === "speaking" ? "Interrupt" : "Start talking"

  return (
    <section className={cn("flex h-full min-h-0 flex-col", compact ? "gap-3" : "gap-4")} aria-label="Voice assistant">
      {/* Orb + status */}
      <div className={cn("flex flex-col items-center gap-3 text-center", compact ? "pt-1" : "pt-4")}>
        <div className={cn("relative", snap.state === "listening" && "pulse-ring", compact ? "size-20" : "size-36 sm:size-44")}>
          <Orb
            className="h-full w-full"
            agentState={ORB_STATE[snap.state]}
            volumeMode="manual"
            inputVolumeRef={inputVolume}
            outputVolumeRef={outputVolume}
            seed={7}
          />
        </div>
        <div className="min-h-[1.5rem]">
          {busy ? (
            <ShimmeringText text={snap.statusLabel} className="text-sm font-medium" duration={1.4} />
          ) : (
            <p className={cn("text-sm font-medium", snap.state === "error" && "text-destructive", snap.state === "disconnected" && "text-muted-foreground")} aria-live="polite">
              {snap.statusLabel}
            </p>
          )}
          <p className="text-muted-foreground mt-0.5 text-xs">
            {snap.mode === "live" ? "Live assistant" : "Demo mode · fictional catalogue"}
            {!snap.serverStt && " · browser speech"}
          </p>
        </div>
        <Waveform data={bars} active={snap.state === "listening" || snap.state === "speaking"} barWidth={2} barGap={2} barRadius={2} height={28} fadeEdges className={cn("w-full max-w-[280px]", compact && "max-w-[200px]")} />
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        <VoiceButton
          state={BUTTON_STATE[snap.state]}
          label={voiceLabel}
          trailing={snap.state === "idle" ? "Space" : undefined}
          variant={snap.state === "listening" ? "default" : "outline"}
          className="rounded-full"
          waveformClassName="rounded-full"
          icon={snap.micPermission === "denied" ? <MicOffIcon className="size-4" /> : <MicIcon className="size-4" />}
          onPress={() => (snap.state === "speaking" ? manager.stopSpeaking() : manager.toggleListening())}
          data-testid="voice-button"
        />
        {snap.state === "speaking" && (
          <Button variant="secondary" className="rounded-full" onClick={() => manager.stopSpeaking()} data-testid="stop-speaking">
            <SquareIcon className="size-3.5 fill-current" /> Stop speaking
          </Button>
        )}
        {busy && (
          <Button variant="ghost" className="rounded-full" onClick={() => manager.cancelTurn()}>
            Cancel
          </Button>
        )}
        <Button variant="ghost" size="icon" className="rounded-full" aria-label="Start over" onClick={onReset}>
          <RotateCcwIcon className="size-4" />
        </Button>
      </div>

      {snap.error && (
        <div role="alert" className="bg-destructive/5 text-destructive flex items-start justify-between gap-2 rounded-lg border border-destructive/20 px-3 py-2 text-xs">
          <span>{snap.error}</span>
          <button className="underline" onClick={() => manager.clearError()}>
            Dismiss
          </button>
        </div>
      )}

      {/* Transcript */}
      <div className="bg-surface/60 min-h-0 flex-1 overflow-hidden rounded-xl border">
        <Conversation className="h-full">
          <ConversationContent className="gap-3 p-3">
            {snap.messages.length === 0 ? (
              <ConversationEmptyState
                title="Say what you're looking for"
                description={<span>Try “red Nike shoes”, then refine with “size 9” or “cheaper ones”.</span>}
                icon={<MicIcon className="text-muted-foreground size-5" />}
                className="py-8"
              />
            ) : (
              snap.messages.map((m) => (
                <Message key={m.id} from={m.role} className={cn(m.partial && "opacity-70")} data-testid={`message-${m.role}`}>
                  <MessageContent className={cn(m.role === "user" && "rounded-2xl", m.role === "assistant" && "bg-transparent px-0")}>
                    <Response className="text-[14px] leading-relaxed">{m.text + (m.partial ? " …" : "")}</Response>
                    {m.role === "assistant" && m.isDemo && <span className="text-muted-foreground mt-1 block text-[10px] tracking-wide uppercase">Demo assistant</span>}
                  </MessageContent>
                  {m.role === "assistant" && (
                    <div className="ring-border size-7 shrink-0 overflow-hidden rounded-full ring-1">
                      <Orb className="h-full w-full" agentState={null} seed={7} />
                    </div>
                  )}
                </Message>
              ))
            )}
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>
      </div>

      {/* Text input (always available: FR-02) */}
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type your request…"
          aria-label="Type your request"
          className="h-10 rounded-full px-4"
          data-testid="text-input"
        />
        <Button type="submit" size="icon" className="size-10 shrink-0 rounded-full" aria-label="Send" disabled={!text.trim() || busy} data-testid="send-button">
          <ArrowUpIcon className="size-4" />
        </Button>
      </form>
      {snap.messages.length === 0 && (
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" onClick={() => submit(s)} className="hover:bg-muted rounded-full border px-3 py-1 text-xs transition-colors">
              {s}
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
