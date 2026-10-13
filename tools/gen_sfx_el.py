#!/usr/bin/env python3
"""用 ElevenLabs 的“文字生成音效”接口生成原始音效，存到 assets/third_party/elevenlabs/（Godot 不导入这个目录）。
再由 tools/gen_sfx.py 读进来裁剪、归一化、接循环，写到 assets/audio/。

用法: python3 tools/gen_sfx_el.py [名字前缀...]      （不给参数就把下面 SPECS 里还没生成的都生成）
      python3 tools/gen_sfx_el.py --list              （只列出要生成的条目和预计花多少积分，不花钱）

- 密钥：环境变量 ELEVENLABS_API_KEY，没有就读 ~/.config/guixu/elevenlabs_key（不进 git）
- 每条生成 variants 个版本：<名字>_v<k>.mp3；文件已经在了就跳过（不重复花积分）。要重新生成就先删掉那个文件
- 每次生成把描述、参数、时间、套餐写进同目录的 prompts.json（授权凭据：哪个声音是在什么套餐下生成的）
- 计费（2026-10 实测）：v2 模型大约每秒 9 积分（第一批 111 秒花了 1020）。Starter 套餐每月 4 万积分，有商用授权（免费套餐没有）
- 生成出来的声音不会自动放，全程不经过声卡
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "third_party" / "elevenlabs"
API = "https://api.elevenlabs.io/v1"

# 名字: (描述, 时长秒, 循环, 版本数, prompt_influence)
# 描述用英文写（模型对英文最熟），要具体：是什么东西、多大、在什么空间里、离耳朵多远；结尾说明不要音乐、人声
SPECS = {
    # 破舱（scripts/breach.gd）：外面一只带骨刺的东西先撞两下、爪子刮过艇壳，再一根骨刺扎穿、顺着艇壳锯开一道口子
    "creature_ram": (
        "A huge sea creature slams into the outside of a steel submarine hull, heard from inside the small steel "
        "compartment: a massive deep muffled thud, the whole hull booming and ringing afterwards, loose metal items "
        "rattling. Single impact, no music, no voices.",
        2.5, False, 3, 0.6),
    "claw_scrape": (
        "A giant sharp claw dragging slowly across the outside of a thick steel submarine hull, heard from inside: "
        "harsh grinding metallic screech and scratching, deep resonance through the hull plates. No music, no voices.",
        2.5, False, 3, 0.6),
    "claw_pierce": (
        "A sharp bony spike violently punches through a thick steel submarine hull and saws along it, heard from "
        "inside: a sharp metallic puncture crack, a shrieking rip of tearing steel, then high pressure water bursting "
        "in with a roar. No music, no voices.",
        3.0, False, 3, 0.6),
    # 挤压：模型做不出 3 秒内的渐强（breach_strain 六个版本都是先响后弱），改成要一段强度平稳的连续吱嘎，
    # 渐强、越绷越紧（加速）在 gen_sfx.py 的 breach_strain 里做
    "hull_groan": (
        "Continuous creaking and groaning of a thick steel submarine hull under heavy deep-sea pressure, heard from "
        "inside a small steel compartment: dense deep metallic creaks, stressed steel plates pinging and popping, "
        "steady constant intensity throughout, no build-up, no ending, no music, no voices.",
        6.0, False, 2, 0.6),
    # v0~v2 用的描述（都是先响后弱，不合用）："Thick steel submarine pressure hull straining under crushing deep-sea
    # pressure, heard from inside a small steel compartment: deep low metallic groans and creaks growing faster and
    # louder, stressed steel plates popping and pinging, rivets ticking, the hull about to give way."
    # v3 起换成下面这句，强调从轻到重的渐强、结尾停在最紧的时候
    "breach_strain": (
        "Crescendo: a steel submarine hull slowly buckling inward under deep-sea pressure, heard from inside. Starts "
        "quiet with a few faint creaks, then the metallic groaning and creaking gets steadily faster, louder and "
        "higher-pitched, steel pinging and popping more and more often, ending at maximum tension right before it "
        "breaks. Steadily rising intensity, no ending boom, no music, no voices.",
        3.0, False, 6, 0.7),
    "breach_burst": (
        "A thick steel submarine hull suddenly ruptures under extreme deep-sea pressure, heard from inside: an enormous "
        "deep metallic bang that shakes the whole hull, a violent shriek of tearing ripping steel, then a blast of "
        "high-pressure seawater exploding into the small steel room. No music, no voices.",
        4.0, False, 3, 0.6),
    "breach_jet": (
        "Continuous powerful high-pressure seawater jet blasting through a hole into a small steel room, like a giant "
        "fire hose: loud constant roaring hiss of the jet, water hammering on a steel floor and splashing off metal "
        "walls, heavy spray. Steady, no build-up, no music.",
        10.0, True, 3, 0.5),
    "flood_churn": (
        "Seawater flooding a small steel submarine compartment, heard from just above the water: turbulent churning "
        "water, heavy sloshing waves slapping steel walls and cabinets, constant gurgling bubbles bursting at the "
        "surface. Steady, no music.",
        10.0, True, 3, 0.5),
    "underwater_roar": (
        "Heard with the head submerged underwater inside a flooded steel room: deep muffled roaring rumble of a "
        "high-pressure water jet nearby, dense turbulent bubbles, low-frequency pressure throbbing in the ears, "
        "everything dull and muffled. Steady, no music.",
        10.0, True, 3, 0.5),
}


def api_key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        p = Path.home() / ".config" / "guixu" / "elevenlabs_key"
        if p.exists():
            k = p.read_text().strip()
    if not k:
        sys.exit("没有密钥：设 ELEVENLABS_API_KEY，或者写到 ~/.config/guixu/elevenlabs_key")
    return k


def request(path, key, body=None, timeout=180):
    req = urllib.request.Request(API + path, headers={"xi-api-key": key, "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def credits(key):
    try:
        d = json.loads(request("/user/subscription", key))
        return d.get("tier"), d.get("character_count"), d.get("character_limit")
    except urllib.error.HTTPError:
        return None, None, None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only_list = "--list" in sys.argv
    todo = []
    for name, (text, dur, loop, n, infl) in SPECS.items():
        if args and not any(name.startswith(a) for a in args):
            continue
        for k in range(n):
            f = OUT / f"{name}_v{k}.mp3"
            if not f.exists():
                todo.append((name, k, f, text, dur, loop, infl))
    cost = sum(int(t[4] * 10) for t in todo)
    print(f"要生成 {len(todo)} 条，预计 {cost} 积分")
    for t in todo:
        print(f"  {t[2].name}  {t[4]:.1f} 秒{'  循环' if t[5] else ''}")
    if only_list or not todo:
        return
    key = api_key()
    tier, used, limit = credits(key)
    if limit is not None:
        print(f"套餐 {tier}：本月已用 {used} / {limit} 积分")
        if limit - used < cost:
            sys.exit("积分不够，先不生成")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ".gdignore").touch()
    log_path = OUT / "prompts.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    for name, k, f, text, dur, loop, infl in todo:
        body = {"text": text, "duration_seconds": dur, "prompt_influence": infl,
                "model_id": "eleven_text_to_sound_v2"}
        if loop:
            body["loop"] = True
        for attempt in range(3):
            try:
                t0 = time.time()
                data = request("/sound-generation?output_format=mp3_44100_128", key, body)
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:300]
                print(f"  {f.name}: HTTP {e.code} {msg}")
                if e.code in (400, 401, 402, 403, 422):
                    sys.exit(1)
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"  {f.name}: 网络错误 {e}，重试")
            time.sleep(3)
        else:
            sys.exit("连续失败，停下")
        f.write_bytes(data)
        log[f.name] = {"text": text, "duration_seconds": dur, "loop": loop, "prompt_influence": infl,
                       "model_id": body["model_id"], "tier": tier, "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(f"  {f.name}  {len(data) / 1024:.0f} KB  {time.time() - t0:.1f} 秒")
    tier, used, limit = credits(key)
    if limit is not None:
        print(f"生成完：本月已用 {used} / {limit} 积分")


if __name__ == "__main__":
    main()
