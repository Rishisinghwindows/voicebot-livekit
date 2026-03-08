package com.ubudy.voiceai

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel

private val Background = Color(0xFF0A0A0F)
private val TextSubtle = Color(0x40FFFFFF)
private val TextDimmed = Color(0x1AFFFFFF)
private val PurpleAccent = Color(0x99A78BFA)
private val TealAccent = Color(0x9934D399)
private val FieldBg = Color(0x0FFFFFFF)
private val FieldBorder = Color(0x1AFFFFFF)
private val PurpleStart = Color(0xFFA78BFA)
private val PurpleEnd = Color(0xFF6366F1)

@Composable
fun VoiceAIScreen(viewModel: VoiceAIViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val audioLevel by viewModel.audioLevel.collectAsState()
    val elapsed by viewModel.elapsedSeconds.collectAsState()

    var hasPermission by remember { mutableStateOf(false) }
    var showForm by remember { mutableStateOf(true) }

    var nameField by remember { mutableStateOf("") }
    var subjectField by remember { mutableStateOf("") }
    var gradeField by remember { mutableStateOf("") }
    var languageField by remember { mutableStateOf("English") }

    val languages = listOf("English", "Hindi", "Hinglish")

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasPermission = granted
        if (granted) viewModel.toggle()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .systemBarsPadding()
    ) {
        AnimatedContent(
            targetState = showForm && (state == ConnectionState.IDLE || state == ConnectionState.DISCONNECTED),
            transitionSpec = {
                fadeIn(animationSpec = tween(300)) togetherWith fadeOut(animationSpec = tween(300))
            },
            label = "screen"
        ) { isFormVisible ->
            if (isFormVisible) {
                // ============ FORM VIEW ============
                FormView(
                    nameField = nameField,
                    onNameChange = { nameField = it },
                    subjectField = subjectField,
                    onSubjectChange = { subjectField = it },
                    gradeField = gradeField,
                    onGradeChange = { gradeField = it },
                    languageField = languageField,
                    onLanguageChange = { languageField = it },
                    languages = languages,
                    onStart = {
                        viewModel.userInfo = UserInfo(
                            name = nameField,
                            subject = subjectField,
                            grade = gradeField,
                            language = languageField
                        )
                        showForm = false
                        if (!hasPermission) {
                            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        } else {
                            viewModel.toggle()
                        }
                    }
                )
            } else {
                // ============ SESSION VIEW ============
                SessionView(
                    state = state,
                    audioLevel = audioLevel,
                    elapsed = elapsed,
                    nameField = nameField,
                    onTap = {
                        if (state == ConnectionState.IDLE || state == ConnectionState.DISCONNECTED) {
                            if (!hasPermission) {
                                permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                            } else {
                                viewModel.toggle()
                            }
                        } else {
                            viewModel.toggle()
                            if (state == ConnectionState.LISTENING || state == ConnectionState.SPEAKING) {
                                showForm = true
                            }
                        }
                    }
                )
            }
        }
    }
}

// ============================================================
// FORM VIEW
// ============================================================

