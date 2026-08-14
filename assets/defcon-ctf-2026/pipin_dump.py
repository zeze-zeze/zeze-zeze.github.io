#!/usr/bin/env python3
"""
pipin_dump.py -- dump your CURRENT game progress to a .pipstate file.

The shipped game has GameSimulation.TryCaptureState() + GameStateFile.TryWrite()
fully implemented but wired to no CLI flag (the server calls them to produce the
state served to attackers). This launches Pipin under Frida, hooks the live
simulation, and lets you press a hotkey while playing to serialise the current
state with the game's OWN serializer -> a guaranteed-valid .pipstate.

Usage (play + hotkey dump, needs WSLg / DISPLAY):
    python3 pipin_dump.py                       # fresh game
    python3 pipin_dump.py --load-state x.pipstate
    #   ... play in the game window; press F8 to dump -> progress_N.pipstate

Generate the pipstate your LOCK produces (what attackers of your lock receive):
    python3 pipin_dump.py --lock lock.json -o lock.pipstate
    #   plays lock.json (a brief game window opens), auto-dumps the final state,
    #   and validates it re-loads. Compose with --load-state to attack-test it.

Self-test (auto-dumps once, then validates by re-loading it):
    python3 pipin_dump.py --selftest

Requires (WSL):  pip3 install --break-system-packages --user frida python-xlib
"""
import argparse, os, sys, time, threading, subprocess

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
MOD = "GameAssembly.so"

