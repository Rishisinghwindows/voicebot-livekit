import SwiftUI

// MARK: - RGBA Helper

private struct RGBA {
    let r: Float, g: Float, b: Float, a: Float

    func lerp(to other: RGBA, t: Float) -> RGBA {
        RGBA(
            r: r + (other.r - r) * t,
            g: g + (other.g - g) * t,
            b: b + (other.b - b) * t,
            a: a + (other.a - a) * t
        )
    }

    var color: Color {
        Color(.sRGB, red: Double(r), green: Double(g), blue: Double(b), opacity: Double(a))
    }
}

// MARK: - Blob Config

private struct BlobConfig {
    let xFreq: Float, xPhase: Float
    let yFreq: Float, yPhase: Float
    let xAmp: Float, yAmp: Float
    let size: Float
    // Secondary oscillation for organic movement
    let x2Freq: Float, y2Freq: Float
    let x2Amp: Float, y2Amp: Float
}

private let blobs: [BlobConfig] = [
    BlobConfig(xFreq: 0.35, xPhase: 0.0, yFreq: 0.28, yPhase: 0.5, xAmp: 55, yAmp: 45, size: 0.82,
               x2Freq: 0.13, y2Freq: 0.17, x2Amp: 20, y2Amp: 15),
    BlobConfig(xFreq: 0.25, xPhase: 1.5, yFreq: 0.32, yPhase: 2.0, xAmp: 50, yAmp: 50, size: 0.72,
               x2Freq: 0.11, y2Freq: 0.19, x2Amp: 18, y2Amp: 22),
    BlobConfig(xFreq: 0.30, xPhase: 3.0, yFreq: 0.22, yPhase: 3.5, xAmp: 40, yAmp: 40, size: 0.65,
               x2Freq: 0.15, y2Freq: 0.12, x2Amp: 15, y2Amp: 18),
    BlobConfig(xFreq: 0.20, xPhase: 4.5, yFreq: 0.35, yPhase: 5.0, xAmp: 45, yAmp: 35, size: 0.55,
               x2Freq: 0.18, y2Freq: 0.14, x2Amp: 12, y2Amp: 20),
    BlobConfig(xFreq: 0.28, xPhase: 5.5, yFreq: 0.25, yPhase: 6.2, xAmp: 35, yAmp: 45, size: 0.45,
               x2Freq: 0.16, y2Freq: 0.21, x2Amp: 16, y2Amp: 14),
    BlobConfig(xFreq: 0.22, xPhase: 2.2, yFreq: 0.30, yPhase: 1.1, xAmp: 48, yAmp: 38, size: 0.60,
               x2Freq: 0.14, y2Freq: 0.16, x2Amp: 14, y2Amp: 16),
    BlobConfig(xFreq: 0.33, xPhase: 4.0, yFreq: 0.18, yPhase: 4.8, xAmp: 30, yAmp: 50, size: 0.50,
               x2Freq: 0.20, y2Freq: 0.10, x2Amp: 10, y2Amp: 12),
]

// MARK: - Color Palettes

private let purpleBlobColors: [RGBA] = [
    RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.90),  // vibrant purple
    RGBA(r: 0.388, g: 0.400, b: 0.945, a: 0.80),  // indigo
    RGBA(r: 0.231, g: 0.510, b: 0.965, a: 0.70),  // blue
    RGBA(r: 0.024, g: 0.714, b: 0.831, a: 0.65),  // cyan
    RGBA(r: 0.655, g: 0.545, b: 0.980, a: 0.55),  // lavender
    RGBA(r: 0.400, g: 0.300, b: 0.900, a: 0.60),  // deep purple
    RGBA(r: 0.500, g: 0.400, b: 0.950, a: 0.50),  // mid purple
]

private let tealBlobColors: [RGBA] = [
    RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.90),  // bright green
    RGBA(r: 0.024, g: 0.714, b: 0.831, a: 0.80),  // cyan
    RGBA(r: 0.204, g: 0.827, b: 0.600, a: 0.70),  // emerald
    RGBA(r: 0.133, g: 0.827, b: 0.933, a: 0.65),  // light cyan
    RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.55),  // mint
    RGBA(r: 0.050, g: 0.800, b: 0.700, a: 0.60),  // teal
    RGBA(r: 0.100, g: 0.900, b: 0.500, a: 0.50),  // green
]