@Composable
private fun FormView(
    nameField: String,
    onNameChange: (String) -> Unit,
    subjectField: String,
    onSubjectChange: (String) -> Unit,
    gradeField: String,
    onGradeChange: (String) -> Unit,
    languageField: String,
    onLanguageChange: (String) -> Unit,
    languages: List<String>,
    onStart: () -> Unit
) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 32.dp, vertical = 40.dp)
        ) {
            // Title
            Text(
                text = "Voice AI Assistant",
                style = TextStyle(
                    fontSize = 28.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = (-0.5).sp,
                    brush = Brush.linearGradient(colors = listOf(PurpleStart, PurpleEnd))
                )
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = "Tell us about yourself to get started",
                style = TextStyle(
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Light,
                    color = TextSubtle
                )
            )

            Spacer(modifier = Modifier.height(28.dp))

            // Form fields
            FormField(icon = "\uD83D\uDC64", placeholder = "Your Name", value = nameField, onValueChange = onNameChange)
            Spacer(modifier = Modifier.height(14.dp))
            FormField(icon = "\uD83D\uDCDA", placeholder = "Subject (e.g. Math, Science)", value = subjectField, onValueChange = onSubjectChange)
            Spacer(modifier = Modifier.height(14.dp))
            FormField(icon = "\uD83C\uDF93", placeholder = "Grade / Class", value = gradeField, onValueChange = onGradeChange)
            Spacer(modifier = Modifier.height(14.dp))

            // Language picker
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(FieldBg)
                    .border(1.dp, FieldBorder, RoundedCornerShape(12.dp))
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "\uD83C\uDF10",
                    fontSize = 16.sp,
                    modifier = Modifier.padding(end = 10.dp)
                )

                languages.forEach { lang ->
                    val isSelected = languageField == lang
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(8.dp))
                            .background(
                                if (isSelected) Color(0x338B5CF6) else Color.Transparent
                            )
                            .border(
                                width = if (isSelected) 1.dp else 0.dp,
                                color = if (isSelected) Color(0x668B5CF6) else Color.Transparent,
                                shape = RoundedCornerShape(8.dp)
                            )
                            .clickable { onLanguageChange(lang) }
                            .padding(vertical = 8.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = lang,
                            style = TextStyle(
                                fontSize = 13.sp,
                                fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Light,
                                color = if (isSelected) PurpleStart else TextSubtle
                            )
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Start button
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(
                        Brush.horizontalGradient(
                            colors = listOf(Color(0xFF8B5CF6), Color(0xFF6366F1))
                        )
                    )
                    .clickable { onStart() }
                    .padding(vertical = 16.dp),
                contentAlignment = Alignment.Center
            ) {
                Row(
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "\uD83C\uDFA4",
                        fontSize = 16.sp,
                        modifier = Modifier.padding(end = 8.dp)
                    )
                    Text(
                        text = "Start Conversation",
                        style = TextStyle(
                            fontSize = 16.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = Color.White
                        )
                    )
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            Text(
                text = "Ask anything \u2014 available 24/7 in English and Hindi",
                style = TextStyle(
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Light,
                    letterSpacing = 0.3.sp,
                    color = TextDimmed,
                    textAlign = TextAlign.Center
                )
            )
        }
    }
}

@Composable
private fun FormField(
    icon: String,
    placeholder: String,
    value: String,
    onValueChange: (String) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(FieldBg)
            .border(1.dp, FieldBorder, RoundedCornerShape(12.dp))
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = icon,
            fontSize = 16.sp,
            modifier = Modifier.padding(end = 10.dp)
        )

        Box(modifier = Modifier.weight(1f)) {
            if (value.isEmpty()) {
                Text(
                    text = placeholder,
                    style = TextStyle(
                        fontSize = 15.sp,
                        color = TextSubtle
                    )
                )
            }
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                textStyle = TextStyle(
                    fontSize = 15.sp,
                    color = Color.White
                ),
                cursorBrush = SolidColor(PurpleStart),
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

// ============================================================
// SESSION VIEW (Orb centered)
// ============================================================

@Composable
private fun SessionView(
    state: ConnectionState,
    audioLevel: Float,
    elapsed: Int,
    nameField: String,
    onTap: () -> Unit
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.fillMaxSize()
    ) {
        // Top: title
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(top = 60.dp)
        ) {
            Text(
                text = "Voice AI Assistant",
                style = TextStyle(
                    fontSize = 28.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = (-0.5).sp,
                    brush = Brush.linearGradient(colors = listOf(PurpleStart, PurpleEnd))
                )
            )

            Text(
                text = "Powered by real-time voice intelligence",
                style = TextStyle(
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Light,
                    letterSpacing = 0.3.sp,
                    color = TextSubtle
                ),
                modifier = Modifier.padding(top = 6.dp)
            )
        }

        Spacer(modifier = Modifier.weight(1f))

        // Center: Orb + status
        Column(
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null
                ) { onTap() }
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
                ConnectionState.CONNECTING -> Color(0x66FFFFFF)
                else -> TextSubtle
            }
            Text(
                text = statusText,
                style = TextStyle(
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
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
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Light,
                        color = TextDimmed
                    ),
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }

        Spacer(modifier = Modifier.weight(1f))

        // Bottom: footer
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(bottom = 30.dp)
        ) {
            if (nameField.isNotEmpty()) {
                Text(
                    text = "Talking as $nameField",
                    style = TextStyle(
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Light,
                        color = TextSubtle
                    ),
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            Text(
                text = "Ask anything \u2014 available 24/7 in English and Hindi",
                style = TextStyle(
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Light,
                    letterSpacing = 0.3.sp,
                    color = TextDimmed,
                    textAlign = TextAlign.Center
                ),
                modifier = Modifier.padding(horizontal = 32.dp)
            )
        }
    }
}