AGENT = r"""
const MOD = "GameAssembly.so";
let ready = false, pendingPath = null;
let capFn, writeFn, mCap, mWrite, strNew, mod = null;
let lastSelf = null, lastCur = 0, lastTick = 0;   // latest live sim state (set every Tick)
let autoDumpPath = null, autoDone = false;         // auto-dump when the TAS run terminates
let performDump = null;

function nf(name, ret, args) {
  return new NativeFunction(mod.getExportByName(name), ret, args);   // frida 17: instance method
}
function cstr(s){ return Memory.allocUtf8String(s); }
function csharpString(p){
  if (p.isNull()) return "<null>";
  const len = p.add(0x10).readS32();
  return len > 0 ? p.add(0x14).readUtf16String(len) : "";
}

function findImage(want){
  const domain_get   = nf("il2cpp_domain_get", "pointer", []);
  const get_asms     = nf("il2cpp_domain_get_assemblies", "pointer", ["pointer","pointer"]);
  const asm_image    = nf("il2cpp_assembly_get_image", "pointer", ["pointer"]);
  const image_name   = nf("il2cpp_image_get_name", "pointer", ["pointer"]);
  const dom = domain_get();
  const cnt = Memory.alloc(Process.pointerSize);
  const arr = get_asms(dom, cnt);
  const n = cnt.readULong();
  for (let i = 0; i < n; i++){
    const asm = arr.add(i * Process.pointerSize).readPointer();
    if (asm.isNull()) continue;
    const img = asm_image(asm);
    if (img.isNull()) continue;
    const nm = image_name(img).readUtf8String();
    if (nm && nm.indexOf(want) >= 0) return img;
  }
  return null;
}

function init(){
  mod = Process.findModuleByName(MOD);
  if (!mod) return false;
  const img = findImage("Pipin.Runtime");
  if (!img) return false;
  const class_from_name = nf("il2cpp_class_from_name", "pointer", ["pointer","pointer","pointer"]);
  const method_from     = nf("il2cpp_class_get_method_from_name", "pointer", ["pointer","pointer","int"]);
  strNew                = nf("il2cpp_string_new", "pointer", ["pointer"]);

  const kSim  = class_from_name(img, cstr("Tas"), cstr("GameSimulation"));
  const kFile = class_from_name(img, cstr("Tas"), cstr("GameStateFile"));
  if (kSim.isNull() || kFile.isNull()) return false;

  mCap        = method_from(kSim,  cstr("TryCaptureState"), 4);   // (prevInput, nextTick, out snap, out err)
  mWrite      = method_from(kFile, cstr("TryWrite"), 3);          // (path, snap, out err)
  const mTick = method_from(kSim,  cstr("Tick"), 3);             // (current, previous, tick)
  if (mCap.isNull() || mWrite.isNull() || mTick.isNull()) return false;

  // MethodInfo.methodPointer is at offset 0
  capFn   = new NativeFunction(mCap.readPointer(),  "bool", ["pointer","uint8","int64","pointer","pointer","pointer"]);
  writeFn = new NativeFunction(mWrite.readPointer(),"bool", ["pointer","pointer","pointer","pointer"]);

  // capture the CURRENT live simulation state (from the last Tick) into a .pipstate
  performDump = function(path){
    if (!lastSelf){ send("ERR no live simulation yet (nothing has ticked)"); return false; }
    try {
      const outSnap = Memory.alloc(Process.pointerSize); outSnap.writePointer(ptr(0));
      const outErr  = Memory.alloc(Process.pointerSize); outErr.writePointer(ptr(0));
      const ok = capFn(lastSelf, lastCur, lastTick + 1, outSnap, outErr, mCap);
      if (!ok){ send("ERR capture: " + csharpString(outErr.readPointer())); return false; }
      const snap = outSnap.readPointer();
      const outErr2 = Memory.alloc(Process.pointerSize); outErr2.writePointer(ptr(0));
      const ok2 = writeFn(strNew(cstr(path)), snap, outErr2, mWrite);
      if (!ok2){ send("ERR write: " + csharpString(outErr2.readPointer())); return false; }
      send("OK wrote " + path + " (tick=" + lastTick + ")");
      return true;
    } catch(e){ send("ERR exception: " + e); return false; }
  };

  Interceptor.attach(mTick.readPointer(), {
    onEnter(a){ lastSelf = a[0]; lastCur = a[1].toInt32() & 0xff; lastTick = a[3].toInt32(); },
    onLeave(r){ if (pendingPath){ const p = pendingPath; pendingPath = null; performDump(p); } }
  });

  // Auto-dump when a TAS run finishes. TasResult.Log(status, exitCode, message,
  // ticks) is THE sink for every terminal outcome (invalid/exhausted/complete),
  // called right before the game quits -> reliable trigger for the final state.
  try {
    const kRes = class_from_name(img, cstr("Tas"), cstr("TasResult"));
    if (kRes.isNull()){ send("WARN TasResult class not loaded yet"); }
    else {
      const mLog = method_from(kRes, cstr("Log"), 4);   // (status, exitCode, message, ticks)
      if (mLog.isNull()){ send("WARN TasResult.Log not found"); }
      else {
        Interceptor.attach(mLog.readPointer(), {
          onEnter(a){
            const status = csharpString(a[0]);
            send("RESULT " + status);
            if (autoDumpPath && !autoDone){
              autoDone = true;
              performDump(autoDumpPath);
              send("AUTODUMP_DONE");
            }
          }
        });
        send("hooked TasResult.Log");
      }
    }
  } catch(e){ send("ERR result-hook: " + e); }
  return true;
}

// Only touch il2cpp AFTER il2cpp_init() has returned -- calling metadata APIs
// too early (esp. in the fast headless --check-input path) crashes the process.
let il2cppUp = false;
function hookInit(){
  const m = Process.findModuleByName(MOD);
  if (!m) return false;
  let p;
  try { p = m.getExportByName("il2cpp_init"); } catch(e){ return false; }
  Interceptor.attach(p, { onLeave(r){ il2cppUp = true; } });
  return true;
}
const hb = setInterval(function(){ try { if (hookInit()) clearInterval(hb); } catch(e){} }, 30);
const ib = setInterval(function(){
  if (ready){ clearInterval(ib); return; }
  if (!il2cppUp) return;
  try { if (init()){ ready = true; clearInterval(ib); send("READY"); } }
  catch(e){ send("init err: " + e); }
}, 50);
setTimeout(function(){ il2cppUp = true; }, 2500);   // long-lived fallback if the init hook was missed

rpc.exports = {
  dump(path){ pendingPath = path; return "queued " + path; },
  setautodump(path){ autoDumpPath = path; autoDone = false; return "auto " + path; },
  isready(){ return ready; }
};
"""


