/* AudioWorklet: downmix to mono, resample to 16 kHz, emit Int16 PCM frames (~20 ms) + an RMS level. */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.targetRate = 16000
    this.ratio = sampleRate / this.targetRate
    this.acc = []
    this.carry = 0
    this.frameSamples = 320 // 20 ms @ 16 kHz
    this.buffer = new Int16Array(0)
  }
  process(inputs) {
    const input = inputs[0]
    if (!input || input.length === 0) return true
    const ch = input[0]
    const n = Math.floor((ch.length - this.carry) / this.ratio)
    const out = new Int16Array(Math.max(0, n))
    let sumsq = 0
    for (let i = 0; i < n; i++) {
      const idx = Math.floor(this.carry + i * this.ratio)
      let s = ch[Math.min(idx, ch.length - 1)]
      if (input.length > 1) s = (s + input[1][Math.min(idx, ch.length - 1)]) / 2
      s = Math.max(-1, Math.min(1, s))
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
      sumsq += s * s
    }
    this.carry = this.carry + n * this.ratio - ch.length
    const merged = new Int16Array(this.buffer.length + out.length)
    merged.set(this.buffer)
    merged.set(out, this.buffer.length)
    let offset = 0
    while (merged.length - offset >= this.frameSamples) {
      const frame = merged.slice(offset, offset + this.frameSamples)
      this.port.postMessage({ type: "frame", pcm: frame.buffer, level: Math.sqrt(sumsq / Math.max(1, n)) }, [frame.buffer])
      offset += this.frameSamples
    }
    this.buffer = merged.slice(offset)
    return true
  }
}
registerProcessor("pcm-processor", PCMProcessor)
