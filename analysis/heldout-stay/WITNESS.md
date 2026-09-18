# 凍結と実行の時刻の証跡

`SPEC.ja.md` §12 の 8 の記録。**サーバが記録した時刻**と**手元の時計の時刻**を分けて書く。
前者は GitHub API から 2026-09-18 に取得した値、後者は著者の機械の時計であり、第三者の証言ではない。

## サーバが記録した時刻 (GitHub)

| 事象 | 時刻 (UTC) | 取得元 |
|---|---|---|
| PR #8 の作成 (凍結 commit を head とする draft PR) | 2026-09-18T07:30:39Z | `GET /repos/mikotomiura/collapsed-decision-space/pulls/8` の `created_at` |
| 凍結 commit に対する `repro` workflow run 35319765158 の作成 → 完了 (success) | 07:30:41Z → 07:31:33Z | `GET .../actions/runs/35319765158` (`head_sha` = 凍結 commit) |
| 凍結 commit に対する `heldout-stay` workflow run 35319765323 の作成 → 完了 (success) | 07:30:42Z → 07:34:16Z | `GET .../actions/runs/35319765323` (`head_sha` = 凍結 commit) |

凍結 commit = `61dbd960142f6db51a83bbaf05dc3c7781cb6559`。PR の作成時刻が示すのは、この commit が
遅くとも 07:30:39Z にサーバに存在したことである。

- PR: https://github.com/mikotomiura/collapsed-decision-space/pull/8
- run: https://github.com/mikotomiura/collapsed-decision-space/actions/runs/35319765323
- run: https://github.com/mikotomiura/collapsed-decision-space/actions/runs/35319765158

## 手元の時計の時刻 (第三者の証言ではない)

| 事象 | 時刻 (UTC) |
|---|---|
| 凍結 commit の committer date | 2026-09-18T07:30:14Z |
| `--run` による `result.json` / `run.log` の作成 (ファイルの更新時刻) | 2026-09-18T07:35:08Z |

## これが示すこと・示さないこと

- 示す: 凍結した仕様と script が、遅くとも 07:30:39Z (サーバ時刻) には存在したこと。凍結 commit に対する
  両 OS の CI が 07:34:16Z までに緑になったこと。
- 示さない: 実行が CI の完了後だったこと (実行時刻は手元の時計の値である)。凍結前に誰も条件別の件数を
  見ていないこと (`SPEC.ja.md` §4 の宣言)。`--run` が 1 回しか実行されていないこと (`SPEC.ja.md` §12 の 6)。
