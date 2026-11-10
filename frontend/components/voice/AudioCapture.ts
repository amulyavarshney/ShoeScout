import { publicAsset } from "@/lib/public-asset"

/** Microphone capture → 16 kHz PCM16 frames via AudioWorklet. Exposes a live level (0..1) for the Orb/waveform. */

export type FrameHandler = (pcm: ArrayBuffer, level: number) => void

export class AudioCapture {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private node: AudioWorkletNode | null = null
  level = 0

  get mediaStream() {
    return this.stream
  }

  async start(onFrame: FrameHandler): Promise<void> {
    if (this.ctx) return
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    this.ctx = new AudioContext()
    await this.ctx.audioWorklet.addModule(publicAsset("/worklets/pcm-processor.js"))
    const source = this.ctx.createMediaStreamSource(this.stream)
    this.node = new AudioWorkletNode(this.ctx, "pcm-processor")
    this.node.port.onmessage = (e: MessageEvent) => {
      if (e.data?.type === "frame") {
        this.level = e.data.level
        onFrame(e.data.pcm, e.data.level)
      }
    }
    source.connect(this.node)
    // Keep the graph alive without echoing the mic to the speakers.
    const sink = this.ctx.createGain()
    sink.gain.value = 0
    this.node.connect(sink).connect(this.ctx.destination)
  }

  async stop(): Promise<void> {
    this.node?.port.close()
    this.node?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    await this.ctx?.close().catch(() => undefined)
    this.node = null
    this.stream = null
    this.ctx = null
    this.level = 0
  }
}
