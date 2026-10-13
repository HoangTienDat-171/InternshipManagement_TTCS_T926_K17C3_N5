# Git branch recovery audit — 2026-10-13

## Git before

- Main: `b7ed285022bde8aaef46cefa6f9899fb87207127`.
- Develop: `87cd5f92eeac96adbe6e8e9091fc57c9588972e2`.
- Common ancestor: `99e4c76eb4ee0457eed9edf9da6fa04fa468f5da`.
- Develop-only / main-only commit count: **2 / 11**.
- Audited all **42** GitHub PRs, remote branches, local branches, existing worktrees, and both sides of the history. No open PRs or remote feature tips outside main/develop were found.
- Owner workspace remains dirty on `feature/admin-temporary-password-reset`; README, launcher edits, the deleted duplicate wrapper, both untracked workbooks, existing stashes and worktrees are preserved. The live app is not stopped by this recovery.

## Integration strategy and scope

Merge `origin/main` into `integration/recover-main-changes-to-develop`, created from `origin/develop`, using a merge commit with both original parents. No squash, rebase, cherry-pick, branch deletion, direct develop push, or main update.

Only two non-merge source commits are absent from develop:

- `80e261f`: PR #40, accepted portal styling, month/year picker, dropdowns, launch locking/child-process ownership, and one startup script.
- `dddc610`: PR #41, role-based mini sidebar, tooltips/alignment, dark theme, login redesign, and demo shortcuts.

The other nine main-only commits are historical merge records. The corresponding feature source changes are already present in develop. Importing the complete main history preserves these records without resurrecting previously removed functionality.

Develop-only PR #42 (`93a7136`, merged as `87cd5f9`) is retained: admin reset endpoint, SMTP refusal handling, expiring/single-use temporary passwords, forced password change, session revocation, admin UI, and migration `20261012_admin_temporary_password_reset.sql`.

US24, US25/US26, US27/US28, and PR #37 launcher source commits are already in both histories. Other remote feature tips are ancestors of main or develop; there are no additional unmerged features to import.

## Conflict resolutions and verification fixes

- `frontend/src/index.css`: retain both the main sidebar/theme rules and develop password reset/visibility controls.
- `frontend/src/views/SupportRequestView.css`: consolidate dark selectors/property declarations from both sides. Where both sides set the same property, the newer develop styling wins; main-only borders, layout and text rules remain.
- Keep combined AccountManagementView: main theme tokens plus the newer develop reset endpoint/confirmation UI.
- Keep backend app, SQL schema and all migrations **byte-for-byte identical to origin/develop**. No migration is added, duplicated or executed on the live database.
- Preserve the main startup lock and owner-token child verification. Skip redundant child probing when the backend has already passed direct ownership verification; the existing backend reuse regression then passes without spawning a probe unnecessarily.
- Correct dated US24 API fixtures by freezing the clock to their explicit October 8 test day. The original production rule is retained. The owner's preference for upcoming leave programs was recorded during audit; implementing that separate behavior is outside this history recovery.
- Align allowance regression fixtures/assertions with the previously accepted production ledger: current open programs, multiple payments in one month, distinct row IDs under concurrent submissions, current history event names, and valid payloads for permission-denial tests. Add explicit closed/upcoming-program rejection checks. No production allowance rule is changed.
- Update stale README allowance descriptions to reflect the existing multi-payment behavior.
- Trim one pre-existing extra blank line in MonthYearPicker.css so diff checking passes.

## Verification

- Backend app compile: PASS.
- Final full isolated SQLite regression: **292 tests PASS**. SMTP is mocked/disabled; no live MySQL tests or data reset. Initial attempts exposed missing test-only httpx, seed suppression in the harness, obsolete allowance assertions and a dated US24 API fixture; these were corrected before the final passing run.
- Targeted allowance regression: **28 tests PASS**.
- Frontend lint: PASS with two existing set-state-in-effect warnings in unchanged LeaveManagementView.jsx.
- Frontend production build: PASS, existing bundle size advisory above 500 kB.
- Headless browser QA against a separate Vite port with mocked API and disabled session sockets: PASS. Login light/dark and 375px layout; demo shortcuts; Admin/HR/Mentor/TTS menus (9/8/4/10); expanded/collapsed toggle; tooltip names; centered icons; no sidebar horizontal overflow; admin reset confirmation/request contract; support dark dropzone and hover. Screenshots were inspected.
- UI QA does not claim real SMTP delivery or owner UAT. Live MySQL migration execution is NOT TESTED and was not authorized by this recovery.
- Develop rules endpoint: no active branch rules. Branch protection endpoint: branch not protected. No rules or settings were changed.
- Git diff/secret/generated-file checks are performed again immediately before push. Reports below are intentional audit artifacts; test dependencies, logs, screenshots, caches and build outputs remain outside tracked changes.

