# Execution environment

The environment is pinned by a lockfile.

## Lockfile

| File | Location | Origin | State |
|---|---|---|---|
| `uv.lock` | `env/uv.lock` | Copied from the upstream source repository | Present, unmodified |
| `pyproject.toml` | `env/pyproject.toml` | The upstream project definition | Present, **not trimmed** — see below |

### Why the project definition was not trimmed

The obvious move would have been to cut the dependency list down to what the analyses here need and
to regenerate the lockfile. **That was not done.** The SHA-256 of `env/uv.lock` equals the
`uv_lock_sha256` pinned in the completed run's manifest, and regenerating the lockfile would break
that equality — and with it the only means of stating that the analysis environment derives from the
same lockfile the measurement ran under. A lockfile here is evidence, not a convenience, so it is
kept byte for byte. `analysis/scripts/verify_data_hashes.py` checks the equality on every run rather
than asserting it.

The cost is a dependency set wider than the analyses strictly require. The only practical effect is
the time `uv sync` takes; the heavy machine-learning stacks sit behind optional extras and are not
installed by default.

### Running it (`--no-install-project` is required)

```bash
uv sync --frozen --no-install-project --project env
```

`env/pyproject.toml` declares `module-root = "src"`, and this repository has no `src/`. Without the
flag the command fails with `Expected a Python module at: env/src/erre_sandbox/__init__.py`. The
analysis scripts read the apparatus through `PYTHONPATH=analysis/apparatus`, so the project itself
never needs to be installed. `repro.sh` invokes it in exactly this form.

## Environment of the completed measurement

Taken from `env_pins` in `data/raw/cproper-manifest.json`, which is the machine-readable original;
the table below is a reading of it.

| Item | Value |
|---|---|
| Model | `qwen3:8b` |
| Model digest | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |
| Backend | ollama 0.31.1 |
| `think` | `false` |
| Python | 3.11.15 |
| httpx / pydantic | 0.28.1 / 2.13.2 |
| VRAM | 16.0 GB |
| Zone-bias environment pin | 0.2 (the zone is read before any bias is applied) |
| `uv.lock` SHA-256 | `9cc70f9dc5d61f6c74c08dee4dd73815993861022a80781a75ef5d873860c0f7` |
| Scale | *M* = 300 × *K* = 8 = 4,800 draws |

## Environment registered for the prospective run

The prospective run happens after in-principle acceptance. Its conditions are frozen in
`manuscript/main.md` §C.

| Item | Value |
|---|---|
| Primary model | `llama3.1:8b`, digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` |
| Control model | `qwen3:8b`, re-run |
| Backend | ollama 0.32.12 |
| GPU | NVIDIA GeForce RTX 5060 Ti (16,311 MiB) |
| Operating system | Windows 11 |
| Scale | two arms × 4,800 = 9,600 draws, projected at roughly 5.09 h |

> Substituting the model, changing the backend version, altering any threshold, the seed, *M*, *K*,
> or the frozen context bank are **not** treated as minor deviations (`manuscript/main.md` §H).

## Environment the reproduction script was run under

| Item | Value |
|---|---|
| Operating system | Windows 11; also verified on Linux (WSL2) and in the public CI on Ubuntu and Windows |
| Python | 3.11.15, obtained by `uv` from the lockfile |
| uv | 0.11.7 |
| Date | 2026-09-13 |

> `repro.sh` reproduces the **analysis**, not the language-model draws. Draws do not recur when
> regenerated, so the frozen output in `data/raw/` is treated as an input.

## A note on determinism

Data originating upstream assumes floating-point values quantised to six decimal places. Hashing a
raw float without re-quantising it produces a one-ULP difference between Windows and Linux. The
scripts here write their output with LF endings and quantised values, which is what lets the CI
require byte-identical artefacts from both platforms.
