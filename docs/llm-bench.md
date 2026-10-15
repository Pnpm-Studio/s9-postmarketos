# LLM speed on the S9 (llama.cpp)

Galaxy S9 (Exynos 9810: 4x A55 + 4x M3, 3.6 GiB RAM), llama.cpp `ghcr.io/ggml-org/llama.cpp:light` in Docker, prompt "Explain in two sentences why old phones make good home servers.", 80 tokens, flash attention on. Context and KV-cache type per row (`CTX=`, `KV=` env vars of the script; defaults 2048 / q8_0). Rows before the script used llama.cpp defaults (auto context, f16 KV). GPU: see the end of this file (works, but 5x slower than CPU).

Add a row: `sudo sh llm/bench.sh <hf-repo[:quant]> [note] >> docs/llm-bench.md` on the phone.

| Date | Model | Backend | Ctx | KV | Prompt t/s | Gen t/s | Load |
|---|---|---|---|---|---|---|---|
| 2026-10-14 | `bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M` | CPU 8 threads | 49152 (auto) | f16 | 15.42 | 4.65 | 2.1 s |
| 2026-10-14 | `ggml-org/gemma-3-1b-it-GGUF` | CPU 8 threads | auto | f16 | 17.82 | 4.77 | 0.7 s |
| 2026-10-14 | `unsloth/gemma-4-E2B-it-GGUF:Q4_K_M` | CPU 8 threads | 2048 | f16 | 7.21 | 1.48 | 8.1 s |
| 2026-10-14 | `ggml-org/gemma-3-1b-it-GGUF` | CPU 8 threads, FA on | 2048 | f16 | 16.00 | 2.69 | 0.6 s |
| 2026-10-14 | `ggml-org/gemma-3-1b-it-GGUF` | CPU 8 threads, FA on | 2048 | q8_0 | 16.10 | 2.51 | 0.8 s |
| 2026-10-14 | `unsloth/gemma-4-E2B-it-GGUF:UD-Q4_K_XL` | CPU 8 threads, FA on | 32768 | q4_0 | 6.90 | 1.42 | 9.1 s |
| 2026-10-14 | `SC117/MiniCPM5-2B-abliterated-FIT-GGUF:Q6_K` | CPU 8 threads, FA on | 8192 | q8_0 | 6.32 | 1.59 | 1.2 s |
| 2026-10-14 | `SC117/MiniCPM5-2B-abliterated-FIT-GGUF:Q6_K` | CPU 6 threads, FA on | 2048 | q8_0 | – | 3.46 | – |
| 2026-10-14 | `SC117/MiniCPM5-2B-abliterated-FIT-GGUF:Q6_K` | **CPU 4 threads (big cores)**, FA on | 2048 | q8_0 | – | **5.06** | – |

Thread count matters most: `-t 4` (the four M3 big cores) is 3.4x faster than `-t 8`, because each token waits for the slow A55 threads. `bench.sh` now defaults to `T=4`.

GPU (Mali-G72 MP18, Android r19p0 blob in a bionic chroot, 2026-10-15): Vulkan works with a patched llama.cpp (`a0e6dc7` + `llm/vulkan-mali-g72-r19.patch`: Vulkan 1.1 instead of 1.2, no timeline semaphores, norm shaders at 256 threads because r19 caps workgroups at 384). It needs `GGML_VK_SERIALIZE_SUBMISSIONS=1`, otherwise overlapping submits hit `DATA_INVALID_FAULT` and the device is lost. It is far slower than the CPU, so it's a dead end:

| Model | Backend | FA | Prompt t/s (pp64) | Gen t/s (tg16) |
|---|---|---|---|---|
| MiniCPM5-2B Q6_K | Vulkan, `-ngl 99` | off | 1.57 | 1.07 |
| MiniCPM5-2B Q6_K | Vulkan, `-ngl 99` | on | 1.53 | 0.63 |
| MiniCPM5-2B Q6_K | CPU 4 threads (reference) | on | – | 5.06 |

CPU+GPU split (`-ngl N`, 2026-10-15, tg16, FA on): llama.cpp runs CPU and GPU layers one after the other for each token, so every layer moved to the slow GPU lowers speed. Partial offload also needs `--no-host 1`; without it the CPU layers' weights land in Vulkan host memory and CPU speed collapses (16 tokens didn't finish in 300 s).

| Setup | Gen t/s |
|---|---|
| **Vulkan build, `-dev none -t 4` (CPU only)** | **5.57** |
| `-ngl 0 --no-host 1` | 4.00 |
| `-ngl 8 --no-host 1` | 1.95 |
| `-ngl 99` | 0.63 |

`-t 2` 3.73, `-t 3` 4.40. The big cores stay at 1.79 GHz under 4-thread load even after raising `/sys/power/cpufreq_max_limit` (the kernel's multi-core cap), so the clock can't be raised either.

OpenCL is out too: llama.cpp's OpenCL kernels need subgroup ops that r19 doesn't expose.

## Packages: Mali driver in the image, llama optional

- **`s9-mali`** (pulled in by `s9-server`, so it is in every image): a minimal bionic root at `/usr/lib/s9-mali/root` with the `libGLES_mali` closure, the linker, `/opt/vk/libvulkan.so` and `vkprobe`. Service `s9-mali` bind-mounts `/dev`, `/proc`, `/sys` and `/srv/models` -> `/models`. `mali-run <prog> [args]` runs a binary from the root's `/opt/bin` (or an absolute path inside the root) as root with `GGML_VK_SERIALIZE_SUBMISSIONS=1`.
- **`s9-llama-vk`** (in the release image): the patched llama.cpp (`llm/vulkan-mali-g72-r19.patch`) `llama-bench`, `llama-cli` and `llama-server` in the root's `/opt/bin`. Built into the image via `extra_packages`; the model is not included.
- Build: `pkg/s9-mali/stage.sh` and `pkg/s9-llama-vk/stage.sh` stage the files into pmaports, then `pmbootstrap build s9-mali s9-llama-vk`.
- Test: `mali-run vkprobe`, then `mali-run llama-bench -m /models/minicpm5-2b-q6_k.gguf -ngl 99` (tg16 1.08 t/s, same as the hand-made chroot).
- The image now carries proprietary Samsung blobs: don't publish it.
