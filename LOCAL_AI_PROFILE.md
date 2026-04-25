# Local AI Profile

## Hardware Summary

- CPU: AMD Ryzen 5 3500U
- RAM: 13.9 GB
- GPU: AMD Radeon Graphics (integrated, about 3 GB shown)
- Free disk: about 369 GB
- Installed runtime: Ollama

## Safe Recommendation

Use Ollama only. Do not add a second heavyweight local runtime unless needed.

### Default model

- `qwen3:4b`
  - Safest always-on choice when you are also building apps or browsing
  - Best default for idle auto-resume simulation on this machine

### High-quality idle mode

- `qwen2-math:7b`
  - Better for math-oriented generation quality
  - Use when the PC is idle and only one job runs at a time

### Reviewer model

- `deepseek-r1:7b`
  - Use only when reviewing or scoring candidate questions
  - Do not keep it loaded all day

### Lightweight fallback

- `qwen3:4b`
  - Use when working on code and running other apps at the same time

## Avoid

- `gpt-oss-20b`
- `qwen3:14b`
- `qwen3:30b`
- any 20B+ model for regular local use on this PC

These are too heavy for sustained multi-app use on this machine.

## Operating Rules

1. Keep only one local model active at a time.
2. Use `qwen3:4b` as the normal background default.
3. Use `qwen2-math:7b` only for higher-quality idle batches.
4. Use reviewer models only in short bursts.
5. Stop models after each batch job.
6. Do not generate huge batches in one call.

## Batch Guidance

- Good: 5-10 candidate questions per batch
- Fine: 10-20 if nothing else heavy is running
- Avoid: 30+ candidates with long explanations in one request

## Suggested Workflow

1. Generate normal idle batches with `qwen3:4b`
2. Run `qwen2-math:7b` only when you want a slower quality pass
3. Score candidates with `deepseek-r1:7b` only if needed
4. Save only high-scoring questions into `data/question_bank.json`
5. Stop the model after the batch

## Supervisor Mode

- `local_ai_supervisor.py` watches idle time, free memory, and time of day
- Daytime:
  - prefers `qwen3:4b`
  - runs only short single jobs
- Nighttime:
  - upgrades question generation to `qwen2-math:7b` when enough memory is free
  - alternates question jobs and material jobs
- If free memory gets too low, it skips the cycle and stops models

Recommended command:

```powershell
python local_ai_supervisor.py --loop
```

## Useful Commands

```powershell
ollama pull qwen3:4b
ollama pull qwen2-math:7b
ollama pull deepseek-r1:7b
```

```powershell
ollama ps
ollama stop qwen3:4b
ollama stop qwen2-math:7b
ollama stop deepseek-r1:7b
```

## Notes

- On this PC, stability matters more than chasing the biggest model.
- For repeated app-building work, a smaller always-usable model is better than a larger unstable one.
- The simulator should rotate jobs and run only short idle batches so the machine does not feel jammed.