private let purpleRing: [Color] = [
    Color(red: 0.545, green: 0.361, blue: 0.965),
    Color(red: 0.388, green: 0.400, blue: 0.945),
    Color(red: 0.231, green: 0.510, blue: 0.965),
    Color(red: 0.024, green: 0.714, blue: 0.831),
    Color(red: 0.655, green: 0.545, blue: 0.980),
    Color(red: 0.545, green: 0.361, blue: 0.965),
]

private let tealRing: [Color] = [
    Color(red: 0.078, green: 0.945, blue: 0.584),
    Color(red: 0.024, green: 0.714, blue: 0.831),
    Color(red: 0.231, green: 0.510, blue: 0.965),
    Color(red: 0.133, green: 0.827, blue: 0.933),
    Color(red: 0.063, green: 0.725, blue: 0.506),
    Color(red: 0.078, green: 0.945, blue: 0.584),
]

// MARK: - OrbView

struct OrbView: View {
    let state: ConnectionState
    let audioLevel: Float

    @State private var startDate = Date()
    @State private var colorT: Float = 0
    @State private var smoothAudio: Float = 0
    @State private var targetColorT: Float = 0
    @State private var breathPhase: Float = 0

    var body: some View {
        TimelineView(.animation) { timeline in
            let elapsed = Float(timeline.date.timeIntervalSince(startDate))

            Canvas { context, size in
                // Manually interpolate color transition for smooth animation
                let dt: Float = 1.0 / 60.0
                let currentColorT = lerpValue(colorT, towards: targetColorT, speed: 2.5 * dt)
                let currentAudio = lerpValue(smoothAudio, towards: audioLevel, speed: 12.0 * dt)

                drawOrb(
                    context: &context,
                    size: size,
                    elapsed: elapsed,
                    colorT: currentColorT,
                    audio: currentAudio,
                    state: state
                )

                // Schedule state update after draw
                DispatchQueue.main.async {
                    self.colorT = currentColorT
                    self.smoothAudio = currentAudio
                    self.breathPhase = elapsed
                }
            }
        }
        .frame(width: 320, height: 320)
        .onChange(of: state) { newState in
            targetColorT = (newState == .speaking) ? 1.0 : 0.0
        }
    }

    private func lerpValue(_ current: Float, towards target: Float, speed: Float) -> Float {
        current + (target - current) * min(speed, 1.0)
    }

    // MARK: - Draw

