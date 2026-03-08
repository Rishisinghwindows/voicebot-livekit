import AVFoundation
import LiveKit

class AudioAnalyzer: @unchecked Sendable, AudioRenderer {
    private let lock = NSLock()
    private var _level: Float = 0
    private var smoothedLevel: Float = 0
    private let lerpFactor: Float = 0.15
    private var attachedTrack: (any AudioTrackProtocol)?
    private var renderCount = 0

    var level: Float {
        lock.lock()
        defer { lock.unlock() }
        return _level
    }

    func attachToTrack(_ track: any AudioTrackProtocol) {
        detach()
        track.add(audioRenderer: self)
        lock.lock()
        attachedTrack = track
        renderCount = 0
        lock.unlock()
        print("[AudioAnalyzer] Attached to track")
    }

    func detach() {
        lock.lock()
        let track = attachedTrack
        attachedTrack = nil
        smoothedLevel = 0
        _level = 0
        lock.unlock()
        track?.remove(audioRenderer: self)
    }

    func render(pcmBuffer: AVAudioPCMBuffer) {
        let rms = calculateRms(buffer: pcmBuffer)
        lock.lock()
        renderCount += 1
        smoothedLevel += (rms - smoothedLevel) * lerpFactor
        _level = smoothedLevel
        // Log first few renders to debug
        if renderCount <= 3 {
            let format = pcmBuffer.format
            print("[AudioAnalyzer] render #\(renderCount): rms=\(rms), smoothed=\(smoothedLevel), format=\(format.commonFormat.rawValue), channels=\(format.channelCount), rate=\(format.sampleRate), frames=\(pcmBuffer.frameLength)")
        }
        lock.unlock()
    }

    private func calculateRms(buffer: AVAudioPCMBuffer) -> Float {
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else { return 0 }

        var sumSquares: Float = 0

        // Try float32 first
        if let channelData = buffer.floatChannelData {
            let samples = channelData[0]
            for i in 0..<frameLength {
                let sample = samples[i]
                sumSquares += sample * sample
            }
        }
        // Try int16
        else if let channelData = buffer.int16ChannelData {
            let samples = channelData[0]
            for i in 0..<frameLength {
                let sample = Float(samples[i]) / Float(Int16.max)
                sumSquares += sample * sample
            }
        }
        // Try int32
        else if let channelData = buffer.int32ChannelData {
            let samples = channelData[0]
            for i in 0..<frameLength {
                let sample = Float(samples[i]) / Float(Int32.max)
                sumSquares += sample * sample
            }
        }
        else {
            return 0
        }

        let rms = sqrt(sumSquares / Float(frameLength))
        // Amplify and clamp
        return min(rms * 4.0, 1.0)
    }
}
