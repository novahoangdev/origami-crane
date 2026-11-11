/**
 * In-app sound (synthesised by tools/sfx.py → assets/sfx): paper creases, the rewind whoosh, the awakening bell arpeggio, wing
 * beats, the vanishing shimmer, a garden ambience loop and the odd glass wind-chime (furin) ding.
 *
 * Played with expo-audio from small player pools (round robin, so quick repeats overlap instead of cutting each other off).
 * The scene calls sfxEvent from its frame worklet through scheduleOnRN. expo-audio is required lazily and everything sits in
 * try/catch: a binary built without the native module simply stays silent, and no sound is ever worth a crash.
 */
import { AppState } from "react-native";

type Player = { play(): void; pause(): void; seekTo(s: number): Promise<void>; volume: number; loop: boolean };
export type SfxEvent = "fold" | "drag" | "rewind" | "awaken" | "takeoff" | "climb" | "vanish" | "sheet";

const SRC = {
  crease_0: require("../../assets/sfx/crease_0.wav"),
  crease_1: require("../../assets/sfx/crease_1.wav"),
  crease_2: require("../../assets/sfx/crease_2.wav"),
  crease_3: require("../../assets/sfx/crease_3.wav"),
  rewind: require("../../assets/sfx/rewind.wav"),
  awaken: require("../../assets/sfx/awaken.wav"),
  takeoff: require("../../assets/sfx/takeoff.wav"),
  flutter: require("../../assets/sfx/flutter.wav"),
  vanish: require("../../assets/sfx/vanish.wav"),
  furin_0: require("../../assets/sfx/furin_0.wav"),
  furin_1: require("../../assets/sfx/furin_1.wav"),
  furin_2: require("../../assets/sfx/furin_2.wav"),
  ambience: require("../../assets/sfx/ambience.wav"),
};
type Key = keyof typeof SRC;

let audio: {
  createAudioPlayer: (src: number, opts?: object) => unknown;
  setAudioModeAsync: (m: object) => Promise<void>;
} | null = null;
const players: Partial<Record<Key, Player[]>> = {};
const rr: Partial<Record<Key, number>> = {};
let ambience: Player | null = null;
let started = false;
let flutterTimer: ReturnType<typeof setInterval> | null = null;
let furinTimer: ReturnType<typeof setTimeout> | null = null;
let lastDrag = 0;

const make = (k: Key, n: number) => {
  if (!audio) return;
  players[k] = Array.from({ length: n }, () => audio!.createAudioPlayer(SRC[k]) as Player);
};

const play = (k: Key, vol: number) => {
  const pool = players[k];
  if (!pool?.length) return;
  try {
    const i = ((rr[k] ?? -1) + 1) % pool.length;
    rr[k] = i;
    const p = pool[i];
    p.volume = Math.max(0, Math.min(1, vol));
    // seekTo is async: play once the rewind has landed, or a finished player plays nothing
    p.seekTo(0)
      .then(() => p.play())
      .catch(() => p.play());
  } catch {}
};

const scheduleFurin = () => {
  if (furinTimer) clearTimeout(furinTimer);
  furinTimer = setTimeout(() => {
    if (AppState.currentState === "active") {
      const k = (["furin_0", "furin_1", "furin_2"] as const)[Math.floor(Math.random() * 3)];
      play(k, 0.16 + Math.random() * 0.12);
    }
    scheduleFurin();
  }, 7000 + Math.random() * 9000);
};

/** load the players and start the ambience; safe to call more than once */
export const initSfx = () => {
  if (started) return;
  started = true;
  try {
    audio = require("expo-audio");
  } catch {
    audio = null;
    return;
  }
  try {
    audio!.setAudioModeAsync({ playsInSilentMode: true, interruptionMode: "mixWithOthers" }).catch(() => {});
    make("crease_0", 2);
    make("crease_1", 2);
    make("crease_2", 2);
    make("crease_3", 2);
    make("rewind", 1);
    make("awaken", 1);
    make("takeoff", 1);
    make("flutter", 2);
    make("vanish", 1);
    make("furin_0", 1);
    make("furin_1", 1);
    make("furin_2", 1);
    ambience = audio!.createAudioPlayer(SRC.ambience) as Player;
    ambience.loop = true;
    ambience.volume = 0.32;
    ambience.play();
    scheduleFurin();
    AppState.addEventListener("change", (st) => {
      if (!ambience) return;
      if (st === "active") ambience.play();
      else ambience.pause();
    });
  } catch {
    audio = null;
  }
};

const crease = (vol: number) => {
  const k = (["crease_0", "crease_1", "crease_2", "crease_3"] as const)[Math.floor(Math.random() * 4)];
  play(k, vol * (0.85 + Math.random() * 0.15));
};

const stopFlutter = () => {
  if (flutterTimer) clearInterval(flutterTimer);
  flutterTimer = null;
};

/** the scene's sound cues (called on the JS thread) */
export const sfxEvent = (e: SfxEvent) => {
  if (!audio) return;
  switch (e) {
    case "fold":
      crease(0.85);
      break;
    case "drag": {
      // the paper ticks under the finger: soft, throttled
      const now = Date.now();
      if (now - lastDrag < 140) return;
      lastDrag = now;
      crease(0.22);
      break;
    }
    case "sheet":
      crease(0.5);
      break;
    case "rewind":
      stopFlutter();
      play("rewind", 0.7);
      break;
    case "awaken":
      play("awaken", 0.75);
      break;
    case "takeoff": {
      play("takeoff", 0.7);
      // wing beats while it loops around the room, fading as it flies away
      stopFlutter();
      let n = 0;
      play("flutter", 0.5);
      flutterTimer = setInterval(() => {
        n += 1;
        if (n > 8) return stopFlutter();
        play("flutter", 0.5 * Math.pow(0.82, n));
      }, 1000);
      break;
    }
    case "climb":
      play("takeoff", 0.35);
      break;
    case "vanish":
      stopFlutter();
      play("vanish", 0.8);
      break;
  }
};
