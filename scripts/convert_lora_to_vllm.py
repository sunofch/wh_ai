"""将 ms-swift 训练的 Qwen3.5 LoRA adapter 转换为 vLLM 兼容格式。

问题根源：
  HF 模型路径: model.language_model.layers.X
  vLLM 模型路径: language_model.model.layers.X
  → safetensors key 前缀需要交换 model/language_model 顺序

  另外 vLLM 使用融合模块名（qkv_proj / gate_up_proj / in_proj_qkvz / in_proj_ba），
  adapter_config.json 的 target_modules 必须换成融合名，
  否则 vLLM 扫描模型时匹配不到，不会对这些层套 LoRA。

用法：
    python scripts/convert_lora_to_vllm.py <adapter_dir> [output_dir]
"""
import json
import shutil
import sys
from pathlib import Path

import safetensors.torch as st
import torch

_KEY_OLD = "base_model.model.model.language_model."
_KEY_NEW = "base_model.model.language_model.model."

_SUBMODULE_TO_FUSED = {
    "q_proj":      "qkv_proj",
    "k_proj":      "qkv_proj",
    "v_proj":      "qkv_proj",
    "gate_proj":   "gate_up_proj",
    "up_proj":     "gate_up_proj",
    "in_proj_qkv": "in_proj_qkvz",
    "in_proj_z":   "in_proj_qkvz",
    "in_proj_b":   "in_proj_ba",
    "in_proj_a":   "in_proj_ba",
}


def convert_keys(tensors: dict[str, torch.Tensor]) -> tuple[dict[str, torch.Tensor], int]:
    renamed, count = {}, 0
    for k, v in tensors.items():
        new_k = k.replace(_KEY_OLD, _KEY_NEW, 1)
        if new_k != k:
            count += 1
        renamed[new_k] = v
    return renamed, count


def convert_target_modules(modules: list[str]) -> list[str]:
    result = set()
    for m in modules:
        result.add(_SUBMODULE_TO_FUSED.get(m, m))
    return sorted(result)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.parent / (src.name + "_vllm")

    safetensors_src = src / "adapter_model.safetensors"
    config_src = src / "adapter_config.json"

    for p in (safetensors_src, config_src):
        if not p.exists():
            print(f"ERROR: {p} not found")
            sys.exit(1)

    dst.mkdir(parents=True, exist_ok=True)

    # --- 转换 safetensors ---
    print(f"读取 {safetensors_src} ...")
    tensors = st.load_file(str(safetensors_src))
    print(f"  共 {len(tensors)} 个 tensor")

    new_tensors, renamed_count = convert_keys(tensors)
    print(f"  路径重命名: {renamed_count} 个 key")

    remaining = [k for k in new_tensors if _KEY_OLD in k]
    if remaining:
        print(f"  WARNING: {len(remaining)} 个 key 仍含旧前缀，请检查:")
        for k in remaining[:3]:
            print(f"    {k}")

    out_safetensors = dst / "adapter_model.safetensors"
    st.save_file(new_tensors, str(out_safetensors))
    print(f"  已写入 {out_safetensors}")

    # --- 转换 adapter_config.json ---
    print(f"读取 {config_src} ...")
    with open(config_src) as f:
        cfg = json.load(f)

    old_modules = cfg.get("target_modules", [])
    new_modules = convert_target_modules(old_modules)
    cfg["target_modules"] = new_modules
    print(f"  target_modules 旧: {old_modules}")
    print(f"  target_modules 新: {new_modules}")

    out_config = dst / "adapter_config.json"
    with open(out_config, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"  已写入 {out_config}")

    # 复制其余文件
    for f in src.iterdir():
        if f.name not in ("adapter_model.safetensors", "adapter_config.json"):
            shutil.copy2(f, dst / f.name)

    print(f"\n完成。转换后的 adapter 在:\n  {dst}")
    print("将 .env 中 VLM35_LORA_MODULES 的路径改为上面目录即可。")


if __name__ == "__main__":
    main()
