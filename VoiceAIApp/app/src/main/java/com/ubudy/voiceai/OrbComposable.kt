package com.ubudy.voiceai

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.*
import androidx.compose.ui.unit.dp
import kotlin.math.*

data class BlobConfig(
    val xFreq: Float, val xPhase: Float,
    val yFreq: Float, val yPhase: Float,
    val xAmp: Float, val yAmp: Float,
    val size: Float,
    val x2Freq: Float, val y2Freq: Float,
    val x2Amp: Float, val y2Amp: Float
)

private val blobConfigs = listOf(
    BlobConfig(0.35f, 0f, 0.28f, 0.5f, 55f, 45f, 0.82f, 0.13f, 0.17f, 20f, 15f),
    BlobConfig(0.25f, 1.5f, 0.32f, 2.0f, 50f, 50f, 0.72f, 0.11f, 0.19f, 18f, 22f),
    BlobConfig(0.30f, 3.0f, 0.22f, 3.5f, 40f, 40f, 0.65f, 0.15f, 0.12f, 15f, 18f),
    BlobConfig(0.20f, 4.5f, 0.35f, 5.0f, 45f, 35f, 0.55f, 0.18f, 0.14f, 12f, 20f),
    BlobConfig(0.28f, 5.5f, 0.25f, 6.2f, 35f, 45f, 0.45f, 0.16f, 0.21f, 16f, 14f),
    BlobConfig(0.22f, 2.2f, 0.30f, 1.1f, 48f, 38f, 0.60f, 0.14f, 0.16f, 14f, 16f),
    BlobConfig(0.33f, 4.0f, 0.18f, 4.8f, 30f, 50f, 0.50f, 0.20f, 0.10f, 10f, 12f),
)

// Default purple palette (7 blobs)
private val purpleBlobs = listOf(
    Color(0xE68B5CF6), Color(0xCC6366F1), Color(0xB33B82F6),
    Color(0x9906B6D4), Color(0x80A78BFA), Color(0xB38B5CF6), Color(0x996366F1)
)
private val tealBlobs = listOf(
    Color(0xE614F195), Color(0xCC06B6D4), Color(0xB334D399),
    Color(0xA622D3EE), Color(0x8014F195), Color(0xB310B981), Color(0x9906B6D4)
)

// Legal amber/gold palette (7 blobs)
private val amberBlobs = listOf(
    Color(0xE6D28C28), Color(0xCCC88220), Color(0xB3DAA030),
    Color(0x99BE7818), Color(0x80E8B045), Color(0xB3D4880A), Color(0x99C87020)
)
private val brightGoldBlobs = listOf(
    Color(0xE6F5C850), Color(0xCCDAA520), Color(0xB3F0C03C),
    Color(0x99C8A020), Color(0x80F5D060), Color(0xB3F5B43C), Color(0x99DAA520)
)

