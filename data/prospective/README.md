# Prospective arms — per-draw outputs

The per-draw outputs of the two prospective arms (§6 of the manuscript), shipped byte for byte as the
run driver wrote them on 2026-09-15:

| Path | SHA-256 | Bytes |
|---|---|---|
| `control/run_annotation.jsonl` | `44571865b31e99c536e58f550df18a6affb9e1d9da163f3962ccbd7ac60295a3` | 682,525 |
| `control/run_records.jsonl` | `ca4ff2f042b855a1c0ef557b1e8fd2c8eea2d41ae44580d3a3de7902e99fe6b7` | 17,764,970 |
| `control/run-manifest.json` | `09fbacb6291e72740e934692bc89eae10f0292cfd409e8ddd15cff4c766629fc` | 1,351 |
| `primary/run_annotation.jsonl` | `ac5b9504b19d4d89fa997451568ffc5b14971edec24a6423d667ff131782ec0d` | 681,875 |
| `primary/run_records.jsonl` | `8fe42e6711537dafedf4fb4522b4d1377f323856d1a1049b7630420e6f4020ae` | 17,351,300 |
| `primary/run-manifest.json` | `98fa9b029b1767f0881bab6aabdfc0fb4cbe6b925f2cbed32e3ac5867a7a565d` | 1,357 |

- `run_records.jsonl` holds every draw's raw model output (`raw_response`), the prompts and the sampling
  parameters. `run_annotation.jsonl` is the read-out the scorer consumed (`pre_bias_destination_zone`
  per draw). `run-manifest.json` records the environment pins and the digests of the other two files.
- The digests above are pinned in `analysis/heldout-stay/freeze.json`, which was committed before
  these files entered the repository. `analysis/scripts/heldout_stay_check.py --verify` recomputes the
  held-out check from these files and requires byte equality with `analysis/heldout-stay/result.json`.
- These are **results, not frozen inputs** in the sense of `data/data.md`, and they are not in
  `data/raw/`. The sealed verdicts in `data/raw/{control,primary}-verdict.json` were computed from the
  annotation files here; `repro.sh` (sealed) does not recompute them.
- `.gitattributes` marks this directory `-text`, and the anonymous bundle copies it verbatim, so that
  a checkout with `core.autocrlf = true` does not change the bytes the digests describe.
- A `None` read-out records that no zone was read for the draw, and it does not mean the same thing
  in every run. In the **earlier completed run** that the hypothesis came from
  (`data/raw/bank_annotation.jsonl`, not these files), every `None` was the string `"null"` rejected
  by the plan schema. In **these two arms**, the control's `None` draws are almost all that same
  string, while most of the primary's are responses with no parseable JSON object (class `F`). The
  counts per class are in `analysis/heldout-stay/result.json` (`classes`); the classes are defined
  in `analysis/heldout-stay/SPEC.ja.md` §5.
