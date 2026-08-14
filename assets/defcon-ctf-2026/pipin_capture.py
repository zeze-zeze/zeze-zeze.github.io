#!/usr/bin/env python3
"""
pipin_capture.py -- windowless BACKGROUND recorder for Pipin.

Run this in a WSL terminal, then play the real game in its own window.
It never opens a window of its own: it polls the X server's physical keyboard
state (XQueryKeymap) at 60 Hz on DISPLAY :0 -- regardless of which window has
focus -- and run-length-encodes what you held into a valid `pipin-tas-v1` file.

    (terminal 1)  ./Pipin                 # or: ./Pipin --load-state x.pipstate
    (terminal 2)  python3 pipin_capture.py -o solve.json

Hotkeys (chosen so the game ignores them -- they are NOT Pipin controls):
    F9    start / pause recording (toggle)
    F10   finish: write the file and exit
    F12   discard everything and reset to tick 0

The keys you actually press to PLAY are read as the four Pipin actions below.
They must match your in-game bindings -- edit KEYS if yours differ, then confirm
by validating the result with:  ./Pipin --check-input solve.json -batchmode -nographics -logFile -

Requires (in WSL):  pip3 install --user --break-system-packages python-xlib
"""
import argparse, json, sys, time

# ---- action -> X keysyms that count as "holding" that action -----------------
# left/right/jump/interact are the ONLY names the game's parser accepts.
KEYS = {
    "left":     [0xff51, 0x61],        # Left arrow, A
    "right":    [0xff53, 0x64],        # Right arrow, D
    "jump":     [0x20, 0xff52, 0x77],  # Space, Up arrow, W
    "interact": [0x65],                # E
}
HOTKEYS = {"toggle": 0xffc6, "save": 0xffc7, "discard": 0xffc9}  # F9 / F10 / F12
GAME_RESTART_KEYSYM = 0x72             # R -- the game reloads the scene on this

FORMAT, LEVEL, TICK_RATE, HARD_MAX = "pipin-tas-v1", "main-v1", 60, 60000
CANON = ["left", "right", "jump", "interact"]
ORDER = {n: i for i, n in enumerate(CANON)}


def frames_to_runs(frames, trim_trailing=True, trim_leading=True):
    frames = list(frames)
    if trim_leading:                       # drop dead time before your first input
        while frames and not frames[0]:
            frames.pop(0)
    if trim_trailing:
        while frames and not frames[-1]:
            frames.pop()
    runs, i, n = [], 0, len(frames)
    while i < n:
        cur, j = frames[i], i + 1
        while j < n and frames[j] == cur:
            j += 1
        runs.append({"ticks": j - i, "held": sorted(cur, key=lambda b: ORDER[b])})
        i = j
    return runs


def write_doc(frames, out_path, level, tick_rate, trim, trim_leading=True):
    runs = frames_to_runs(frames, trim_trailing=trim, trim_leading=trim_leading)
    doc = {"format": FORMAT, "level": level, "tickRate": tick_rate, "runs": runs}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"))
    total = sum(r["ticks"] for r in runs)
    print(f"\n[saved] {out_path}  ({total} ticks / ~{total/tick_rate:.2f}s, {len(runs)} segments)")
    if total > HARD_MAX:
        print(f"  !! WARNING: {total} > HardMaxTicks {HARD_MAX}; the game will reject it.")
    for k, r in enumerate(runs[:30]):
        print(f"    run {k:>3}: {r['ticks']:>5} ticks  [{','.join(r['held']) or 'idle'}]")
    if len(runs) > 30:
        print(f"    ... (+{len(runs)-30} more)")
    return doc


def main():
    ap = argparse.ArgumentParser(description="Windowless 60Hz background recorder -> pipin-tas-v1")
    ap.add_argument("-o", "--out", default="recording.json")
    ap.add_argument("--display", default=":0")
    ap.add_argument("--level", default=LEVEL)
    ap.add_argument("--tickrate", type=int, default=TICK_RATE)
    ap.add_argument("--keep-trailing", action="store_true", help="don't trim trailing idle ticks")
    ap.add_argument("--keep-leading", action="store_true",
                    help="keep the idle ticks before your first input (default: trimmed)")
    ap.add_argument("--wait", action="store_true",
                    help="start PAUSED and wait for F9 (default: start recording immediately)")
    ap.add_argument("--no-reset-on-r", action="store_true",
                    help="do NOT clear the take when you press the game's restart key (R)")
    args = ap.parse_args()

    try:
        from Xlib import display
    except ImportError:
        sys.exit("need python-xlib:  pip3 install --user --break-system-packages python-xlib")

    d = display.Display(args.display)
    # resolve keysyms -> keycodes once
    kc = {a: [d.keysym_to_keycode(ks) for ks in kss] for a, kss in KEYS.items()}
    hk = {name: d.keysym_to_keycode(ks) for name, ks in HOTKEYS.items()}
    kc_r = d.keysym_to_keycode(GAME_RESTART_KEYSYM)

    def down(km, code):
        return code and (km[code >> 3] & (1 << (code & 7)))

    def held_now(km):
        return frozenset(a for a, codes in kc.items() if any(down(km, c) for c in codes))

    frames, recording = [], (not args.wait)   # start recording immediately by default
    prev_hk = {k: False for k in hk}
    prev_r = False
    dt = 1.0 / args.tickrate
    next_t = time.perf_counter()

    print(f"pipin_capture on {args.display} @ {args.tickrate}Hz")
    print("  F9=pause/resume   F10=save & exit   F12=discard/reset")
    print(f"  actions: {{left:Left/A  right:Right/D  jump:Space/Up/W  interact:E}}")
    if recording:
        print("  RECORDING NOW -- just play. (leading idle before your first input is trimmed)\n")
    else:
        print("  paused (--wait): press F9 to start\n")

    try:
        while True:
            now = time.perf_counter()
            if now < next_t:
                time.sleep(min(dt, next_t - now))
                continue
            next_t += dt
            if now - next_t > 0.25:          # fell far behind -> resync
                next_t = now + dt

            km = d.query_keymap()

            # ---- hotkeys (edge-triggered) ----
            cur = {k: bool(down(km, c)) for k, c in hk.items()}
            if cur["toggle"] and not prev_hk["toggle"]:
                recording = not recording
            if cur["discard"] and not prev_hk["discard"]:
                frames = []; recording = False
                print("\n[discarded] reset to tick 0")
            save_now = cur["save"] and not prev_hk["save"]
            prev_hk = cur

            # ---- game restart (R) keeps us aligned with the reloaded scene ----
            r_down = bool(down(km, kc_r))
            if (not args.no_reset_on_r) and r_down and not prev_r and recording:
                frames = []
                print("\n[R] scene restart detected -> recording reset to tick 0")
            prev_r = r_down

            if save_now:
                break

            if recording:
                frames.append(held_now(km))
                if len(frames) >= HARD_MAX:
                    print("\n[hit 60000 tick cap] stopping."); break

            h = held_now(km)
            print(f"\r  {'REC ' if recording else 'idle'} tick={len(frames):>6} "
                  f"held=[{','.join(sorted(h, key=lambda b: ORDER[b])) or '-'}]      ",
                  end="", flush=True)
    except KeyboardInterrupt:
        print("\n[ctrl-c] finishing...")

    write_doc(frames, args.out, args.level, args.tickrate,
              trim=not args.keep_trailing, trim_leading=not args.keep_leading)


if __name__ == "__main__":
    main()
