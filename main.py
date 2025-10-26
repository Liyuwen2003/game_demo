import pygame
import os
import math
import time
import threading
import sys
import random

# Optional camera/mediapipe imports (guarded)
USE_MEDIAPIPE = False
try:
    import cv2
    import mediapipe as mp
    USE_MEDIAPIPE = True
except Exception:
    # mediapipe / opencv not available; will use simulated hand
    USE_MEDIAPIPE = False

# Simple Pygame demo based on user's snippet
# This demo shows moving "stairs" (rectangles) and a player that jumps horizontally
# when a simulated "hand" gesture is detected.

pygame.init()
SCREEN_W, SCREEN_H = 800, 600

# Try to create a display. In headless environments this can fail; detect and
# show a friendly message instead of crashing with a long traceback.
try:
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)
    title_font = pygame.font.SysFont(None, 72)
except Exception as e:
    print("无法创建显示窗口（可能是无头/headless 环境或缺少图形支持）。")
    print("错误信息:", str(e))
    print("解决建议：")
    print("  1) 在本地桌面环境运行该脚本（例如 macOS 本地终端），或")
    print("  2) 如果在远程服务器上运行，请使用 X11 转发或在环境中安装虚拟帧缓冲（例如 Xvfb），或")
    print("  3) 使用 ./run.sh 在项目虚拟环境中运行以确保依赖已安装。")
    print("示例（在 macOS 本地）：\n  cd /Users/liyuwen/game_demo\n  source .venv/bin/activate\n  python3 main.py")
    raise SystemExit(1)

# Optional external background image (replace demo background)
# Prefer the new background first, fall back to the old one if missing
BACKGROUND_IMG_CANDIDATES = [
    "/Users/liyuwen/Documents/制作小游戏背景图-3 拷贝.png",
    "/Users/liyuwen/Downloads/制作小游戏背景图-3.png",
    "/Users/liyuwen/Documents/新背景.png",
    "/Users/liyuwen/Documents/background.jpg",
]
background_surface = None
PARALLAX_ENABLED = True
# Parallax follows player progress to the right (no oscillation)
PARALLAX_MAX_SHIFT = 40   # max pixels the background can shift to the right
PARALLAX_SMOOTH = 0.15    # smoothing factor per frame for following
parallax_offset_x = 0.0
parallax_origin_x = 0.0

# Recording / autoplay options (enabled via CLI)
RECORD_GIF = False
RECORD_PATH = None
RECORD_FPS = 30
RECORD_SECONDS = 8
AUTO_PLAY = False
AUTOPLAY_INTERVAL = 0.55
_gif_writer = None
_record_end_time = None
_last_autoplay_time = 0.0

def _parse_cli():
    global RECORD_GIF, RECORD_PATH, RECORD_FPS, RECORD_SECONDS, AUTO_PLAY
    # Light argument parser to avoid adding argparse
    args = sys.argv[1:]
    for a in list(args):
        if a.startswith("--record-gif="):
            RECORD_GIF = True
            RECORD_PATH = a.split("=", 1)[1]
        elif a.startswith("--record-seconds="):
            try:
                RECORD_SECONDS = int(a.split("=", 1)[1])
            except Exception:
                pass
        elif a.startswith("--record-fps="):
            try:
                RECORD_FPS = int(a.split("=", 1)[1])
            except Exception:
                pass
        elif a == "--autoplay":
            AUTO_PLAY = True

_parse_cli()
# Optional title image shown on the start/pause screen
TITLE_IMG_PATH = "/Users/liyuwen/Documents/副本标题.png"
title_image = None
# Optional stair image (replace stair rectangles)
STAIR_IMG_PATH = "/Users/liyuwen/Documents/截屏2025-10-26 00.55.59 拷贝.png"
stair_image = None
# Player sprite images (idle/landing/jump start/jump mid)
SPRITE_PATH_IDLE = "/Users/liyuwen/Documents/静止 拷贝.png"
SPRITE_PATH_LAND = "/Users/liyuwen/Documents/落地 拷贝.png"
SPRITE_PATH_JUMP = "/Users/liyuwen/Documents/跳 拷贝.png"
SPRITE_PATH_AIR = "/Users/liyuwen/Documents/跳跃过程中 拷贝.png"
sprite_idle = sprite_land = sprite_jump = sprite_air = None
# Optional start platform image (fixed high platform at far left)
START_PLATFORM_IMG_PATH = "/Users/liyuwen/Documents/高台.jpg"
start_platform_image = None
try:
    for _p in BACKGROUND_IMG_CANDIDATES:
        if os.path.exists(_p):
            bg = pygame.image.load(_p)
            background_surface = pygame.transform.scale(bg, (SCREEN_W, SCREEN_H))
            break
    # load title image if available (preserve alpha if present)
    if os.path.exists(TITLE_IMG_PATH):
        try:
            ti = pygame.image.load(TITLE_IMG_PATH).convert_alpha()
            iw, ih = ti.get_size()
            max_w = int(SCREEN_W * 0.7)
            max_h = int(SCREEN_H * 0.25)
            # scale down if too big, preserve aspect ratio
            scale = min(max_w / max(1, iw), max_h / max(1, ih), 1.0)
            new_size = (max(1, int(iw * scale)), max(1, int(ih * scale)))
            title_image = pygame.transform.smoothscale(ti, new_size)
        except Exception:
            title_image = None
    # (stair image will be loaded after stair size constants are defined)
