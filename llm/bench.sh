#!/bin/sh
# bench.sh <hf-repo[:quant]> [backend-note]: run one llama.cpp completion on the phone (Docker, CPU),
# print a markdown row for docs/llm-bench.md. Models cache in /srv/models.
# Run on the phone: sudo sh bench.sh unsloth/gemma-4-E2B-it-GGUF:Q4_K_M >> llm-bench.md
M=${1:?usage: bench.sh hf-repo[:quant] [note]}
T=${T:-4}  # 4 = big M3 cores only; 8 threads is ~3x slower (waits on the A55s)
N=${2:-CPU $T threads}
C=${CTX:-2048}; KV=${KV:-q8_0}  # e.g. CTX=4096 KV=q8_0 sh bench.sh ... (quantized V cache needs flash attention)
out=$(docker run --rm -e LLAMA_CACHE=/root/.cache/llama.cpp -v /srv/models:/root/.cache/llama.cpp --entrypoint /app/llama-completion \
	ghcr.io/ggml-org/llama.cpp:light -hf "$M" -p "Explain in two sentences why old phones make good home servers." \
	-n 80 -t "$T" -c "$C" -ctk "$KV" -ctv "$KV" -fa on -no-cnv 2>&1)
tps() { echo "$out" | grep "common_perf_print: *$1" | sed -E 's/.*\( *[0-9.]+ ms per token, *([0-9.]+) tokens per second\).*/\1/'; }
load=$(echo "$out" | grep "load time" | sed -E 's/.*= *([0-9.]+) ms.*/\1/')
echo "| $(date +%F) | \`$M\` | $N | $C | $KV | $(tps 'prompt eval time') | $(tps 'eval time') | $(awk "BEGIN{printf \"%.1f\", $load/1000}") s |"
