package com.ubudy.voiceai

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.delay

private val Background = Color(0xFF0A0A0F)
private val TextSubtle = Color(0x40FFFFFF)
private val TextDimmed = Color(0x1AFFFFFF)
private val PurpleAccent = Color(0x99A78BFA)
private val TealAccent = Color(0x9934D399)
private val FieldBg = Color(0x0FFFFFFF)
private val FieldBorder = Color(0x1AFFFFFF)
private val PurpleStart = Color(0xFFA78BFA)
private val PurpleEnd = Color(0xFF6366F1)

// Legal theme colors
private val LegalAmber = Color(0xFFD4880A)
private val LegalGold = Color(0xFFDAA520)
private val LegalBright = Color(0xFFF5C850)
private val LegalBg = Color(0xFF1A120A)
private val LegalGoldStart = Color(0xFFF5B43C)
private val LegalGoldEnd = Color(0xFFC87820)

@Composable
fun VoiceAIScreen(viewModel: VoiceAIViewModel = viewModel(), agentType: String = "") {
    val state by viewModel.state.collectAsState()
    val audioLevel by viewModel.audioLevel.collectAsState()
    val elapsed by viewModel.elapsedSeconds.collectAsState()

    var hasPermission by remember { mutableStateOf(false) }
    var showForm by remember { mutableStateOf(true) }

    var nameField by remember { mutableStateOf("") }
    var subjectField by remember { mutableStateOf("") }
    var gradeField by remember { mutableStateOf("") }
    var languageField by remember { mutableStateOf("English") }
    var typeField by remember { mutableStateOf(agentType.ifEmpty { "MentalHealth" }) }

    val languages = listOf("English", "Hindi", "Hinglish")
    val agentTypes = listOf("MentalHealth", "legalAdviser", "FinanceGuru")

    val isLegal = typeField == "legalAdviser"

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasPermission = granted
        if (granted) viewModel.toggle()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(if (isLegal) LegalBg else Background)
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
                    typeField = typeField,
                    onTypeChange = { typeField = it },
                    agentTypes = agentTypes,
                    isLegal = isLegal,
                    onStart = {
                        viewModel.userInfo = UserInfo(
                            name = nameField,
                            subject = subjectField,
                            grade = gradeField,
                            language = languageField,
                            type = typeField
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
                    isLegal = isLegal,
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
// TYPEWRITER TEXT
// ============================================================

@Composable
private fun TypewriterText(
    phrases: List<String>,
    cursorColor: Color = Color(0x80A78BFA),
    modifier: Modifier = Modifier
) {
    var displayedText by remember { mutableStateOf("") }
    var phraseIndex by remember { mutableIntStateOf(0) }
    var charIndex by remember { mutableIntStateOf(0) }
    var isDeleting by remember { mutableStateOf(false) }

    // Cursor blink
    val infiniteTransition = rememberInfiniteTransition(label = "cursor")
    val cursorAlpha by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(
            animation = tween(500, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "cursorBlink"
    )

    LaunchedEffect(phraseIndex, isDeleting) {
        val phrase = phrases[phraseIndex]
        if (isDeleting) {
            while (displayedText.isNotEmpty()) {
                delay(20)
                displayedText = displayedText.dropLast(1)
            }
            isDeleting = false
            phraseIndex = (phraseIndex + 1) % phrases.size
            charIndex = 0
        } else {
            while (charIndex < phrase.length) {
                delay(40)
                displayedText = phrase.substring(0, charIndex + 1)
                charIndex++
            }
            delay(3000)
            isDeleting = true
        }
    }

    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier.height(20.dp)
    ) {
        Text(
            text = displayedText,
            style = TextStyle(
                fontSize = 13.sp,
                fontWeight = FontWeight.Light,
                color = Color(0x59FFFFFF)  // 35% opacity white
            )
        )
        // Blinking cursor
        Box(
            modifier = Modifier
                .width(1.dp)
                .height(14.dp)
                .background(cursorColor.copy(alpha = cursorAlpha))
        )
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
    typeField: String,
    onTypeChange: (String) -> Unit,
    agentTypes: List<String>,
    isLegal: Boolean = false,
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
                text = if (isLegal) "AI Legal Guru" else "Voice AI Assistant",
                style = TextStyle(
                    fontSize = 28.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = (-0.5).sp,
                    brush = Brush.linearGradient(
                        colors = if (isLegal) listOf(LegalGoldStart, LegalGoldEnd)
                        else listOf(PurpleStart, PurpleEnd)
                    )
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
            FormField(icon = "\uD83D\uDC64", placeholder = "Your Name", value = nameField, onValueChange = onNameChange, isLegal = isLegal)
            Spacer(modifier = Modifier.height(14.dp))
            FormField(
                icon = "\uD83D\uDCAC",
                placeholder = if (isLegal) "Legal topic to discuss" else "Mental health topic to discuss",
                value = subjectField,
                onValueChange = onSubjectChange,
                isLegal = isLegal
            )
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
                    val selectedBg = if (isLegal) Color(0x33DAA520) else Color(0x338B5CF6)
                    val selectedBorder = if (isLegal) Color(0x66DAA520) else Color(0x668B5CF6)
                    val selectedText = if (isLegal) LegalGoldStart else PurpleStart
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(8.dp))
                            .background(
                                if (isSelected) selectedBg else Color.Transparent
                            )
                            .border(
                                width = if (isSelected) 1.dp else 0.dp,
                                color = if (isSelected) selectedBorder else Color.Transparent,
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
                                color = if (isSelected) selectedText else TextSubtle
                            )
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Type picker
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
                    text = "\u2728",
                    fontSize = 16.sp,
                    modifier = Modifier.padding(end = 10.dp)
                )

                agentTypes.forEach { type ->
                    val isSelected = typeField == type
                    val selectedBg = if (isLegal) Color(0x33DAA520) else Color(0x338B5CF6)
                    val selectedBorder = if (isLegal) Color(0x66DAA520) else Color(0x668B5CF6)
                    val selectedText = if (isLegal) LegalGoldStart else PurpleStart
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(8.dp))
                            .background(if (isSelected) selectedBg else Color.Transparent)
                            .border(
                                width = if (isSelected) 1.dp else 0.dp,
                                color = if (isSelected) selectedBorder else Color.Transparent,
                                shape = RoundedCornerShape(8.dp)
                            )
                            .clickable { onTypeChange(type) }
                            .padding(vertical = 8.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = when (type) {
                                "MentalHealth" -> "Mental"
                                "legalAdviser" -> "Legal"
                                "FinanceGuru" -> "Finance"
                                else -> type
                            },
                            style = TextStyle(
                                fontSize = 13.sp,
                                fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Light,
                                color = if (isSelected) selectedText else TextSubtle
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
                            colors = if (isLegal) listOf(LegalGoldStart, LegalGoldEnd)
                            else listOf(Color(0xFF8B5CF6), Color(0xFF6366F1))
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
                text = if (isLegal) "Ask about BNS, IPC, Constitution & more \u2014 24/7"
                       else "Ask anything \u2014 available 24/7 in English and Hindi",
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
    onValueChange: (String) -> Unit,
    isLegal: Boolean = false
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
                cursorBrush = SolidColor(if (isLegal) LegalGoldStart else PurpleStart),
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
    isLegal: Boolean = false,
    onTap: () -> Unit
) {
    // Staggered fade-in entrance animations
    var showTitle by remember { mutableStateOf(false) }
    var showSubtitle by remember { mutableStateOf(false) }
    var showTagline by remember { mutableStateOf(false) }
    var showOrb by remember { mutableStateOf(false) }
    var showStatus by remember { mutableStateOf(false) }
    var showFooter by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        showTitle = true
        delay(200); showSubtitle = true
        delay(100); showOrb = true      // 300ms total
        delay(100); showTagline = true   // 400ms total
        delay(300); showStatus = true    // 700ms total
        delay(100); showFooter = true    // 800ms total
    }

    val titleAlpha by animateFloatAsState(if (showTitle) 1f else 0f, tween(800), label = "ta")
    val titleOffset by animateFloatAsState(if (showTitle) 0f else 12f, tween(800), label = "to")

    val subtitleAlpha by animateFloatAsState(if (showSubtitle) 1f else 0f, tween(800), label = "sa")
    val subtitleOffset by animateFloatAsState(if (showSubtitle) 0f else 12f, tween(800), label = "so")

    val taglineAlpha by animateFloatAsState(if (showTagline) 1f else 0f, tween(800), label = "tga")
    val taglineOffset by animateFloatAsState(if (showTagline) 0f else 12f, tween(800), label = "tgo")

    val orbScale by animateFloatAsState(if (showOrb) 1f else 0.92f, tween(1000), label = "os")
    val orbAlpha by animateFloatAsState(if (showOrb) 1f else 0f, tween(1000), label = "oa")

    val statusAlpha by animateFloatAsState(if (showStatus) 1f else 0f, tween(800), label = "sta")
    val statusOffset by animateFloatAsState(if (showStatus) 0f else 12f, tween(800), label = "sto")

    val footerAlpha by animateFloatAsState(if (showFooter) 1f else 0f, tween(800), label = "fa")
    val footerOffset by animateFloatAsState(if (showFooter) 0f else 12f, tween(800), label = "fo")

    // Tagline phrases
    val taglinePhrases = if (isLegal) {
        listOf(
            "Ask about IPC, BNS & Indian Constitution",
            "Get instant answers on legal sections",
            "Understand your rights under Indian law"
        )
    } else {
        listOf(
            "I'm Maya, your mental health companion",
            "Share how you feel, I'm here to listen",
            "Breathing exercises & coping tips available"
        )
    }

    val taglineCursorColor = if (isLegal) Color(0x80DAA520) else Color(0x80A78BFA)

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
                text = if (isLegal) "AI Legal Guru" else "Voice AI Assistant",
                style = TextStyle(
                    fontSize = 28.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = (-0.5).sp,
                    brush = Brush.linearGradient(
                        colors = if (isLegal) listOf(LegalGoldStart, LegalGoldEnd)
                        else listOf(PurpleStart, PurpleEnd)
                    )
                ),
                modifier = Modifier.graphicsLayer(
                    alpha = titleAlpha,
                    translationY = titleOffset
                )
            )

            Text(
                text = if (isLegal) "Your AI guide to Indian law"
                       else "Talk in Hindi or English \u2014 powered by real-time AI",
                style = TextStyle(
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Light,
                    letterSpacing = 0.3.sp,
                    color = TextSubtle
                ),
                modifier = Modifier
                    .padding(top = 6.dp)
                    .graphicsLayer(
                        alpha = subtitleAlpha,
                        translationY = subtitleOffset
                    )
            )

            // Typewriter tagline
            TypewriterText(
                phrases = taglinePhrases,
                cursorColor = taglineCursorColor,
                modifier = Modifier
                    .padding(top = 8.dp)
                    .graphicsLayer(
                        alpha = taglineAlpha,
                        translationY = taglineOffset
                    )
            )
        }

        Spacer(modifier = Modifier.weight(1f))

        // Center: Orb + status
        Column(
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier
                    .graphicsLayer(
                        scaleX = orbScale,
                        scaleY = orbScale,
                        alpha = orbAlpha
                    )
                    .clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null
                    ) { onTap() }
            ) {
                AnimatedOrb(
                    state = state,
                    audioLevel = audioLevel,
                    isLegal = isLegal
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
                ConnectionState.SPEAKING -> if (isLegal) LegalBright else TealAccent
                ConnectionState.LISTENING -> if (isLegal) LegalGold else PurpleAccent
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
                ),
                modifier = Modifier.graphicsLayer(
                    alpha = statusAlpha,
                    translationY = statusOffset
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
            modifier = Modifier
                .padding(bottom = 30.dp)
                .graphicsLayer(
                    alpha = footerAlpha,
                    translationY = footerOffset
                )
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
                text = if (isLegal) "Ask about BNS, IPC, Constitution & more \u2014 24/7"
                       else "Ask anything \u2014 available 24/7 in English and Hindi",
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