except Exception:
    background_surface = None

# Game parameters
STAIR_WIDTH = int(50 * 1.5)  # enlarged 150%
STAIR_HEIGHT = int(20 * 1.5)  # enlarged 150%
STAIRS = [
    {"x": 100, "y_base": 50, "freq": 0.5, "amp": 20},
    {"x": 250, "y_base": 120, "freq": 1.0, "amp": 30},
    {"x": 400, "y_base": 200, "freq": 1.5, "amp": 25},
    {"x": 550, "y_base": 280, "freq": 2.0, "amp": 15},
    {"x": 700, "y_base": 360, "freq": 2.5, "amp": 10},
]

# determine start position: start from the leftmost stair
leftmost_stair = min(STAIRS, key=lambda s: s["x"])
start_player_x = leftmost_stair["x"] - 12 - 2  # place to the left of the leftmost stair
# place the player center on top of that stair (use its y_base for initial placement)
start_player_y = leftmost_stair["y_base"] - 12  # top surface minus radius

# Start platform (fixed high platform) at the far left
# Width auto-adjusts so it does not overlap with the first moving stair
START_PLATFORM_X = 0
PLATFORM_GAP = 10  # leave a small horizontal gap to the first stair
START_PLATFORM_W = max(60, leftmost_stair["x"] - START_PLATFORM_X - PLATFORM_GAP)
START_PLATFORM_H = STAIR_HEIGHT  # keep thickness similar to stairs
# Align its top with the first (leftmost) stair's top so heights are close
START_PLATFORM_Y = leftmost_stair["y_base"]

player_x = float(start_player_x)
player_y = float(start_player_y)
player_radius = 12
# Place the player initially on the left high platform so it rests there visibly
try:
    player_x = float(START_PLATFORM_X + START_PLATFORM_W / 2)
    player_y = float(START_PLATFORM_Y - player_radius)
except Exception:
    pass

# (sprites will be loaded after helper is defined)
player_color = (255, 50, 50)

water_y = SCREEN_H + 100  # off-screen (no water)

# Hand simulation state
hand_y = 500.0
hand_width = 0.0
hand_center_x = SCREEN_W // 2
prev_hand_center_x = None
# removed: last_swipe_time (replaced by last_gesture_time)

# Swipe / jump tuning
SWIPE_THRESHOLD = 40  # pixels of rightward movement to consider a swipe
SWIPE_COOLDOWN = 0.35  # seconds between accepted gestures
VERTICAL_HYSTERESIS = 40  # pixels to lift back above threshold before rearming vertical trigger
vertical_ready = True
last_gesture_time = 0.0

# Jump animation state
is_animating_jump = False
anim_start_x = 0.0
anim_start_y = 0.0
anim_target_x = 0.0
anim_target_y = 0.0
anim_start_time = 0.0
JUMP_DURATION = 0.28  # seconds for smooth jump
render_jump_progress = None  # New variable to track jump animation progress

# Jump sound (bouncy "boing"), prefer synthesized if no custom file is provided
JUMP_SOUND_PATH = "/Users/liyuwen/Documents/jump.wav"  # if you add a custom bounce SFX
jump_sound = None
try:
    # initialize mixer if not already
    try:
        pygame.mixer.get_init()
    except Exception:
        pygame.mixer.init()

    if os.path.exists(JUMP_SOUND_PATH):
        # If user has provided a custom file, use it
        jump_sound = pygame.mixer.Sound(JUMP_SOUND_PATH)
    else:
        # Synthesize a springy "boing" using a short downward chirp with envelope
        try:
            import numpy as np

            sr = 22050
            dur = 0.25  # seconds
            t = np.linspace(0.0, dur, int(sr * dur), endpoint=False)

            f_start = 900.0
            f_end = 260.0
            # Linear chirp phase: 2π(f0 t + 0.5 (f1 - f0) t^2 / dur)
            phase = 2.0 * math.pi * (f_start * t + 0.5 * (f_end - f_start) * (t * t / dur))
            base = np.sin(phase)
            # Add a weak second harmonic to add "rubber" character
            harm = 0.28 * np.sin(2.0 * phase + 0.3)
            # Fast attack, exponential decay envelope
            env = (1.0 - np.exp(-30.0 * t)) * np.exp(-4.5 * t)
            wave = (base * 0.85 + harm) * env

            # Gentle soft-clip to avoid harsh peaks
            wave = np.tanh(wave * 1.4)

            audio = (wave * 32767).astype(np.int16)
            stereo = np.column_stack((audio, audio))
            jump_sound = pygame.sndarray.make_sound(stereo)
            try:
                jump_sound.set_volume(0.7)
            except Exception:
                pass
        except Exception:
            jump_sound = None
except Exception:
    jump_sound = None

