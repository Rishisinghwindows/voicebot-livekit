package com.ubudy.voiceai

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel

private val Background = Color(0xFF0A0A0F)
private val TextPrimary = Color(0xFFFFFFFF)
private val TextSubtle = Color(0x40FFFFFF)
private val TextDimmed = Color(0x1AFFFFFF)
private val PurpleAccent = Color(0x99A78BFA)
private val TealAccent = Color(0x9934D399)

@Composable
fun VoiceAIScreen(viewModel: VoiceAIViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val audioLevel by viewModel.audioLevel.collectAsState()
    val elapsed by viewModel.elapsedSeconds.collectAsState()

    var hasPermission by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasPermission = granted
        if (granted) {
            viewModel.toggle()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .systemBarsPadding(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.fillMaxSize()
        ) {
            Spacer(modifier = Modifier.weight(0.15f))

            // Title
            Text(
                text = "Voice AI Assistant",
                style = TextStyle(
                    fontSize = 28.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = (-0.5).sp,
                    color = Color(0xE6A78BFA)
                )
            )

            // Subtitle
            Text(
                text = "Powered by real-time voice intelligence",
                style = TextStyle(
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Light,
                    letterSpacing = 0.3.sp,
                    color = TextSubtle
                ),
                modifier = Modifier.padding(top = 6.dp)
            )

            Spacer(modifier = Modifier.weight(0.2f))

            // Orb
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null
                ) {
                    if (!hasPermission && (state == ConnectionState.IDLE || state == ConnectionState.DISCONNECTED)) {
                        permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    } else {
                        viewModel.toggle()
                    }
                }
            ) {
                AnimatedOrb(
                    state = state,
                    audioLevel = audioLevel
                )
            }

            Spacer(modifier = Modifier.height(28.dp))

            // Status text
            val statusText = when (state) {
                ConnectionState.IDLE -> "Tap the orb to start talking"
                ConnectionState.CONNECTING -> "Connecting..."
                ConnectionState.LISTENING -> "Listening..."
                ConnectionState.SPEAKING -> "Speaking..."
                ConnectionState.DISCONNECTED -> "Tap to reconnect"
            }
            val statusColor = when (state) {
                ConnectionState.SPEAKING -> TealAccent
                ConnectionState.LISTENING -> PurpleAccent
                else -> TextSubtle
            }
            Text(
                text = statusText,
                style = TextStyle(
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Normal,
                    letterSpacing = 0.5.sp,
                    color = statusColor
                )
            )

            // Timer
            if (state == ConnectionState.LISTENING || state == ConnectionState.SPEAKING) {
                val minutes = elapsed / 60
                val seconds = elapsed % 60
                Text(
                    text = "%02d:%02d".format(minutes, seconds),
                    style = TextStyle(
                        fontSize = 11.sp,
                        color = TextDimmed
                    ),
                    modifier = Modifier.padding(top = 6.dp)
                )
            }

            Spacer(modifier = Modifier.weight(0.3f))

            // Footer
            Text(
                text = "Ask anything \u2014 available 24/7 in English and Hindi",
                style = TextStyle(
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Light,
                    letterSpacing = 0.3.sp,
                    color = TextDimmed,
                    textAlign = TextAlign.Center
                ),
                modifier = Modifier.padding(bottom = 24.dp, start = 32.dp, end = 32.dp)
            )
        }
    }
}
