/**
 * AudioWorkletProcessor that converts the browser's native mic audio
 * (Float32, whatever sample rate the AudioContext ended up with) into
 * PCM16 mono at the target sample rate the active realtime voice provider
 * requires (OpenAI: 24kHz, Gemini Live: 16kHz -- see
 * backend/app/services/realtime/capabilities.py). Defaults to 24000 if the
 * caller doesn't pass processorOptions.targetSampleRate.
 *
 * Runs on the audio rendering thread, so this file must have zero
 * dependencies and stay allocation-light per process() call.
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super()
    this.targetSampleRate = options?.processorOptions?.targetSampleRate || 24000
    // `sampleRate` is a global provided by AudioWorkletGlobalScope -- the
    // *actual* rate the AudioContext negotiated, which may not match
    // targetSampleRate (Safari in particular can ignore the constructor
    // hint, and the two are independent by design -- see the AudioContext
    // sampleRate hint in useRealtimeSpeakingSession.ts).
    this.ratio = sampleRate / this.targetSampleRate
    // Fractional read position carried across process() calls so the
    // downsampling stays continuous across 128-sample render-quantum blocks
    // instead of resetting phase (and introducing clicks) at every boundary.
    this.readPos = 0
  }

  process(inputs) {
    const channelData = inputs[0] && inputs[0][0]
    if (!channelData || channelData.length === 0) return true

    const outputLength = Math.floor(channelData.length / this.ratio)
    if (outputLength <= 0) return true

    const pcm16 = new Int16Array(outputLength)
    let pos = this.readPos
    for (let i = 0; i < outputLength; i++) {
      const idx = Math.floor(pos)
      const nextIdx = Math.min(idx + 1, channelData.length - 1)
      const frac = pos - idx
      const sample = channelData[idx] * (1 - frac) + channelData[nextIdx] * frac
      const clamped = Math.max(-1, Math.min(1, sample))
      pcm16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff
      pos += this.ratio
    }
    this.readPos = pos - channelData.length

    this.port.postMessage(pcm16.buffer, [pcm16.buffer])
    return true
  }
}

registerProcessor('pcm-processor', PCMProcessor)
