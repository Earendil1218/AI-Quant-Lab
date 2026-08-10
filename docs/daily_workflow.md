# 每日工作收尾任务

本流程用于在当天工作结束时保存代码、文档与项目进度。请按顺序执行，并且一次只执行一条命令；每条命令完成后再进行下一条。

## 0. 更新项目文档

完成工作后，先更新与实际变更对应的文档：

- `docs/current_status.md`：完成项、进行中事项和待办事项
- `docs/project_context.md`：项目阶段、当前重点和下一步
- `docs/decisions.md`：新的重要技术决策及其原因
- `docs/roadmap.md`：阶段或计划发生调整时才更新

如当天使用 Codex，可直接说明：

> 请根据我今天完成的工作更新相关 docs 文件，并说明修改了哪些内容。

## 1. 查看改动

```powershell
git status
```

作用：显示当天有哪些新增、修改或删除的文件，以及哪些文件已经暂存。此命令不会修改或上传任何内容。

检查要点：确认代码和 `docs/` 中应保存的更新都在列表中；确认 `.env`、`secrets/`、`.venv311/` 等敏感或本机文件没有被暂存。

## 2. 暂存要提交的文件

若当天希望保存所有项目改动，执行：

```powershell
git add .
```

作用：将当前目录内符合 `.gitignore` 规则的改动加入“准备提交”区。它不会创建提交，也不会上传到 GitHub。

若只想保存指定文件，可改用：

```powershell
git add 文件路径
```

示例：

```powershell
git add docs/current_status.md
```

## 3. 再次检查暂存内容

```powershell
git status
```

作用：确认将要进入本次提交的文件位于 `Changes to be committed` 区域。若发现不应提交的文件，先停止并处理后再继续。

## 4. 创建本地提交

```powershell
git commit -m "简要说明今天完成的工作"
```

作用：在本机 Git 历史中创建一个可追溯、可回退的版本记录。该命令不会上传到 GitHub。

提交说明示例：

```text
完成 AAPL 历史数据获取模块
更新 Greeks 计算说明
修复 IBKR 历史数据请求
```

## 5. 上传到 GitHub

```powershell
git push
```

作用：将已提交的本地 Git 记录上传到已关联的 GitHub 远程仓库。成功后，GitHub 网页会同步显示最新提交。

## 6. 确认收尾状态

```powershell
git status
```

作用：确认工作目录是否干净，并检查本地分支是否已同步远程仓库。理想结果包含：

```text
nothing to commit, working tree clean
```

## 异常处理原则

- 不确定某条命令的作用时，不要执行；先询问 Codex。
- 发现疑似密码、API Key、Token、私钥或账户凭据时，不要执行 `git add` 或 `git push`；先移出文件并更新 `.gitignore`。
- 已上传敏感信息时，应先到对应服务商撤销或轮换凭据，再处理 Git 历史。