## PR audit

Columns distinguish merge-record ancestry from feature-code ancestry. Missing merge records do not imply missing functionality. Full titles, files changed, source commit SHAs and merge timestamps are in [20261013-pr-branch-audit.json](20261013-pr-branch-audit.json).

| PR | Author | Base ← head | Merge SHA | Merge on main/develop | Source commits on main/develop | Merged UTC |
| --- | --- | --- | --- | --- | --- | --- |
| [#1](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/1) | HoangTienDat-171 | main ← feature/US01-auth | `a3743f9` | YES/YES | YES/YES | 2026-09-27T17:26:08Z |
| [#2](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/2) | HoangTienDat-171 | main ← feature/US01-auth | `b9c7c1f` | YES/YES | YES/YES | 2026-09-28T06:39:36Z |
| [#3](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/3) | HoangTienDat-171 | main ← feature/US01-auth | `6e4c954` | YES/YES | YES/YES | 2026-09-28T17:14:38Z |
| [#4](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/4) | HoangTienDat-171 | main ← feature/sprint2-us08-email-notification | `84d958d` | YES/YES | YES/YES | 2026-10-01T05:12:30Z |
| [#5](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/5) | HoangTienDat-171 | develop ← feature/sprint2-internal-mailbox | `c377aa3` | YES/YES | YES/YES | 2026-09-30T15:52:12Z |
| [#6](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/6) | HoangTienDat-171 | main ← fix-loi-giao-dien | `e4f9d5e` | YES/YES | YES/YES | 2026-10-01T05:12:28Z |
| [#7](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/7) | HoangTienDat-171 | main ← feature/sprint2-us14-personal-schedule | `144d12e` | YES/YES | YES/YES | 2026-10-01T16:32:33Z |
| [#8](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/8) | VuDucDat2006 | main ← feature/guest-and-email-updates | `488d0bf` | YES/YES | YES/YES | 2026-10-02T05:40:39Z |
| [#9](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/9) | HoangTienDat-171 | main ← integration/us14-guest-email | `ea00f99` | YES/YES | YES/YES | 2026-10-02T05:40:38Z |
| [#10](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/10) | HoangTienDat-171 | main ← feature/sprint2-us16-task-progress | `54e37e3` | YES/YES | YES/YES | 2026-10-02T06:38:17Z |
| [#11](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/11) | HoangTienDat-171 | main ← fix/sprint2-us14-us16-ui-integration | `5d352c0` | YES/YES | YES/YES | 2026-10-02T07:05:59Z |
| [#12](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/12) | HoangTienDat-171 | main ← fix/sprint2-us08-us16-final-cleanup | `5bd1884` | YES/YES | YES/YES | 2026-10-02T11:58:40Z |
| [#13](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/13) | HoangTienDat-171 | main ← integration/sprint2-final | `8a2331c` | YES/YES | YES/YES | 2026-10-04T17:48:07Z |
| [#14](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/14) | HoangTienDat-171 | develop ← main | `af26bcd` | YES/YES | YES/YES | 2026-10-04T18:28:13Z |
| [#15](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/15) | HoangTienDat-171 | main ← develop | `9bff37d` | YES/YES | YES/YES | 2026-10-04T18:36:29Z |
| [#16](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/16) | HoangTienDat-171 | main ← fix/us23-shift-creation-ux | `47d513f` | YES/YES | YES/YES | 2026-10-06T08:56:38Z |
| [#17](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/17) | HoangTienDat-171 | main ← docs/sprint2-handoff | `27d3188` | YES/YES | YES/YES | 2026-10-06T09:01:18Z |
| [#18](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/18) | HoangTienDat-171 | develop ← integration/sprint3-baseline-sync | `afcec77` | YES/YES | YES/YES | 2026-10-06T14:46:33Z |
| [#19](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/19) | HoangTienDat-171 | main ← develop | `3100807` | YES/YES | YES/YES | 2026-10-06T15:01:10Z |
| [#20](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/20) | HoangTienDat-171 | main ← feature/sprint3-us05-document-review | `eca57f4` | YES/YES | YES/YES | 2026-10-07T03:00:18Z |
| [#21](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/21) | HoangTienDat-171 | develop ← feature/sprint3-us05-document-review | `d90bcbb` | YES/YES | YES/YES | 2026-10-07T06:34:51Z |
| [#22](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/22) | HoangTienDat-171 | main ← develop | `4d72c84` | YES/YES | YES/YES | 2026-10-07T06:35:12Z |
| [#23](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/23) | dtc245180064-beep | develop ← feature/sprint3-us06-application-flow | `675bd3b` | YES/YES | YES/YES | 2026-10-07T08:37:34Z |
| [#24](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/24) | HoangTienDat-171 | main ← develop | `9516258` | YES/YES | YES/YES | 2026-10-07T08:38:01Z |
| [#25](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/25) | VuDucDat2006 | main ← feature/sprint3-us12-us30-mentor-assignment | `75a5256` | YES/YES | YES/YES | 2026-10-07T10:31:59Z |
| [#26](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/26) | HoangTienDat-171 | main ← fix/closed-program-overlap | `67e097a` | YES/YES | YES/YES | 2026-10-07T12:29:16Z |
| [#27](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/27) | HoangTienDat-171 | develop ← sync/main-to-develop-20261007 | `a13f2dc` | YES/YES | YES/YES | 2026-10-07T15:57:33Z |
| [#28](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/28) | HoangTienDat-171 | main ← develop | `091c6ea` | YES/NO | YES/YES | 2026-10-07T15:58:09Z |
| [#29](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/29) | HoangTienDat-171 | develop ← fix/us14-schedule-warning-regression | `25a2520` | YES/YES | YES/YES | 2026-10-07T16:17:58Z |
| [#30](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/30) | HoangTienDat-171 | main ← develop | `cf8cd49` | YES/NO | YES/YES | 2026-10-07T17:01:30Z |
| [#31](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/31) | HoangTienDat-171 | main ← feature/sprint3-us24-leave-request | `2b8cba9` | YES/NO | YES/YES | 2026-10-08T06:45:41Z |
| [#32](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/32) | HoangTienDat-171 | develop ← feature/sprint3-us24-leave-request | `cd41923` | YES/YES | YES/YES | 2026-10-08T07:42:12Z |
| [#33](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/33) | HoangTienDat-171 | main ← develop | `f493224` | YES/NO | YES/YES | 2026-10-08T07:42:42Z |
| [#34](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/34) | HoangTienDat-171 | develop ← feature/sprint3-us25-us26-allowance | `bd67491` | YES/YES | YES/YES | 2026-10-08T11:26:14Z |
| [#35](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/35) | HoangTienDat-171 | main ← feature/sprint3-us25-us26-receipt-confirmation | `1e4b789` | YES/NO | YES/YES | 2026-10-08T16:31:08Z |
| [#36](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/36) | HoangTienDat-171 | main ← develop | `2bbfce1` | YES/NO | YES/YES | 2026-10-08T16:59:49Z |
| [#37](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/37) | VuDucDat2006 | develop ← feature/one-click-server-startup | `99e4c76` | YES/YES | YES/YES | 2026-10-09T13:35:32Z |
| [#38](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/38) | VuDucDat2006 | develop ← feature/sprint3-us27-us28-support-requests | `c96a857` | YES/YES | YES/YES | 2026-10-09T13:34:50Z |
| [#39](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/39) | HoangTienDat-171 | main ← develop | `c779240` | YES/NO | YES/YES | 2026-10-09T13:53:01Z |
| [#40](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/40) | HoangTienDat-171 | main ← feature/portal-ui-ux-enhancement | `ac34750` | YES/NO | YES/NO | 2026-10-10T04:32:52Z |
| [#41](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/41) | HoangTienDat-171 | main ← feature/portal-mini-sidebar | `b7ed285` | YES/NO | YES/NO | 2026-10-10T08:11:46Z |
| [#42](https://github.com/HoangTienDat-171/InternshipManagement_TTCS_T926_K17C3_N5/pull/42) | HoangTienDat-171 | develop ← feature/admin-temporary-password-reset | `87cd5f9` | NO/YES | NO/YES | 2026-10-12T15:26:38Z |

## Remote branch audit

| Branch | Tip | Ancestry / reason retained |
| --- | --- | --- |
| origin | `b7ed285` | main ancestor; included in recovery |
| origin/US-09 | `b939fcf` | develop ancestor |
| origin/develop | `87cd5f9` | develop ancestor |
| origin/docs/sprint2-handoff | `017f497` | develop ancestor |
| origin/feature/US01-auth | `2a02ae2` | develop ancestor |
| origin/feature/admin-temporary-password-reset | `93a7136` | develop ancestor |
| origin/feature/guest-and-email-updates | `3f1fe8a` | develop ancestor |
| origin/feature/one-click-server-startup | `739fa5f` | develop ancestor |
| origin/feature/portal-mini-sidebar | `dddc610` | main ancestor; included in recovery |
| origin/feature/portal-ui-ux-enhancement | `80e261f` | main ancestor; included in recovery |
| origin/feature/sprint2-internal-mailbox | `6f1d952` | develop ancestor |
| origin/feature/sprint2-us08-email-notification | `84d958d` | develop ancestor |
| origin/feature/sprint2-us10-contract-confirmation | `b20dcb2` | develop ancestor |
| origin/feature/sprint2-us14-personal-schedule | `212ec52` | develop ancestor |
| origin/feature/sprint2-us15-mentor-task | `e3a99b7` | develop ancestor |
| origin/feature/sprint2-us16-task-progress | `cc0f594` | develop ancestor |
| origin/feature/sprint2-us17-weekly-report | `17f245b` | develop ancestor |
| origin/feature/sprint2-us18-weekly-report-review | `8f88430` | develop ancestor |
| origin/feature/sprint2-us19-intern-evaluation | `f9c8c07` | develop ancestor |
| origin/feature/sprint2-us21-attendance | `a41d954` | develop ancestor |
| origin/feature/sprint2-us23-flexible-work-shifts | `de57498` | develop ancestor |
| origin/feature/sprint3-us05-document-review | `a299e0d` | develop ancestor |
| origin/feature/sprint3-us06-application-flow | `bbe8b77` | develop ancestor |
| origin/feature/sprint3-us12-us30-mentor-assignment | `e707a21` | develop ancestor |
| origin/feature/sprint3-us24-leave-request | `30d2c46` | develop ancestor |
| origin/feature/sprint3-us25-us26-allowance | `41c9533` | develop ancestor |
| origin/feature/sprint3-us25-us26-receipt-confirmation | `8d9f0f4` | develop ancestor |
| origin/feature/sprint3-us27-us28-support-requests | `9013965` | develop ancestor |
| origin/fix-loi-giao-dien | `59e2c8a` | develop ancestor |
| origin/fix/closed-program-overlap | `e755309` | develop ancestor |
| origin/fix/sprint2-us08-us16-final-cleanup | `af47d0d` | develop ancestor |
| origin/fix/sprint2-us14-us16-ui-integration | `66f9474` | develop ancestor |
| origin/fix/us14-schedule-warning-regression | `5b87cf3` | develop ancestor |
| origin/fix/us18-intern-dashboard-layout | `1959887` | develop ancestor |
| origin/fix/us23-shift-creation-ux | `92c503a` | develop ancestor |
| origin/integration/sprint2-final | `a41d954` | develop ancestor |
| origin/integration/sprint2-us08-us16-baseline | `5bd1884` | develop ancestor |
| origin/integration/sprint3-baseline-sync | `27d3188` | develop ancestor |
| origin/integration/us14-guest-email | `488d0bf` | develop ancestor |
| origin/main | `b7ed285` | main ancestor; included in recovery |
| origin/sync/main-to-develop-20261007 | `67e097a` | develop ancestor |

## Publication state

Prepared for a normal push of the integration branch and a PR targeting **develop**. Merge is authorized by the owner only after all verification and GitHub checks pass. Final PR number, merge SHA, after-state and canonical-workspace checks are reported after GitHub confirms the result. Main must remain at the recorded before SHA.
