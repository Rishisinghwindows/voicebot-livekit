"""
Web frontend for AI Voice Assistant.
Serves an HTML page and a token endpoint for LiveKit connection.
"""

import os
import json
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from livekit.api import AccessToken, VideoGrants

load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
PUBLIC_LIVEKIT_URL = os.getenv("PUBLIC_LIVEKIT_URL", LIVEKIT_URL)
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
PORT = 8090


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/token":
            self.send_token(parsed)
        elif parsed.path == "/" or parsed.path == "":
            self.send_html()
        else:
            self.send_error(404)

    def send_token(self, parsed):
        params = parse_qs(parsed.query)
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        room_name = f"voice-{uuid.uuid4().hex[:6]}"

        # Build user metadata from query params
        metadata = {}
        for key in ("name", "subject", "grade", "language"):
            val = params.get(key, [""])[0].strip()
            if val:
                metadata[key] = val

        token_builder = (
            AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(user_id)
            .with_grants(VideoGrants(room_join=True, room=room_name))
        )
        if metadata:
            token_builder = token_builder.with_metadata(json.dumps(metadata))

        data = {
            "token": token_builder.to_jwt(),
            "url": PUBLIC_LIVEKIT_URL,
        }
        print(f"[token] user={user_id} room={room_name} metadata={metadata} url={PUBLIC_LIVEKIT_URL} client={self.client_address[0]}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_html(self):
        html = HTML_PAGE.replace("{{LIVEKIT_URL}}", PUBLIC_LIVEKIT_URL)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        print(f"[web] {args[0]}")


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Voice AI</title>
<script src="https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}

body{
    font-family:'Inter',-apple-system,sans-serif;
    background:radial-gradient(ellipse at 50% 40%,#0e0b1a 0%,#060608 55%,#030305 100%);
    min-height:100vh;overflow:hidden;color:#fff;
    display:flex;align-items:center;justify-content:center;
}

.scene{display:flex;flex-direction:column;align-items:center;gap:28px}

.heading{text-align:center;margin-bottom:8px}
.heading h1{
    font-size:28px;font-weight:600;letter-spacing:-.5px;
    background:linear-gradient(135deg,rgba(167,139,250,.9),rgba(99,102,241,.9),rgba(6,182,212,.8));
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    background-clip:text;
}
.heading p{
    font-size:14px;color:rgba(255,255,255,.25);
    margin-top:6px;font-weight:300;letter-spacing:.3px;
}

.footer-text{
    text-align:center;margin-top:4px;
    font-size:12px;color:rgba(255,255,255,.10);
    font-weight:300;letter-spacing:.3px;
    max-width:300px;line-height:1.5;
}

/* ── Floating particles ── */
.ptc{
    position:fixed;width:2px;height:2px;border-radius:50%;
    pointer-events:none;opacity:0;
}
@keyframes floatUp{
    0%{transform:translateY(0) translateX(0);opacity:0}
    8%{opacity:1}
    92%{opacity:1}
    100%{transform:translateY(-110vh) translateX(80px);opacity:0}
}

/* ── Orb system (responsive) ── */
:root{
    --orb-size:min(284px, 60vw);
    --ring-sharp:min(296px, 63vw);
    --ring-soft:min(320px, 68vw);
    --wrap-size:min(380px, 80vw);
    --glow-far:min(520px, 110vw);
    --glow-mid:min(400px, 85vw);
}

.orb-wrap{
    position:relative;
    width:var(--wrap-size);height:var(--wrap-size);
    display:flex;align-items:center;justify-content:center;
}

/* Glow layers */
.glow{position:absolute;border-radius:50%;pointer-events:none}
.glow-far{
    width:var(--glow-far);height:var(--glow-far);
    background:radial-gradient(circle,rgba(139,92,246,.18) 0%,transparent 65%);
    filter:blur(40px);
    animation:glowBreathe 5s ease-in-out infinite;
}
.glow-mid{
    width:var(--glow-mid);height:var(--glow-mid);
    background:radial-gradient(circle,rgba(139,92,246,.28) 0%,transparent 55%);
    filter:blur(20px);
    animation:glowBreathe 5s ease-in-out infinite 1.2s;
}
@keyframes glowBreathe{
    0%,100%{transform:scale(1);opacity:.75}
    50%{transform:scale(1.06);opacity:1}
}

/* Rotating border ring */
@property --ba{syntax:'<angle>';initial-value:0deg;inherits:false}
.ring{
    position:absolute;border-radius:50%;
    background:conic-gradient(from var(--ba),#8B5CF6,#6366F1,#3B82F6,#06B6D4,#A78BFA,#8B5CF6);
    animation:rspin 5s linear infinite;
}
.ring-sharp{width:var(--ring-sharp);height:var(--ring-sharp);opacity:.65}
.ring-soft{width:var(--ring-soft);height:var(--ring-soft);filter:blur(14px);opacity:.3}
@keyframes rspin{to{--ba:360deg}}

/* Main orb */
.orb{
    position:relative;
    width:var(--orb-size);height:var(--orb-size);
    border-radius:50%;
    overflow:hidden;
    clip-path:circle(50%);
    -webkit-clip-path:circle(50%);
    z-index:1;
    box-shadow:
        0 0 60px 15px rgba(139,92,246,.30),
        0 0 120px 50px rgba(139,92,246,.12),
        0 0 220px 100px rgba(139,92,246,.05);
    transition:box-shadow 2s ease,transform .15s ease-out;
}

.orb-bg{
    position:absolute;inset:0;
    background:radial-gradient(circle at 48% 45%,#1e1245 0%,#0f0b20 50%,#080812 100%);
}

/* Gradient blobs inside orb (use % for responsive sizing) */
.blob{
    position:absolute;border-radius:50%;
    filter:blur(28px);
    mix-blend-mode:screen;
    will-change:transform;
    transition:background 2.5s ease;
}
.b1{width:85%;height:85%;background:rgba(139,92,246,.9);top:-30%;left:-18%}
.b2{width:74%;height:74%;background:rgba(99,102,241,.8);bottom:-22%;right:-16%}
.b3{width:67%;height:67%;background:rgba(59,130,246,.7);top:18%;left:22%}
.b4{width:56%;height:56%;background:rgba(6,182,212,.6);bottom:0%;left:-8%}
.b5{width:46%;height:46%;background:rgba(167,139,250,.5);top:35%;right:-5%}

/* Glass specular + edge depth */
.shine{
    position:absolute;inset:0;border-radius:50%;
    background:
        radial-gradient(circle at 32% 26%,rgba(255,255,255,.25),transparent 35%),
        radial-gradient(ellipse at 50% 50%,transparent 52%,rgba(0,0,0,.40) 100%);
    pointer-events:none;
}

/* Icon */
.icon{position:absolute;z-index:2;pointer-events:none}
.icon svg{
    width:30px;height:30px;
    color:rgba(255,255,255,.85);
    filter:drop-shadow(0 2px 10px rgba(0,0,0,.5));
    transition:all .4s;
}

.hit{
    position:absolute;z-index:3;
    width:var(--orb-size);height:var(--orb-size);
    border-radius:50%;border:none;
    background:transparent;cursor:pointer;outline:none;
    -webkit-tap-highlight-color:transparent;
}
.hit:disabled{cursor:not-allowed}

/* Status */
#st{
    font-size:14px;font-weight:400;letter-spacing:.5px;
    text-align:center;min-height:22px;
    transition:all .6s;
    color:rgba(255,255,255,.18);
}
#st.on{color:rgba(167,139,250,.6)}
#st.sp{color:rgba(52,211,153,.6)}

.tmr{
    font-size:11px;color:rgba(255,255,255,.08);
    margin-top:6px;text-align:center;
    font-variant-numeric:tabular-nums;display:none;
}
.tmr.v{display:block}

.dots{display:inline-flex;gap:4px;margin-left:4px}
.dots span{
    width:4px;height:4px;border-radius:50%;
    background:rgba(167,139,250,.5);
    animation:db 1.4s ease-in-out infinite;
}
.dots span:nth-child(2){animation-delay:.2s}
.dots span:nth-child(3){animation-delay:.4s}
@keyframes db{0%,80%,100%{transform:translateY(0);opacity:.3}40%{transform:translateY(-5px);opacity:1}}

/* ═══ Speaking state ═══ */
.orb-wrap.speaking .orb{
    box-shadow:
        0 0 60px 15px rgba(20,241,149,.30),
        0 0 120px 50px rgba(20,241,149,.12),
        0 0 220px 100px rgba(20,241,149,.05);
}
.orb-wrap.speaking .b1{background:rgba(20,241,149,.9)}
.orb-wrap.speaking .b2{background:rgba(6,182,212,.8)}
.orb-wrap.speaking .b3{background:rgba(52,211,153,.7)}
.orb-wrap.speaking .b4{background:rgba(34,211,238,.65)}
.orb-wrap.speaking .b5{background:rgba(20,241,149,.5)}
.orb-wrap.speaking .glow-far{background:radial-gradient(circle,rgba(20,241,149,.18) 0%,transparent 65%)}
.orb-wrap.speaking .glow-mid{background:radial-gradient(circle,rgba(20,241,149,.28) 0%,transparent 55%)}
.orb-wrap.speaking .ring-sharp{
    background:conic-gradient(from var(--ba),#14F195,#06B6D4,#3B82F6,#22D3EE,#10B981,#14F195);
}
.orb-wrap.speaking .ring-soft{
    background:conic-gradient(from var(--ba),#14F195,#06B6D4,#3B82F6,#22D3EE,#10B981,#14F195);
}
.orb-wrap.speaking .orb-bg{
    background:radial-gradient(circle at 48% 45%,#0a1a1a 0%,#081215 50%,#060a10 100%);
}
</style>
</head>
<body>
<div class="scene">
    <div class="heading">
        <h1>Voice AI Assistant</h1>
        <p>Powered by real-time voice intelligence</p>
    </div>
    <div class="orb-wrap" id="orbWrap">
        <div class="glow glow-far" id="glowFar"></div>
        <div class="glow glow-mid" id="glowMid"></div>
        <div class="ring ring-soft"></div>
        <div class="ring ring-sharp"></div>
        <div class="orb" id="orb">
            <div class="orb-bg"></div>
            <div class="blob b1" id="b1"></div>
            <div class="blob b2" id="b2"></div>
            <div class="blob b3" id="b3"></div>
            <div class="blob b4" id="b4"></div>
            <div class="blob b5" id="b5"></div>
            <div class="shine"></div>
        </div>
        <div class="icon">
            <svg id="mic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
                <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
            <svg id="stp" style="display:none" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"/>
            </svg>
        </div>
        <button class="hit" id="btn" onclick="tog()"></button>
    </div>
    <div>
        <div id="st">Tap the orb to start talking</div>
        <div class="tmr" id="tmr">00:00</div>
    </div>
    <div class="footer-text">Ask anything — available 24/7 in English and Hindi</div>
</div>

<script>
const LK=window.LivekitClient;
let room=null,conn=false,tInt=null,sec=0,bSt='idle',spHold=0;

/* Audio */
let uCtx,uAn,uSrc,uArr,bCtx,bAn,bSrc,bArr;

/* DOM */
const orbEl=document.getElementById('orb');
const orbWrap=document.getElementById('orbWrap');
const glowFar=document.getElementById('glowFar');
const glowMid=document.getElementById('glowMid');
const blobs=[
    document.getElementById('b1'),document.getElementById('b2'),
    document.getElementById('b3'),document.getElementById('b4'),
    document.getElementById('b5')
];

/* Blob movement configs */
const drifts=[
    {xs:.35,xo:0,   ys:.28,yo:.5,  xA:55,yA:45},
    {xs:.25,xo:1.5, ys:.32,yo:2.0, xA:50,yA:50},
    {xs:.30,xo:3.0, ys:.22,yo:3.5, xA:40,yA:40},
    {xs:.20,xo:4.5, ys:.35,yo:5.0, xA:45,yA:35},
    {xs:.28,xo:5.5, ys:.25,yo:6.2, xA:35,yA:45}
];

/* Floating background particles */
(function createParticles(){
    for(var i=0;i<25;i++){
        var p=document.createElement('div');
        p.className='ptc';
        p.style.left=Math.random()*100+'vw';
        p.style.top=Math.random()*100+'vh';
        p.style.width=(1+Math.random()*2)+'px';
        p.style.height=p.style.width;
        p.style.background='rgba('+(100+Math.random()*80)+','+(80+Math.random()*60)+','+(200+Math.random()*55)+','+(0.15+Math.random()*0.2)+')';
        p.style.animation='floatUp '+(18+Math.random()*20)+'s linear infinite';
        p.style.animationDelay=(-Math.random()*30)+'s';
        document.body.appendChild(p);
    }
})();

function setBSt(s){
    if(bSt===s)return;bSt=s;
    var st=document.getElementById('st');
    if(s==='speaking'){st.textContent='Speaking...';st.className='sp';orbWrap.classList.add('speaking');}
    else if(s==='listening'){st.textContent='Listening...';st.className='on';orbWrap.classList.remove('speaking');}
}

function getLevel(an,arr){
    if(!an||!arr)return 0;
    an.getByteFrequencyData(arr);
    var s=0;for(var i=0;i<arr.length;i++)s+=arr[i];
    return Math.min(1,s/arr.length/100);
}

/* ── Animation loop ── */
var t0=performance.now(),speedMul=1,smoothAudio=0;

function animate(){
    var time=(performance.now()-t0)/1000;

    var bLvl=getLevel(bAn,bArr);
    var uLvl=getLevel(uAn,uArr);

    /* Auto-detect speaking vs listening */
    if(conn&&bSt!=='connecting'){
        if(bLvl>.06){spHold=25;if(bSt!=='speaking')setBSt('speaking');}
        else if(spHold>0)spHold--;
        else if(bSt!=='listening')setBSt('listening');
    }

    var aLvl=bSt==='speaking'?bLvl:bSt==='listening'?uLvl:0;
    smoothAudio+=(aLvl-smoothAudio)*.12;

    /* Speed multiplier */
    var targetSpd=bSt==='connecting'?2.8:bSt==='speaking'?1.6+smoothAudio*1.5:1;
    speedMul+=(targetSpd-speedMul)*.025;

    /* Move blobs */
    for(var i=0;i<5;i++){
        var d=drifts[i];
        var t=time*speedMul;
        var x=Math.sin(t*d.xs+d.xo)*d.xA;
        var y=Math.cos(t*d.ys+d.yo)*d.yA;
        var sc=1+smoothAudio*.12;
        blobs[i].style.transform='translate('+x+'%,'+y+'%) scale('+sc+')';
    }

    /* Audio-reactive orb scale + glow */
    orbEl.style.transform='scale('+(1+smoothAudio*.045)+')';
    glowFar.style.transform='scale('+(1+smoothAudio*.15)+')';
    glowMid.style.transform='scale('+(1+smoothAudio*.10)+')';

    requestAnimationFrame(animate);
}
animate();

/* ── Audio setup ── */
function setupUA(){
    try{var pub=room.localParticipant.getTrackPublication(LK.Track.Source.Microphone);
    if(!pub||!pub.track)return;var stream=new MediaStream([pub.track.mediaStreamTrack]);
    uCtx=new AudioContext();uAn=uCtx.createAnalyser();uAn.fftSize=256;uAn.smoothingTimeConstant=.8;
    uSrc=uCtx.createMediaStreamSource(stream);uSrc.connect(uAn);uArr=new Uint8Array(uAn.frequencyBinCount);
    }catch(e){console.warn('UA:',e)}
}
function setupBA(trk){
    try{var stream=new MediaStream([trk]);bCtx=new AudioContext();bAn=bCtx.createAnalyser();
    bAn.fftSize=256;bAn.smoothingTimeConstant=.8;bSrc=bCtx.createMediaStreamSource(stream);
    bSrc.connect(bAn);bArr=new Uint8Array(bAn.frequencyBinCount);
    }catch(e){console.warn('BA:',e)}
}
function tearA(){
    [uSrc,bSrc].forEach(function(s){if(s)s.disconnect()});
    [uCtx,bCtx].forEach(function(c){if(c)c.close().catch(function(){})});
    uCtx=uAn=uSrc=uArr=null;bCtx=bAn=bSrc=bArr=null;
}

/* Timer */
function startT(){sec=0;document.getElementById('tmr').classList.add('v');updT();tInt=setInterval(function(){sec++;updT()},1000)}
function stopT(){clearInterval(tInt);document.getElementById('tmr').classList.remove('v')}
function updT(){document.getElementById('tmr').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0')}

function tog(){if(conn)disc();else connect()}

function connect(){
    var btn=document.getElementById('btn'),st=document.getElementById('st');
    btn.disabled=true;
    st.innerHTML='Connecting<span class="dots"><span></span><span></span><span></span></span>';
    st.className='';bSt='connecting';

    console.log('[LK] Fetching token...');
    fetch('/token').then(function(r){return r.json()}).then(function(data){
        console.log('[LK] Token received, connecting to:', data.url);
        room=new LK.Room({audioCaptureDefaults:{autoGainControl:true,noiseSuppression:true,echoCancellation:true}});
        room.on(LK.RoomEvent.TrackSubscribed,function(track){
            console.log('[LK] Track subscribed:', track.kind, track.source);
            if(track.kind==='audio'){var el=track.attach();el.style.display='none';document.body.appendChild(el);setupBA(track.mediaStreamTrack);}
        });
        room.on(LK.RoomEvent.Disconnected,function(reason){console.log('[LK] Disconnected, reason:', reason);disc()});
        room.on(LK.RoomEvent.Reconnecting,function(){console.log('[LK] Reconnecting...')});
        room.on(LK.RoomEvent.Reconnected,function(){console.log('[LK] Reconnected')});
        room.on(LK.RoomEvent.SignalConnected,function(){console.log('[LK] Signal connected (WebSocket OK)')});
        room.on(LK.RoomEvent.MediaDevicesError,function(e){console.error('[LK] Media device error:', e)});
        room.on(LK.RoomEvent.ConnectionQualityChanged,function(q,p){console.log('[LK] Connection quality:', q, 'participant:', p.identity)});
        room.on(LK.RoomEvent.ParticipantConnected,function(p){console.log('[LK] Participant joined:', p.identity)});

        /* Monitor ICE connection state */
        room.on(LK.RoomEvent.SignalConnected, function(){
            console.log('[LK] Signal connected - checking PC state...');
            try {
                var engine = room.engine;
                if (engine && engine.pcManager) {
                    var pcs = [engine.pcManager.publisher, engine.pcManager.subscriber];
                    pcs.forEach(function(pc, idx) {
                        if (pc && pc.pc) {
                            var label = idx === 0 ? 'publisher' : 'subscriber';
                            pc.pc.onicecandidate = function(ev) {
                                if (ev.candidate) {
                                    console.log('[ICE][' + label + '] candidate:', ev.candidate.type, ev.candidate.protocol, ev.candidate.address + ':' + ev.candidate.port);
                                } else {
                                    console.log('[ICE][' + label + '] gathering complete');
                                }
                            };
                            pc.pc.oniceconnectionstatechange = function() {
                                console.log('[ICE][' + label + '] state:', pc.pc.iceConnectionState);
                            };
                            pc.pc.onconnectionstatechange = function() {
                                console.log('[PC][' + label + '] state:', pc.pc.connectionState);
                            };
                            pc.pc.onicegatheringstatechange = function() {
                                console.log('[ICE][' + label + '] gathering:', pc.pc.iceGatheringState);
                            };
                        }
                    });
                }
            } catch(e) { console.warn('[LK] Could not attach ICE monitors:', e); }
        });

        return room.connect(data.url,data.token).then(function(){
            console.log('[LK] Room connected, enabling mic...');
            return room.localParticipant.setMicrophoneEnabled(true);
        });
    }).then(function(){
        console.log('[LK] Mic enabled, fully connected!');
        conn=true;btn.disabled=false;
        document.getElementById('mic').style.display='none';
        document.getElementById('stp').style.display='block';
        setBSt('listening');setupUA();startT();
    }).catch(function(e){
        console.error('[LK] Connection error:', e.message || e);
        console.error('[LK] Error details:', e);
        st.textContent='Connection failed: ' + (e.message || 'unknown error');st.className='';
        btn.disabled=false;bSt='idle';
    });
}

function disc(){
    if(room){room.disconnect();room=null}conn=false;
    document.getElementById('mic').style.display='block';
    document.getElementById('stp').style.display='none';
    document.getElementById('st').textContent='Tap to start';
    document.getElementById('st').className='';
    orbWrap.classList.remove('speaking');
    tearA();bSt='idle';spHold=0;stopT();
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print(f"Voice AI running at: http://localhost:{PORT}")
    print(f"LiveKit URL: {LIVEKIT_URL}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
