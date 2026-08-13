# 每日开发与 Git/GitHub 工作流程

本文件是一份可在 VS Code Terminal 中逐项执行的 checklist。命令默认在项目根目录 `AI-Quant-Lab` 中运行，并且一次只执行一条；先检查结果，再继续下一条。

## 一、开始工作前

### 1. 检查分支、上游和本地改动

```powershell
git status -sb
```

目的：同时查看当前分支、与上游分支的关系以及未提交改动。

当前仓库通常应显示 `main...origin/main`。如果存在上次遗留的修改，应先弄清这些修改的状态和用途，不要覆盖或混入无关任务。

如需单独确认分支：

```powershell
git branch --show-current
```

### 2. 确认 Python 环境

如果终端尚未使用项目环境，在 PowerShell 中激活 Python 3.11 虚拟环境：

```powershell
.\.venv311\Scripts\Activate.ps1
```

然后检查：

```powershell
python --version
```

目的：确认当前使用项目预期的 Python 3.11，而不是其他全局解释器。

### 3. 必要时检查远端更新

```powershell
git fetch
```

目的：更新本地保存的远端分支信息，但不合并代码，也不修改工作文件。该命令需要网络连接。

再次检查：

```powershell
git status -sb
```

只有在工作区干净、确认需要同步且不希望产生合并提交时，才执行：

```powershell
git pull --ff-only
```

目的：仅允许快进同步；如果本地和远端已经分叉，命令会停止，避免自动创建意外的合并提交。

不要在存在未理解或未保存的本地改动时机械执行 `git pull`。

## 二、开发过程中

- 先明确任务范围、预计修改文件和验证方式。
- 小步修改，每完成一步立即运行与风险相称的测试。
- 使用 Codex 时，按任务约定执行审批流程；不要默认授权连续修改大量文件。
- 任何订单、自动化 Paper Trading 或 Live Trading 能力必须单独设计并明确批准。
- 定期查看尚未暂存的具体变化：

```powershell
git diff
```

目的：审阅已跟踪文件的实际内容变化，而不只是查看文件名。

查看包括未跟踪文件在内的总体状态：

```powershell
git status --short
```

如果出现任务范围之外的文件变化，先停止并查明来源，不要随意删除或覆盖。

## 三、判断是否需要更新文档

普通代码修改通常不需要更新 docs。完成工作后先分类：

- 项目长期目标、范围、总体架构或协作原则变化：检查 `project_context.md`
- 当前阶段、重要完成项、验证结果、已知问题或下一步变化：检查 `current_status.md`
- 长期阶段、顺序、范围或完成标准变化：检查 `roadmap.md`
- 产生重要技术、架构或安全决定：向 `decisions.md` 追加记录
- 日常开发、Git 或 GitHub 操作方式变化：检查 `daily_workflow.md`

如果以上均不适用，不修改文档，并明确记录：

> 本次修改不需要更新 docs。

完成重要 Step 时可以检查 `current_status.md`，但只有项目状态发生明显变化才更新。完成 Phase 或 milestone 时通常更新 `current_status.md`，并仅在路线本身改变时更新 `roadmap.md`。

## 四、当天工作结束：审阅并保存

### 1. 查看全部状态

```powershell
git status
```

目的：确认新增、修改、删除和已暂存文件的范围。

检查 `.env`、虚拟环境、缓存、生成的数据和任何凭据没有进入待提交范围。

### 2. 审阅未暂存内容

```powershell
git diff
```

目的：逐行检查已跟踪文件尚未暂存的修改。

未跟踪文件不会显示在该 diff 中，应结合 `git status` 打开并检查其内容。

### 3. 暂存明确属于本次提交的文件

优先按明确路径暂存：

```powershell
git add 文件路径
```

可一次指定多个相关路径，例如：

```powershell
git add main.py broker tests
```

目的：只把已经审阅、属于同一逻辑变更的文件加入暂存区。

只有确认当前所有未忽略变化都应进入同一个提交时，才使用：

```powershell
git add .
```

`git add` 不会创建提交，也不会上传到 GitHub。

### 4. 审阅将要提交的实际内容

```powershell
git diff --cached
```

目的：逐行检查暂存区内容，也就是下一次 commit 真正会记录的变化。

然后检查文件状态：

```powershell
git status
```

如果暂存了不应提交的内容，先停止并询问如何安全取消暂存；不要使用破坏性命令处理不确定的文件。

### 5. 创建本地提交

```powershell
git commit -m "简要说明本次完成的工作"
```

目的：在本地 Git 历史中创建一个可追溯的版本记录，不会上传到 GitHub。

提交信息应说明完成了什么，例如：

```text
完成 IBKR 历史数据模块化改造
增加历史数据空结果测试
整理项目文档职责和工作流
```

一次提交尽量只包含一个逻辑完整的改动主题。

### 6. 上传到 GitHub

当前 `main` 分支已跟踪 `origin/main`。确认本地提交正确后执行：

```powershell
git push
```

目的：将当前分支的新本地提交上传到已配置的 GitHub 上游分支。

如果 push 被拒绝，不要盲目使用强制推送；先运行 `git status -sb` 和 `git fetch`，查明本地与远端关系。

### 7. 确认收尾状态

```powershell
git status -sb
```

目的：确认工作区是否干净，以及本地分支是否与 `origin/main` 同步。

理想状态应没有未提交文件，也不显示本地领先或落后远端。

## 五、异常与安全处理

- 不确定命令作用时，先停止并询问 Codex。
- 发现密码、API Key、Token、私钥或账户凭据时，不执行 `git add`、`git commit` 或 `git push`。
- 敏感信息已上传时，先到对应服务商撤销或轮换凭据，再制定 Git 历史处理方案。
- 不使用 `git reset --hard`、强制推送或批量删除来处理不确定状态。
- 当前工作区已有他人或此前任务的修改时，保留并区分其归属，不擅自覆盖。
- Git 暂存、提交和推送会改变项目或远端状态；使用 Codex 时应先获得明确授权。
