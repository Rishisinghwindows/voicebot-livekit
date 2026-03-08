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
    val xSpeed: Float, val xOffset: Float,
    val ySpeed: Float, val yOffset: Float,
    val xAmplitude: Float, val yAmplitude: Float,
    val sizeRatio: Float
)

private val blobConfigs = listOf(
    BlobConfig(0.35f, 0f, 0.28f, 0.5f, 55f, 45f, 0.84f),
    BlobConfig(0.25f, 1.5f, 0.32f, 2.0f, 50f, 50f, 0.74f),
    BlobConfig(0.30f, 3.0f, 0.22f, 3.5f, 40f, 40f, 0.67f),
    BlobConfig(0.20f, 4.5f, 0.35f, 5.0f, 45f, 35f, 0.56f),
    BlobConfig(0.28f, 5.5f, 0.25f, 6.2f, 35f, 45f, 0.46f)
)

private val purpleBlobs = listOf(
    Color(0xE68B5CF6), Color(0xCC6366F1), Color(0xB33B82F6),
    Color(0x9906B6D4), Color(0x80A78BFA)
)

private val tealBlobs = listOf(
    Color(0xE614F195), Color(0xCC06B6D4), Color(0xB334D399),
    Color(0xA622D3EE), Color(0x8014F195)
)

@Composable
fun AnimatedOrb(
    state: ConnectionState,
    audioLevel: Float,
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

    val ringAngle by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 5000, easing = LinearEasing)
        ),
        label = "ring"
    )

    val glowPulse by infiniteTransition.animateFloat(
        initialValue = 0.75f,
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
        isSpeaking -> 1.6f + smoothedAudio * 1.5f
        else -> 1f
    }

    Canvas(modifier = modifier.size(300.dp)) {
        val centerX = size.width / 2
        val centerY = size.height / 2
        val orbRadius = size.width * 0.37f
        val t = time * speedMultiplier

        // Outer glow
        val glowScale = 1f + smoothedAudio * 0.15f
        val glowAlpha = glowPulse * if (isActive) 1f else 0.4f
        val glowColor = lerp(
            Color(0x2E8B5CF6),
            Color(0x2E14F195),
            colorTransition
        )
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(glowColor, Color.Transparent),
                center = Offset(centerX, centerY),
                radius = orbRadius * 2.0f * glowScale
            ),
            radius = orbRadius * 2.0f * glowScale,
            center = Offset(centerX, centerY),
            alpha = glowAlpha
        )

        // Mid glow
        val midGlowColor = lerp(
            Color(0x478B5CF6),
            Color(0x4714F195),
            colorTransition
        )
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(midGlowColor, Color.Transparent),
                center = Offset(centerX, centerY),
                radius = orbRadius * 1.5f * glowScale
            ),
            radius = orbRadius * 1.5f * glowScale,
            center = Offset(centerX, centerY),
            alpha = glowAlpha
        )

        // Ring colors
        val ringColors = if (colorTransition > 0.5f) {
            listOf(
                Color(0xFF14F195), Color(0xFF06B6D4), Color(0xFF3B82F6),
                Color(0xFF22D3EE), Color(0xFF10B981), Color(0xFF14F195)
            )
        } else {
            listOf(
                Color(0xFF8B5CF6), Color(0xFF6366F1), Color(0xFF3B82F6),
                Color(0xFF06B6D4), Color(0xFFA78BFA), Color(0xFF8B5CF6)
            )
        }

        // Outer ring (soft glow)
        drawCircle(
            brush = Brush.sweepGradient(
                colors = ringColors,
                center = Offset(centerX, centerY)
            ),
            radius = orbRadius * 1.12f,
            center = Offset(centerX, centerY),
            alpha = 0.3f
        )

        // Inner ring (sharp)
        drawCircle(
            brush = Brush.sweepGradient(
                colors = ringColors,
                center = Offset(centerX, centerY)
            ),
            radius = orbRadius * 1.04f,
            center = Offset(centerX, centerY),
            alpha = 0.65f
        )

        // Orb background
        val orbScale = 1f + smoothedAudio * 0.045f
        val bgColor = lerp(
            Color(0xFF1E1245),
            Color(0xFF0A1A1A),
            colorTransition
        )
        drawCircle(
            color = Color(0xFF080812),
            radius = orbRadius * orbScale,
            center = Offset(centerX, centerY)
        )
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(bgColor, Color(0xFF080812)),
                center = Offset(centerX * 0.96f, centerY * 0.9f),
                radius = orbRadius * orbScale
            ),
            radius = orbRadius * orbScale,
            center = Offset(centerX, centerY)
        )

        // Blobs
        for (i in blobConfigs.indices) {
            val cfg = blobConfigs[i]
            val blobRadius = orbRadius * cfg.sizeRatio * (1f + smoothedAudio * 0.12f)

            val x = centerX + sin(t * cfg.xSpeed + cfg.xOffset) * cfg.xAmplitude * orbRadius / 142f
            val y = centerY + cos(t * cfg.ySpeed + cfg.yOffset) * cfg.yAmplitude * orbRadius / 142f

            val color = lerp(purpleBlobs[i], tealBlobs[i], colorTransition)

            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(color, color.copy(alpha = 0f)),
                    center = Offset(x, y),
                    radius = blobRadius
                ),
                radius = blobRadius,
                center = Offset(x, y),
                blendMode = BlendMode.Screen
            )
        }

        // Glass shine overlay
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color(0x40FFFFFF), Color.Transparent),
                center = Offset(centerX * 0.82f, centerY * 0.72f),
                radius = orbRadius * 0.5f
            ),
            radius = orbRadius * orbScale,
            center = Offset(centerX, centerY)
        )

        // Edge depth
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color.Transparent, Color(0x66000000)),
                center = Offset(centerX, centerY),
                radius = orbRadius * orbScale
            ),
            radius = orbRadius * orbScale,
            center = Offset(centerX, centerY)
        )

        // Outer shadow for orb
        val shadowColor = lerp(
            Color(0x4D8B5CF6),
            Color(0x4D14F195),
            colorTransition
        )
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color.Transparent, shadowColor, Color.Transparent),
                center = Offset(centerX, centerY),
                radius = orbRadius * 1.3f
            ),
            radius = orbRadius * 1.3f,
            center = Offset(centerX, centerY),
            alpha = 0.5f + smoothedAudio * 0.3f
        )
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
