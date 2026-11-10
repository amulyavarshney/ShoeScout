/** Plays streamed TTS audio. MP3 chunks: MediaSource when available, otherwise buffered Blob playback.
 *  PCM16 chunks: scheduled AudioBuffer playback. Also exposes an output level for the Orb. */
export class AudioPlayback {
  private audio: HTMLAudioElement | null = null
  private mediaSource: MediaSource | null = null
  private sourceBuffer: SourceBuffer | null = null
  private queue: ArrayBuffer[] = []
  private ended = false
  private blobChunks: ArrayBuffer[] = []
  private ctx: AudioContext | null = null
  private nextTime = 0
  private codec: "mp3" | "pcm_s16le" | "none" = "none"
  private sampleRate = 44100
  private analyser: AnalyserNode | null = null
  private levelBuf: Uint8Array<ArrayBuffer> | null = null
  private sources: AudioBufferSourceNode[] = []
  onEnded: (() => void) | null = null
  private useMSE = false

  level(): number {
    if (this.analyser && this.levelBuf) {
      this.analyser.getByteTimeDomainData(this.levelBuf)
      let sum = 0
      for (let i = 0; i < this.levelBuf.length; i++) {
        const v = (this.levelBuf[i] - 128) / 128
        sum += v * v
      }
      return Math.min(1, Math.sqrt(sum / this.levelBuf.length) * 3)
    }
    return 0
  }

  start(codec: string, sampleRate: number) {
    this.stop()
    this.codec = codec === "mp3" ? "mp3" : codec === "pcm_s16le" ? "pcm_s16le" : "none"
    this.sampleRate = sampleRate
    this.ended = false
    this.queue = []
    this.blobChunks = []
    if (this.codec === "mp3") {
      this.audio = new Audio()
      this.audio.onended = () => this.onEnded?.()
      this.useMSE = typeof MediaSource !== "undefined" && MediaSource.isTypeSupported("audio/mpeg")
      if (this.useMSE) {
        this.mediaSource = new MediaSource()
        this.audio.src = URL.createObjectURL(this.mediaSource)
        this.mediaSource.addEventListener("sourceopen", () => {
          try {
            this.sourceBuffer = this.mediaSource!.addSourceBuffer("audio/mpeg")
            this.sourceBuffer.addEventListener("updateend", () => this.pump())
            this.pump()
          } catch {
            this.useMSE = false
          }
        })
      }
      this.attachAnalyser(this.audio)
      this.audio.play().catch(() => undefined)
    } else if (this.codec === "pcm_s16le") {
      this.ctx = new AudioContext({ sampleRate })
      this.analyser = this.ctx.createAnalyser()
      this.analyser.fftSize = 256
      this.levelBuf = new Uint8Array(this.analyser.fftSize)
      this.analyser.connect(this.ctx.destination)
      this.nextTime = this.ctx.currentTime + 0.05
    }
  }

  private attachAnalyser(el: HTMLAudioElement) {
    try {
      this.ctx = this.ctx || new AudioContext()
      const src = this.ctx.createMediaElementSource(el)
      this.analyser = this.ctx.createAnalyser()
      this.analyser.fftSize = 256
      this.levelBuf = new Uint8Array(this.analyser.fftSize)
      src.connect(this.analyser).connect(this.ctx.destination)
    } catch {
      this.analyser = null
    }
  }

  push(chunk: ArrayBuffer) {
    if (this.codec === "mp3") {
      if (this.useMSE) {
        this.queue.push(chunk)
        this.pump()
      } else {
        this.blobChunks.push(chunk)
      }
    } else if (this.codec === "pcm_s16le" && this.ctx) {
      const int16 = new Int16Array(chunk)
      const buf = this.ctx.createBuffer(1, int16.length, this.sampleRate)
      const data = buf.getChannelData(0)
      for (let i = 0; i < int16.length; i++) data[i] = int16[i] / 32768
      const src = this.ctx.createBufferSource()
      src.buffer = buf
      src.connect(this.analyser || this.ctx.destination)
      const at = Math.max(this.ctx.currentTime, this.nextTime)
      src.start(at)
      this.nextTime = at + buf.duration
      this.sources.push(src)
      src.onended = () => {
        this.sources = this.sources.filter((s) => s !== src)
        if (this.ended && this.sources.length === 0) this.onEnded?.()
      }
    }
  }

  private pump() {
    if (!this.sourceBuffer || this.sourceBuffer.updating || this.mediaSource?.readyState !== "open") return
    const next = this.queue.shift()
    if (next) {
      try {
        this.sourceBuffer.appendBuffer(next)
      } catch {
        /* buffer closed */
      }
    } else if (this.ended) {
      try {
        this.mediaSource?.endOfStream()
      } catch {
        /* ignore */
      }
    }
  }

  end() {
    this.ended = true
    if (this.codec === "mp3") {
      if (this.useMSE) this.pump()
      else if (this.audio) {
        const blob = new Blob(this.blobChunks, { type: "audio/mpeg" })
        this.audio.src = URL.createObjectURL(blob)
        this.audio.play().catch(() => this.onEnded?.())
      }
    } else if (this.codec === "pcm_s16le" && this.sources.length === 0) {
      this.onEnded?.()
    } else if (this.codec === "none") {
      this.onEnded?.()
    }
  }

  stop() {
    if (this.audio) {
      this.audio.pause()
      this.audio.src = ""
      this.audio = null
    }
    this.sources.forEach((s) => {
      try {
        s.stop()
      } catch {
        /* ignore */
      }
    })
    this.sources = []
    this.mediaSource = null
    this.sourceBuffer = null
    this.queue = []
    this.blobChunks = []
    this.ended = true
  }
}