# Victory sounds (cheer and claps)
CHEER_SOUND_PATH = "/Users/liyuwen/Documents/cheer.wav"
CLAP_SOUND_PATH = "/Users/liyuwen/Documents/clap.wav"
victory_cheer_sound = None
victory_clap_sound = None
try:
    # mixer should already be initialized above
    def _make_sound_from_array(wave_arr):
        import numpy as np
        audio = (wave_arr * 32767).astype(np.int16)
        stereo = np.column_stack((audio, audio))
        return pygame.sndarray.make_sound(stereo)

    if os.path.exists(CHEER_SOUND_PATH):
        victory_cheer_sound = pygame.mixer.Sound(CHEER_SOUND_PATH)
    else:
        try:
            import numpy as np
            sr = 22050
            dur = 2.8
            t = np.linspace(0.0, dur, int(sr * dur), endpoint=False)
            # crowd-like noise: band-limited noise via simple IIR low-pass
            rng = np.random.default_rng(123)
            noise = rng.normal(0.0, 1.0, t.shape[0])
            # 1-pole low-pass
            alpha = 0.06
            y = np.zeros_like(noise)
            for i in range(1, len(noise)):
                y[i] = y[i-1] + alpha * (noise[i] - y[i-1])
            # envelope: quick attack then slow decay with slight tremolo
            env = (1.0 - np.exp(-6.0 * t)) * np.exp(-0.7 * t) * (0.9 + 0.1 * np.sin(2*np.pi*2.2*t))
            cheer = 0.6 * y * env
            cheer = np.tanh(cheer * 1.6)
            victory_cheer_sound = _make_sound_from_array(cheer)
            try:
                victory_cheer_sound.set_volume(0.6)
            except Exception:
                pass
        except Exception:
            victory_cheer_sound = None

    if os.path.exists(CLAP_SOUND_PATH):
        victory_clap_sound = pygame.mixer.Sound(CLAP_SOUND_PATH)
    else:
        try:
            import numpy as np
            sr = 22050
            dur = 1.2
            t = np.linspace(0.0, dur, int(sr * dur), endpoint=False)
            wave = np.zeros_like(t)
            rng = np.random.default_rng(456)
            # generate multiple clap bursts (short noise hits)
            for _ in range(20):
                start = rng.integers(0, len(t)-int(0.1*sr))
                length = rng.integers(int(0.015*sr), int(0.07*sr))
                env = np.linspace(1.0, 0.0, length)**2
                burst = rng.normal(0.0, 1.0, length) * env
                # high-pass-ish by subtracting a smoothed version
                alpha = 0.2
                hp = np.zeros_like(burst)
                for i in range(1, len(burst)):
                    hp[i] = burst[i] - (hp[i-1] + alpha*(burst[i]-hp[i-1]))
                wave[start:start+length] += hp
            wave *= 0.4
            wave = np.clip(wave, -1.0, 1.0)
            victory_clap_sound = _make_sound_from_array(wave)
            try:
                victory_clap_sound.set_volume(0.7)
            except Exception:
                pass
        except Exception:
            victory_clap_sound = None
except Exception:
    victory_cheer_sound = None
    victory_clap_sound = None

# Tweakable parameters and controls
jump_threshold = 200  # pixel threshold for hand_y to trigger a jump
invert_hand_y = False  # if True, invert camera Y mapping (so lower hand -> smaller value)

# helper to reset player to configured start (on current lowest stair)
def reset_player_to_start():
    global player_x, player_y, parallax_origin_x, parallax_offset_x
    # recompute leftmost stair current y
    leftmost = min(STAIRS, key=lambda s: s["x"])  # use leftmost stair for left-start behavior
    player_x = float(leftmost["x"] - player_radius - 2)
    # use current animated stair y so player sits on moving stair
    player_y = float(leftmost.get("y", leftmost["y_base"]) - player_radius)

    # new: place player on the start platform
    global current_stair_index, is_animating_jump, is_falling, game_over, pending_target_index
    current_stair_index = -1
    is_animating_jump = False
    is_falling = False
    game_over = False
    pending_target_index = None
    # place on start platform center
    player_x = float(START_PLATFORM_X + START_PLATFORM_W / 2)
    player_y = float(START_PLATFORM_Y - player_radius)
    # reset parallax origin to current player position so background follows progress
    parallax_origin_x = player_x
    parallax_offset_x = 0.0


def draw_start_platform(dst):
    if start_platform_image is not None:
        dst.blit(start_platform_image, (int(START_PLATFORM_X), int(START_PLATFORM_Y)))
    else:
        pygame.draw.rect(dst, (40, 120, 240), (int(START_PLATFORM_X), int(START_PLATFORM_Y), START_PLATFORM_W, START_PLATFORM_H))


