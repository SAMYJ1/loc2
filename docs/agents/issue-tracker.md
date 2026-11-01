# Issue tracker: GitHub

本项目的任务和规格发布到 SAMYJ1/toAnywhere 的 GitHub Issues。
使用 gh CLI，在本仓库目录执行。

## 操作约定

- 首次写入前运行 `gh repo view --json nameWithOwner`，
  确认目标为 SAMYJ1/toAnywhere。
- 创建：`gh issue create --title "..." --body-file <file>`。
  多行正文写入临时文件，保留实际换行。
- 读取：`gh issue view <number> --json number,title,body,labels,comments`。
- 列表：`gh issue list --state open --json number,title,body,labels`；
  按需要使用 --label 和 --state 筛选。
- 更新正文：`gh issue edit <number> --body-file <file>`。
- 评论：`gh issue comment <number> --body-file <file>`。
- 标签：`gh issue edit <number> --add-label "..."` 或 --remove-label。
- 关闭：先发表评论说明原因，再运行 `gh issue close <number>`。
- 创建或更新后读回正文与标签，确认结果。

## 层级与依赖

优先使用 GitHub 原生 sub-issues 和 issue dependencies。
操作前检查当前 gh 版本的支持情况；必要时通过 gh api 操作。
API 所需数据库 id 与 issue number 不同，必须查询取得。

原生能力不可用时：
- 子任务正文注明 `Part of #<parent>`，父任务维护任务清单。
- 依赖写为 `Blocked by: #<number>`。
- 所有阻塞任务关闭后，任务才视为解除阻塞。

## Pull requests as a triage surface

PRs as a request surface: no.

## 技能用语

“publish to the issue tracker”表示创建 GitHub Issue。
“fetch the relevant ticket”表示读取对应 Issue 及其评论。
