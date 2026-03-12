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

// MARK: - Color Palettes (Default: Purple)

private let purpleBlobColors: [RGBA] = [
    RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.90),
    RGBA(r: 0.388, g: 0.400, b: 0.945, a: 0.80),
    RGBA(r: 0.231, g: 0.510, b: 0.965, a: 0.70),
    RGBA(r: 0.024, g: 0.714, b: 0.831, a: 0.65),
    RGBA(r: 0.655, g: 0.545, b: 0.980, a: 0.55),
    RGBA(r: 0.400, g: 0.300, b: 0.900, a: 0.60),
    RGBA(r: 0.500, g: 0.400, b: 0.950, a: 0.50),
]

private let tealBlobColors: [RGBA] = [
    RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.90),
    RGBA(r: 0.024, g: 0.714, b: 0.831, a: 0.80),
    RGBA(r: 0.204, g: 0.827, b: 0.600, a: 0.70),
    RGBA(r: 0.133, g: 0.827, b: 0.933, a: 0.65),
    RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.55),
    RGBA(r: 0.050, g: 0.800, b: 0.700, a: 0.60),
    RGBA(r: 0.100, g: 0.900, b: 0.500, a: 0.50),
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

// MARK: - Color Palettes (Legal: Amber/Gold)

private let amberBlobColors: [RGBA] = [
    RGBA(r: 0.824, g: 0.549, b: 0.157, a: 0.90),  // warm amber
    RGBA(r: 0.784, g: 0.510, b: 0.137, a: 0.80),  // deep gold
    RGBA(r: 0.855, g: 0.627, b: 0.196, a: 0.70),  // golden
    RGBA(r: 0.745, g: 0.471, b: 0.118, a: 0.65),  // bronze
    RGBA(r: 0.906, g: 0.690, b: 0.275, a: 0.55),  // light gold
    RGBA(r: 0.780, g: 0.490, b: 0.120, a: 0.60),  // dark amber
    RGBA(r: 0.860, g: 0.600, b: 0.200, a: 0.50),  // mid gold
]

private let brightGoldBlobColors: [RGBA] = [
    RGBA(r: 0.961, g: 0.784, b: 0.314, a: 0.90),  // bright gold
    RGBA(r: 0.855, g: 0.667, b: 0.125, a: 0.80),  // rich gold
    RGBA(r: 0.941, g: 0.753, b: 0.235, a: 0.70),  // warm yellow
    RGBA(r: 0.784, g: 0.627, b: 0.157, a: 0.65),  // golden bronze
    RGBA(r: 0.961, g: 0.816, b: 0.376, a: 0.55),  // pale gold
    RGBA(r: 0.880, g: 0.700, b: 0.200, a: 0.60),  // deep gold
    RGBA(r: 0.940, g: 0.780, b: 0.280, a: 0.50),  // mid bright
]

private let amberRing: [Color] = [
    Color(red: 0.831, green: 0.533, blue: 0.039),  // D4880A
    Color(red: 0.784, green: 0.439, blue: 0.125),  // C87020
    Color(red: 0.910, green: 0.627, blue: 0.125),  // E8A020
    Color(red: 0.722, green: 0.525, blue: 0.043),  // B8860B
    Color(red: 0.855, green: 0.667, blue: 0.125),  // DAA520
    Color(red: 0.831, green: 0.533, blue: 0.039),  // D4880A
]

private let brightGoldRing: [Color] = [
    Color(red: 0.961, green: 0.784, blue: 0.314),  // F5C850
    Color(red: 0.855, green: 0.667, blue: 0.125),  // DAA520
    Color(red: 0.910, green: 0.722, blue: 0.188),  // E8B830
    Color(red: 0.784, green: 0.627, blue: 0.125),  // C8A020
    Color(red: 0.941, green: 0.816, blue: 0.376),  // F0D060
    Color(red: 0.961, green: 0.784, blue: 0.314),  // F5C850
]

// MARK: - OrbView

struct OrbView: View {
    let state: ConnectionState
    let audioLevel: Float
    var isLegal: Bool = false

    @State private var startDate = Date()
    @State private var colorT: Float = 0
    @State private var smoothAudio: Float = 0
    @State private var targetColorT: Float = 0
    @State private var breathPhase: Float = 0

    // Resolved palettes based on theme
    private var idleBlobColors: [RGBA] { isLegal ? amberBlobColors : purpleBlobColors }
    private var activeBlobColors: [RGBA] { isLegal ? brightGoldBlobColors : tealBlobColors }
    private var idleRingColors: [Color] { isLegal ? amberRing : purpleRing }
    private var activeRingColors: [Color] { isLegal ? brightGoldRing : tealRing }