def schedule_jump_to_stair(index, strength_value):
    """Start a parabolic jump to stair[index] center. Returns True if started."""
    global is_animating_jump, anim_start_x, anim_start_y, anim_target_x, anim_target_y
    global anim_start_time, pending_target_index, last_jump_distance, last_gesture_time
    if index < 0 or index >= len(STAIRS):
        return False
    next_stair = STAIRS[index]
    target_x = float(next_stair["x"] + STAIR_WIDTH / 2)
    target_y = float(next_stair.get("y", next_stair["y_base"]) - player_radius)
    is_animating_jump = True
    anim_start_x = player_x
    anim_start_y = player_y
    anim_target_x = target_x
    anim_target_y = target_y
    anim_start_time = time.time()
    pending_target_index = index
    last_jump_distance = strength_value
    last_gesture_time = anim_start_time
    try:
        if jump_sound is not None:
            jump_sound.play()
    except Exception:
        pass
    return True


# load stair image now that STAIR_WIDTH/HEIGHT are defined
try:
    if os.path.exists(STAIR_IMG_PATH):
        si = pygame.image.load(STAIR_IMG_PATH).convert_alpha()
        stair_image = pygame.transform.smoothscale(si, (STAIR_WIDTH, STAIR_HEIGHT))
    else:
        stair_image = None
except Exception:
    stair_image = None

# helper: load and scale a sprite to target height while preserving aspect ratio
def load_sprite_scaled(path, target_h):
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        w, h = img.get_size()
        if h == 0:
            return img
        scale = target_h / h
        nw, nh = int(w * scale), int(h * scale)
        return pygame.transform.smoothscale(img, (max(1, nw), max(1, nh)))
    except Exception:
        return None

SPRITE_TARGET_H = int(player_radius * 2 * 2.0)  # 200% of ball height
sprite_idle = load_sprite_scaled(SPRITE_PATH_IDLE, SPRITE_TARGET_H)
sprite_land = load_sprite_scaled(SPRITE_PATH_LAND, SPRITE_TARGET_H)
sprite_jump = load_sprite_scaled(SPRITE_PATH_JUMP, SPRITE_TARGET_H)
sprite_air = load_sprite_scaled(SPRITE_PATH_AIR, SPRITE_TARGET_H)
SPRITE_FOOT_OFFSET = 0  # disabled: keep true center alignment

def get_player_sprite():
    # choose sprite based on animation/fall state
    if is_animating_jump:
        p = render_jump_progress if render_jump_progress is not None else 0.0
        if p < 0.2:
            return sprite_jump or sprite_air or sprite_idle
        elif p < 0.85:
            return sprite_air or sprite_jump or sprite_idle
        else:
            return sprite_land or sprite_air or sprite_idle
    if is_falling:
        return sprite_air or sprite_jump or sprite_idle
    return sprite_idle

def draw_player(dst):
    img = get_player_sprite()
    if img is not None:
        # render exactly centered at (player_x, player_y)
        rect = img.get_rect(center=(int(player_x), int(player_y)))
        dst.blit(img, rect)
    else:
        # fallback to the circle if sprites missing
        pygame.draw.circle(dst, player_color, (int(player_x), int(player_y)), player_radius)

# load start platform image now that START_PLATFORM_W/H are defined
try:
    if os.path.exists(START_PLATFORM_IMG_PATH):
        pi = pygame.image.load(START_PLATFORM_IMG_PATH).convert()
        start_platform_image = pygame.transform.smoothscale(pi, (START_PLATFORM_W, START_PLATFORM_H))
    else:
        start_platform_image = None
except Exception:
    start_platform_image = None


# MediaPipe camera state
mp_hands = None
mp_drawing = None
cap = None
hand_lock = threading.Lock()
debug_window_name = "Hand Debug"
show_debug_window = False

if USE_MEDIAPIPE:
    try:
        mp = mp
        mp_hands = mp.solutions.hands
        mp_drawing = mp.solutions.drawing_utils
        # Try to open default camera
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap.release()
            cap = None
            USE_MEDIAPIPE = False
        else:
            # create a persistent Hands object for efficiency
            hands = mp_hands.Hands(static_image_mode=False,
                                   max_num_hands=1,
                                   min_detection_confidence=0.5,
                                   min_tracking_confidence=0.5)
            show_debug_window = True
    except Exception:
        USE_MEDIAPIPE = False

running = True
last_jump_distance = 0.0
game_started = False  # keep game paused on title screen until SPACE is pressed
game_over = False
game_won = False
current_stair_index = -1
pending_target_index = None
is_falling = False
fall_velocity = 0.0
GRAVITY = 1200.0
prev_frame_time = time.time()

# Victory celebration (confetti)
confetti_particles = []
confetti_active = False
victory_prev_time = time.time()
VICTORY_GRAVITY = 400.0
CONFETTI_COLORS = [
    (255, 99, 71),    # tomato
    (255, 215, 0),    # gold
    (50, 205, 50),    # lime green
    (30, 144, 255),   # dodger blue
    (186, 85, 211),   # medium orchid
]

# Fireworks rockets (festival-style)
firework_rockets = []  # each: [x, y, vx, vy, target_y, exploded, color]


