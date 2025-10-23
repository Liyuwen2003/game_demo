import pygame
import math
import time
import threading

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
except Exception as e:
    print("无法创建显示窗口（可能是无头/headless 环境或缺少图形支持）。")
    print("错误信息:", str(e))
    print("解决建议：")
    print("  1) 在本地桌面环境运行该脚本（例如 macOS 本地终端），或")
    print("  2) 如果在远程服务器上运行，请使用 X11 转发或在环境中安装虚拟帧缓冲（例如 Xvfb），或")
    print("  3) 使用 ./run.sh 在项目虚拟环境中运行以确保依赖已安装。")
    print("示例（在 macOS 本地）：\n  cd /Users/liyuwen/game_demo\n  source .venv/bin/activate\n  python3 main.py")
    raise SystemExit(1)

# Game parameters
STAIR_WIDTH = 50
STAIR_HEIGHT = 20
STAIRS = [
    {"x": 100, "y_base": 50, "freq": 0.5, "amp": 20},
    {"x": 250, "y_base": 120, "freq": 1.0, "amp": 30},
    {"x": 400, "y_base": 200, "freq": 1.5, "amp": 25},
    {"x": 550, "y_base": 280, "freq": 2.0, "amp": 15},
    {"x": 700, "y_base": 360, "freq": 2.5, "amp": 10},
]

player_x = 50.0
player_y = SCREEN_H - 80.0
player_radius = 12
player_color = (255, 50, 50)

water_y = SCREEN_H + 100  # off-screen (no water)

# Hand simulation state
hand_y = 500.0
hand_width = 0.0

# MediaPipe camera state
mp_hands = None
mp_drawing = None
cap = None
hand_lock = threading.Lock()

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
    except Exception:
        USE_MEDIAPIPE = False

running = True
last_jump_distance = 0.0

start_time = time.time()

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

    # time in seconds since start
    t = time.time() - start_time

    # Update stairs vertical positions (wave motion)
    for stair in STAIRS:
        stair["y"] = stair["y_base"] + stair["amp"] * math.sin(stair["freq"] * t * 2 * math.pi)

    # If MediaPipe is enabled and camera is available, try to read hand landmarks
    if USE_MEDIAPIPE and cap is not None:
        try:
            ret, frame = cap.read()
            if ret:
                # Flip and convert to RGB for MediaPipe
                frame_rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
                with mp_hands.Hands(static_image_mode=False,
                                   max_num_hands=1,
                                   min_detection_confidence=0.5,
                                   min_tracking_confidence=0.5) as hands:
                    results = hands.process(frame_rgb)
                    if results.multi_hand_landmarks:
                        # Use bounding box of landmarks to compute hand_y and hand_width
                        lm = results.multi_hand_landmarks[0]
                        xs = [p.x for p in lm.landmark]
                        ys = [p.y for p in lm.landmark]
                        # normalized coordinates 0..1 relative to image (after flip)
                        x_min = min(xs)
                        x_max = max(xs)
                        y_min = min(ys)
                        y_max = max(ys)
                        # map y to screen coordinates
                        hh, ww = frame.shape[0], frame.shape[1]
                        # center y in pixels, invert because screen y grows downwards
                        center_y = (y_min + y_max) / 2.0
                        with hand_lock:
                            hand_y = center_y * SCREEN_H
                            hand_width = (x_max - x_min) * SCREEN_W
                    else:
                        # no hand detected -> keep previous or fallback
                        pass
        except Exception:
            # if camera or mediapipe processing fails, disable and fall back
            USE_MEDIAPIPE = False
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            cap = None
    else:
        # Simulate hand movement: use a slow sawtooth pattern so the demo is visible
        hand_cycle = (t % 4.0) / 4.0  # 0->1 over 4 seconds
        hand_y = 500 - hand_cycle * 450  # moves between ~500 and ~50
        hand_width = 5 + (math.sin(t * 3.0) + 1) * 10  # oscillates 5..25

    # Trigger jump when hand is low enough
    last_jump_distance = 0.0
    if hand_y < 200:
        jump_distance = max(0.0, hand_width * 2.0)
        player_x += jump_distance
        last_jump_distance = jump_distance
        # move hand out of trigger zone briefly
        hand_y = 500

    # Keep player inside screen
    if player_x > SCREEN_W - 20:
        player_x = 50.0  # reset to start for demo

    # Draw
    screen.fill((10, 10, 30))

    # Draw stairs
    for stair in STAIRS:
        pygame.draw.rect(screen, (0, 180, 0), (int(stair["x"]), int(stair["y"]), STAIR_WIDTH, STAIR_HEIGHT))

    # Draw player
    pygame.draw.circle(screen, player_color, (int(player_x), int(player_y)), player_radius)

    # HUD
    info = f"Hand Y: {int(hand_y)}  Width: {int(hand_width)}  Last Jump: {int(last_jump_distance)}"
    text = font.render(info, True, (220, 220, 220))
    screen.blit(text, (10, 10))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
print("Exited")