    private func drawOrb(
        context: inout GraphicsContext,
        size: CGSize,
        elapsed: Float,
        colorT: Float,
        audio: Float,
        state: ConnectionState
    ) {
        let cx = size.width / 2
        let cy = size.height / 2
        let baseRadius = size.width * 0.34
        let isActive = state != .idle && state != .disconnected
        let isConnecting = state == .connecting
        let isSpeaking = state == .speaking

        // Speed & breathing
        let speed: Float = isConnecting ? 2.8 : (isSpeaking ? 1.6 + audio * 2.0 : 1.0)
        let t = elapsed * speed
        let breath = 1.0 + 0.012 * sin(elapsed * 1.8) + 0.008 * sin(elapsed * 2.7)
        let audioScale = 1.0 + CGFloat(audio) * 0.08
        let orbRadius = baseRadius * CGFloat(breath) * audioScale
        let center = CGPoint(x: cx, y: cy)

        // Glow intensity
        let glowPulse = Float(0.7 + 0.3 * (0.5 + 0.5 * sin(Double(elapsed) * 1.2)))
        let glowIntensity = CGFloat(glowPulse) * (isActive ? 1.0 : 0.3)

        // ========== LAYER 1: Deep ambient glow ==========
        let deepGlow = RGBA(r: 0.35, g: 0.20, b: 0.85, a: 0.12)
            .lerp(to: RGBA(r: 0.05, g: 0.75, b: 0.45, a: 0.12), t: colorT)
        let deepRadius = orbRadius * 2.8

        var g1 = context
        g1.opacity = glowIntensity * 0.8
        g1.fill(circle(center, deepRadius), with: .radialGradient(
            Gradient(colors: [deepGlow.color, deepGlow.color.opacity(0.3), .clear]),
            center: center, startRadius: 0, endRadius: deepRadius
        ))

        // ========== LAYER 2: Mid glow ==========
        let midGlow = RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.22)
            .lerp(to: RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.22), t: colorT)
        let midRadius = orbRadius * 1.8

        var g2 = context
        g2.opacity = glowIntensity
        g2.fill(circle(center, midRadius), with: .radialGradient(
            Gradient(colors: [midGlow.color, midGlow.color.opacity(0.4), .clear]),
            center: center, startRadius: orbRadius * 0.3, endRadius: midRadius
        ))

        // ========== LAYER 3: Inner glow halo ==========
        let innerGlow = RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.35)
            .lerp(to: RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.35), t: colorT)
        let innerRadius = orbRadius * 1.35

        var g3 = context
        g3.opacity = glowIntensity * 1.2
        g3.fill(circle(center, innerRadius), with: .radialGradient(
            Gradient(colors: [innerGlow.color, .clear]),
            center: center, startRadius: orbRadius * 0.7, endRadius: innerRadius
        ))

        // ========== LAYER 4: Rotating ring ==========
        let ringAngle = fmod(Double(elapsed) * 55.0, 360.0)
        let ringColors = colorT > 0.5 ? tealRing : purpleRing
        let ringPulse = 0.5 + 0.15 * sin(Double(elapsed) * 2.0) + Double(audio) * 0.35

        // Soft outer ring
        var r1 = context
        r1.opacity = 0.25 * Double(glowIntensity)
        r1.fill(circle(center, orbRadius * 1.18), with: .conicGradient(
            Gradient(colors: ringColors),
            center: center, angle: .degrees(ringAngle)
        ))

        // Sharp inner ring
        var r2 = context
        r2.opacity = ringPulse * Double(glowIntensity)
        r2.fill(circle(center, orbRadius * 1.06), with: .conicGradient(
            Gradient(colors: ringColors),
            center: center, angle: .degrees(ringAngle + 180)
        ))

        // ========== LAYER 5: Orb body ==========
        // Dark base
        context.fill(circle(center, orbRadius),
            with: .color(Color(red: 0.03, green: 0.03, blue: 0.07)))

        // Colored gradient base
        let bgA = RGBA(r: 0.12, g: 0.07, b: 0.27, a: 1)
            .lerp(to: RGBA(r: 0.04, g: 0.12, b: 0.10, a: 1), t: colorT)
        context.fill(circle(center, orbRadius), with: .radialGradient(
            Gradient(colors: [bgA.color, Color(red: 0.03, green: 0.03, blue: 0.07)]),
            center: CGPoint(x: cx * 0.92, y: cy * 0.85),
            startRadius: 0, endRadius: orbRadius
        ))

        // ========== LAYER 6: Organic blobs with compound motion ==========
        for i in blobs.indices {
            let b = blobs[i]
            let blobRadius = orbRadius * CGFloat(b.size) * (1.0 + CGFloat(audio) * 0.25)

            // Compound sine motion for organic feel
            let px = CGFloat(sin(t * b.xFreq + b.xPhase) * b.xAmp + sin(t * b.x2Freq + b.xPhase * 2.1) * b.x2Amp)
            let py = CGFloat(cos(t * b.yFreq + b.yPhase) * b.yAmp + cos(t * b.y2Freq + b.yPhase * 1.7) * b.y2Amp)

            let bx = cx + px * orbRadius / 150.0
            let by = cy + py * orbRadius / 150.0
            let blobCenter = CGPoint(x: bx, y: by)

            let blobColor = purpleBlobColors[i].lerp(to: tealBlobColors[i], t: colorT)

            var bc = context
            bc.blendMode = .screen
            bc.fill(circle(blobCenter, blobRadius), with: .radialGradient(
                Gradient(stops: [
                    .init(color: blobColor.color, location: 0),
                    .init(color: blobColor.color.opacity(0.6), location: 0.4),
                    .init(color: blobColor.color.opacity(0.15), location: 0.75),
                    .init(color: .clear, location: 1.0),
                ]),
                center: blobCenter, startRadius: 0, endRadius: blobRadius
            ))
        }

        // ========== LAYER 7: Audio-reactive energy waves ==========
        if audio > 0.02 && isActive {
            let waveCount = 3
            for w in 0..<waveCount {
                let wPhase = Float(w) * 2.1 + elapsed * 3.0
                let wRadius = orbRadius * (0.5 + CGFloat(audio) * 0.6 + CGFloat(sin(wPhase)) * 0.15)
                let wAlpha = Double(audio) * 0.35 * (1.0 - Double(w) * 0.25)

                let waveColor = RGBA(r: 0.545, g: 0.400, b: 0.980, a: Float(wAlpha))
                    .lerp(to: RGBA(r: 0.078, g: 0.900, b: 0.600, a: Float(wAlpha)), t: colorT)

                var wc = context
                wc.blendMode = .screen
                wc.fill(circle(center, wRadius), with: .radialGradient(
                    Gradient(colors: [waveColor.color, waveColor.color.opacity(0.3), .clear]),
                    center: center, startRadius: wRadius * 0.6, endRadius: wRadius
                ))
            }
        }

        // ========== LAYER 8: Glass highlight ==========
        context.fill(circle(center, orbRadius), with: .radialGradient(
            Gradient(stops: [
                .init(color: Color.white.opacity(0.30), location: 0),
                .init(color: Color.white.opacity(0.08), location: 0.35),
                .init(color: .clear, location: 0.7),
            ]),
            center: CGPoint(x: cx * 0.78, y: cy * 0.68),
            startRadius: 0, endRadius: orbRadius * 0.65
        ))

        // Secondary subtle highlight
        context.fill(circle(center, orbRadius), with: .radialGradient(
            Gradient(colors: [Color.white.opacity(0.06), .clear]),
            center: CGPoint(x: cx * 1.15, y: cy * 1.25),
            startRadius: 0, endRadius: orbRadius * 0.4
        ))

        // ========== LAYER 9: Edge vignette ==========
        context.fill(circle(center, orbRadius), with: .radialGradient(
            Gradient(stops: [
                .init(color: .clear, location: 0.5),
                .init(color: Color.black.opacity(0.25), location: 0.85),
                .init(color: Color.black.opacity(0.55), location: 1.0),
            ]),
            center: center, startRadius: 0, endRadius: orbRadius
        ))

        // ========== LAYER 10: Rim light ==========
        let rimColor = RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.30)
            .lerp(to: RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.30), t: colorT)
        let rimAlpha = 0.4 + Double(audio) * 0.5

        var rc = context
        rc.opacity = rimAlpha
        rc.fill(circle(center, orbRadius * 1.25), with: .radialGradient(
            Gradient(colors: [.clear, rimColor.color, .clear]),
            center: center, startRadius: orbRadius * 0.9, endRadius: orbRadius * 1.25
        ))

        // ========== LAYER 11: Floating particles ==========
        if isActive {
            let particleCount = 12
            for p in 0..<particleCount {
                let fp = Float(p)
                let angle = fp * (2.0 * .pi / Float(particleCount)) + elapsed * (0.15 + fp * 0.02)
                let dist = orbRadius * (1.15 + CGFloat(sin(elapsed * 0.8 + fp * 0.7)) * 0.2)
                    + CGFloat(audio) * orbRadius * 0.15
                let px = cx + cos(CGFloat(angle)) * dist
                let py = cy + sin(CGFloat(angle)) * dist
                let pSize: CGFloat = 1.5 + CGFloat(sin(elapsed * 1.5 + fp * 1.3)) * 1.0
                    + CGFloat(audio) * 3.0
                let pAlpha = 0.15 + 0.15 * sin(Double(elapsed) * 2.0 + Double(fp) * 0.9)
                    + Double(audio) * 0.3

                let pColor = RGBA(r: 0.655, g: 0.545, b: 0.980, a: Float(pAlpha))
                    .lerp(to: RGBA(r: 0.078, g: 0.945, b: 0.584, a: Float(pAlpha)), t: colorT)

                var pc = context
                pc.blendMode = .screen
                let particleCenter = CGPoint(x: px, y: py)
                pc.fill(circle(particleCenter, pSize * 3), with: .radialGradient(
                    Gradient(colors: [pColor.color, .clear]),
                    center: particleCenter, startRadius: 0, endRadius: pSize * 3
                ))
            }
        }

        // ========== LAYER 12: Connecting spinner dots ==========
        if isConnecting {
            let dotCount = 8
            for d in 0..<dotCount {
                let fd = Float(d)
                let angle = fd * (2.0 * .pi / Float(dotCount)) + elapsed * 4.0
                let dist = orbRadius * 1.22
                let dx = cx + cos(CGFloat(angle)) * dist
                let dy = cy + sin(CGFloat(angle)) * dist
                let dotAlpha = 0.3 + 0.4 * (0.5 + 0.5 * sin(Double(angle) - Double(elapsed) * 6.0))

                var dc = context
                dc.opacity = dotAlpha
                let dotCenter = CGPoint(x: dx, y: dy)
                dc.fill(circle(dotCenter, 3), with: .radialGradient(
                    Gradient(colors: [Color.white, .clear]),
                    center: dotCenter, startRadius: 0, endRadius: 3
                ))
            }
        }
    }

    // MARK: - Helpers

    private func circle(_ center: CGPoint, _ radius: CGFloat) -> Path {
        Path(ellipseIn: CGRect(
            x: center.x - radius, y: center.y - radius,
            width: radius * 2, height: radius * 2
        ))
    }
}