def spawn_confetti_burst(cx, cy, count=80, speed_min=250, speed_max=520):
    global confetti_particles
    for _ in range(count):
        ang = random.uniform(-math.pi, 0)  # upwards hemisphere
        spd = random.uniform(speed_min, speed_max)
        vx = math.cos(ang) * spd
        vy = math.sin(ang) * spd
        life = random.uniform(1.5, 3.2)
        col = random.choice(CONFETTI_COLORS)
        size = random.randint(2, 4)
        confetti_particles.append([float(cx), float(cy), vx, vy, life, col, size])


def spawn_firework_rocket(x=None, speed_up=700.0):
    """Spawn a rocket that will travel upward and explode in the upper half of the screen.
    Rocket fields: x, y, vx, vy, target_y, exploded(bool), color
    """
    if x is None:
        x = random.uniform(0.12, 0.88) * SCREEN_W
    # start near bottom
    y = SCREEN_H - 8
    vx = random.uniform(-30.0, 30.0)
    vy = -abs(random.uniform(speed_up * 0.8, speed_up * 1.2))
    # choose a target in the top half (festival concentrated there)
    target_y = random.uniform(SCREEN_H * 0.12, SCREEN_H * 0.45)
    color = random.choice(CONFETTI_COLORS)
    firework_rockets.append([float(x), float(y), vx, vy, float(target_y), False, color])


def explode_rocket(rx, count=80, speed_min=120, speed_max=420):
    """Convert a rocket at rx=[x,y,...] into spark particles (confetti_particles)."""
    x = rx[0]
    y = rx[1]
    for _ in range(count):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(speed_min, speed_max)
        vx = math.cos(ang) * spd
        vy = math.sin(ang) * spd
        life = random.uniform(1.4, 2.8)
        col = random.choice(CONFETTI_COLORS)
        size = random.randint(2, 4)
        confetti_particles.append([float(x), float(y), vx, vy, life, col, size])

def start_victory_celebration():
    global confetti_active, confetti_particles, victory_prev_time
    if confetti_active:
        return
    confetti_active = True
    confetti_particles.clear()
    victory_prev_time = time.time()
    # Launch several fireworks rockets that will explode in the upper half
    for _ in range(6):
        # spread launches across the width, slight horizontal variance
        spawn_firework_rocket(x=random.uniform(0.08, 0.92) * SCREEN_W, speed_up=random.uniform(580, 860))
    # play victory sounds if available
    try:
        if victory_cheer_sound is not None:
            victory_cheer_sound.play()
        if victory_clap_sound is not None:
            victory_clap_sound.play()
    except Exception:
        pass

start_time = time.time()