@Composable
fun AnimatedOrb(
    state: ConnectionState,
    audioLevel: Float,
    isLegal: Boolean = false,
    modifier: Modifier = Modifier
) {
    val infiniteTransition = rememberInfiniteTransition(label = "orb")

    val time by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1000f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1_000_000, easing = LinearEasing)
        ),
        label = "time"
    )

    val glowPulse by infiniteTransition.animateFloat(
        initialValue = 0.7f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2500, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "glow"
    )

    val isSpeaking = state == ConnectionState.SPEAKING
    val isConnecting = state == ConnectionState.CONNECTING
    val isActive = state != ConnectionState.IDLE && state != ConnectionState.DISCONNECTED

    val smoothedAudio by animateFloatAsState(
        targetValue = audioLevel,
        animationSpec = tween(durationMillis = 80),
        label = "audio"
    )

    val colorTransition by animateFloatAsState(
        targetValue = if (isSpeaking) 1f else 0f,
        animationSpec = tween(durationMillis = 800),
        label = "color"
    )

    val speedMultiplier = when {
        isConnecting -> 2.8f
        isSpeaking -> 1.6f + smoothedAudio * 2.0f
        else -> 1f
    }

    val idleBlobs = if (isLegal) amberBlobs else purpleBlobs
    val activeBlobs = if (isLegal) brightGoldBlobs else tealBlobs

    Canvas(modifier = modifier.size(320.dp)) {
        val cx = size.width / 2
        val cy = size.height / 2
        val baseRadius = size.width * 0.34f
        val t = time * speedMultiplier

        // Breathing effect
        val breath = 1f + 0.012f * sin(time * 1.8f) + 0.008f * sin(time * 2.7f)
        val audioScale = 1f + smoothedAudio * 0.08f
        val orbRadius = baseRadius * breath * audioScale
        val center = Offset(cx, cy)

        val glowIntensity = glowPulse * if (isActive) 1f else 0.3f

        // === LAYER 1: Deep ambient glow ===
        val deepIdle = if (isLegal) Color(0x1FD28C28) else Color(0x1F8B5CF6)
        val deepActive = if (isLegal) Color(0x1FF5C850) else Color(0x1F14F195)
        val deepGlow = lerp(deepIdle, deepActive, colorTransition)
        val deepRadius = orbRadius * 2.8f
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(deepGlow, deepGlow.copy(alpha = 0.3f), Color.Transparent),
                center = center,
                radius = deepRadius
            ),
            radius = deepRadius,
            center = center,
            alpha = glowIntensity * 0.8f
        )

        // === LAYER 2: Mid glow ===
        val midIdle = if (isLegal) Color(0x47D28C28) else Color(0x478B5CF6)
        val midActive = if (isLegal) Color(0x47F5C850) else Color(0x4714F195)
        val midGlow = lerp(midIdle, midActive, colorTransition)
        val midRadius = orbRadius * 1.8f
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(midGlow, midGlow.copy(alpha = 0.4f), Color.Transparent),
                center = center,
                radius = midRadius
            ),
            radius = midRadius,
            center = center,
            alpha = glowIntensity
        )

        // === LAYER 3: Inner glow halo ===
        val innerIdle = if (isLegal) Color(0x59D28C28) else Color(0x598B5CF6)
        val innerActive = if (isLegal) Color(0x59F5C850) else Color(0x5914F195)
        val innerGlow = lerp(innerIdle, innerActive, colorTransition)
        val innerRadius = orbRadius * 1.35f
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(innerGlow, Color.Transparent),
                center = center,
                radius = innerRadius
            ),
            radius = innerRadius,
            center = center,
            alpha = glowIntensity * 1.2f
        )

        // === LAYER 4: Rotating ring ===
        val ringAngle = (time * 55f) % 360f
        val ringColors = if (colorTransition > 0.5f) {
            if (isLegal) listOf(
                Color(0xFFF5C850), Color(0xFFDAA520), Color(0xFFE8B830),
                Color(0xFFC8A020), Color(0xFFF0D060), Color(0xFFF5C850)
            ) else listOf(
                Color(0xFF14F195), Color(0xFF06B6D4), Color(0xFF3B82F6),
                Color(0xFF22D3EE), Color(0xFF10B981), Color(0xFF14F195)
            )
        } else {
            if (isLegal) listOf(
                Color(0xFFD4880A), Color(0xFFC87020), Color(0xFFE8A020),
                Color(0xFFB8860B), Color(0xFFDAA520), Color(0xFFD4880A)
            ) else listOf(
                Color(0xFF8B5CF6), Color(0xFF6366F1), Color(0xFF3B82F6),
                Color(0xFF06B6D4), Color(0xFFA78BFA), Color(0xFF8B5CF6)
            )
        }
        val ringPulse = 0.5f + 0.15f * sin(time * 2f) + smoothedAudio * 0.35f

        // Outer ring
        drawCircle(
            brush = Brush.sweepGradient(colors = ringColors, center = center),
            radius = orbRadius * 1.18f,
            center = center,
            alpha = 0.25f * glowIntensity
        )
        // Inner ring
        drawCircle(
            brush = Brush.sweepGradient(colors = ringColors, center = center),
            radius = orbRadius * 1.06f,
            center = center,
            alpha = ringPulse * glowIntensity
        )

        // === LAYER 5: Orb body ===
        val orbDarkBase = if (isLegal) Color(0xFF0D0804) else Color(0xFF080812)
        val idleBg = if (isLegal) Color(0xFF1A1008) else Color(0xFF1E1245)
        val activeBg = if (isLegal) Color(0xFF1A1508) else Color(0xFF0A1A1A)
        val bgColor = lerp(idleBg, activeBg, colorTransition)

        drawCircle(color = orbDarkBase, radius = orbRadius, center = center)
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(bgColor, orbDarkBase),
                center = Offset(cx * 0.92f, cy * 0.85f),
                radius = orbRadius
            ),
            radius = orbRadius,
            center = center
        )

        // === LAYER 6: Organic blobs (7 with compound oscillation) ===
        for (i in blobConfigs.indices) {
            val b = blobConfigs[i]
            val blobRadius = orbRadius * b.size * (1f + smoothedAudio * 0.25f)
            val px = sin(t * b.xFreq + b.xPhase) * b.xAmp + sin(t * b.x2Freq + b.xPhase * 2.1f) * b.x2Amp
            val py = cos(t * b.yFreq + b.yPhase) * b.yAmp + cos(t * b.y2Freq + b.yPhase * 1.7f) * b.y2Amp
            val blobCenter = Offset(cx + px * orbRadius / 150f, cy + py * orbRadius / 150f)
            val color = lerp(idleBlobs[i], activeBlobs[i], colorTransition)

            drawCircle(
                brush = Brush.radialGradient(
                    colorStops = arrayOf(
                        0f to color,
                        0.4f to color.copy(alpha = color.alpha * 0.6f),
                        0.75f to color.copy(alpha = color.alpha * 0.15f),
                        1f to Color.Transparent
                    ),
                    center = blobCenter,
                    radius = blobRadius
                ),
                radius = blobRadius,
                center = blobCenter,
                blendMode = BlendMode.Screen
            )
        }

        // === LAYER 7: Audio-reactive energy waves ===
        if (smoothedAudio > 0.02f && isActive) {
            for (w in 0 until 3) {
                val wPhase = w * 2.1f + time * 3f
                val wRadius = orbRadius * (0.5f + smoothedAudio * 0.6f + sin(wPhase) * 0.15f)
                val wAlpha = smoothedAudio * 0.35f * (1f - w * 0.25f)
                val waveIdle = if (isLegal) Color(0xFFD28C28) else Color(0xFF8B5CF6)
                val waveActive = if (isLegal) Color(0xFFF5C850) else Color(0xFF14F195)
                val waveColor = lerp(waveIdle, waveActive, colorTransition).copy(alpha = wAlpha)

                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(waveColor, waveColor.copy(alpha = 0.3f), Color.Transparent),
                        center = center,
                        radius = wRadius
                    ),
                    radius = wRadius,
                    center = center,
                    blendMode = BlendMode.Screen
                )
            }
        }

        // === LAYER 8: Glass highlight ===
        drawCircle(
            brush = Brush.radialGradient(
                colorStops = arrayOf(
                    0f to Color(0x4DFFFFFF),
                    0.35f to Color(0x14FFFFFF),
                    0.7f to Color.Transparent
                ),
                center = Offset(cx * 0.78f, cy * 0.68f),
                radius = orbRadius * 0.65f
            ),
            radius = orbRadius,
            center = center
        )
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color(0x0FFFFFFF), Color.Transparent),
                center = Offset(cx * 1.15f, cy * 1.25f),
                radius = orbRadius * 0.4f
            ),
            radius = orbRadius,
            center = center
        )

        // === LAYER 9: Edge vignette ===
        drawCircle(
            brush = Brush.radialGradient(
                colorStops = arrayOf(
                    0.5f to Color.Transparent,
                    0.85f to Color(0x40000000),
                    1f to Color(0x8C000000)
                ),
                center = center,
                radius = orbRadius
            ),
            radius = orbRadius,
            center = center
        )

        // === LAYER 10: Rim light ===
        val rimIdle = if (isLegal) Color(0x4DD28C28) else Color(0x4D8B5CF6)
        val rimActive = if (isLegal) Color(0x4DF5C850) else Color(0x4D14F195)
        val rimColor = lerp(rimIdle, rimActive, colorTransition)
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color.Transparent, rimColor, Color.Transparent),
                center = center,
                radius = orbRadius * 1.25f
            ),
            radius = orbRadius * 1.25f,
            center = center,
            alpha = 0.4f + smoothedAudio * 0.5f
        )

        // === LAYER 11: Floating particles ===
        if (isActive) {
            for (p in 0 until 12) {
                val fp = p.toFloat()
                val angle = fp * (2f * PI.toFloat() / 12f) + time * (0.15f + fp * 0.02f)
                val dist = orbRadius * (1.15f + sin(time * 0.8f + fp * 0.7f) * 0.2f) + smoothedAudio * orbRadius * 0.15f
                val pSize = 1.5f + sin(time * 1.5f + fp * 1.3f) * 1f + smoothedAudio * 3f
                val pAlpha = (0.15f + 0.15f * sin(time * 2f + fp * 0.9f) + smoothedAudio * 0.3f).coerceIn(0f, 1f)
                val pIdle = if (isLegal) Color(0xFFD28C28) else Color(0xFF8B5CF6)
                val pActive = if (isLegal) Color(0xFFF5C850) else Color(0xFF14F195)
                val pColor = lerp(pIdle, pActive, colorTransition).copy(alpha = pAlpha)
                val particleCenter = Offset(cx + cos(angle) * dist, cy + sin(angle) * dist)

                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(pColor, Color.Transparent),
                        center = particleCenter,
                        radius = pSize * 3f
                    ),
                    radius = pSize * 3f,
                    center = particleCenter,
                    blendMode = BlendMode.Screen
                )
            }
        }

        // === LAYER 12: Connecting spinner ===
        if (isConnecting) {
            val accentColor = if (isLegal) Color(0xFFDAA520) else Color(0xFFA78BFA)
            for (d in 0 until 8) {
                val fd = d.toFloat()
                val dAngle = fd * (2f * PI.toFloat() / 8f) + time * 4f
                val dist = orbRadius * 1.22f
                val dotAlpha = (0.3f + 0.4f * (0.5f + 0.5f * sin(dAngle - time * 6f))).coerceIn(0f, 1f)
                val dotCenter = Offset(cx + cos(dAngle) * dist, cy + sin(dAngle) * dist)

                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(accentColor, Color.Transparent),
                        center = dotCenter,
                        radius = 3.dp.toPx()
                    ),
                    radius = 3.dp.toPx(),
                    center = dotCenter,
                    alpha = dotAlpha
                )
            }
        }
    }
}

private fun lerp(start: Color, end: Color, fraction: Float): Color {
    return Color(
        red = start.red + (end.red - start.red) * fraction,
        green = start.green + (end.green - start.green) * fraction,
        blue = start.blue + (end.blue - start.blue) * fraction,
        alpha = start.alpha + (end.alpha - start.alpha) * fraction
    )
}