class Launcher:
    """Launch Pipin normally (subprocess) and frida-ATTACH to it. Note: frida
    *spawn* makes the Pipin launcher re-exec into a child that's painful to
    follow; a plain subprocess launch stays a single process, so we just attach
    to it as soon as it appears. Fast headless TAS runs can finish before our
    hooks install, so callers use graphical mode (capped ~60fps) for a margin."""

    def __init__(self, autodump=None, on_agent=None):
        import frida
        self.frida = frida
        self.dev = frida.get_local_device()
        self.autodump = autodump
        self.on_agent = on_agent
        self.proc = self.session = self.script = self.exports = None
        self.pid = None
        self.ready = False

    def _msg(self, msg, data):
        if msg.get("type") == "send":
            p = msg["payload"]
            print("[agent]", p)
            if p == "READY":
                self.ready = True
            if self.on_agent:
                self.on_agent(str(p))
        elif msg.get("type") == "error":
            print("[agent-error]", msg.get("stack") or msg.get("description"))

    def spawn(self, argv, headless):
        prog = os.path.join(GAME_DIR, "Pipin")
        full = [prog] + list(argv)
        if headless:
            full += ["-batchmode", "-nographics", "-logFile", "-"]
        env = dict(os.environ); env.setdefault("DISPLAY", ":0")
        before = {p.pid for p in self.dev.enumerate_processes() if p.name == "Pipin"}
        self.proc = subprocess.Popen(full, cwd=GAME_DIR, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()                              # attach to the new Pipin process ASAP
        while time.time() - t0 < 15 and self.session is None:
            for pid in [p.pid for p in self.dev.enumerate_processes()
                        if p.name == "Pipin" and p.pid not in before]:
                try:
                    self.session = self.dev.attach(pid); self.pid = pid; break
                except Exception:
                    self.session = None
            if self.session is None:
                time.sleep(0.01)
        if self.session is None:
            raise RuntimeError("could not attach to Pipin (did it start?)")
        self.script = self.session.create_script(AGENT)
        self.script.on("message", self._msg)
        self.script.load()
        self.exports = getattr(self.script, "exports_sync", None) or self.script.exports
        if self.autodump:
            try: self.exports.setautodump(self.autodump)
            except Exception as e: print("[!] setautodump:", e)
        return self.pid

    def wait_ready(self, timeout=25):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.ready:
                return True
            time.sleep(0.05)
        return False

    def dump(self, path):
        try: self.exports.dump(path)
        except Exception as e: print("[!] dump:", e)

    def kill_all(self):
        try:
            if self.pid: self.dev.kill(self.pid)
        except Exception: pass
        try:
            if self.proc: self.proc.kill()
        except Exception: pass


def _validate(pipstate_path):
    okjson = os.path.join(GAME_DIR, "_ok_probe.json")
    with open(okjson, "w") as f:
        f.write('{"format":"pipin-tas-v1","level":"main-v1","tickRate":60,"runs":[{"ticks":1,"held":[]}]}')
    try:
        r = subprocess.run([os.path.join(GAME_DIR, "Pipin"), "--load-state", pipstate_path,
                            "--check-input", okjson, "-batchmode", "-nographics", "-logFile", "-"],
                           cwd=GAME_DIR, capture_output=True, text=True, timeout=120)
    finally:
        os.remove(okjson)
    line = next((l for l in (r.stdout + r.stderr).splitlines() if "TAS_RESULT" in l), "(no TAS_RESULT)")
    print("[validate]", line)
    return "Save state" not in line and "TAS_RESULT" in line


def _wait_file(lch, path, done, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
        if done.get("flag"):
            return os.path.exists(path) and os.path.getsize(path) > 0
        time.sleep(0.05)
    return os.path.exists(path) and os.path.getsize(path) > 0


def selftest():
    out = os.path.join(GAME_DIR, "selftest_dump.pipstate")
    if os.path.exists(out): os.remove(out)
    done = {"flag": False}
    lch = Launcher(on_agent=lambda p: done.__setitem__("flag", True) if p.startswith(("OK ", "ERR")) else None)
    lch.spawn([], headless=True)
    try:
        if not lch.wait_ready():
            print("FAIL: agent never became ready"); return
        time.sleep(1.0)
        print("[*] requesting dump ->", out)
        lch.dump(out)
        _wait_file(lch, out, done, 8)
    finally:
        lch.kill_all()
    time.sleep(0.3)
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        print("FAIL: no .pipstate produced"); return
    print(f"[*] produced {out} ({os.path.getsize(out)} bytes); validating ...")
    print("PASS -- game loaded and resumed from the produced pipstate" if _validate(out)
          else "FAIL: game rejected the produced pipstate")


def run_lock(lock_path, out):
    """Play a lock TAS via --check-input and auto-dump the resulting state --
    exactly the pipstate the server would serve to attackers of your lock."""
    lock_abs, out = os.path.abspath(lock_path), os.path.abspath(out)
    if not os.path.exists(lock_abs): sys.exit(f"lock not found: {lock_abs}")
    if os.path.exists(out): os.remove(out)
    done = {"flag": False}
    lch = Launcher(autodump=out,
                   on_agent=lambda p: done.__setitem__("flag", True) if p.startswith(("AUTODUMP_DONE", "ERR")) else None)
    print(f"[*] playing lock '{os.path.basename(lock_abs)}' -> auto-dump {out}")
    # graphical (capped ~60fps): headless runs can finish before our hooks install
    lch.spawn(["--check-input", lock_abs], headless=False)
    try:
        _wait_file(lch, out, done, 90)
        time.sleep(0.3)
    finally:
        lch.kill_all()
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        print("FAIL: no .pipstate produced (did the lock tick / terminate?)"); return
    print(f"[+] wrote {out} ({os.path.getsize(out)} bytes)")
    print("OK: this is the pipstate an attacker of your lock would receive."
          if _validate(out) else "WARNING: game rejected the produced pipstate")


def play_and_dump(extra_argv, out_prefix, hotkey_keysym):
    from Xlib import display
    lch = Launcher()
    lch.spawn(extra_argv, headless=False)
    if not lch.wait_ready(timeout=30):
        print("[!] agent not ready yet; will keep trying while you play.")
    d = display.Display(os.environ.get("DISPLAY", ":0"))
    kc = d.keysym_to_keycode(hotkey_keysym)
    def down(km, c): return c and (km[c >> 3] & (1 << (c & 7)))
    n, prev = 0, False
    print(f"[*] playing. Press F8 in-game to dump -> {out_prefix}_N.pipstate  (Ctrl+C to quit)")
    try:
        while True:
            cur = bool(down(d.query_keymap(), kc))
            if cur and not prev:
                n += 1
                path = os.path.abspath(f"{out_prefix}_{n}.pipstate")
                print(f"[*] F8 -> dumping to {path}")
                lch.dump(path)
            prev = cur
            time.sleep(1/60)
    except KeyboardInterrupt:
        print("\n[*] quitting")
    finally:
        lch.kill_all()


def main():
    ap = argparse.ArgumentParser(description="Dump current Pipin progress to .pipstate via Frida")
    ap.add_argument("--lock", help="play this lock TAS (json) headless, then auto-dump the resulting state")
    ap.add_argument("--load-state", dest="load_state", help="start from an existing .pipstate")
    ap.add_argument("-o", "--out", help="output .pipstate path (for --lock; default <lock>.pipstate)")
    ap.add_argument("--out-prefix", default=os.path.join(GAME_DIR, "progress"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    try:
        import frida  # noqa
    except ImportError:
        sys.exit("need frida:  pip3 install --break-system-packages --user frida")

    if args.selftest:
        selftest(); return

    if args.lock:
        out = args.out or (os.path.splitext(os.path.abspath(args.lock))[0] + ".pipstate")
        run_lock(args.lock, out); return

    extra = ["--load-state", os.path.abspath(args.load_state)] if args.load_state else []
    play_and_dump(extra, args.out_prefix, 0xffc5)   # F8


if __name__ == "__main__":
    main()