while running:
    # compute frame delta time for physics and timing
    now_frame = time.time()
    dt = now_frame - prev_frame_time
    prev_frame_time = now_frame
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_SPACE:
                if not game_started:
                    # Start the game from the title/pause screen
                    game_started = True
                    # reset timers and player so the game begins cleanly
                    start_time = time.time()
                    reset_player_to_start()
                else:
                    # manual jump trigger for testing during gameplay
                    jump_distance = max(0.0, hand_width * 2.0)
                    player_x += jump_distance
                    last_jump_distance = jump_distance
            elif event.key == pygame.K_r:
                reset_player_to_start()
            elif event.key == pygame.K_q:
                # allow Q to quickly force game over for testing
                game_over = True
            elif event.key == pygame.K_i:
                invert_hand_y = not invert_hand_y
            elif event.key == pygame.K_d:
                show_debug_window = not show_debug_window
            elif event.key == pygame.K_UP:
                jump_threshold = max(10, jump_threshold - 10)
            elif event.key == pygame.K_DOWN:
                jump_threshold = jump_threshold + 10
            # live tuning: [ ] adjust swipe threshold, ; ' adjust vertical hysteresis
            elif event.key == pygame.K_LEFTBRACKET:  # [
                SWIPE_THRESHOLD = max(5, SWIPE_THRESHOLD - 5)
            elif event.key == pygame.K_RIGHTBRACKET:  # ]
                SWIPE_THRESHOLD = min(200, SWIPE_THRESHOLD + 5)
            elif event.key == pygame.K_SEMICOLON:  # ;
                VERTICAL_HYSTERESIS = max(0, VERTICAL_HYSTERESIS - 5)
            elif event.key == pygame.K_QUOTE:  # '
                VERTICAL_HYSTERESIS = min(200, VERTICAL_HYSTERESIS + 5)

    # If the game hasn't started yet, show the title/pause screen and skip updates
    if not game_started:
        # Draw title/pause background
        if background_surface is not None:
            screen.blit(background_surface, (0, 0))
        else:
            screen.fill((10, 10, 30))

        # Title image (use provided image if available), otherwise fallback to text
        if title_image is not None:
            trect = title_image.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 40))
            screen.blit(title_image, trect)
        else:
            # Title text
            title_surf = title_font.render("Ladder Demo", True, (255, 240, 200))
            title_rect = title_surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 40))
            screen.blit(title_surf, title_rect)

        instr_surf = font.render("按 SPACE 开始游戏  |  ESC 退出", True, (200, 200, 180))
        instr_rect = instr_surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 20))
        screen.blit(instr_surf, instr_rect)

        hint_surf = font.render("在游戏中按 SPACE 触发跳跃，R 重置，I 反转手势映射", True, (180, 180, 160))
        hint_rect = hint_surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 60))
        screen.blit(hint_surf, hint_rect)

        # draw start platform and player so avatar is visible at start
        draw_start_platform(screen)
        draw_player(screen)
        # If recording, we skip title screen and start immediately
        if RECORD_GIF:
            game_started = True
            start_time = time.time()
            reset_player_to_start()
        else:
            pygame.display.flip()
            clock.tick(60)
            # Skip game updates until started
            continue
        # fall through into gameplay when recording

    # If game over, show game over screen and wait for reset
    # If game won, show victory screen
    if game_won:
        # background
        if background_surface is not None:
            screen.blit(background_surface, (0, 0))
        else:
            screen.fill((5, 10, 20))

        # update confetti physics
        nowv = time.time()
        dtv = nowv - victory_prev_time
        victory_prev_time = nowv
        # Update rockets
        # rockets travel up to a target_y then explode into sparks (confetti_particles)
        alive_rockets = []
        for r in firework_rockets:
            x, y, vx, vy, target_y, exploded, col = r
            if not exploded:
                # simple integrate
                vy += -0.0 * dtv  # rockets keep initial upward speed; minor drag omitted
                x += vx * dtv
                y += vy * dtv
                # check for reach target (or overshoot)
                if y <= target_y:
                    # explode here
                    explode_rocket([x, y])
                    # small colorful flash particle (one-off)
                    for _ in range(6):
                        confetti_particles.append([float(x), float(y), random.uniform(-60, 60), random.uniform(-220, -40), random.uniform(0.6, 1.4), col, random.randint(2, 4)])
                    exploded = True
                alive_rockets.append([x, y, vx, vy, target_y, exploded, col])
            else:
                # after explosion the rocket is removed (no trails)
                pass
        firework_rockets[:] = [r for r in alive_rockets if not r[5]]

        # Update spark particles (confetti_particles): gravity & movement
        alive = []
        for p in confetti_particles:
            x, y, vx, vy, life, col, size = p
            vy += VICTORY_GRAVITY * dtv * 0.6  # lighter gravity for sparks
            x += vx * dtv
            y += vy * dtv
            life -= dtv
            if life > 0 and y < SCREEN_H + 40:
                alive.append([x, y, vx, vy, life, col, size])
        confetti_particles[:] = alive

        # If fewer sparks, occasionally launch new rockets to sustain festival feel
        if len(confetti_particles) < 160 and len(firework_rockets) < 4:
            spawn_firework_rocket()

        # draw sparks (bright points)
        for x, y, vx, vy, life, col, size in confetti_particles:
            # fade color a bit by life remaining
            alpha = max(0.2, min(1.0, life / 2.6))
            # simple brightness modulation instead of true alpha blending
            col_draw = (int(col[0] * alpha), int(col[1] * alpha), int(col[2] * alpha))
            pygame.draw.rect(screen, col_draw, (int(x), int(y), size, size))

        # draw rockets as small bright points while rising
        for x, y, vx, vy, target_y, exploded, col in firework_rockets:
            pygame.draw.circle(screen, col, (int(x), int(y)), 3)

        # title
        win = title_font.render("Congratulations!", True, (235, 245, 255))
        win_rect = win.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 40))
        screen.blit(win, win_rect)
        instr = font.render("按 R 重置并返回起点，ESC 退出", True, (220, 220, 220))
        instr_rect = instr.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 20))
        screen.blit(instr, instr_rect)
        pygame.display.flip()
        clock.tick(60)
        continue

    if game_over:
        # draw background
        if background_surface is not None:
            screen.blit(background_surface, (0, 0))
        else:
            screen.fill((20, 10, 30))
        go = title_font.render("Game Over", True, (240, 80, 80))
        go_rect = go.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 20))
        screen.blit(go, go_rect)
        instr = font.render("按 R 重置并返回起点，ESC 退出", True, (220, 220, 220))
        instr_rect = instr.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 20))
        screen.blit(instr, instr_rect)
        pygame.display.flip()
        clock.tick(30)
        continue

    # time in seconds since start
    t = time.time() - start_time

    # Update stairs vertical positions (wave motion)
    for stair in STAIRS:
        stair["y"] = stair["y_base"] + stair["amp"] * math.sin(stair["freq"] * t * 2 * math.pi)

    # If standing on a support (start platform or a stair) and not jumping/falling,
    # keep the player's Y locked to the support's top so he doesn't float when it moves.
    if not is_animating_jump and not is_falling:
        if current_stair_index is not None and current_stair_index >= 0 and current_stair_index < len(STAIRS):
            player_y = float(STAIRS[current_stair_index]["y"] - player_radius)
        else:
            # treat as on start platform
            player_y = float(START_PLATFORM_Y - player_radius)

    # If MediaPipe is enabled and camera is available, try to read hand landmarks
    if USE_MEDIAPIPE and cap is not None:
        try:
            ret, frame = cap.read()
            if ret:
                # Flip and convert to RGB for MediaPipe
                frame_flipped = cv2.flip(frame, 1)
                frame_rgb = cv2.cvtColor(frame_flipped, cv2.COLOR_BGR2RGB)
                results = hands.process(frame_rgb)
                detection_score = 0.0
                if results.multi_hand_landmarks:
                    # Use bounding box of landmarks to compute hand_y and hand_width
                    lm = results.multi_hand_landmarks[0]
                    xs = [p.x for p in lm.landmark]
                    ys = [p.y for p in lm.landmark]
                    x_min = min(xs)
                    x_max = max(xs)
                    y_min = min(ys)
                    y_max = max(ys)
                    center_y = (y_min + y_max) / 2.0
                    center_x = (x_min + x_max) / 2.0
                    raw_hand_y = center_y * SCREEN_H
                    # optionally invert mapping so lower camera y becomes smaller value
                    with hand_lock:
                        hand_y = (SCREEN_H - raw_hand_y) if invert_hand_y else raw_hand_y
                        hand_width = (x_max - x_min) * SCREEN_W
                        hand_center_x = center_x * SCREEN_W
                    # detection confidence if available
                    if results.multi_handedness:
                        detection_score = float(results.multi_handedness[0].classification[0].score)

                # Debug window: draw landmarks and overlay parameters
                if show_debug_window:
                    debug_frame = frame_flipped.copy()
                    if results.multi_hand_landmarks:
                        mp_drawing.draw_landmarks(debug_frame, results.multi_hand_landmarks[0], mp_hands.HAND_CONNECTIONS)
                    # overlay text
                    disp_y = int(hand_y)
                    disp_w = int(hand_width)
                    cv2.putText(debug_frame, f"Hand Y: {disp_y}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    cv2.putText(debug_frame, f"Width: {disp_w}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    cv2.putText(debug_frame, f"Score: {detection_score:.2f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    cv2.imshow(debug_window_name, debug_frame)
                    cv2.waitKey(1)
        except Exception:
            # if camera or mediapipe processing fails, disable and fall back
            USE_MEDIAPIPE = False
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
            cap = None
    else:
        # Simulate hand movement: use a slow sawtooth pattern so the demo is visible
        hand_cycle = (t % 4.0) / 4.0  # 0->1 over 4 seconds
        hand_y = 500 - hand_cycle * 450  # moves between ~500 and ~50
        hand_width = 5 + (math.sin(t * 3.0) + 1) * 10  # oscillates 5..25
        # simulated horizontal movement for swipe testing
        hand_center_x = int(100 + hand_cycle * (SCREEN_W - 200))

    # Autoplay: automatically jump to next stair on a short cadence
    if AUTO_PLAY and game_started and (not is_animating_jump) and (not is_falling) and (not game_over) and (not game_won):
        next_index = current_stair_index + 1
        if next_index < len(STAIRS) and (time.time() - _last_autoplay_time) > AUTOPLAY_INTERVAL:
            if schedule_jump_to_stair(next_index, 20):
                _last_autoplay_time = time.time()

    # Trigger jump when hand meets threshold (with cooldown & hysteresis)
    last_jump_distance = 0.0
    # Grounded check: only accept gestures while supported and idle
    grounded = (not is_animating_jump) and (not is_falling)
    if grounded:
        if current_stair_index is None:
            current_stair_index = -1
    # Detect rightward swipe (small movement to the right) to jump to next stair
    now = time.time()
    if prev_hand_center_x is not None:
        dx = hand_center_x - prev_hand_center_x
        # only allow jumping to the immediate next stair
        next_index = current_stair_index + 1
        if grounded and (now - last_gesture_time) > SWIPE_COOLDOWN:
            if next_index < len(STAIRS) and dx > SWIPE_THRESHOLD:
                if schedule_jump_to_stair(next_index, int(dx)):
                    hand_center_x = SCREEN_W + 100
    # store current center for next frame
    prev_hand_center_x = hand_center_x

    # vertical trigger: only jump if next stair exists and hand crosses below threshold (with hysteresis)
    if grounded and vertical_ready and (hand_y < jump_threshold):
        next_index = current_stair_index + 1
        if next_index < len(STAIRS) and hand_width > 10 and (now - last_gesture_time) > SWIPE_COOLDOWN:
            if schedule_jump_to_stair(next_index, hand_width):
                hand_y = SCREEN_H + 100
                vertical_ready = False
    # re-arm vertical trigger after hand lifts back above threshold + hysteresis
    if not vertical_ready and hand_y > (jump_threshold + VERTICAL_HYSTERESIS):
        vertical_ready = True

    # Keep player inside screen
    if player_x > SCREEN_W - 20:
        # reset to configured start position (side of lowest stair)
        reset_player_to_start()

    # Update jump animation if active
    if is_animating_jump:
        prog = (time.time() - anim_start_time) / JUMP_DURATION  # Calculate progress
        render_jump_progress = max(0.0, min(1.0, prog))  # Update render_jump_progress
        if prog >= 1.0:
            # finish animation
            player_x = anim_target_x
            player_y = anim_target_y
            is_animating_jump = False
            # validate landing: must land on the pending target stair index
            try:
                if pending_target_index is not None:
                    if pending_target_index >= 0 and pending_target_index < len(STAIRS):
                        expected = STAIRS[pending_target_index]
                        # check x match (player placed at expected center)
                        expected_x = float(expected["x"] + STAIR_WIDTH / 2)
                        if abs(player_x - expected_x) < 2.0:
                            # successful landing
                            current_stair_index = pending_target_index
                            # snap y to current stair top
                            player_y = float(expected.get("y", expected["y_base"]) - player_radius)
                            is_falling = False
                            # auto-win if this is the last stair
                            if current_stair_index == (len(STAIRS) - 1):
                                game_won = True
                                start_victory_celebration()
                        else:
                            # missed: fall into water
                            is_falling = True
                            fall_velocity = 0.0
                    else:
                        # invalid target -> fall
                        is_falling = True
                        fall_velocity = 0.0
                pending_target_index = None
            except Exception:
                pending_target_index = None
        else:
            # ease-out cubic
            p = 1 - pow(1 - prog, 3)
            player_x = anim_start_x + (anim_target_x - anim_start_x) * p
            player_y = anim_start_y + (anim_target_y - anim_start_y) * p

    # Update falling physics if active (always, not only during animation)
    if is_falling:
        fall_velocity += GRAVITY * dt
        player_y += fall_velocity * dt
        if player_y > SCREEN_H + 20:
            is_falling = False
            game_over = True

    # Update parallax target based on player progress to the right
    if PARALLAX_ENABLED and background_surface is not None:
        last_center_x = float(STAIRS[-1]["x"] + STAIR_WIDTH / 2)
        denom = max(1.0, last_center_x - parallax_origin_x)
        progress = (player_x - parallax_origin_x) / denom
        if progress < 0.0:
            progress = 0.0
        elif progress > 1.0:
            progress = 1.0
        target_px = progress * PARALLAX_MAX_SHIFT
        # smooth follow
        parallax_offset_x += (target_px - parallax_offset_x) * PARALLAX_SMOOTH

    # Initialize GIF writer on first use
    if RECORD_GIF and _gif_writer is None:
        try:
            import imageio, numpy as np  # noqa: F401
            _record_end_time = time.time() + max(1, int(RECORD_SECONDS))
            _gif_writer = imageio.get_writer(RECORD_PATH or "demo.gif", mode="I", fps=RECORD_FPS)
        except Exception:
            pass

    # Draw
    if background_surface is not None:
        if PARALLAX_ENABLED:
            # follow player's progress with seamless wrap
            px_mod = int(parallax_offset_x) % SCREEN_W
            screen.blit(background_surface, (-px_mod, 0))
            screen.blit(background_surface, (-px_mod + SCREEN_W, 0))
        else:
            screen.blit(background_surface, (0, 0))
    else:
        screen.fill((10, 10, 30))

    # Draw stairs
    for stair in STAIRS:
        sx = int(stair["x"])
        sy = int(stair["y"])
        if stair_image is not None:
            # blit stair image (already scaled to STAIR_WIDTH/STAIR_HEIGHT)
            screen.blit(stair_image, (sx, sy))
        else:
            pygame.draw.rect(screen, (0, 180, 0), (sx, sy, STAIR_WIDTH, STAIR_HEIGHT))

    # Draw start platform (image if available)
    draw_start_platform(screen)

    # Draw player
    draw_player(screen)

    # HUD
    info = f"Hand Y: {int(hand_y)}  Width: {int(hand_width)}  Last Jump: {int(last_jump_distance)}"
    text = font.render(info, True, (220, 220, 220))
    screen.blit(text, (10, 10))

    # Controls HUD
    ctrl_lines = [
        f"SPACE: manual jump  R: reset  I: invert mapping ({'ON' if invert_hand_y else 'OFF'})",
        f"UP/DOWN: adjust vertical trigger ({jump_threshold})  D: toggle debug window",
        f"[/]: swipe threshold ({SWIPE_THRESHOLD})  ;/': vertical hysteresis ({VERTICAL_HYSTERESIS})"
    ]
    for i, line in enumerate(ctrl_lines):
        t = font.render(line, True, (200, 200, 120))
        screen.blit(t, (10, 40 + i * 20))

    # Capture frame for GIF if enabled
    if RECORD_GIF and _gif_writer is not None:
        try:
            import numpy as np
            arr = pygame.surfarray.array3d(screen)  # (w, h, 3)
            frame = np.transpose(arr, (1, 0, 2))    # (h, w, 3)
            _gif_writer.append_data(frame)
        except Exception:
            pass

    pygame.display.flip()
    clock.tick(60)

    # Stop recording after duration
    if RECORD_GIF and _gif_writer is not None and _record_end_time is not None:
        if time.time() >= _record_end_time:
            try:
                _gif_writer.close()
            except Exception:
                pass
            running = False

pygame.quit()
# cleanup camera and debug window
try:
    if USE_MEDIAPIPE and cap is not None:
        cap.release()
except Exception:
    pass
try:
    if show_debug_window:
        cv2.destroyAllWindows()
except Exception:
    pass
print("Exited")