    var body: some View {
        TimelineView(.animation) { timeline in
            let elapsed = Float(timeline.date.timeIntervalSince(startDate))

            Canvas { context, size in
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

        let speed: Float = isConnecting ? 2.8 : (isSpeaking ? 1.6 + audio * 2.0 : 1.0)
        let t = elapsed * speed
        let breath = 1.0 + 0.012 * sin(elapsed * 1.8) + 0.008 * sin(elapsed * 2.7)
        let audioScale = 1.0 + CGFloat(audio) * 0.08
        let orbRadius = baseRadius * CGFloat(breath) * audioScale
        let center = CGPoint(x: cx, y: cy)

        let glowPulse = Float(0.7 + 0.3 * (0.5 + 0.5 * sin(Double(elapsed) * 1.2)))
        let glowIntensity = CGFloat(glowPulse) * (isActive ? 1.0 : 0.3)

        // Idle base colors based on theme
        let idleDeepGlow = isLegal
            ? RGBA(r: 0.55, g: 0.35, b: 0.10, a: 0.12)
            : RGBA(r: 0.35, g: 0.20, b: 0.85, a: 0.12)
        let activeDeepGlow = isLegal
            ? RGBA(r: 0.70, g: 0.55, b: 0.15, a: 0.12)
            : RGBA(r: 0.05, g: 0.75, b: 0.45, a: 0.12)

        let idleMidGlow = isLegal
            ? RGBA(r: 0.824, g: 0.549, b: 0.157, a: 0.22)
            : RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.22)
        let activeMidGlow = isLegal
            ? RGBA(r: 0.961, g: 0.784, b: 0.314, a: 0.22)
            : RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.22)

        let idleInnerGlow = isLegal
            ? RGBA(r: 0.824, g: 0.549, b: 0.157, a: 0.35)
            : RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.35)
        let activeInnerGlow = isLegal
            ? RGBA(r: 0.961, g: 0.784, b: 0.314, a: 0.35)
            : RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.35)

        // ========== LAYER 1: Deep ambient glow ==========
        let deepGlow = idleDeepGlow.lerp(to: activeDeepGlow, t: colorT)
        let deepRadius = orbRadius * 2.8

        var g1 = context
        g1.opacity = glowIntensity * 0.8
        g1.fill(circle(center, deepRadius), with: .radialGradient(
            Gradient(colors: [deepGlow.color, deepGlow.color.opacity(0.3), .clear]),
            center: center, startRadius: 0, endRadius: deepRadius
        ))

        // ========== LAYER 2: Mid glow ==========
        let midGlow = idleMidGlow.lerp(to: activeMidGlow, t: colorT)
        let midRadius = orbRadius * 1.8

        var g2 = context
        g2.opacity = glowIntensity
        g2.fill(circle(center, midRadius), with: .radialGradient(
            Gradient(colors: [midGlow.color, midGlow.color.opacity(0.4), .clear]),
            center: center, startRadius: orbRadius * 0.3, endRadius: midRadius
        ))

        // ========== LAYER 3: Inner glow halo ==========
        let innerGlow = idleInnerGlow.lerp(to: activeInnerGlow, t: colorT)
        let innerRadius = orbRadius * 1.35

        var g3 = context
        g3.opacity = glowIntensity * 1.2
        g3.fill(circle(center, innerRadius), with: .radialGradient(
            Gradient(colors: [innerGlow.color, .clear]),
            center: center, startRadius: orbRadius * 0.7, endRadius: innerRadius
        ))

        // ========== LAYER 4: Rotating ring ==========
        let ringAngle = fmod(Double(elapsed) * 55.0, 360.0)
        let ringColors = colorT > 0.5 ? activeRingColors : idleRingColors
        let ringPulse = 0.5 + 0.15 * sin(Double(elapsed) * 2.0) + Double(audio) * 0.35

        var r1 = context
        r1.opacity = 0.25 * Double(glowIntensity)
        r1.fill(circle(center, orbRadius * 1.18), with: .conicGradient(
            Gradient(colors: ringColors),
            center: center, angle: .degrees(ringAngle)
        ))

        var r2 = context
        r2.opacity = ringPulse * Double(glowIntensity)
        r2.fill(circle(center, orbRadius * 1.06), with: .conicGradient(
            Gradient(colors: ringColors),
            center: center, angle: .degrees(ringAngle + 180)
        ))

        // ========== LAYER 5: Orb body ==========
        let orbDarkBase = isLegal
            ? Color(red: 0.05, green: 0.03, blue: 0.02)
            : Color(red: 0.03, green: 0.03, blue: 0.07)
        context.fill(circle(center, orbRadius), with: .color(orbDarkBase))

        let idleBg = isLegal
            ? RGBA(r: 0.10, g: 0.06, b: 0.03, a: 1)
            : RGBA(r: 0.12, g: 0.07, b: 0.27, a: 1)
        let activeBg = isLegal
            ? RGBA(r: 0.10, g: 0.08, b: 0.03, a: 1)
            : RGBA(r: 0.04, g: 0.12, b: 0.10, a: 1)
        let bgA = idleBg.lerp(to: activeBg, t: colorT)
        context.fill(circle(center, orbRadius), with: .radialGradient(
            Gradient(colors: [bgA.color, orbDarkBase]),
            center: CGPoint(x: cx * 0.92, y: cy * 0.85),
            startRadius: 0, endRadius: orbRadius
        ))

        // ========== LAYER 6: Organic blobs with compound motion ==========
        for i in blobs.indices {
            let b = blobs[i]
            let blobRadius = orbRadius * CGFloat(b.size) * (1.0 + CGFloat(audio) * 0.25)

            let px = CGFloat(sin(t * b.xFreq + b.xPhase) * b.xAmp + sin(t * b.x2Freq + b.xPhase * 2.1) * b.x2Amp)
            let py = CGFloat(cos(t * b.yFreq + b.yPhase) * b.yAmp + cos(t * b.y2Freq + b.yPhase * 1.7) * b.y2Amp)

            let bx = cx + px * orbRadius / 150.0
            let by = cy + py * orbRadius / 150.0
            let blobCenter = CGPoint(x: bx, y: by)

            let blobColor = idleBlobColors[i].lerp(to: activeBlobColors[i], t: colorT)

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
            let idleWave = isLegal
                ? RGBA(r: 0.824, g: 0.549, b: 0.157, a: 1)
                : RGBA(r: 0.545, g: 0.400, b: 0.980, a: 1)
            let activeWave = isLegal
                ? RGBA(r: 0.961, g: 0.784, b: 0.314, a: 1)
                : RGBA(r: 0.078, g: 0.900, b: 0.600, a: 1)

            let waveCount = 3
            for w in 0..<waveCount {
                let wPhase = Float(w) * 2.1 + elapsed * 3.0
                let wRadius = orbRadius * (0.5 + CGFloat(audio) * 0.6 + CGFloat(sin(wPhase)) * 0.15)
                let wAlpha = Float(audio) * 0.35 * (1.0 - Float(w) * 0.25)

                let waveBase = RGBA(r: idleWave.r, g: idleWave.g, b: idleWave.b, a: wAlpha)
                let waveTgt = RGBA(r: activeWave.r, g: activeWave.g, b: activeWave.b, a: wAlpha)
                let waveColor = waveBase.lerp(to: waveTgt, t: colorT)

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
        let idleRim = isLegal
            ? RGBA(r: 0.824, g: 0.549, b: 0.157, a: 0.30)
            : RGBA(r: 0.545, g: 0.361, b: 0.965, a: 0.30)
        let activeRim = isLegal
            ? RGBA(r: 0.961, g: 0.784, b: 0.314, a: 0.30)
            : RGBA(r: 0.078, g: 0.945, b: 0.584, a: 0.30)
        let rimColor = idleRim.lerp(to: activeRim, t: colorT)
        let rimAlpha = 0.4 + Double(audio) * 0.5

        var rc = context
        rc.opacity = rimAlpha
        rc.fill(circle(center, orbRadius * 1.25), with: .radialGradient(
            Gradient(colors: [.clear, rimColor.color, .clear]),
            center: center, startRadius: orbRadius * 0.9, endRadius: orbRadius * 1.25
        ))

        // ========== LAYER 11: Floating particles ==========
        if isActive {
            let idleParticle = isLegal
                ? RGBA(r: 0.855, g: 0.667, b: 0.125, a: 1)
                : RGBA(r: 0.655, g: 0.545, b: 0.980, a: 1)
            let activeParticle = isLegal
                ? RGBA(r: 0.961, g: 0.784, b: 0.314, a: 1)
                : RGBA(r: 0.078, g: 0.945, b: 0.584, a: 1)

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
                let pAlpha = Float(0.15 + 0.15 * sin(Double(elapsed) * 2.0 + Double(fp) * 0.9)
                    + Double(audio) * 0.3)

                let pColor = RGBA(r: idleParticle.r, g: idleParticle.g, b: idleParticle.b, a: pAlpha)
                    .lerp(to: RGBA(r: activeParticle.r, g: activeParticle.g, b: activeParticle.b, a: pAlpha), t: colorT)

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

                let dotColor = isLegal ? Color(red: 0.961, green: 0.784, blue: 0.314) : Color.white

                var dc = context
                dc.opacity = dotAlpha
                let dotCenter = CGPoint(x: dx, y: dy)
                dc.fill(circle(dotCenter, 3), with: .radialGradient(
                    Gradient(colors: [dotColor, .clear]),
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
