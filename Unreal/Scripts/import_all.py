"""把 import_models.py 一个一个地跑（Interchange 在命令行模式下一个进程只能导一个）：
py -3.13 Unreal/Scripts/import_all.py [models|props|seabed_props|名字 …]"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ue_bg  # noqa: E402

CMD = ue_bg.UE.replace("UnrealEditor.exe", "UnrealEditor-Cmd.exe")
MODELS = ["submarine_exterior", "submarine_cockpit", "seabed"]
PROPS = ["brass_diya_lantern", "vintage_radio_transceiver", "power_box_01", "vintage_spacecraft_instrument", "old_gas_mask",
         "korean_fire_extinguisher_01", "plastic_thermos", "clipboard", "binder_notebook", "signal_flashlight", "retro_multimeter",
         "medical_box", "portable_cassette_player", "round_spectacles", "digital_wrist_watch", "screwdriver", "pliers",
         "medical_tape", "modified_thermos", "office_notepads", "pocket_watch", "adjustable_wrench", "seadogs_compass"]


SEABED_PROPS = ["antique_ceramic_vase_01", "brass_vase_03", "ceramic_pot", "coastal_cliff_04", "dutch_ship_medium", "moon_rock_01",
                "moon_rock_03", "moon_rock_05", "namaqualand_boulder_02", "treasure_chest", "tree_stump_02"]


def run_one(name):
    env = dict(os.environ, GUIXU_IMPORT=name)
    env["UE-LocalDataCachePath"] = ue_bg.DDC
    t0 = time.time()
    out = subprocess.run([CMD, ue_bg.PROJECT, "-run=pythonscript", f"-script={os.path.join(HERE, 'import_models.py')}",
                          "-unattended", "-nosplash", "-nosound", "-nullrhi", "-nop4", "-stdout"],
                         env=env, capture_output=True, creationflags=0x08000000)
    text = out.stdout.decode("utf-8", "replace")
    lines = [l for l in text.splitlines() if "[import]" in l and "个节点" in l or "Error:" in l]
    print(f"{name}（{time.time() - t0:.0f} 秒）：" + (lines[-1].split("[import]")[-1].strip() if lines else f"退出码 {out.returncode}"), flush=True)


if __name__ == "__main__":
    args = sys.argv[1:] or ["models", "props"]
    names = []
    for a in args:
        names += (MODELS if a == "models" else ["prop:" + p for p in PROPS] if a == "props"
                  else ["prop:" + p for p in SEABED_PROPS] if a == "seabed_props" else [a])
    for n in names:
        run_one(n)
