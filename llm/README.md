# llama.cpp on the S9 (in the image as `s9-llama-vk`; the model is not)

`llama.cpp/` is upstream llama.cpp pinned at `a0e6dc7` (2026-10-14) as a git submodule.
`vulkan-mali-g72-r19.patch` is our work on top of it: it makes the Vulkan backend run, somewhat, on the
Mali-G72 MP18 with Samsung's Android r19p0 driver (Vulkan 1.1 instead of 1.2, no timeline semaphores,
norm shaders at 256 threads because r19 caps workgroups at 384).

It runs, but it is slower than the CPU (tg ~1 t/s on the GPU vs ~5 t/s on 4 big cores, see
`../docs/llm-bench.md`). The fastest setup is this same build with `-dev none -t 4`.

## Model

MiniCPM5-2B abliterated, Q6_K (apache-2.0, base `openbmb/MiniCPM5-2B`):
<https://huggingface.co/SC117/MiniCPM5-2B-abliterated-FIT-GGUF/blob/main/MiniCPM5-2B-abliterated-Q6_K.gguf>

```sh
wget https://huggingface.co/SC117/MiniCPM5-2B-abliterated-FIT-GGUF/resolve/main/MiniCPM5-2B-abliterated-Q6_K.gguf
sha256sum MiniCPM5-2B-abliterated-Q6_K.gguf   # 2d31080e2c05588d48230bb7f2ffb331a9ab61f4de0787b00138e3611b256e7c
```

## Build (Android NDK r27c, on a PC)

The GPU path needs the Mali blob (`s9-mali`, a bionic root with Samsung's driver), which the image ships.

```sh
git submodule update --init llm/llama.cpp
git -C llm/llama.cpp apply ../vulkan-mali-g72-r19.patch
# Vulkan-Headers and SPIRV-Headers checkouts for the includes; glslc comes with the NDK
cmake -S llm/llama.cpp -B vk-build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE=$NDK/build/cmake/android.toolchain.cmake \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=29 \
  -DGGML_VULKAN=ON -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DLLAMA_CURL=OFF \
  -DCMAKE_C_FLAGS=-march=armv8-a \
  -DCMAKE_CXX_FLAGS="-march=armv8-a -I$VULKAN_HEADERS/include -I$SPIRV_HEADERS/include" \
  -DVulkan_INCLUDE_DIR=$VULKAN_HEADERS/include \
  -DVulkan_GLSLC_EXECUTABLE=$NDK/shader-tools/linux-x86_64/glslc \
  -DVulkan_LIBRARY=$NDK/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/29/libvulkan.so
cmake --build vk-build --target llama-bench llama-cli llama-server
```

Package it as `s9-llama-vk` with `../pkg/s9-llama-vk/stage.sh` (expects the build in `<workdir>/gpu/vk-build`).

## Run

```sh
mali-run llama-bench -m /models/minicpm5-2b-q6_k.gguf -dev none -t 4      # CPU, fastest
GGML_VK_SERIALIZE_SUBMISSIONS=1 mali-run llama-bench -m /models/minicpm5-2b-q6_k.gguf -ngl 99   # GPU
```

`GGML_VK_SERIALIZE_SUBMISSIONS=1` is required on the GPU: overlapping submits hit `DATA_INVALID_FAULT` and lose the device.
`bench.sh` is the older Docker (CPU) benchmark behind the first rows of `../docs/llm-bench.md`.
